import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from pulse.context import PulseContext
from pulse.messages import (
	ClientChannelConnectMessage,
	ClientChannelDisconnectMessage,
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
	ServerChannelMessage,
	ServerChannelRequestMessage,
	ServerChannelResponseMessage,
)
from pulse.scheduling import create_future

if TYPE_CHECKING:
	from pulse.render_session import RenderSession
	from pulse.user_session import UserSession

logger = logging.getLogger(__name__)


ChannelHandler = Callable[[Any], Any | Awaitable[Any]]
"""Handler function for channel events. Can be sync or async.

Type alias for ``Callable[[Any], Any | Awaitable[Any]]``.
"""


class ChannelClosed(RuntimeError):
	"""Raised when interacting with a channel that has been closed.

	This exception is raised when attempting to call ``on()``, ``emit()``,
	or ``request()`` on a channel that has already been closed.

	Example:

	```python
	ch = ps.channel("my-channel")
	ch.close()
	ch.emit("event")  # Raises ChannelClosed
	```
	"""


class ChannelTimeout(asyncio.TimeoutError):
	"""Raised when a channel request times out waiting for a response.

	This exception is raised by ``Channel.request()`` when the specified
	timeout elapses before receiving a response from the client.

	Example:

	```python
	result = await ch.request("get_value", timeout=5.0)  # Raises if no response in 5s
	```
	"""


@dataclass(slots=True)
class PendingRequest:
	future: asyncio.Future[Any]
	channel_id: str


