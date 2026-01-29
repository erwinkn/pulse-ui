# Python-to-JavaScript Transpiler

Transpile Python functions to JavaScript for client-side execution.

## `@ps.javascript` Decorator

Mark Python functions for JS transpilation. Code runs in the browser, not on the server.

```python
@ps.javascript
def calculate(x: int, y: int) -> int:
    return x + y

# Transpiles to: function calculate_1(x, y) { return x + y; }
```

### JSX Mode

Use `jsx=True` for React components. Parameters become destructured props.

```python
@ps.javascript(jsx=True)
def ClientWidget(*, name: str, count: int = 0):
    return ps.div(className="widget")[
        ps.h1(f"Hello, {name}"),
        ps.span(f"Count: {count}"),
    ]

# Transpiles to:
# function ClientWidget_1({name, count = 0}) {
#   return <div className="widget"><h1>{`Hello, ${name}`}</h1>...</div>
# }
```

### When Code Runs

- `@ps.javascript` functions execute client-side in the browser
- Server-side Python code cannot call transpiled functions directly
- Use `run_js()` to invoke transpiled code from server callbacks (see js-interop.md)

## Import and DynamicImport

### Static Imports

Use `Import` for npm packages and local files.

```python
# Named export
useState = ps.Import("useState", "react")
useEffect = ps.Import("useEffect", "react")

# Default export
React = ps.Import("react")
lodash = ps.Import("lodash", kind="default")

# Namespace import (import * as X)
utils = ps.Import("*", "lodash")

# Side-effect import (CSS, etc.)
ps.Import("./styles.css", side_effect=True)
```

### Local Path Imports

Paths starting with `~/` resolve relative to project root. Relative paths (`./`, `../`) resolve from the calling file.

```python
# Project-relative (alias path)
MyComponent = ps.Import("MyComponent", "~/components/my-component")

# Relative to current file
utils = ps.Import("*", "./utils")
config = ps.Import("config", "../config")
```

Local imports auto-resolve JS extensions (`.ts`, `.tsx`, `.js`, `.jsx`).

### Lazy Loading

Use `lazy=True` for code-splitting. Creates a factory for `React.lazy`.

```python
from pulse.js.react import lazy, Suspense

# Create lazy-loaded component
LazyChart = lazy(ps.Import("LineChart", "recharts", lazy=True))

# Use with Suspense
@ps.component
def Dashboard():
    return Suspense(fallback=ps.div("Loading..."))[
        LazyChart(data=chart_data),
    ]
```

### Dynamic Imports

Use `import_` for runtime dynamic imports inside `@javascript` functions.

```python
from pulse.transpiler import import_

@ps.javascript
async def load_module():
    module = await import_("./heavy-module")
    return module.default

# Transpiles to: async function load_module_1() {
#   const module = await import("./heavy-module");
#   return module.default;
# }
```

## Supported Python Syntax

### Variables and Functions

```python
@ps.javascript
def example():
    # Variable declarations
    x = 10
    y: int = 20  # Type hints are ignored at runtime

    # Nested functions
    def helper(a, b):
        return a + b

    return helper(x, y)
```

### Control Flow

```python
@ps.javascript
def control_flow(x):
    # If/else
    if x > 0:
        result = "positive"
    elif x < 0:
        result = "negative"
    else:
        result = "zero"

    # While loops
    i = 0
    while i < 10:
        i += 1
        if i == 5:
            continue
        if i == 8:
            break

    # For loops (for-of in JS)
    total = 0
    for item in items:
        total += item

    # Tuple unpacking in loops
    for key, value in pairs:
        print(key, value)

    return result
```

### Ternary and Boolean Operators

```python
@ps.javascript
def expressions(x, y):
    # Ternary
    result = "yes" if x > 0 else "no"

    # Boolean operators (and/or become &&/||)
    both = x and y
    either = x or y

    # Comparisons (== becomes ===, != becomes !==)
    equal = x == y
    not_equal = x != y

    # Chained comparisons
    in_range = 0 < x < 10

    return result
```

### Subscript access

```python
@ps.javascript
def last(arr):
    return arr[-1]

# -> return arr[-1];
```

Negative indices are not rewritten. Use `.at(-1)` or `arr[arr.length - 1]` for array-last behavior.

### List and Dict Comprehensions

```python
@ps.javascript
def comprehensions():
    # List comprehension -> .map()
    squares = [x * x for x in range(10)]

    # With filter -> .filter().map()
    evens = [x for x in range(20) if x % 2 == 0]

    # Nested comprehensions -> .flatMap()
    pairs = [[i, j] for i in range(3) for j in range(3)]

    # Dict comprehension -> new Map()
    mapping = {k: v * 2 for k, v in items}

    # Set comprehension -> new Set()
    unique = {x % 5 for x in numbers}

    return squares
```

