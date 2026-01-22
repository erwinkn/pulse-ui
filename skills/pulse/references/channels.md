# Channels

Bidirectional real-time communication between server (Python) and client (browser).

## Creating a Channel

```python
class ChatState(ps.State):
    messages: list[str] = []

    def __init__(self):
        self.channel = ps.channel()
        self._cleanup = self.channel.on("client:message", self._on_message)

    def _on_message(self, payload: dict):
        self.messages.append(payload["text"])

    def on_dispose(self):
        self._cleanup()
```

`ps.channel()` creates a unique channel ID. Pass `channel.id` to client components.

## Server → Client

### Emit (fire-and-forget)

```python
self.channel.emit("server:notify", {"type": "update", "data": {...}})
```

### Request (with response)

```python
try:
    response = await self.channel.request(
        "server:ask",
        {"question": "confirm?"},
        timeout=5.0,  # Optional, default no timeout
    )
    print(f"Client responded: {response}")
except ps.ChannelTimeout:
    print("Client didn't respond in time")
except ps.ChannelClosed:
    print("Channel was closed")
```

## Client → Server

### Listen for events

```python
def _on_ping(self, payload: dict):
    print(f"Client pinged: {payload}")
    # Optionally respond
    self.channel.emit("server:pong", {"ack": True})

# Register handler
cleanup = self.channel.on("client:ping", _on_ping)

# Unregister when done
cleanup()
```

### Handle requests (return response)

```python
async def _on_request(self, payload: dict) -> dict:
    result = await process(payload)
    return {"status": "ok", "result": result}

self.channel.on("client:request", _on_request)
```

## Client-Side (JavaScript)

Use `@ps.javascript` to write client code that uses channels:

```python
from pulse.js.pulse import usePulseChannel

@ps.javascript(jsx=True)
def ChatClient(*, channelId: str):
    bridge = usePulseChannel(channelId)

    # Send event to server
    def sendMessage(text: str):
        bridge.emit("client:message", {"text": text})

    # Request with response
    async def askServer():
        response = await bridge.request("client:request", {"data": "..."})
        print(response)

    # Listen for server events
    def setupListeners():
        def onNotify(payload):
            print("Server notified:", payload)

        off = bridge.on("server:notify", onNotify)
        return off  # Cleanup

    useEffect(setupListeners, [bridge])

    return ps.div(...)
```

### Client Bridge API

```typescript
bridge.emit(event: string, payload?: any): void
bridge.request(event: string, payload?: any): Promise<any>
bridge.on(event: string, handler: (payload) => any): () => void
```

## Full Example

```python
import pulse as ps
from pulse.js.pulse import usePulseChannel

useState = ps.Import("useState", "react")
useEffect = ps.Import("useEffect", "react")


class ChatRoom(ps.State):
    messages: list[dict] = []

    def __init__(self):
        self.channel = ps.channel()
        self._handlers = [
            self.channel.on("client:send", self._on_send),
        ]

    def _on_send(self, payload: dict):
        msg = {"user": "User", "text": payload["text"]}
        self.messages.append(msg)
        # Broadcast to client
        self.channel.emit("server:message", msg)

    def on_dispose(self):
        for cleanup in self._handlers:
            cleanup()


@ps.javascript(jsx=True)
def ChatWidget(*, channelId: str):
    bridge = usePulseChannel(channelId)
    messages, setMessages = useState([])
    draft, setDraft = useState("")

    def subscribe():
        def onMessage(msg):
            setMessages(lambda prev: [*prev, msg])

        return bridge.on("server:message", onMessage)

    useEffect(subscribe, [bridge])

    def send():
        if draft.strip():
            bridge.emit("client:send", {"text": draft})
            setDraft("")

    return ps.div(className="chat")[
        ps.div(className="messages")[
            ps.For(
                messages,
                lambda m, i: ps.div(f"{m['user']}: {m['text']}", key=str(i)),
            )
        ],
        ps.input(
            value=draft,
            onChange=lambda e: setDraft(e.target.value),
            placeholder="Type message...",
        ),
        ps.button("Send", onClick=send),
    ]


@ps.component
def ChatApp():
    with ps.init():
        room = ChatRoom()

    return ps.div(
        ps.h1("Chat"),
        # Server-rendered message list
        ps.ul(
            ps.For(
                room.messages,
                lambda m, _: ps.li(f"{m['user']}: {m['text']}"),
            )
        ),
        # Client widget with channel
        ChatWidget(channelId=room.channel.id),
    )
```

## Error Handling

```python
# Timeout on request
try:
    response = await channel.request("event", data, timeout=5.0)
except ps.ChannelTimeout:
    # Handle timeout
    pass

# Channel closed (user navigated away)
try:
    channel.emit("event", data)
except ps.ChannelClosed:
    # Handle closed channel
    pass
```

## Channel Lifecycle

1. **Created** — `ps.channel()` in State `__init__`
2. **Active** — While component is mounted
3. **Closed** — When component unmounts or user disconnects

Always clean up handlers in `on_dispose()`:

```python
class MyState(ps.State):
    def __init__(self):
        self.channel = ps.channel()
        self._cleanup = []
        self._cleanup.append(self.channel.on("event1", self._h1))
        self._cleanup.append(self.channel.on("event2", self._h2))

    def on_dispose(self):
        for cleanup in self._cleanup:
            cleanup()
```

## Channel Properties

```python
channel.id      # str — unique channel identifier
channel.closed  # bool — True if channel is closed
```

## Use Cases

- **Chat/messaging** — Real-time message sync
- **Live updates** — Push data changes to client
- **Collaborative editing** — Multi-user sync
- **Notifications** — Server-initiated alerts
- **Gaming** — Low-latency state sync
- **Progress tracking** — Long-running task updates

## See Also

- `js-interop.md` - React integration for channel UI
- `reactive.md` - Effect for cleanup patterns
- `middleware.md` - Channel authorization with channel hook
