# JavaScript Interop

Integrate React components, execute JavaScript, and transpile Python to JS.

## Wrapping React Components

Use existing React/npm components in Pulse:

```python
@ps.react_component(
    ps.Import("Button", "@mantine/core"),
)
def Button(
    *children: ps.Node,
    variant: str = "filled",
    color: str = "blue",
    onClick: ps.EventHandler0 | None = None,
    disabled: bool = False,
) -> ps.Element: ...
```

### Import Syntax

```python
# Named export
ps.Import("Button", "@mantine/core")

# Default export — single argument (name == src ⇒ default import)
ps.Import("react-datepicker")

# Local file, named export
ps.Import("MyComponent", "~/components/my-component")

# Local file, default export
ps.Import("~/components/my-component")
```

### Lazy Loading with `@ps.react_component`

```python
@ps.react_component(
    ps.Import("HeavyChart", "chart-library"),
    lazy=True,  # Code-split, load on demand
)
def Chart(...) -> ps.Element: ...
```

### Lazy Loading with `React.lazy`

For more control over lazy loading, use `Import(lazy=True)` with `React.lazy`:

```python
from pulse.js.react import lazy, Suspense

# Create lazy-loaded component (code-split)
LazyChart = lazy(ps.Import("LineChart", "recharts", lazy=True))

# Use with Suspense for loading fallback
@ps.component
def Dashboard():
    return ps.div[
        Suspense(fallback=ps.div("Loading chart..."))[
            LazyChart(data=chart_data, width=600, height=400),
        ],
    ]
```

### How Lazy Loading Works

1. `Import(..., lazy=True)` generates a dynamic import factory: `() => import("recharts")`
2. `lazy(factory)` wraps it with `React.lazy` for component-level code splitting
3. `Suspense` shows a fallback while the component loads

### When to Use Lazy Loading

- Large components (charts, editors, heavy UI)
- Components not immediately visible (modals, below-the-fold content)
- Reducing initial bundle size

### Full Example

```python
@ps.react_component(
    ps.Import("react-datepicker"),  # default export
    lazy=True,
)
def DatePicker(
    *children: ps.Node,
    key: str | None = None,
    value: datetime | None = None,
    onChange: ps.EventHandler1[datetime | None] | None = None,
    placeholder: str = "Select date",
    showTimeSelect: bool = False,
) -> ps.Element: ...


class FormState(ps.State):
    date: datetime | None = None

    def set_date(self, d: datetime | None):
        self.date = d


@ps.component
def DateForm():
    with ps.init():
        state = FormState()

    return ps.div(
        DatePicker(
            value=state.date,
            onChange=state.set_date,
            showTimeSelect=True,
        ),
        ps.p(f"Selected: {state.date}"),
    )
```

## Render Props: Callables Are Server Callbacks

A Python callable passed as a prop (or child) is registered as a **server callback**: the client receives a stub function that serializes its arguments, sends them over the WebSocket, and returns nothing. This is exactly right for event handlers — and exactly wrong for render props:

- The stub's return value is `undefined`; whatever your Python function returns is **never rendered**.
- Arguments are serialized event payloads; the callable cannot receive live client-side objects (functions, class instances) that render-prop APIs pass.
- Raw DOM nodes are rejected. React event arguments are extracted into serializable dictionaries before they cross the wire.

For render-prop APIs — components that call `children(args)` and render the result — pass a **transpiled** `@ps.javascript(jsx=True)` function instead. It runs fully client-side, receives the real render args, and its return value is rendered:

```python
@ps.react_component(ps.Import("CopyButton", "@mantine/core"))
def CopyButton(*children: ps.Node, value: str) -> ps.Element: ...
# Mantine calls children({copied, copy}) and renders the result

# BAD — server callback: returns nothing to render, args aren't live client objects
CopyButton(lambda state: ps.button("Copy", onClick=state["copy"]), value=text)

# GOOD — transpiled render prop, runs entirely in the browser
@ps.javascript(jsx=True)
def CopyLabel(state):
    return ps.button(
        "Copied" if state.copied else "Copy",
        onClick=state.copy,
    )

CopyButton(CopyLabel, value=text)
```

