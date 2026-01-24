# Pulse JS Client

React client library that renders server-driven VDOM and handles WebSocket communication with the Pulse Python server.

## Architecture

Client receives VDOM updates via Socket.IO and renders using React. Events are serialized and sent back to server.

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser                                                        │
│  ┌──────────────┐  ┌────────────┐  ┌─────────────────────────┐  │
│  │ PulseProvider│──│ PulseClient│──│ Transport (Socket.IO)   │  │
│  └──────────────┘  └────────────┘  └─────────────────────────┘  │
│         │                │                                      │
│         ▼                ▼                                      │
│  ┌──────────────┐  ┌────────────┐                               │
│  │  PulseView   │  │  Renderer  │                               │
│  │  (per route) │  │  (VDOM→DOM)│                               │
│  └──────────────┘  └────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
         ▲                                        │
         │ VDOM updates                           │ Events/callbacks
         │                                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Python Server                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Folder Structure

```
src/
├── index.ts            # Public API exports
├── pulse.tsx           # PulseProvider, PulseView, context
├── client.tsx          # PulseClient - manages connection & views
├── renderer.tsx        # VDOM-to-React rendering
├── channel.ts          # Channel bridge for real-time messaging
├── transport.ts        # Socket.IO transport layer
├── messages.ts         # Client<->server message types
├── form.tsx            # PulseForm component
├── helpers.ts          # Route info extraction utilities
├── vdom.ts             # VDOM types (VDOMNode, VDOMElement)
├── usePulseChannel.ts  # React hook for channels
│
└── serialize/          # Data serialization
    ├── serializer.ts   # Main serialize/deserialize
    ├── clean.ts        # Data cleaning for wire transfer
    ├── elements.ts     # Element extraction from refs
    ├── events.ts       # Event serialization
    └── extractor.ts    # Data extraction utilities
```

## Key Concepts

### PulseProvider

Root provider establishing server connection:

```tsx
import { PulseProvider } from "pulse-client";

function App() {
  return (
    <PulseProvider config={{ serverUrl: "http://localhost:8000" }}>
      <Routes />
    </PulseProvider>
  );
}
```

### PulseView

Renders server-driven view for a route:

```tsx
import { PulseView } from "pulse-client";

function Dashboard() {
  return <PulseView path="/dashboard" />;
}
```

### PulseClient

Manages WebSocket connection, route mounting, message handling. Access via `usePulseClient()`.

### Renderer

Converts VDOM to React:
- Handles element types (div, span, etc.)
- Resolves component references
- Binds event handlers to server
- Manages refs and lazy loading

### Transport

Socket.IO transport with automatic reconnection, message queuing, connection status.

### Channels

Real-time messaging:

```tsx
import { usePulseChannel } from "pulse-client";

function Chat() {
  const channel = usePulseChannel("chat");
  channel.on("new_message", (msg) => { /* handle */ });
  channel.emit("message", { text: "Hello" });
}
```

## Main Exports

**Components**: `PulseProvider`, `PulseRouterProvider`, `PulseRoutes`, `PulseView`, `PulseForm`, `Link`, `Outlet`, `RenderLazy`

**Hooks**: `usePulseClient()`, `usePulseChannel(name)`

**Functions**: `serialize`, `deserialize`, `buildRouteInfo`, `submitForm`

**Types**: `VDOM`, `VDOMNode`, `VDOMElement`, `PulseClient`, `Transport`, `ComponentRegistry`
