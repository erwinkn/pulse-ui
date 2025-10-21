import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pulse.context import PulseContext
from pulse.helpers import create_future_on_loop
from pulse.messages import (
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
	ServerChannelMessage,
	ServerChannelRequestMessage,
	ServerChannelResponseMessage,
)
from pulse.routing import normalize_path

if TYPE_CHECKING:
	from pulse.app import App
	from pulse.render_session import RenderSession
	from pulse.user_session import UserSession

logger = logging.getLogger(__name__)


ChannelHandler = Callable[[Any], Any | Awaitable[Any]]


class ChannelClosed(RuntimeError):
	"""Raised when interacting with a channel that has been closed."""


class ChannelTimeout(asyncio.TimeoutError):
	"""Raised when a channel request times out waiting for a response."""


@dataclass(slots=True)
class PendingRequest:
	future: asyncio.Future[Any]
	channel_id: str


class ChannelsManager:
	"""Coordinates creation, routing, and cleanup of Pulse channels."""

	_app: "App"
	_channels: dict[str, "Channel"]
	_channels_by_render: dict[str, set[str]]
	_channels_by_route: dict[tuple[str, str], set[str]]
	pending_requests: dict[str, PendingRequest]

	def __init__(self, app: "App") -> None:
		self._app = app
		self._channels = {}
		self._channels_by_render = defaultdict(set)
		self._channels_by_route = defaultdict(set)
		self.pending_requests = {}

	# ------------------------------------------------------------------
	def create(self, identifier: str | None = None) -> "Channel":
		ctx = PulseContext.get()
		render = ctx.render
		session = ctx.session
		if render is None or session is None:
			raise RuntimeError("Channels require an active render and session")

		channel_id = identifier or uuid.uuid4().hex
		if channel_id in self._channels:
			raise ValueError(f"Channel id '{channel_id}' is already in use")

		route_path: str | None = None
		if ctx.route is not None:
			route_path = normalize_path(ctx.route.pulse_route.unique_path())

		channel = Channel(
			self,
			channel_id,
			render_id=render.id,
			session_id=session.sid,
			route_path=route_path,
		)
		self._channels[channel_id] = channel
		self._channels_by_render[render.id].add(channel_id)
		if route_path is not None:
			self._channels_by_route[(render.id, route_path)].add(channel_id)
		return channel

	# ------------------------------------------------------------------
	def remove_render(self, render_id: str) -> None:
		ids = list(self._channels_by_render.get(render_id, set()))
		for channel_id in ids:
			channel = self._channels.get(channel_id)
			if channel is None:
				continue
			channel.closed = True
			self.dispose_channel(channel)
		self._channels_by_render.pop(render_id, None)

	def remove_route(self, render_id: str, route_path: str) -> None:
		key = (render_id, normalize_path(route_path))
		for channel_id in list(self._channels_by_route.get(key, set())):
			channel = self._channels.get(channel_id)
			if channel is None:
				continue
			channel.closed = True
			self.dispose_channel(channel)
		self._channels_by_route.pop(key, None)

	# ------------------------------------------------------------------
	def handle_client_response(self, message: ClientChannelResponseMessage) -> None:
		response_to = message.get("responseTo")
		if not response_to:
			return

		if error := message.get("error") is not None:
			self.resolve_pending_error(response_to, error)
		else:
			self._resolve_pending_success(response_to, message.get("payload"))

	def handle_client_event(
		self,
		*,
		render: "RenderSession",
		session: "UserSession",
		message: ClientChannelRequestMessage,
	) -> None:
		channel_id = str(message.get("channel"))
		channel = self._channels.get(channel_id)
		if channel is None:
			if request_id := message.get("requestId"):
				self._send_error_response(channel_id, request_id, "Channel closed")
			return

		if channel.render_id != render.id or channel.session_id != session.sid:
			logger.warning(
				"Ignoring channel message for mismatched context: %s", channel_id
			)
			return

		event = message["event"]
		payload = message.get("payload")
		request_id = message.get("requestId")

		route_ctx = None
		if channel.route_path is not None:
			try:
				mount = render.get_route_mount(channel.route_path)
				route_ctx = mount.route
			except Exception:
				route_ctx = None

		async def _invoke() -> None:
			try:
				with PulseContext.update(
					session=session, render=render, route=route_ctx
				):
					result = await channel.dispatch(event, payload, request_id)
			except Exception as exc:
				if request_id:
					self._send_error_response(channel.id, request_id, str(exc))
				else:
					logger.exception("Unhandled error in channel handler")
				return

			if request_id:
				msg = ServerChannelResponseMessage(
					type="channel_message",
					channel=channel.id,
					event=None,
					responseTo=request_id,
					payload=result,
				)
				self.send_to_client(
					channel=channel,
					msg=msg,
				)

		asyncio.create_task(_invoke())

	# ------------------------------------------------------------------
	def register_pending(
		self,
		request_id: str,
		future: asyncio.Future[Any],
		channel_id: str,
	) -> None:
		self.pending_requests[request_id] = PendingRequest(
			future=future, channel_id=channel_id
		)

	def _resolve_pending_success(self, request_id: str, payload: Any) -> None:
		pending = self.pending_requests.pop(request_id, None)
		if not pending:
			return
		if pending.future.done():
			return
		pending.future.set_result(payload)

	def resolve_pending_error(self, request_id: str, error: Any) -> None:
		pending = self.pending_requests.pop(request_id, None)
		if not pending:
			return
		if pending.future.done():
			return
		if isinstance(error, Exception):
			pending.future.set_exception(error)
		else:
			pending.future.set_exception(RuntimeError(str(error)))

	def _send_error_response(
		self, channel_id: str, request_id: str, message: str
	) -> None:
		channel = self._channels.get(channel_id)
		if channel is None:
			self.resolve_pending_error(request_id, ChannelClosed(message))
			return
		try:
			msg = ServerChannelResponseMessage(
				type="channel_message",
				channel=channel.id,
				event=None,
				responseTo=request_id,
				payload=None,
				error=message,
			)
			self.send_to_client(
				channel=channel,
				msg=msg,
			)
		except ChannelClosed:
			self.resolve_pending_error(request_id, ChannelClosed(message))

	def send_error(self, channel_id: str, request_id: str, message: str) -> None:
		self._send_error_response(channel_id, request_id, message)

	def _cancel_pending_for_channel(self, channel_id: str) -> None:
		for key, pending in list(self.pending_requests.items()):
			if pending.channel_id != channel_id:
				continue
			if not pending.future.done():
				pending.future.set_exception(ChannelClosed("Channel closed"))
			self.pending_requests.pop(key, None)

	# ------------------------------------------------------------------
	def _cleanup_channel_refs(self, channel: "Channel") -> None:
		render_bucket = self._channels_by_render.get(channel.render_id)
		if render_bucket is not None:
			render_bucket.discard(channel.id)
			if not render_bucket:
				self._channels_by_render.pop(channel.render_id, None)
		if channel.route_path is not None:
			key = (channel.render_id, channel.route_path)
			route_bucket = self._channels_by_route.get(key)
			if route_bucket is not None:
				route_bucket.discard(channel.id)
				if not route_bucket:
					self._channels_by_route.pop(key, None)

	def dispose_channel(self, channel: "Channel") -> None:
		self._cleanup_channel_refs(channel)
		self._cancel_pending_for_channel(channel.id)
		self._channels.pop(channel.id, None)
		# Notify client that the channel has been closed
		try:
			msg = ServerChannelRequestMessage(
				type="channel_message",
				channel=channel.id,
				event="__close__",
				payload=None,
			)
			self.send_to_client(
				channel=channel,
				msg=msg,
			)
		except Exception:
			logger.debug("Failed to send close notification for channel %s", channel.id)

	def send_to_client(
		self,
		*,
		channel: "Channel",
		msg: ServerChannelMessage,
	) -> None:
		render = self._app.render_sessions.get(channel.render_id)
		if render is None:
			raise ChannelClosed(f"Render session {channel.render_id} is closed")
		render.send(msg)