## `@ps.javascript` — Transpile Python to JS

Write client-side code in Python, runs in browser:

```python
@ps.javascript
def calculate(x: int, y: int) -> int:
    return x + y

# Emits JavaScript, executes client-side
```

### JSX Mode

```python
@ps.javascript(jsx=True)
def ClientWidget(*, name: str):
    return ps.div(className="widget")[
        ps.h1(f"Hello, {name}"),
        ps.button("Click", onClick=lambda: alert("Clicked!")),
    ]
```

### React Hooks in Transpiled Code

```python
from pulse.js.pulse import usePulseChannel

useState = ps.Import("useState", "react")
useEffect = ps.Import("useEffect", "react")
useCallback = ps.Import("useCallback", "react")
useRef = ps.Import("useRef", "react")


@ps.javascript(jsx=True)
def InteractiveWidget():
    count, setCount = useState(0)
    inputRef = useRef(None)

    def handleClick():
        setCount(lambda c: c + 1)

    def focusInput():
        if inputRef.current:
            inputRef.current.focus()

    useEffect(lambda: print(f"Count: {count}"), [count])

    return ps.div[
        ps.p(f"Count: {count}"),
        ps.button("Increment", onClick=handleClick),
        ps.input(ref=inputRef, placeholder="Focus me"),
        ps.button("Focus", onClick=focusInput),
    ]
```

### JavaScript Builtins

Access JS globals via `pulse.js`:

```python
from pulse.js import (
    AbortController,
    Animation,
    ArrayBuffer,
    Blob,
    CustomEvent,
    DOMParser,
    DocumentTimeline,
    Error,
    File,
    FileReader,
    FormData,
    Headers,
    Intl,
    IntersectionObserver,
    JSON,
    KeyframeEffect,
    Math,
    MutationObserver,
    Promise,
    Request,
    ResizeObserver,
    Response,
    TextDecoder,
    TextEncoder,
    URL,
    URLSearchParams,
    Uint8Array,
    XMLSerializer,
    decodeURI,
    decodeURIComponent,
    encodeURI,
    encodeURIComponent,
    console,
    crypto,
    document,
    window,
)
from pulse.js.date import Date

@ps.javascript
def example():
    # Math
    x = Math.random()
    y = Math.floor(3.7)

    # Console
    console.log("Hello")

    # Date
    now = Date.now()
    d = Date()
    iso = d.toISOString()

    # JSON
    s = JSON.stringify({"a": 1})
    obj = JSON.parse(s)

    # Window/Document
    window.alert("Hi")
    el = document.getElementById("app")
```

### Object Literals

```python
from pulse.js import obj

@ps.javascript
def create_config():
    return obj(
        name="config",
        nested=obj(a=1, b=2),
        items=[1, 2, 3],
    )
```

## Latency-sensitive interactions

Handlers bound to `ps.State` execute **on the server**: each call is a WebSocket round-trip (event up, re-render diff back). Deliberate, infrequent actions absorb that latency fine. Rapid or frequent callbacks do not — routing them through the server makes the UI feel laggy.

**Keep on the server (round-trip is fine):** button clicks, form submits, changing an explicit filter/toggle, navigation, opening a modal.

**Keep client-side in transpiled code:** `moveend`/pan/zoom, scroll, drag, resize, pointer-move, animation frames, and per-keystroke work beyond what `ps.debounced` smooths. Rule of thumb: *if it fires faster than a human clicks, it belongs in transpiled JS.*

The shape that works: the server renders the page and passes data down as props; a client component (`@ps.javascript(jsx=True)` or a hand-written react_component) owns the hot interaction and applies the effect locally, never touching the server.

