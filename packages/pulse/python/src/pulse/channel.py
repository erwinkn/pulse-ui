from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal

from pulse.context import PulseContext
from pulse.messages import (
	ChannelError,
	ChannelErrorCode,
	ClientChannelEventMessage,
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
	ServerChannelEventMessage,
	ServerChannelRequestMessage,
	ServerChannelResponseMessage,
)
from pulse.reactive_extensions import (
	ReactiveDict,
	ReactiveList,
	ReactiveSet,
	unwrap,
)

if TYPE_CHECKING:
	from pulse.render_session import RenderSession

logger = logging.getLogger(__name__)

ChannelLifetime = Literal["route", "tab"]
ChannelHandler = Callable[[Any], Any | Awaitable[Any]]
ChannelHandlerRemover = Callable[[], None]


class ChannelTimeout(Exception):
	timeout: float
	event: str

	def __init__(self, timeout: float, event: str):
		self.timeout = timeout
		self.event = event
		super().__init__(f"Channel request timed out after {timeout}s: {event}")


class ChannelDetached(Exception):
	"""Raised when `on()` is called on a detached handle."""


class ChannelDisconnected(Exception):
	"""Raised when a request cannot complete because the socket is down or died."""


class ChannelRemoteError(Exception):
	code: ChannelErrorCode
	message: str

	def __init__(self, code: ChannelErrorCode, message: str):
		self.code = code
		self.message = message
		super().__init__(f"{code}: {message}")


class Channel:
	"""A local handle on a mailbox. Messages route by `id`."""

	_session: RenderSession
	_id: str
	_lifetime: ChannelLifetime
	_route_path: str | None
	_handlers: dict[str, list[ChannelHandler]]
	_detached: bool

	def __init__(
		self,
		session: RenderSession,
		identifier: str,
		lifetime: ChannelLifetime,
		*,
		route_path: str | None = None,
	):
		self._session = session
		self._id = identifier
		self._lifetime = lifetime
		self._route_path = route_path
		self._handlers = {}
		self._detached = False

	@property
	def id(self) -> str:
		return self._id

	@property
	def lifetime(self) -> ChannelLifetime:
		return self._lifetime

	def _assert_attached(self) -> None:
		if self._detached:
			raise ChannelDetached(f"Channel {self._id} is detached")

	def on(self, event: str, handler: ChannelHandler) -> ChannelHandlerRemover:
		self._assert_attached()
		handlers = self._handlers.setdefault(event, [])
		handlers.append(handler)

		def remove() -> None:
			if handler in handlers:
				handlers.remove(handler)
			if not handlers:
				self._handlers.pop(event, None)

		return remove

	def emit(self, event: str, payload: Any = None) -> None:
		self._session.channels.send_event(self._id, event, payload)

	async def request(
		self, event: str, payload: Any = None, *, timeout: float | None = None
	) -> Any:
		if not self._session.channels.can_request():
			raise ChannelDisconnected("No render session is connected")
		request_id = str(uuid.uuid4())
		future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
		self._session.channels.register_pending(request_id, future)
		self._session.channels.send_request(self._id, event, payload, request_id)
		try:
			if timeout is None:
				return await future
			return await asyncio.wait_for(future, timeout)
		except TimeoutError:
			self._session.channels.cancel_pending(request_id)
			raise ChannelTimeout(timeout or 0, event) from None

	def is_detached(self) -> bool:
		return self._detached

	def has_handler(self, event: str) -> bool:
		return event in self._handlers

	def detach(self) -> None:
		if self._detached:
			return
		self._detached = True
		self._handlers.clear()
		self._session.channels.forget_handle(self)

	def dispatch_event(self, event: str, payload: Any) -> None:
		if self._detached:
			return
		for handler in list(self._handlers.get(event, [])):
			self._session.create_task(
				self._invoke_handler(handler, payload, required=False),
				name=f"channel:{self._id}:{event}",
			)

	async def dispatch_request(self, event: str, payload: Any) -> Any:
		if self._detached:
			return None
		handlers = list(self._handlers.get(event, []))
		if not handlers:
			return None
		return await self._invoke_handler(handlers[0], payload, required=True)

	async def _invoke_handler(
		self, handler: ChannelHandler, payload: Any, *, required: bool
	) -> Any:
		from pulse.context import PULSE_CONTEXT
		from pulse.helpers import maybe_await

		render = self._session
		route_ctx = None
		source_mount_id = None
		if self._lifetime == "route" and self._route_path:
			mount = render.route_mounts.get(self._route_path)
			if mount is None:
				if not required:
					logger.debug(
						"Skipping channel %s handler; route %s is gone",
						self._id,
						self._route_path,
					)
					return None
				raise RuntimeError(
					f"Route {self._route_path} is gone for channel {self._id}"
				)
			route_ctx = mount.route
			source_mount_id = mount.mount_id

		if PULSE_CONTEXT.get() is None:
			return await maybe_await(handler(payload))
		with PulseContext.update(
			render=render,
			route=route_ctx,
			source_route_path=route_ctx.route_path if route_ctx is not None else None,
			source_path=route_ctx.pathname if route_ctx is not None else None,
			source_mount_id=source_mount_id,
		):
			return await maybe_await(handler(payload))


