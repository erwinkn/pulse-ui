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

### Lazy Loading

```python
@ps.react_component(
    ps.Import("HeavyChart", "chart-library"),
    lazy=True,  # Code-split, load on demand
)
def Chart(...) -> ps.Element: ...
```

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

## Run JavaScript Imperatively

Execute JS from server code:

```python
# Run expression, get result
result = await ps.run_js("window.innerWidth")

# Run statement
await ps.run_js("console.log('Hello from server')")

# With arguments
await ps.run_js(
    "document.getElementById(id).scrollIntoView()",
    id="target-element",
)
```

## API Calls from Server

Make fetch requests to external APIs:

```python
response = await ps.call_api(
    "https://api.example.com/data",
    method="POST",
    headers={"Authorization": "Bearer token"},
    body={"key": "value"},
)
# response is dict from JSON
```

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