### Coordinating two client components without the server

A server-rendered parent can't hand a shared mutable object to two sibling client components. Bridge them with a `window` `CustomEvent` — pure browser, no round-trip. One component dispatches; the other subscribes with `useEffect` + `addEventListener`.

```python
from pulse.js import window
from pulse.js.react import useEffect, useState

VIEWPORT_EVENT = "app:viewport"  # keep in sync with the dispatcher

@ps.javascript(jsx=True)
def GallerySection(*, photos: list[dict] | None = None, filterByMap: bool = True):
    photos = photos or []
    state = useState(None)          # visible IDs; None = "no viewport info yet"
    visible_ids, set_visible_ids = state[0], state[1]

    def subscribe():
        def handle(event):
            set_visible_ids(event.detail.itemIds)
        window.addEventListener(VIEWPORT_EVENT, handle)
        return lambda: window.removeEventListener(VIEWPORT_EVENT, handle)

    useEffect(subscribe, [])

    shown = (
        [p for p in photos if p["item_id"] in visible_ids]
        if filterByMap and visible_ids is not None
        else photos
    )
    return Gallery(photos=shown)
```

The dispatcher side (here a hand-written react_component map) computes the payload from local state and broadcasts on the rapid event:

```ts
// The payload is a pure derivation of (viewport, points): string[] when points
// are loaded, or null = "no answer yet" (the listener shows everything). Emit on
// BOTH the rapid event AND whenever the data changes, so the listener updates the
// moment points load instead of waiting for a move it can't predict.
function emitViewport() {
  const itemIds =
    points.length === 0
      ? null
      : points.filter(p => bounds.contains([p.lng, p.lat])).map(p => p.itemId);
  window.dispatchEvent(new CustomEvent("app:viewport", { detail: { itemIds } }));
}
map.on("moveend", emitViewport);
// ...and call emitViewport() again right after the point data is (re)loaded.
```

A server-owned **toggle** (clicked rarely) can still gate the client behavior — pass it as a prop (`filterByMap` above); the one round-trip per click is acceptable.

**Gotchas:**
- Give the payload an explicit **"unknown" value** (`null`) distinct from **"known-empty"** (`[]`): `null` ⇒ listener shows everything; `[]` ⇒ genuinely nothing in view. Broadcasting `[]` before the data has loaded makes the listener flash empty.
- Treat the broadcast as a **pure function of its inputs** and re-emit when *either* input changes (viewport **or** data) — not only on the rapid event. Pushing updates "at lifecycle moments" (a one-time `load`, the first `moveend`) races async data: a late data load leaves the listener stale until the next move.
- A **virtualized** list (`@tanstack/react-virtual`) can't be filtered by hiding DOM nodes — only the rendered window exists. Filter the **data array** you feed the virtualizer.
- Shareable URL state (query params) can also be synced client-side with `history.replaceState` inside the component — no navigation, no server hop. (Server-synced `ps.QueryParam` is for deliberate state changes, not per-frame viewport updates; see `routing.md`.)

## `ps.require()` — Declare npm Dependencies

Register npm package version requirements at module level:

```python
import pulse as ps

# Declare dependencies (call at module level, not inside components)
ps.require({"recharts": "^2.0.0"})
ps.require({"lodash": "^4.17.0", "@tanstack/react-query": ">=5.0.0"})
```

### Signature

```python
def require(packages: Mapping[str, str]) -> None:
    """Register npm package version requirements for dependency syncing."""
```

### When to Call

- **Module level**: Call `ps.require()` at the top of your module, outside component functions
- **Not inside components**: Requirements are collected during module import, not during render

### Version Specifier Syntax

Uses standard npm semver syntax:

```python
ps.require({"package": "^1.0.0"})   # Compatible with 1.x.x
ps.require({"package": "~1.0.0"})   # Compatible with 1.0.x
ps.require({"package": ">=2.0.0"})  # 2.0.0 or higher
ps.require({"package": "1.2.3"})    # Exact version
```