### F-Strings

F-strings become template literals.

```python
@ps.javascript
def greet(name, age):
    return f"Hello, {name}! You are {age} years old."
    # -> `Hello, ${name}! You are ${age} years old.`
```

Format specifiers are supported:

```python
@ps.javascript
def formatting():
    value = 3.14159
    formatted = f"{value:.2f}"    # -> value.toFixed(2)
    padded = f"{value:>10}"       # -> value.padStart(10, " ")
    hex_val = f"{255:#x}"         # -> "0x" + (255).toString(16)
```

### Lambda Functions

```python
@ps.javascript
def with_lambdas():
    double = lambda x: x * 2
    # -> const double = x => x * 2

    items.map(lambda x: x.upper())
    # -> items.map(x => x.toUpperCase())
```

### Async/Await

```python
@ps.javascript
async def fetch_data(url):
    response = await fetch(url)
    data = await response.json()
    return data
```

### Try/Except

```python
@ps.javascript
def safe_parse(text):
    try:
        return JSON.parse(text)
    except e:
        console.log(f"Parse error: {e}")
        return None
    finally:
        console.log("Done")
```

Note: Only single `except` clause supported (JS has one `catch`).

### Classes

```python
@ps.javascript
def with_class():
    # Python dict becomes JS Map
    mapping = {"a": 1, "b": 2}

    # Python set becomes JS Set
    unique = {1, 2, 3}

    # Use new for JS classes
    error = Error("Something went wrong")
    date = Date()
```

## Built-in JS Modules (pulse.js)

Access JavaScript globals via `pulse.js`:

```python
from pulse.js import Math, console, window, document, JSON, Intl, crypto
from pulse.js.date import Date
from pulse.js import (
    AbortController,
    Array,
    ArrayBuffer,
    Blob,
    CustomEvent,
    DOMParser,
    Error,
    File,
    FileReader,
    FormData,
    Headers,
    IntersectionObserver,
    Map,
    MutationObserver,
    Object,
    PerformanceObserver,
    Promise,
    Request,
    ResizeObserver,
    Response,
    Set,
    TextDecoder,
    TextEncoder,
    URL,
    URLSearchParams,
    Uint8Array,
    XMLSerializer,
)

@ps.javascript
def using_builtins():
    # Math
    x = Math.random()
    y = Math.floor(3.7)
    z = Math.max(1, 2, 3)

    # Console
    console.log("Debug message")
    console.error("Error!")

    # JSON
    text = JSON.stringify({"a": 1})
    obj = JSON.parse(text)

    # Date
    now = Date.now()
    d = Date()
    iso = d.toISOString()

    # Window/Document
    window.alert("Hello")
    el = document.getElementById("app")
    window.localStorage.setItem("key", "value")

    # Timers
    setTimeout(lambda: console.log("delayed"), 1000)
    interval_id = setInterval(lambda: console.log("tick"), 500)
    clearInterval(interval_id)

    # Promise
    Promise.resolve(42).then(lambda x: console.log(x))
```

### Object Literals

Python dicts transpile to `Map`. Use `obj()` for plain JS objects:

```python
from pulse.js import obj

@ps.javascript
def create_config():
    # Plain JS object (not Map)
    return obj(
        name="config",
        nested=obj(a=1, b=2),
        items=[1, 2, 3],
    )
    # -> { name: "config", nested: { a: 1, b: 2 }, items: [1, 2, 3] }
```

### Python Builtins

Many Python builtins transpile automatically:

| Python | JavaScript |
|--------|------------|
| `print(x)` | `console.log(x)` |
| `len(x)` | `x.length ?? x.size` |
| `str(x)` | `String(x)` |
| `int(x)` | `parseInt(x)` |
| `float(x)` | `parseFloat(x)` |
| `bool(x)` | `Boolean(x)` |
| `list(x)` | `Array.from(x)` |
| `range(n)` | `Array.from(new Array(n).keys())` |
| `abs(x)` | `Math.abs(x)` |
| `min/max` | `Math.min/max` |
| `round(x)` | `Math.round(x)` |
| `sum(xs)` | `xs.reduce((a,b) => a+b, 0)` |
| `sorted(xs)` | `xs.slice().sort(...)` |
| `reversed(xs)` | `xs.slice().reverse()` |
| `enumerate(xs)` | `xs.map((v,i) => [i, v])` |
| `zip(a, b)` | `Array.from(...)` |
| `map(fn, xs)` | `xs.map(fn)` |
| `filter(fn, xs)` | `xs.filter(fn)` |
| `any(xs)` | `xs.some(v => v)` |
| `all(xs)` | `xs.every(v => v)` |

