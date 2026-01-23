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

# Default export
ps.Import("DatePicker", "react-datepicker", kind="default")

# Local file
ps.Import("MyComponent", "~/components/my-component", kind="default")
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
    ps.Import("DatePicker", "react-datepicker", kind="default"),
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
from pulse.js import Math, console, window, document, JSON
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
    credentials: str = "include",
) -> dict[str, Any]:
    """Make an API call through the client browser.

    Args:
        path: URL path or full URL. Relative paths are resolved against server address.
        method: HTTP method (default: "POST").
        headers: Optional HTTP headers.
        body: Optional request body (JSON serialized).
        credentials: Credential mode - "include" (default) or "omit".

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
    domain=".example.com",
    secure=True,
    samesite="strict",
    max_age_seconds=3600,
)
```

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

## Limitations

- Transpiled code runs client-side only
- No Python standard library in transpiled code
- Limited Python syntax support (basic control flow, functions)
- Use `pulse.js` imports for browser APIs
- Complex logic should stay server-side

## See Also

- `channels.md` - Server-client bidirectional communication
- `dom.md` - HTML elements and events
