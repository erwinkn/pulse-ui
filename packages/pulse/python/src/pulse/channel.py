from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
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
from pulse.serializer import serialize

if TYPE_CHECKING:
	from pulse.render_session import RenderSession

logger = logging.getLogger(__name__)

ChannelLifetime = Literal["route", "tab"]
ChannelInternKey = tuple[ChannelLifetime, str, str | None]
ChannelHandler = Callable[[Any], Any | Awaitable[Any]]
ChannelHandlerRemover = Callable[[], None]

# Cap on events waiting on a handle's serial pump (drop-oldest past this): a
# handler that awaits for a long time must not grow the backlog without bound.
MAX_QUEUED_EVENTS = 500


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
	"""A local handle on a channel name. Messages route by `id`."""

	_session: RenderSession
	_id: str
	_lifetime: ChannelLifetime
	_route_path: str | None
	_handlers: dict[str, list[ChannelHandler]]
	_detached: bool
	_events: deque[tuple[str, Any]]
	_pump: asyncio.Task[None] | None
	_events_overflowed: bool

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
		self._events = deque(maxlen=MAX_QUEUED_EVENTS)
		self._pump = None
		self._events_overflowed = False

	@property
	def id(self) -> str:
		return self._id

	@property
	def lifetime(self) -> ChannelLifetime:
		return self._lifetime

	@property
	def route_path(self) -> str | None:
		return self._route_path

	def _assert_attached(self) -> None:
		if self._detached:
			raise ChannelDetached(f"Channel {self._id} is detached")

	def on(self, event: str, handler: ChannelHandler) -> ChannelHandlerRemover:
		self._assert_attached()
		handlers = self._handlers.setdefault(event, [])
		if handler not in handlers:
			handlers.append(handler)

		def remove() -> None:
			if handler in handlers:
				handlers.remove(handler)
			if self._handlers.get(event) is handlers and not handlers:
				self._handlers.pop(event, None)

		return remove

	def emit(self, event: str, payload: Any = None) -> None:
		# Emits legitimately race detach (background tasks): no-op instead of raising.
		if self._detached:
			logger.debug("Dropping emit %s on detached channel %s", event, self._id)
			return
		self._session.channels.send_event(self._id, event, payload)

	async def request(
		self, event: str, payload: Any = None, *, timeout: float | None = None
	) -> Any:
		self._assert_attached()
		if not self._session.channels.can_request():
			raise ChannelDisconnected("No render session is connected")
		request_id = str(uuid.uuid4())
		future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
		self._session.channels.register_pending(request_id, self._id, future)
		try:
			self._session.channels.send_request(self._id, event, payload, request_id)
			if timeout is None:
				return await future
			return await asyncio.wait_for(future, timeout)
		except TimeoutError:
			raise ChannelTimeout(timeout or 0, event) from None
		finally:
			# Covers timeout, caller cancellation and send failures alike.
			self._session.channels.forget_pending(request_id)

	def is_detached(self) -> bool:
		return self._detached

	def has_handler(self, event: str) -> bool:
		return event in self._handlers

	def detach(self) -> None:
		if self._detached:
			return
		self._detached = True
		self._handlers.clear()
		self._events.clear()
		if self._pump is not None:
			self._pump.cancel()
			self._pump = None
		self._session.channels.forget_handle(self)

	def _report_task_error(self, task: asyncio.Task[Any]) -> None:
		if task.cancelled():
			return
		try:
			exc = task.exception()
		except asyncio.CancelledError:
			return
		if exc is None:
			return
		self._session.report_error(self._route_path, "channel", exc)

	def dispatch_event(self, event: str, payload: Any) -> None:
		"""Queue an event. One serial pump per handle keeps events in arrival order."""
		if self._detached:
			return
		if len(self._events) == MAX_QUEUED_EVENTS and not self._events_overflowed:
			# Nothing sensible to do but shed load: a handler is holding the pump.
			self._events_overflowed = True
			logger.warning(
				"Channel %s event backlog hit %d; dropping oldest events",
				self._id,
				MAX_QUEUED_EVENTS,
			)
		self._events.append((event, payload))
		if self._pump is not None and not self._pump.done():
			return
		self._pump = self._session.create_task(
			self._pump_events(),
			name=f"channel:{self._id}",
			on_done=self._report_task_error,
		)

	async def _pump_events(self) -> None:
		while self._events:
			event, payload = self._events.popleft()
			for handler in list(self._handlers.get(event, [])):
				# Detach can land while an earlier handler was awaiting.
				if self._detached:
					return
				try:
					await self._invoke_handler(handler, payload, required=False)
				except Exception as exc:
					self._session.report_error(self._route_path, "channel", exc)

	async def dispatch_request(self, event: str, payload: Any) -> Any:
		"""Runs outside the event pump: request handlers may await client RPCs."""
		if self._detached:
			return None
		handlers = list(self._handlers.get(event, []))
		if not handlers:
			return None
		return await self._invoke_handler(handlers[0], payload, required=True)

	async def _invoke_handler(
		self, handler: ChannelHandler, payload: Any, *, required: bool
	) -> Any:
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
		# (lifetime, channel_id, route_path) → live handle
		self._intern: dict[ChannelInternKey, Channel] = {}
		self._by_name: dict[str, list[Channel]] = {}
		# request id → (channel id, future)
		self._pending: dict[str, tuple[str, asyncio.Future[Any]]] = {}

	def can_request(self) -> bool:
		return self._session.connected

	def _current_route_path(self) -> str | None:
		route = PulseContext.get().route
		return route.route_path if route is not None else None

	def _intern_key(self, handle: Channel) -> ChannelInternKey:
		return (handle.lifetime, handle.id, handle.route_path)

	def _register(self, handle: Channel) -> None:
		self._intern[self._intern_key(handle)] = handle
		self._by_name.setdefault(handle.id, []).append(handle)

	def acquire(
		self, identifier: str | None = None, *, lifetime: ChannelLifetime = "route"
	) -> Channel:
		if identifier is not None and identifier == "":
			raise ValueError("Channel identifier cannot be empty")
		if lifetime not in ("route", "tab"):
			raise ValueError(f"Invalid channel lifetime {lifetime!r}")
		channel_id = identifier or str(uuid.uuid4())
		if lifetime == "tab":
			route_path = None
		else:
			route_path = self._current_route_path()
			if route_path is None:
				raise RuntimeError(
					"channel(..., lifetime='route') requires a route context"
				)
		key = (lifetime, channel_id, route_path)
		existing = self._intern.get(key)
		if existing is not None and not existing.is_detached():
			return existing
		handle = Channel(self._session, channel_id, lifetime, route_path=route_path)
		self._register(handle)
		return handle

	def forget_handle(self, handle: Channel) -> None:
		key = self._intern_key(handle)
		if self._intern.get(key) is handle:
			del self._intern[key]
		bucket = self._by_name.get(handle.id)
		if bucket is None:
			return
		if handle in bucket:
			bucket.remove(handle)
		if not bucket:
			del self._by_name[handle.id]

	def detach_route(self, route_path: str) -> None:
		handles = [
			handle
			for handle in self._intern.values()
			if handle.lifetime == "route" and handle.route_path == route_path
		]
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
			message["payload"] = self._wire_payload(channel_id, event, payload)
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
			message["payload"] = self._wire_payload(channel_id, event, payload)
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
			message["payload"] = self._wire_payload(channel_id, request_id, payload)
		self._session.send(message)

	def send_error(
		self, channel_id: str, request_id: str, code: ChannelErrorCode, message: str
	) -> None:
		self.send_response(
			channel_id, request_id, error={"code": code, "message": message}
		)

	def register_pending(
		self, request_id: str, channel_id: str, future: asyncio.Future[Any]
	) -> None:
		self._pending[request_id] = (channel_id, future)

	def forget_pending(self, request_id: str) -> None:
		self._pending.pop(request_id, None)

	def fail_pending(self) -> None:
		pending = [future for _, future in self._pending.values()]
		self._pending.clear()
		for future in pending:
			if not future.done():
				future.set_exception(ChannelDisconnected("Render session disconnected"))

	def reset(self) -> None:
		self.fail_pending()
		for handle in list(self._intern.values()):
			handle.detach()
		self._intern.clear()
		self._by_name.clear()

	def _handles_for(self, channel_id: str) -> list[Channel]:
		return [h for h in self._by_name.get(channel_id, []) if not h.is_detached()]

	def handle_event(self, message: ClientChannelEventMessage) -> None:
		channel_id = message["channel"]
		event = message["event"]
		payload = message.get("payload")
		handles = self._handles_for(channel_id)
		if not handles:
			logger.debug(
				"Dropping event %s on channel %s (no listeners)", event, channel_id
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
				self.send_response(channel_id, request_id, result)
			except Exception:
				logger.exception("Channel %s handler for %s failed", channel_id, event)
				self.send_error(
					channel_id, request_id, "handler_error", "Channel handler failed"
				)
			return
		self.send_error(
			channel_id,
			request_id,
			"no_handler",
			f"No handler for '{event}' on channel '{channel_id}'",
		)

	def handle_response(self, message: ClientChannelResponseMessage) -> None:
		request_id = message["responseTo"]
		entry = self._pending.get(request_id)
		if entry is None:
			return
		channel_id, future = entry
		if message["channel"] != channel_id:
			logger.warning(
				"Ignoring response for %s: claims channel %s, expected %s",
				request_id,
				message["channel"],
				channel_id,
			)
			return
		del self._pending[request_id]
		if future.done():
			return
		error = message.get("error")
		if error is not None:
			future.set_exception(ChannelRemoteError(error["code"], error["message"]))
			return
		future.set_result(message.get("payload"))

	def _wire_payload(self, channel_id: str, label: str, payload: Any) -> Any:
		if isinstance(payload, ReactiveDict | ReactiveList | ReactiveSet):
			payload = unwrap(payload)
		if not self._session.connected:
			# The message goes on the disconnect queue, where a serialization
			# failure would only surface at flush time, far from its origin.
			# While connected the socket serializes it here, in the caller's frame.
			try:
				serialize(payload)
			except (TypeError, ValueError) as exc:
				raise TypeError(
					f"Channel {channel_id!r} payload for {label!r} is not serializable: {exc}"
				) from exc
		return payload


def channel(
	identifier: str | None = None, *, lifetime: ChannelLifetime = "route"
) -> Channel:
	"""Return a handle on a channel name. Empty identifier raises. None generates a UUID."""
	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError("channel() requires a render session")
	return ctx.render.channels.acquire(identifier, lifetime=lifetime)