### How Dependencies Work

Dependencies declared via `ps.require()` are:
1. Collected during Python module import
2. Merged with component-level imports (from `ps.Import`)
3. Synced to `package.json` during codegen
4. Installed via npm/bun when running the dev server

**Note**: You can also specify versions inline with `ps.Import`:

```python
# Version in Import (alternative to ps.require)
Chart = ps.Import("LineChart", "recharts@^2.0.0")
```

## `run_js()` — Execute JavaScript Imperatively

Execute JavaScript on the client from server callbacks:

```python
from pulse import run_js
from pulse.transpiler import javascript

@javascript
def focus_element(selector: str):
    document.querySelector(selector).focus()

@javascript
def get_scroll_position():
    return {"x": window.scrollX, "y": window.scrollY}

# Fire-and-forget (no result)
def on_save():
    save_data()
    run_js(focus_element("#next-input"))

# With result (must await)
async def on_click():
    pos = await run_js(get_scroll_position(), result=True)
    print(pos["x"], pos["y"])
```

### Signature

```python
def run_js(
    expr: Expr,
    *,
    result: bool = False,
    timeout: float = 10.0,
) -> Future[Any] | None:
    """Execute JavaScript on the client.

    Args:
        expr: An Expr from calling a @javascript function.
        result: If True, returns a Future that resolves with the JS return value.
                If False (default), returns None (fire-and-forget).
        timeout: Maximum seconds to wait for result (default 10s, only applies when
                 result=True). Future raises asyncio.TimeoutError if exceeded.
    """
```

### Error Handling

```python
from pulse import run_js, JsExecError

@javascript
def risky_operation():
    raise Error("Something went wrong")

async def handle_action():
    try:
        result = await run_js(risky_operation(), result=True)
    except JsExecError as e:
        print(f"JS error: {e}")
```

### Requirements

- Must be called from a Pulse callback (event handler, effect, etc.)
- Cannot be called during render
- The `expr` argument must be from a `@javascript` function or `pulse.js` module

## `ps.call_api()` — API Calls Through Client Browser

Make fetch requests through the client's browser, useful for APIs that require browser cookies or credentials:

```python
# GET request (to your own API)
result = await ps.call_api("/api/users")

# POST with body
result = await ps.call_api(
    "/api/login",
    method="POST",
    body={"email": email, "password": password},
)

# External API with headers
result = await ps.call_api(
    "https://api.example.com/data",
    method="POST",
    headers={"Authorization": f"Bearer {token}"},
    body={"key": "value"},
)
```

### Signature

```python
async def call_api(
    path: str,
    *,
    method: str = "POST",
    headers: Mapping[str, str] | None = None,
    body: Any | None = None,
    credentials: Literal["omit", "same-origin", "include"] = "same-origin",
) -> dict[str, Any]:
    """Make an API call through the client browser.

    Args:
        path: URL path or full URL. Relative paths target the current origin.
        method: HTTP method (default: "POST").
        headers: Optional HTTP headers.
        body: Optional request body (JSON serialized).
        credentials: Fetch credential mode; defaults to "same-origin".

    Returns:
        dict with: ok (bool), status (int), headers (dict), body (parsed JSON)
    """
```

### Response Format

```python
result = await ps.call_api("/api/data")

if result["ok"]:
    data = result["body"]  # Parsed JSON
    print(f"Status: {result['status']}")
    print(f"Headers: {result['headers']}")
else:
    print(f"Request failed with status {result['status']}")
```

### Use Cases

- Call your FastAPI endpoints that need session cookies
- Access third-party APIs that require browser credentials
- Make requests that need to respect CORS from the client

## Set Cookies

```python
await ps.set_cookie(
    "auth_token",
    token_value,
    secure=True,
    samesite="strict",
    max_age_seconds=3600,
)
```

