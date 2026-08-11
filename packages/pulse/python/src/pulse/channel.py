"""Bidirectional channels with client subscription lifetimes.

The server owns channel lifetime; clients only subscribe and unsubscribe. Server
emits made without a subscriber are buffered per channel in a 64-item FIFO. Once
the cap is reached, the oldest event is dropped. Buffered events flush in order
after a subscription is acknowledged. Requests are never buffered and fail
immediately while disconnected.

Route-lifetime channels close with the route that created them. Tab-lifetime
channels survive route changes and close with the browser tab's render session.
Both lifetimes permit an earlier explicit ``Channel.close()``.
"""

import asyncio
import logging
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from pulse.context import PulseContext
from pulse.messages import (
	ClientChannelConnectMessage,
	ClientChannelDisconnectMessage,
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
	ServerChannelConnectAckMessage,
	ServerChannelMessage,
	ServerChannelRequestMessage,
	ServerChannelResponseMessage,
)
from pulse.scheduling import create_future
from pulse.serializer import deserialize, serialize

if TYPE_CHECKING:
	from pulse.render_session import RenderSession
	from pulse.user_session import UserSession

logger = logging.getLogger(__name__)

DISCONNECTED_EMIT_BUFFER_CAP = 64


ChannelLifetime = Literal["route", "tab"]


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