class ChannelsManager:
	"""Coordinates creation, routing, and cleanup of Pulse channels."""

	_render_session: "RenderSession"
	_channels: dict[str, "Channel"]
	_channels_by_view: dict[str, set[str]]
	pending_requests: dict[str, PendingRequest]

	def __init__(self, render_session: "RenderSession") -> None:
		self._render_session = render_session
		self._channels = {}
		self._channels_by_view = defaultdict(set)
		self.pending_requests = {}

	# ------------------------------------------------------------------
	def create(
		self, identifier: str | None = None, *, bind_view: bool = True
	) -> "Channel":
		ctx = PulseContext.get()
		render = ctx.render
		session = ctx.session
		if render is None or session is None:
			raise RuntimeError("Channels require an active render and session")

		channel_id = identifier or uuid.uuid4().hex
		if channel_id in self._channels:
			raise ValueError(f"Channel id '{channel_id}' is already in use")

		view_id = ctx.view.id if bind_view and ctx.view is not None else None

		channel = Channel(
			self,
			channel_id,
			render_id=render.id,
			session_id=session.sid,
			view_id=view_id,
		)
		self._channels[channel_id] = channel
		if view_id is not None:
			self._channels_by_view[view_id].add(channel_id)
		return channel

	# ------------------------------------------------------------------
	def remove_view(self, view_id: str) -> None:
		view_channels = list(self._channels_by_view.get(view_id, set()))
		for channel_id in view_channels:
			channel = self._channels.get(channel_id)
			if channel is None:
				continue
			channel.closed = True
			self.dispose_channel(channel, reason="view.unmount")
		self._channels_by_view.pop(view_id, None)

	def _validate_client_endpoint(
		self, channel: "Channel", view_id: str, action: str
	) -> bool:
		if channel.view_id is None:
			return True
		if view_id != channel.view_id:
			logger.warning(
				"Rejecting channel %s for wrong view: %s view=%s owner=%s",
				action,
				channel.id,
				view_id,
				channel.view_id,
			)
			return False
		view = self._render_session.views.get(channel.view_id)
		if view is None or view.state != "active":
			logger.warning(
				"Rejecting stale channel %s: %s view=%s", action, channel.id, view_id
			)
			return False
		return True

	def handle_client_connect(self, message: ClientChannelConnectMessage) -> None:
		channel_id = str(message.get("channel"))
		channel = self._channels.get(channel_id)
		if channel is None or channel.closed:
			return

		view_id = str(message.get("view", ""))
		if not self._validate_client_endpoint(channel, view_id, "connect"):
			return

		channel.connected = True

	def resume_client_channel(self, channel_id: str, view_id: str) -> bool:
		channel = self._channels.get(channel_id)
		if channel is None or channel.closed:
			return False

		if not self._validate_client_endpoint(channel, view_id, "resume"):
			return False

		channel.connected = True
		return True

	def handle_client_disconnect(self, message: ClientChannelDisconnectMessage) -> None:
		channel_id = str(message.get("channel"))
		channel = self._channels.get(channel_id)
		if channel is None:
			return
		channel.connected = False
		self._cancel_pending_for_channel(
			channel_id, message="Channel has no connected client"
		)

	def disconnect_all(self) -> None:
		for channel in self._channels.values():
			channel.connected = False
			self._cancel_pending_for_channel(
				channel.id, message="Channel has no connected client"
			)

	def reject_client_connect(self, channel_id: str, message: str) -> None:
		channel = self._channels.get(channel_id)
		if channel is None:
			return
		channel.connected = False
		try:
			self.send_to_client(
				channel=channel,
				msg=ServerChannelRequestMessage(
					type="channel_message",
					channel=channel.id,
					event="__close__",
					payload={"reason": message},
				),
				allow_unconnected=True,
			)
		except ChannelClosed:
			return

	# ------------------------------------------------------------------
	def handle_client_response(self, message: ClientChannelResponseMessage) -> None:
		response_to = message.get("responseTo")
		if not response_to:
			return

		error = message.get("error")
		if error is not None:
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
		if channel is None or channel.closed:
			if request_id := message.get("requestId"):
				self._send_error_response(channel_id, request_id, "Channel closed")
			return

		if channel.render_id != render.id or channel.session_id != session.sid:
			logger.warning(
				"Ignoring channel message for mismatched context: %s", channel_id
			)
			return

		if not channel.connected:
			if request_id := message.get("requestId"):
				self._send_error_response(
					channel_id, request_id, "Channel has no connected client"
				)
			return

		event = message["event"]
		payload = message.get("payload")
		request_id = message.get("requestId")

		view = (
			render.views.get(channel.view_id) if channel.view_id is not None else None
		)
		route_ctx = view.route if view is not None else None
		source_pathname = route_ctx.pathname if route_ctx is not None else None

		async def _invoke() -> None:
			try:
				with PulseContext.update(
					session=session,
					render=render,
					route=route_ctx,
					view=view,
					source_pathname=source_pathname,
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
				try:
					self.send_to_client(
						channel=channel,
						msg=msg,
					)
				except ChannelClosed:
					return

		render.create_task(_invoke(), name=f"channel:{channel_id}:{event}")

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
				allow_unconnected=True,
			)
		except ChannelClosed:
			self.resolve_pending_error(request_id, ChannelClosed(message))

	def send_error(self, channel_id: str, request_id: str, message: str) -> None:
		self._send_error_response(channel_id, request_id, message)

	def _cancel_pending_for_channel(
		self, channel_id: str, *, message: str = "Channel closed"
	) -> None:
		for key, pending in list(self.pending_requests.items()):
			if pending.channel_id != channel_id:
				continue
			if not pending.future.done():
				pending.future.set_exception(ChannelClosed(message))
			self.pending_requests.pop(key, None)

	# ------------------------------------------------------------------
	def release_channel(
		self,
		channel_id: str,
		*,
		reason: str | None = None,
	) -> bool:
		channel = self._channels.get(channel_id)
		if channel is None:
			return False
		if channel.closed:
			# Already closed but still tracked; ensure cleanup completes.
			self.dispose_channel(channel, reason=reason or "client.close")
			return True

		channel.closed = True
		self.dispose_channel(channel, reason=reason or "client.close")
		return True

	# ------------------------------------------------------------------
	def _cleanup_channel_refs(self, channel: "Channel") -> None:
		if channel.view_id is not None:
			view_bucket = self._channels_by_view.get(channel.view_id)
			if view_bucket is not None:
				view_bucket.discard(channel.id)
				if not view_bucket:
					self._channels_by_view.pop(channel.view_id, None)

	def dispose_channel(
		self,
		channel: "Channel",
		*,
		reason: str | None = None,
	) -> None:
		self._cleanup_channel_refs(channel)
		self._cancel_pending_for_channel(channel.id)
		# Notify client that the channel has been closed
		if channel.connected:
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
					allow_unconnected=True,
				)
			except Exception:
				print(f"Failed to send close notification for channel {channel.id}")
		channel.connected = False
		channel.clear_handlers()
		self._channels.pop(channel.id, None)

	def send_to_client(
		self,
		*,
		channel: "Channel",
		msg: ServerChannelMessage,
		allow_unconnected: bool = False,
	) -> None:
		if channel.closed and not allow_unconnected:
			raise ChannelClosed(f"Channel '{channel.id}' is closed")
		if not allow_unconnected and not channel.connected:
			raise ChannelClosed("Channel has no connected client")
		if channel.view_id is not None and "view" not in msg:
			msg = cast(
				ServerChannelMessage,
				cast(object, {**msg, "view": channel.view_id}),
			)
		self._render_session.send(msg)