Pulse cookies are host-only. There is no cookie-domain option.

## Type Annotations

Event handler types for wrapped components:

```python
ps.EventHandler0              # () -> None
ps.EventHandler1[T]           # (T) -> None
ps.EventHandler2[T1, T2]      # (T1, T2) -> None
# ... up to EventHandler10
```

## Common Patterns

### Wrap Mantine Component

```python
@ps.react_component(ps.Import("TextInput", "@mantine/core"))
def TextInput(
    *children: ps.Node,
    label: str = "",
    placeholder: str = "",
    value: str = "",
    onChange: ps.EventHandler1[str] | None = None,
    error: str | None = None,
    disabled: bool = False,
) -> ps.Element: ...
```

### Chart Library

```python
@ps.react_component(
    ps.Import("LineChart", "recharts"),
    lazy=True,
)
def LineChart(
    *children: ps.Node,
    data: list[dict] = [],
    width: int = 400,
    height: int = 300,
) -> ps.Element: ...
```

### Client-Side Animation

Using the Web Animations API for smooth, hardware-accelerated animations:

```python
from pulse.js import Animation, KeyframeEffect, obj

@ps.javascript
def slide_in(element):
    """Slide an element in from the left with a fade."""
    effect = KeyframeEffect(
        element,
        [
            obj(opacity=0, transform="translateX(-20px)"),
            obj(opacity=1, transform="translateX(0)"),
        ],
        obj(duration=300, easing="ease-out", fill="forwards"),
    )
    animation = Animation(effect, document.timeline)
    animation.play()
    return animation  # Return so caller can await animation.finished
```

Or use React hooks for state-driven animations:

```python
@ps.javascript(jsx=True)
def AnimatedCounter(*, target: int):
    count, setCount = useState(0)

    def animate():
        if count < target:
            setTimeout(lambda: setCount(count + 1), 50)

    useEffect(animate, [count, target])

    return ps.span(className="counter")[str(count)]
```

### Local Storage

```python
@ps.javascript(jsx=True)
def PersistentInput():
    value, setValue = useState("")

    def loadSaved():
        saved = window.localStorage.getItem("input_value")
        if saved:
            setValue(saved)

    def save(newValue):
        setValue(newValue)
        window.localStorage.setItem("input_value", newValue)

    useEffect(loadSaved, [])

    return ps.input(
        value=value,
        onChange=lambda e: save(e.target.value),
    )
```

### Reading Clipboard on Paste

Serialized paste events include only `clipboardData` **metadata** (item kinds and MIME types) — never the pasted contents, so a server-side `onPaste` handler cannot read what was pasted. Read the clipboard client-side and forward the text to a Python callback prop:

```python
from pulse.js.react import useEffect, useRef

@ps.javascript(jsx=True)
def PasteCapture(*children, onPasteText):
    ref = useRef(None)

    def attach():
        def handle(event):
            text = event.clipboardData.getData("text/plain")
            if "\t" in text or "\n" in text:  # multi-cell paste → handle in Python
                event.preventDefault()
                onPasteText(text)
            # single values fall through to the browser default paste

        node = ref.current
        node.addEventListener("paste", handle, True)  # capture phase
        return lambda: node.removeEventListener("paste", handle, True)

    useEffect(attach, [])
    return ps.div(ref=ref)[children]

# Server side: onPasteText is a regular server callback receiving the text
PasteCapture(grid_inputs, onPasteText=state.apply_pasted_rows)
```

The capture-phase listener sees the paste before any nested input consumes it; only multi-value pastes are intercepted, so typing and single-value pastes keep native behavior.

## Limitations

- Transpiled code runs client-side only
- No Python standard library in transpiled code
- Limited Python syntax support (basic control flow, functions)
- Use `pulse.js` imports for browser APIs
- Complex logic should stay server-side

## See Also

- `channels.md` - Server-client bidirectional communication
- `dom.md` - HTML elements and events