class ChannelsManager:
	_session: RenderSession

	def __init__(self, session: RenderSession):
		self._session = session
		self._handles: set[Channel] = set()
		self._mailboxes: dict[str, list[Channel]] = {}
		self._route_handles: dict[tuple[str, str], Channel] = {}
		self._handles_by_route: dict[str, set[Channel]] = {}
		self._tab_handles: dict[str, Channel] = {}
		self._unscoped_handles: dict[str, Channel] = {}
		self._pending: dict[str, asyncio.Future[Any]] = {}

	def can_request(self) -> bool:
		return self._session.connected

	def _current_route_path(self) -> str | None:
		route = PulseContext.get().route
		return route.route_path if route is not None else None

	def _register(self, handle: Channel) -> None:
		self._handles.add(handle)
		self._mailboxes.setdefault(handle.id, []).append(handle)

	def acquire(
		self, identifier: str | None = None, *, lifetime: ChannelLifetime = "route"
	) -> Channel:
		if identifier is not None and identifier == "":
			raise ValueError("Channel identifier cannot be empty")
		channel_id = identifier or str(uuid.uuid4())
		route_path = self._current_route_path()
		if lifetime == "tab":
			existing = self._tab_handles.get(channel_id)
			if existing is not None and not existing.is_detached():
				return existing
			handle = Channel(self._session, channel_id, "tab")
			self._tab_handles[channel_id] = handle
			self._register(handle)
			return handle
		if route_path is None:
			existing = self._unscoped_handles.get(channel_id)
			if existing is not None and not existing.is_detached():
				return existing
			handle = Channel(self._session, channel_id, "route")
			self._unscoped_handles[channel_id] = handle
			self._register(handle)
			return handle
		key = (channel_id, route_path)
		existing = self._route_handles.get(key)
		if existing is not None and not existing.is_detached():
			return existing
		handle = Channel(self._session, channel_id, "route", route_path=route_path)
		self._route_handles[key] = handle
		self._handles_by_route.setdefault(route_path, set()).add(handle)
		self._register(handle)
		return handle

	def open_handle(
		self, identifier: str, *, lifetime: ChannelLifetime = "route"
	) -> Channel:
		"""Always create a new handle on the mailbox (no intern)."""
		if identifier == "":
			raise ValueError("Channel identifier cannot be empty")
		route_path = self._current_route_path() if lifetime == "route" else None
		handle = Channel(self._session, identifier, lifetime, route_path=route_path)
		self._register(handle)
		if lifetime == "route" and route_path is not None:
			self._handles_by_route.setdefault(route_path, set()).add(handle)
		return handle

	def forget_handle(self, handle: Channel) -> None:
		self._handles.discard(handle)
		mailbox = self._mailboxes.get(handle.id)
		if mailbox is not None:
			if handle in mailbox:
				mailbox.remove(handle)
			if not mailbox:
				del self._mailboxes[handle.id]
		if self._tab_handles.get(handle.id) is handle:
			del self._tab_handles[handle.id]
			return
		if self._unscoped_handles.get(handle.id) is handle:
			del self._unscoped_handles[handle.id]
			return
		for key, existing in list(self._route_handles.items()):
			if existing is not handle:
				continue
			del self._route_handles[key]
			route_handles = self._handles_by_route.get(key[1])
			if route_handles is not None:
				route_handles.discard(handle)
				if not route_handles:
					del self._handles_by_route[key[1]]
			return

	def detach_route(self, route_path: str) -> None:
		handles = list(self._handles_by_route.pop(route_path, set()))
		for handle in handles:
			handle.detach()

	def send_event(self, channel_id: str, event: str, payload: Any) -> None:
		message: ServerChannelEventMessage = {
			"type": "channel",
			"action": "event",
			"channel": channel_id,
			"event": event,
		}
		if payload is not None:
			message["payload"] = _serialize_payload(payload)
		self._session.send(message)

	def send_request(
		self, channel_id: str, event: str, payload: Any, request_id: str
	) -> None:
		message: ServerChannelRequestMessage = {
			"type": "channel",
			"action": "request",
			"channel": channel_id,
			"event": event,
			"requestId": request_id,
		}
		if payload is not None:
			message["payload"] = _serialize_payload(payload)
		self._session.send(message)

	def send_response(
		self,
		channel_id: str,
		request_id: str,
		payload: Any = None,
		error: ChannelError | None = None,
	) -> None:
		message: ServerChannelResponseMessage = {
			"type": "channel",
			"action": "response",
			"channel": channel_id,
			"responseTo": request_id,
		}
		if error is not None:
			message["error"] = error
		elif payload is not None:
			message["payload"] = _serialize_payload(payload)
		self._session.send(message)

	def send_error(
		self, channel_id: str, request_id: str, code: ChannelErrorCode, message: str
	) -> None:
		self.send_response(
			channel_id, request_id, error={"code": code, "message": message}
		)

	def register_pending(self, request_id: str, future: asyncio.Future[Any]) -> None:
		self._pending[request_id] = future

	def cancel_pending(self, request_id: str) -> None:
		self._pending.pop(request_id, None)

	def fail_pending(self) -> None:
		pending = list(self._pending.values())
		self._pending.clear()
		for future in pending:
			if not future.done():
				future.set_exception(ChannelDisconnected("Render session disconnected"))

	def reset(self) -> None:
		self.fail_pending()
		for handle in list(self._handles):
			handle.detach()
		self._handles.clear()
		self._mailboxes.clear()
		self._route_handles.clear()
		self._handles_by_route.clear()
		self._tab_handles.clear()
		self._unscoped_handles.clear()

	def _handles_for(self, channel_id: str) -> list[Channel]:
		return [h for h in self._mailboxes.get(channel_id, []) if not h.is_detached()]

	def handle_event(self, message: ClientChannelEventMessage) -> None:
		channel_id = message["channel"]
		event = message["event"]
		payload = message.get("payload")
		handles = self._handles_for(channel_id)
		if not handles:
			logger.debug(
				"Dropping event %s on mailbox %s (no listeners)", event, channel_id
			)
			return
		for handle in handles:
			handle.dispatch_event(event, payload)

	async def handle_request(self, message: ClientChannelRequestMessage) -> None:
		channel_id = message["channel"]
		event = message["event"]
		payload = message.get("payload")
		request_id = message["requestId"]
		for handle in self._handles_for(channel_id):
			if not handle.has_handler(event):
				continue
			try:
				result = await handle.dispatch_request(event, payload)
			except Exception:
				logger.exception("Channel %s handler for %s failed", channel_id, event)
				self.send_error(
					channel_id, request_id, "handler_error", "Channel handler failed"
				)
				return
			self.send_response(channel_id, request_id, result)
			return
		self.send_error(
			channel_id,
			request_id,
			"no_handler",
			f"No handler for '{event}' on channel '{channel_id}'",
		)

	def handle_response(self, message: ClientChannelResponseMessage) -> None:
		request_id = message["responseTo"]
		future = self._pending.pop(request_id, None)
		if future is None or future.done():
			return
		error = message.get("error")
		if error is not None:
			future.set_exception(ChannelRemoteError(error["code"], error["message"]))
			return
		future.set_result(message.get("payload"))


def _serialize_payload(payload: Any) -> Any:
	if isinstance(payload, ReactiveDict | ReactiveList | ReactiveSet):
		return unwrap(payload)
	return payload


def channel(
	identifier: str | None = None, *, lifetime: ChannelLifetime = "route"
) -> Channel:
	"""Return a handle on a mailbox. Empty identifier raises. None generates a UUID."""
	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError("channel() requires a render session")
	return ctx.render.channels.acquire(identifier, lifetime=lifetime)
