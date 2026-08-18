"""
Pulse UI client bindings for channel communication.

Usage:

```python
from pulse.js.pulse import useChannel, ChannelBridge

@ps.javascript(jsx=True)
def MyChannelComponent(*, channel_id: str):
    bridge = useChannel(channel_id)

    # Subscribe to events
    useEffect(
        lambda: bridge.on("server:notify", lambda payload: console.log(payload)),
        [bridge],
    )

    # Emit events to server
    def send_ping():
        bridge.emit("client:ping", {"message": "hello"})

    # Make requests to server
    async def send_request():
        response = await bridge.request("client:request", {"data": 123})
        console.log(response)

    return ps.div()[
        ps.button(onClick=send_ping)["Send Ping"],
        ps.button(onClick=send_request)["Send Request"],
    ]
```
"""

from collections.abc import Awaitable as _Awaitable
from collections.abc import Callable as _Callable
from typing import Any as _Any
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import JsModule

T = _TypeVar("T")


class PulseChannelDetachedError(Exception):
	"""Kept for the JS export. Client `on()` is legal while detached."""

	pass


class PulseChannelDisconnectedError(Exception):
	"""Raised when a request cannot complete because the socket is down."""

	pass


class PulseChannelRemoteError(Exception):
	"""Raised when the peer responds with an error."""

	pass


class PulseChannelTimeoutError(Exception):
	"""Raised when a client request exceeds `options.timeout` (milliseconds)."""

	pass


class ChannelBridge:
	"""A local handle on a channel name. Messages route by `id`."""

	@property
	def id(self) -> str:
		"""The unique channel identifier."""
		...

	def emit(self, event: str, payload: _Any = None) -> None:
		"""Emit an event to the server.

		Args:
		    event: The event name to emit.
		    payload: Optional data to send with the event.
		"""
		...

	def request(
		self, event: str, payload: _Any = None, options: dict[str, _Any] | None = None
	) -> _Awaitable[_Any]:
		"""Make a request to the server and await a response.

		Args:
		    event: The event name to send.
		    payload: Optional data to send with the request.
		    options: Optional `{ timeout }` in milliseconds.

		Returns:
		    A Promise that resolves with the server's response.
		"""
		...

	def on(self, event: str, handler: _Callable[[_Any], _Any]) -> _Callable[[], None]:
		"""Subscribe to events from the server.

		Args:
		    event: The event name to listen for.
		    handler: A callback function that receives the event payload.
		        May be sync or async. For request events, the return value
		        is sent back to the server.

		Returns:
		    A cleanup function that unsubscribes the handler.
		"""
		...


def useChannel(channel_id: str) -> ChannelBridge:
	"""React hook to attach a handle to a Pulse channel.

	Must be called from within a React component. Client lifetime is React
	placement (route component vs layout). Registers the handle during render
	so a live-socket emit is not dropped waiting for useEffect.

	Args:
	    channel_id: The channel identifier.

	Returns:
	    A ChannelBridge handle for that channel.
	"""
	...


# Register as a JS module with named imports from pulse-ui-client
JsModule.register(name="pulse", src="pulse-ui-client", values="named_import")
