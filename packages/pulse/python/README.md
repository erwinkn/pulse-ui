# Pulse Python

Core Python framework for building full-stack reactive web apps with React frontends.

## Architecture

Server-driven UI model: Python components render to VDOM, synced to React via WebSocket. State changes trigger re-renders; diffs are sent to client.

```
┌─────────────────────────────────────────────────────────────────┐
│  Python Server                                                  │
│  ┌──────────┐  ┌───────────────┐  ┌──────────────────────────┐  │
│  │   App    │──│ RenderSession │──│ VDOM Renderer            │  │
│  │ (FastAPI)│  │ (per browser) │  │ (diff & serialize)       │  │
│  └──────────┘  └───────────────┘  └──────────────────────────┘  │
│       │                │                      │                 │
│       │         ┌──────┴───────┐              │                 │
│       │         │    Hooks     │              │                 │
│       │         │ (state/setup)│              │                 │
│       │         └──────────────┘              │                 │
└───────┼───────────────────────────────────────┼─────────────────┘
        │ Socket.IO                             │ VDOM updates
        ▼                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Browser (React)                                                │
└─────────────────────────────────────────────────────────────────┘
```

## Folder Structure

```
src/pulse/
├── app.py              # Main App class, FastAPI + Socket.IO setup
├── channel.py          # Bidirectional real-time channels
├── routing.py          # Route/Layout definitions, URL matching
├── vdom.py             # VDOM node types (Element, Component, Node)
├── renderer.py         # VDOM rendering and diffing
├── render_session.py   # Per-browser session, manages mounted routes
├── reactive.py         # Signal/Computed/Effect primitives
├── reactive_extensions.py  # ReactiveList, ReactiveDict, ReactiveSet
├── state.py            # State management
├── serializer.py       # Python<->JSON serialization
├── middleware.py       # Request middleware (prerender, connect, message)
├── plugin.py           # Plugin interface for extensions
├── form.py             # Form handling
├── context.py          # PulseContext (request/session context)
├── cookies.py          # Cookie management
├── request.py          # PulseRequest abstraction
├── user_session.py     # User session storage
├── helpers.py          # Utilities (CSSProperties, later, repeat)
├── decorators.py       # @computed, @effect decorators
├── messages.py         # Client<->server message types
├── react_component.py  # ReactComponent wrapper for JS libraries
│
├── hooks/              # Server-side hooks (like React hooks)
│   ├── core.py         # Hook registry, HooksAPI
│   ├── runtime.py      # session(), route(), navigate(), redirect()
│   ├── states.py       # Reactive state hook
│   ├── effects.py      # Side effects hook
│   ├── setup.py        # Initialization hook
│   ├── init.py         # One-time setup hook
│   └── stable.py       # Memoization hook
│
├── queries/            # Data fetching (like TanStack Query)
│   ├── query.py        # @query decorator
│   ├── mutation.py     # @mutation decorator
│   ├── infinite_query.py  # Pagination support
│   ├── client.py       # QueryClient for cache management
│   └── store.py        # Query state store
│
├── components/         # Built-in components
│   ├── for_.py         # <For> loop component
│   ├── if_.py          # <If> conditional component
│   └── react_router.py # Link, Outlet for routing
│
├── html/               # HTML element bindings
│   ├── tags.py         # div, span, button, etc.
│   ├── props.py        # Typed props for HTML elements
│   ├── events.py       # Event types (MouseEvent, etc.)
│   └── elements.py     # Element type definitions
│
├── transpiler/         # Python->JS transpilation
│   ├── function.py     # JsFunction, @javascript decorator
│   └── imports.py      # Import/CssImport for client-side JS
│
├── codegen/            # Code generation for React Router
│   ├── codegen.py      # Generates routes.ts, loaders
│   └── templates/      # Mako templates for generated code
│
├── cli/                # Command-line interface
│   ├── cmd.py          # pulse run, pulse build
│   └── processes.py    # Dev server process management
│
└── js/                 # JS API stubs for transpilation
    ├── window.py, document.py, navigator.py
    ├── array.py, object.py, string.py
    └── ...
```

## Key Concepts

### App

Entry point defining routes, middleware, plugins.

```python
import pulse as ps

app = ps.App(routes=[
    ps.Route("/", home),
    ps.Layout("/dashboard", layout, children=[
        ps.Route("/", dashboard),
    ]),
])
```

### Components

Functions returning VDOM. Use `@ps.component` for stateful components.

```python
def greeting(name: str):
    return ps.div(f"Hello, {name}!")

@ps.component
def counter():
    count = ps.states.use(0)
    return ps.button(f"Count: {count()}", onClick=lambda _: count.set(count() + 1))
```

### Reactivity

- `Signal[T]` - reactive value
- `Computed[T]` - derived value
- `Effect` - side effect on change

### Hooks

Server-side hooks via `ps.states`, `ps.effects`, `ps.setup`:
- `states.use(initial)` - reactive state
- `effects.use(fn, deps)` - side effects
- `setup.use(fn)` - one-time initialization

### Queries

Data fetching with caching:

```python
@ps.query
async def fetch_user(id: str):
    return await db.get_user(id)
```

### Channels

Bidirectional real-time messaging:

```python
ch = ps.channel("chat")

@ch.on("message")
def handle_message(data):
    ch.broadcast("new_message", data)
```

## Main Exports

- `App`, `Route`, `Layout` - app/routing
- `component` - server-side component decorator
- `states`, `effects`, `setup`, `init` - hooks
- `query`, `mutation`, `infinite_query` - data fetching
- `channel` - real-time channels
- `State`, `@computed`, `@effect` - reactivity
- `ReactiveList`, `ReactiveDict`, `ReactiveSet` - reactive containers
- `div`, `span`, `button`, ... - HTML elements
- `For`, `If`, `Link`, `Outlet` - built-in components
- `@react_component` - wrap JS components
- `@javascript` - transpile Python to JS