class Channel:
	"""Bidirectional communication channel bound to a render session.

	Channels enable real-time messaging between server and client. Use
	``ps.channel()`` to create a channel within a component.

	Attributes:
		id: Channel identifier (auto-generated UUID or user-provided).
		render_id: Associated render session ID.
		session_id: Associated user session ID.
		view_id: Id of the view this channel is bound to, or None.
		closed: Whether the channel has been closed.

	Example:

	```python
	@ps.component
	def ChatRoom():
	    ch = ps.channel("chat")

	    @ch.on("message")
	    def handle_message(payload):
	        ch.emit("broadcast", payload)

	    return ps.div("Chat room")
	```
	"""

	_manager: ChannelsManager
	id: str
	render_id: str
	session_id: str
	view_id: str | None
	connected: bool
	_handlers: dict[str, list[ChannelHandler]]
	closed: bool

	def __init__(
		self,
		manager: ChannelsManager,
		identifier: str,
		*,
		render_id: str,
		session_id: str,
		view_id: str | None,
	) -> None:
		self._manager = manager
		self.id = identifier
		self.render_id = render_id
		self.session_id = session_id
		self.view_id = view_id
		self.connected = False
		self._handlers = defaultdict(list)
		self.closed = False

	# ---------------------------------------------------------------------
	# Registration
	# ---------------------------------------------------------------------
	def on(self, event: str, handler: ChannelHandler) -> Callable[[], None]:
		"""Register a handler for an incoming event.

		Args:
			event: Event name to listen for.
			handler: Callback function ``(payload: Any) -> Any | Awaitable[Any]``.

		Returns:
			Callable that removes the handler when invoked.

		Raises:
			ChannelClosed: If the channel is closed.

		Example:

		```python
		ch = ps.channel()
		remove_handler = ch.on("data", lambda payload: print(payload))
		# Later, to unregister:
		remove_handler()
		```
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
		"""Send a fire-and-forget event to the client.

		Args:
			event: Event name.
			payload: Data to send (optional).

		Raises:
			ChannelClosed: If the channel is closed.

		Example:

		```python
		ch.emit("notification", {"message": "Hello"})
		```
		"""

		self._ensure_open()
		self._ensure_connected()
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
		"""Send a request to the client and await the response.

		Args:
			event: Event name.
			payload: Data to send (optional).
			timeout: Timeout in seconds (optional).

		Returns:
			Response payload from client.

		Raises:
			ChannelClosed: If the channel is closed.
			ChannelTimeout: If the request times out.

		Example:

		```python
		result = await ch.request("get_value", timeout=5.0)
		```
		"""

		self._ensure_open()
		self._ensure_connected()
		request_id = uuid.uuid4().hex
		fut = create_future()
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
		self._manager.register_pending(request_id, fut, self.id)
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
		"""Close the channel and clean up resources.

		After closing, any further operations on the channel will raise
		``ChannelClosed``. Pending requests will be cancelled.
		"""
		if self.closed:
			return
		self.closed = True
		self._handlers.clear()
		self._manager.dispose_channel(self, reason="channel.close")

	# ---------------------------------------------------------------------
	def _ensure_open(self) -> None:
		if self.closed:
			raise ChannelClosed(f"Channel '{self.id}' is closed")

	def _ensure_connected(self) -> None:
		if not self.connected:
			raise ChannelClosed("Channel has no connected client")

	def clear_handlers(self) -> None:
		self._handlers.clear()

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
	"""Create a channel bound to the current render session.

	Args:
		identifier: Optional channel ID. Auto-generated UUID if not provided.

	Returns:
		Channel instance.

	Raises:
		RuntimeError: If called outside an active render session.

	Example:

	```python
	import pulse as ps

	@ps.component
	def ChatRoom():
	    ch = ps.channel("chat")

	    @ch.on("message")
	    def handle_message(payload):
	        ch.emit("broadcast", payload)

	    return ps.div("Chat room")
	```
	"""

	ctx = PulseContext.get()
	if ctx.render is None:
		raise RuntimeError("Channels require an active render session")
	return ctx.render.channels.create(identifier)


__all__ = [
	"ChannelsManager",
	"Channel",
	"ChannelClosed",
	"ChannelTimeout",
	"channel",
]