class ChannelDisconnected(RuntimeError):
	"""Raised when a channel request has no connected client subscriber."""


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
	_channels_by_owner: dict[object, set[str]]
	pending_requests: dict[str, PendingRequest]

	def __init__(self, render_session: "RenderSession") -> None:
		self._render_session = render_session
		self._channels = {}
		self._channels_by_owner = defaultdict(set)
		self.pending_requests = {}

	# ------------------------------------------------------------------
	def create(
		self,
		identifier: str | None = None,
		*,
		lifetime: ChannelLifetime = "route",
	) -> "Channel":
		ctx = PulseContext.get()
		render = ctx.render
		session = ctx.session
		if render is None or session is None:
			raise RuntimeError("Channels require an active render and session")
		if lifetime not in ("route", "tab"):
			raise ValueError("Channel lifetime must be 'route' or 'tab'")
		if lifetime == "route" and ctx.route is None:
			raise RuntimeError(
				"Route channels require an active route; use lifetime='tab' outside a route"
			)

		channel_id = identifier or uuid.uuid4().hex
		if channel_id in self._channels:
			raise ValueError(f"Channel id '{channel_id}' is already in use")

		owner_token: object | None = None
		if lifetime == "route":
			owner_token = ctx.route.route_path  # pyright: ignore[reportOptionalMemberAccess]

		channel = Channel(
			self,
			channel_id,
			render_id=render.id,
			session_id=session.sid,
			owner_token=owner_token,
			lifetime=lifetime,
		)
		self._channels[channel_id] = channel
		if owner_token is not None:
			self._channels_by_owner[owner_token].add(channel_id)
		return channel

	# ------------------------------------------------------------------
	def remove_route(self, path: str) -> None:
		"""Dispose channels owned by the opaque token currently represented by path."""
		route_channels = list(self._channels_by_owner.get(path, set()))
		for channel_id in route_channels:
			channel = self._channels.get(channel_id)
			if channel is None:
				continue
			self.dispose_channel(channel, reason="route.unmount")
		self._channels_by_owner.pop(path, None)

	def validate_owner(
		self,
		channel: "Channel",
		*,
		render: "RenderSession",
		session: "UserSession",
		owner_token: object | None,
		require_active: bool = True,
	) -> tuple[Any | None, str | None] | None:
		"""Validate channel ownership and resolve its route context in one place."""
		if channel.render_id != render.id or channel.session_id != session.sid:
			return None
		if channel._owner_token != owner_token:  # pyright: ignore[reportPrivateUsage]
			return None
		if owner_token is None:
			return (None, None)
		if not isinstance(owner_token, str):
			return None
		try:
			mount = render.get_route_mount(owner_token)
		except ValueError:
			return None
		if require_active and mount.state != "active":
			return None
		return (mount.route, mount.mount_id)

	def handle_client_connect(
		self,
		*,
		render: "RenderSession",
		session: "UserSession",
		message: ClientChannelConnectMessage,
	) -> bool:
		channel_id = str(message.get("channel", ""))
		subscription_id = str(message.get("subscriptionId", ""))
		owner_token = message.get("owner")
		channel = self._channels.get(channel_id)
		if (
			channel is None
			or channel.closed
			or not subscription_id
			or self.validate_owner(
				channel,
				render=render,
				session=session,
				owner_token=owner_token,
			)
			is None
		):
			self.reject_client_connect(message, "Channel is unavailable")
			return False

		channel._connect(subscription_id)  # pyright: ignore[reportPrivateUsage]
		self._send_connect_ack(channel_id, subscription_id, accepted=True)
		channel._flush_buffer()  # pyright: ignore[reportPrivateUsage]
		return True

	def reject_client_connect(
		self, message: ClientChannelConnectMessage, error: str
	) -> None:
		self._send_connect_ack(
			str(message.get("channel", "")),
			str(message.get("subscriptionId", "")),
			accepted=False,
			error=error,
		)

	def _send_connect_ack(
		self,
		channel_id: str,
		subscription_id: str,
		*,
		accepted: bool,
		error: str | None = None,
	) -> None:
		message = ServerChannelConnectAckMessage(
			type="channel_connect_ack",
			channel=channel_id,
			subscriptionId=subscription_id,
			accepted=accepted,
		)
		if error is not None:
			message["error"] = error
		self._render_session.send(message)

	def handle_client_disconnect(
		self,
		*,
		render: "RenderSession",
		session: "UserSession",
		message: ClientChannelDisconnectMessage,
	) -> bool:
		channel = self._channels.get(str(message.get("channel", "")))
		if channel is None:
			return False
		if (
			self.validate_owner(
				channel,
				render=render,
				session=session,
				owner_token=message.get("owner"),
				require_active=False,
			)
			is None
		):
			return False
		return channel._disconnect(  # pyright: ignore[reportPrivateUsage]
			str(message.get("subscriptionId", ""))
		)

	def disconnect_all(self) -> None:
		for channel in self._channels.values():
			channel._disconnect()  # pyright: ignore[reportPrivateUsage]

	def close_all(self) -> None:
		for channel in list(self._channels.values()):
			self.dispose_channel(channel, reason="render.close")

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
		if channel is None:
			if request_id := message.get("requestId"):
				self._send_error_response(channel_id, request_id, "Channel closed")
			return

		owner = self.validate_owner(
			channel,
			render=render,
			session=session,
			owner_token=channel._owner_token,  # pyright: ignore[reportPrivateUsage]
		)
		if owner is None:
			logger.warning(
				"Ignoring channel message for mismatched context: %s", channel_id
			)
			if request_id := message.get("requestId"):
				self._send_error_response(
					channel_id, request_id, "Channel owner is inactive"
				)
			return
		if not channel.connected:
			if request_id := message.get("requestId"):
				self._send_error_response(
					channel_id, request_id, "Channel is disconnected"
				)
			return

		event = message["event"]
		payload = message.get("payload")
		request_id = message.get("requestId")

		route_ctx, source_mount_id = owner

		async def _invoke() -> None:
			try:
				with PulseContext.update(
					session=session,
					render=render,
					route=route_ctx,
					source_route_path=(
						route_ctx.route_path if route_ctx is not None else None
					),
					source_path=route_ctx.pathname if route_ctx is not None else None,
					source_mount_id=source_mount_id,
				):
					result = await channel.dispatch(event, payload, request_id)
			except Exception as exc:
				if request_id:
					self._send_error_response(channel.id, request_id, str(exc))
				else:
					logger.exception("Unhandled error in channel handler")
				return

			if request_id and channel.connected and not channel.closed:
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
		msg = ServerChannelResponseMessage(
			type="channel_message",
			channel=channel.id if channel is not None else channel_id,
			event=None,
			responseTo=request_id,
			payload=None,
			error=message,
		)
		self._render_session.send(msg)

	def send_error(self, channel_id: str, request_id: str, message: str) -> None:
		self._send_error_response(channel_id, request_id, message)

	def _cancel_pending_for_channel(
		self, channel_id: str, error: Exception | None = None
	) -> None:
		error = error or ChannelClosed("Channel closed")
		for key, pending in list(self.pending_requests.items()):
			if pending.channel_id != channel_id:
				continue
			if not pending.future.done():
				pending.future.set_exception(error)
			self.pending_requests.pop(key, None)

	# ------------------------------------------------------------------
	def _cleanup_channel_refs(self, channel: "Channel") -> None:
		owner_token = channel._owner_token  # pyright: ignore[reportPrivateUsage]
		if owner_token is not None:
			route_bucket = self._channels_by_owner.get(owner_token)
			if route_bucket is not None:
				route_bucket.discard(channel.id)
				if not route_bucket:
					self._channels_by_owner.pop(owner_token, None)

	def dispose_channel(
		self,
		channel: "Channel",
		*,
		reason: str | None = None,
	) -> None:
		if channel.closed:
			return
		was_connected = channel.connected
		channel._finalize()  # pyright: ignore[reportPrivateUsage]
		self._cleanup_channel_refs(channel)
		self._cancel_pending_for_channel(channel.id)
		self._channels.pop(channel.id, None)
		if was_connected:
			msg = ServerChannelRequestMessage(
				type="channel_message",
				channel=channel.id,
				event="__close__",
				payload={"reason": reason or "channel.close"},
			)
			self._render_session.send(msg)

	def send_to_client(
		self,
		*,
		channel: "Channel",
		msg: ServerChannelMessage,
	) -> None:
		if channel.closed:
			raise ChannelClosed(f"Channel '{channel.id}' is closed")
		if not channel.connected:
			raise ChannelDisconnected(
				f"Channel '{channel.id}' has no connected client subscriber"
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
		lifetime: Automatic channel lifetime, ``"route"`` or ``"tab"``.
		route_path: Route path this channel is bound to, or None.
		closed: Whether the channel has been closed.
		connected: Whether a client is currently subscribed.

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
	lifetime: ChannelLifetime
	_owner_token: object | None
	_handlers: dict[str, list[ChannelHandler]]
	_buffer: deque[ServerChannelRequestMessage]
	_subscription_id: str | None
	closed: bool
	connected: bool

	def __init__(
		self,
		manager: ChannelsManager,
		identifier: str,
		*,
		render_id: str,
		session_id: str,
		owner_token: object | None,
		lifetime: ChannelLifetime,
	) -> None:
		self._manager = manager
		self.id = identifier
		self.render_id = render_id
		self.session_id = session_id
		self.lifetime = lifetime
		self._owner_token = owner_token
		self._handlers = defaultdict(list)
		self._buffer = deque(maxlen=DISCONNECTED_EMIT_BUFFER_CAP)
		self._subscription_id = None
		self.closed = False
		self.connected = False

	@property
	def route_path(self) -> str | None:
		"""Current route-shaped owner token, retained for introspection."""
		return self._owner_token if isinstance(self._owner_token, str) else None

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
		msg = ServerChannelRequestMessage(
			type="channel_message",
			channel=self.id,
			event=event,
			payload=payload,
		)
		if not self.connected:
			if len(self._buffer) == DISCONNECTED_EMIT_BUFFER_CAP:
				logger.warning(
					"Dropping oldest buffered event for disconnected channel '%s'",
					self.id,
				)
			self._buffer.append(
				cast(ServerChannelRequestMessage, deserialize(serialize(msg)))
			)
			return
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
			ChannelDisconnected: If no client is subscribed.
			ChannelTimeout: If the request times out.

		Example:

		```python
		result = await ch.request("get_value", timeout=5.0)
		```
		"""

		self._ensure_connected()
		request_id = uuid.uuid4().hex
		fut = create_future()
		self._manager.register_pending(request_id, fut, self.id)
		msg = ServerChannelRequestMessage(
			type="channel_message",
			channel=self.id,
			event=event,
			payload=payload,
			requestId=request_id,
		)
		sent = False
		try:
			self._manager.send_to_client(
				channel=self,
				msg=msg,
			)
			sent = True
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
			if not sent and fut.done() and not fut.cancelled():
				fut.exception()

	# ---------------------------------------------------------------------
	def close(self) -> None:
		"""Close the channel and clean up resources.

		After closing, any further operations on the channel will raise
		``ChannelClosed``. Pending requests will be cancelled.
		"""
		if self.closed:
			return
		self._manager.dispose_channel(self, reason="channel.close")

	# ---------------------------------------------------------------------
	def _ensure_open(self) -> None:
		if self.closed:
			raise ChannelClosed(f"Channel '{self.id}' is closed")

	def _ensure_connected(self) -> None:
		self._ensure_open()
		if not self.connected:
			raise ChannelDisconnected(
				f"Channel '{self.id}' has no connected client subscriber"
			)

	def _connect(self, subscription_id: str) -> None:
		self._ensure_open()
		self._subscription_id = subscription_id
		self.connected = True

	def _disconnect(self, subscription_id: str | None = None) -> bool:
		if subscription_id is not None and subscription_id != self._subscription_id:
			return False
		if not self.connected and self._subscription_id is None:
			return False
		self.connected = False
		self._subscription_id = None
		self._manager._cancel_pending_for_channel(  # pyright: ignore[reportPrivateUsage]
			self.id,
			ChannelDisconnected(
				f"Channel '{self.id}' lost its connected client subscriber"
			),
		)
		return True

	def _flush_buffer(self) -> None:
		while self._buffer and self.connected and not self.closed:
			self._manager.send_to_client(channel=self, msg=self._buffer.popleft())

	def _finalize(self) -> None:
		self.closed = True
		self.connected = False
		self._subscription_id = None
		self._handlers.clear()
		self._buffer.clear()

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


def channel(
	identifier: str | None = None,
	*,
	lifetime: ChannelLifetime = "route",
) -> Channel:
	"""Create a channel with a route or browser-tab lifetime.

	Args:
		identifier: Optional channel ID. Auto-generated UUID if not provided.
		lifetime: ``"route"`` closes the channel with the current route.
			``"tab"`` keeps it alive until explicit close or render-session close.

	Returns:
		Channel instance.

	Raises:
		RuntimeError: If called outside an active render session, or if a
			route-lifetime channel is created without an active route.
		ValueError: If ``lifetime`` is not ``"route"`` or ``"tab"``.

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
	return ctx.render.channels.create(identifier, lifetime=lifetime)


__all__ = [
	"ChannelsManager",
	"Channel",
	"ChannelClosed",
	"ChannelDisconnected",
	"ChannelLifetime",
	"ChannelTimeout",
	"channel",
]