class Channel:
	"""Bidirectional communication channel bound to a render session."""

	_manager: ChannelsManager
	id: str
	render_id: str
	session_id: str
	route_path: str | None
	_handlers: dict[str, list[ChannelHandler]]
	closed: bool

	def __init__(
		self,
		manager: ChannelsManager,
		identifier: str,
		*,
		render_id: str,
		session_id: str,
		route_path: str | None,
	) -> None:
		self._manager = manager
		self.id = identifier
		self.render_id = render_id
		self.session_id = session_id
		self.route_path = route_path
		self._handlers = defaultdict(list)
		self.closed = False

	# ---------------------------------------------------------------------
	# Registration
	# ---------------------------------------------------------------------
	def on(self, event: str, handler: ChannelHandler) -> Callable[[], None]:
		"""Register a handler for an incoming event.

		Returns a callable that removes the handler when invoked.
		"""

		self._ensure_open()
		bucket = self._handlers[event]
		bucket.append(handler)

		def _remove() -> None:
			handlers = self._handlers.get(event)
			if not handlers:
				return
			try:
				handlers.remove(handler)
			except ValueError:
				return
			if not handlers:
				self._handlers.pop(event, None)

		return _remove

	# ---------------------------------------------------------------------
	# Outgoing messages
	# ---------------------------------------------------------------------
	def emit(self, event: str, payload: Any = None) -> None:
		"""Send a fire-and-forget event to the client."""

		self._ensure_open()
		msg = ServerChannelRequestMessage(
			type="channel_message",
			channel=self.id,
			event=event,
			payload=payload,
		)
		self._manager.send_to_client(
			channel=self,
			msg=msg,
		)

	async def request(
		self,
		event: str,
		payload: Any = None,
		*,
		timeout: float | None = None,
	) -> Any:
		"""Send a request to the client and await the response."""

		self._ensure_open()
		request_id = uuid.uuid4().hex
		fut = create_future_on_loop()
		self._manager.register_pending(request_id, fut, self.id)
		msg = ServerChannelRequestMessage(
			type="channel_message",
			channel=self.id,
			event=event,
			payload=payload,
			requestId=request_id,
		)
		self._manager.send_to_client(
			channel=self,
			msg=msg,
		)
		try:
			if timeout is None:
				return await fut
			return await asyncio.wait_for(fut, timeout=timeout)
		except TimeoutError as exc:
			self._manager.resolve_pending_error(
				request_id,
				ChannelTimeout("Channel request timed out"),
			)
			raise ChannelTimeout("Channel request timed out") from exc
		finally:
			self._manager.pending_requests.pop(request_id, None)

	# ---------------------------------------------------------------------
	def close(self) -> None:
		if self.closed:
			return
		self.closed = True
		self._handlers.clear()
		self._manager.dispose_channel(self)

	# ---------------------------------------------------------------------
	def _ensure_open(self) -> None:
		if self.closed:
			raise ChannelClosed(f"Channel '{self.id}' is closed")

	async def dispatch(
		self, event: str, payload: Any, request_id: str | None
	) -> Any | None:
		handlers = list(self._handlers.get(event, ()))
		if not handlers:
			return None

		last_result: Any | None = None
		for handler in handlers:
			try:
				result = handler(payload)
				if asyncio.iscoroutine(result):
					result = await result
			except Exception as exc:
				logger.exception(
					"Error in channel handler '%s' for event '%s'", self.id, event
				)
				raise exc
			if request_id is not None and result is not None:
				return result
			if result is not None:
				last_result = result
		return last_result


def channel(identifier: str | None = None) -> Channel:
	"""Convenience helper to create a channel using the active PulseContext."""

	ctx = PulseContext.get()
	return ctx.app.channels.create(identifier)


__all__ = [
	"ChannelsManager",
	"Channel",
	"ChannelClosed",
	"ChannelTimeout",
	"channel",
]
