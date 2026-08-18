# Channels

A channel id is a session-scoped name. Messages route by id. The only lifecycle is local listener attach/detach. The name is not created or destroyed on the wire.

## Creating a handle

```python
class ChatState(ps.State):
    messages: list[str] = []

    def __init__(self):
        self.channel = ps.channel("chat")
        self._cleanup = self.channel.on("client:message", self._on_message)

    def _on_message(self, payload: dict):
        self.messages.append(payload["text"])

    def on_dispose(self):
        self._cleanup()
```

`ps.channel()` with `None` generates a UUID. Empty string raises `ValueError`. Pass `channel.id` to client components.

`lifetime="route"` (default) auto-detaches this handle on real route unmount and requires a route context. `lifetime="tab"` survives navigation until session end or `detach()`.

During a live route mount, `ps.channel("foo")` returns the same handle. `on(event, handler)` is idempotent for that triple. Use a stable method, not a new lambda each render. After auto-detach, the next call is a new handle on the same name.

## Server → Client

### Emit (fire-and-forget)

```python
self.channel.emit("server:notify", {"type": "update", "data": {...}})
```

If the WebSocket is down, emit uses the session global queue. No per-channel buffer.

Do not emit during prerender / first server render and expect the client to hear it. `useChannel` registers during render, so an emit after the client has rendered the hook is delivered. Earlier events drop — no listener yet.

### Request (with response)

```python
try:
    response = await self.channel.request(
        "server:ask",
        {"question": "confirm?"},
        timeout=5.0,
    )
except ps.ChannelTimeout:
    print("Client didn't respond in time")
except ps.ChannelDisconnected:
    print("Socket is down")
except ps.ChannelRemoteError as exc:
    print(exc.code, exc.message)
```

No handler → immediate `no_handler` NACK. Middleware `Deny` → `denied`. Middleware exception → `handler_error`. Requests are not queued while the socket is down.

## Client → Server

```python
cleanup = self.channel.on("client:ping", self._on_ping)
cleanup()
```

`on()` after `detach()` raises `ChannelDetached`. `emit` / `request` still address the channel name.

## Client-side

```python
from pulse.js.pulse import useChannel

@ps.javascript(jsx=True)
def ChatClient(*, channel_id: str):
    bridge = useChannel(channel_id)

    def sendMessage(text: str):
        bridge.emit("client:message", {"text": text})

    def setupListeners():
        return bridge.on("server:notify", lambda payload: print(payload))

    useEffect(setupListeners, [bridge])
    return ps.div(...)
```

No `lifetime` argument. Place the hook in a layout to keep listeners across routes. The hook attaches during render (not only in `useEffect`).

Two hooks → two handles, one name. Events fan out. RPC uses the first handler in attach order. Client `on()` is legal while detached (StrictMode). Optional `request(event, payload, { timeout })` is milliseconds.

## Wire

```
{type:"channel", action:"event", channel, event, payload?}
{type:"channel", action:"request", channel, event, payload?, requestId}
{type:"channel", action:"response", channel, responseTo, payload?, error?}
```

`error.code` is `no_handler` | `denied` | `handler_error`. No connect/disconnect/close/subscriptionId on the wire. Reconnect sends zero channel protocol traffic. Events may flush from the global queue; request/response never do.

## Middleware

`channel()` sees inbound events and requests only. `Deny` on event = drop. `Deny` on request = `denied` error response. Channel ids are guessable; gate messages.

## See Also

- `js-interop.md` - React integration for channel UI
- `reactive.md` - Effect for cleanup patterns
- `middleware.md` - Channel authorization
- `errors.md` - Channel exceptions