### String Methods

```python
@ps.javascript
def string_ops(s):
    s.lower()        # -> s.toLowerCase()
    s.upper()        # -> s.toUpperCase()
    s.strip()        # -> s.trim()
    s.split()        # -> s.trim().split(/\s+/)
    s.split(",")     # -> s.split(",")
    s.replace(a, b)  # -> s.replaceAll(a, b)
    s.startswith(x)  # -> s.startsWith(x)
    s.find(x)        # -> s.indexOf(x)
    ",".join(items)  # -> items.join(",")
```

### List Methods

```python
@ps.javascript
def list_ops(lst):
    lst.append(x)    # -> (lst.push(x), undefined)[1]
    lst.pop()        # -> lst.pop()
    lst.pop(0)       # -> lst.splice(0, 1)[0]
    lst.insert(i, x) # -> (lst.splice(i, 0, x), undefined)[1]
    lst.index(x)     # -> lst.indexOf(x)
    lst.copy()       # -> lst.slice()
```

### Dict Methods (Map)

```python
@ps.javascript
def dict_ops(d):
    d.get(k, default)  # -> d.get(k) ?? default
    d.keys()           # -> [...d.keys()]
    d.values()         # -> [...d.values()]
    d.items()          # -> [...d.entries()]
    d.copy()           # -> new Map(d.entries())
```

## Transpiler Limitations

### No Python Standard Library

The transpiler does not support Python's stdlib. You cannot use:

```python
@ps.javascript
def bad():
    import os            # Error: module not registered
    import datetime      # Error: use pulse.js.date.Date instead
    import re            # Error: use JS RegExp
```

Use `pulse.js` equivalents or `Import` for npm packages.

### No Complex Python Features

The following are not supported:

- **Generators**: `yield`, `yield from`
- **Decorators inside `@javascript`**: Cannot decorate nested functions
- **Context managers**: `with` statements
- **Match statements**: `match`/`case`
- **Multiple inheritance**: Only single inheritance
- **Metaclasses**: Not supported
- **`*args` in calls**: Spread `*` in function calls not supported
- **Walrus operator**: `:=` assignment expressions

### Type Hints Ignored

Type hints are parsed but ignored at runtime:

```python
@ps.javascript
def typed(x: int, y: str) -> bool:
    # Types have no effect on transpiled output
    return x > 0
```

### Operator Differences

- `==` becomes `===` (strict equality)
- `!=` becomes `!==`
- `is` becomes `===` (except `is None` -> `== null`)
- `and`/`or` become `&&`/`||`
- `not` becomes `!`
- `//` (floor div) becomes `Math.floor(a / b)`

### Dict vs Object

Python dicts transpile to `Map`, not plain objects:

```python
@ps.javascript
def dict_behavior():
    d = {"a": 1}      # -> new Map([["a", 1]])
    d["a"]            # -> d.get("a")
    d["a"] = 2        # -> d.set("a", 2)

    # For plain objects, use obj()
    from pulse.js import obj
    o = obj(a=1)      # -> { a: 1 }
```

## Debugging Transpiled Code

### View Transpiled Output

The transpiler generates named functions with unique IDs:

```python
@ps.javascript
def my_function():
    return 42

# Generates: function my_function_1() { return 42; }
```

### Error Messages

Transpile errors include source location:

```
TranspileError: Unsupported statement: Match
in my_function at /path/to/file.py:15:4
    match x:
    ^
```

### Common Errors

**"Unbound name referenced"**
```python
@ps.javascript
def bad():
    return unknown_var  # Error: unknown_var not in scope
```
Fix: Import the dependency or define it.

**"Cannot resolve module"**
```python
@ps.javascript
def bad():
    import some_module  # Error if not registered
```
Fix: Use `Import` for npm packages or register the module.

**"Spread (**expr) not supported"**
```python
@ps.javascript
def bad():
    fn(**kwargs)  # Error: spread kwargs not supported
```
Fix: Pass arguments explicitly.

**"Multiple except clauses not supported"**
```python
@ps.javascript
def bad():
    try:
        risky()
    except ValueError:
        pass
    except TypeError:  # Error: JS only has one catch
        pass
```
Fix: Use single `except` and check error type inside.

### Dependencies

Transpiled functions track dependencies automatically:

```python
helper = ps.Import("helper", "./utils")

@ps.javascript
def main():
    return helper()  # helper is a dependency

# Both helper import and main function are emitted
```

## See Also

- `js-interop.md` - `run_js()`, `@ps.react_component`, `Import` details
- `dom.md` - HTML elements for JSX mode
- `channels.md` - Server-client communication
