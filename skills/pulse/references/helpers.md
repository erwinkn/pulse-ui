# Helper Utilities

Scheduling, styling, serialization, and type utilities.

## ps.later()

Schedule a function to run after a delay.

```python
handle = ps.later(delay, fn, *args, **kwargs)
```

**Parameters:**
- `delay: float` - Seconds to wait
- `fn` - Sync or async function
- `*args, **kwargs` - Arguments passed to fn

**Returns:** `asyncio.TimerHandle` with `.cancel()` method

`ps.later()` callbacks are not canceled by route unmounting. They run unless you
cancel the returned handle or the render session/app closes. If a later callback
calls `ps.navigate()`, that navigation is route-bound by default and is ignored
after the source route has unmounted; use `force=True` only for intentionally
global navigation.

```python
# Delayed cleanup
def cleanup():
    print("Cleaning up...")

handle = ps.later(5.0, cleanup)

# Cancel if needed
handle.cancel()
```

Async functions are awaited automatically:

```python
async def save_draft():
    await api.save(draft)

ps.later(2.0, save_draft)  # Runs as task after 2s
```

**Note:** Callbacks run outside reactive scope (via `Untrack()`), so they won't create dependencies.

## ps.repeat()

Run a function repeatedly at an interval.

```python
handle = ps.repeat(interval, fn, *args, **kwargs)
```

**Parameters:**
- `interval: float` - Seconds between runs
- `fn` - Sync or async function
- `*args, **kwargs` - Arguments passed to fn

**Returns:** `RepeatHandle` with `.cancel()` method

```python
class DashboardState(ps.State):
    data: dict | None = None

    def __init__(self):
        # Poll every 30 seconds
        self._poll = ps.repeat(30.0, self.refresh)

    async def refresh(self):
        self.data = await api.fetch_metrics()

    def on_dispose(self):
        self._poll.cancel()
```

For async functions, waits for completion before starting next interval:

```python
async def slow_task():
    await asyncio.sleep(3)  # Takes 3s
    print("Done")

# With interval=5: runs at t=5, t=13 (5+3+5), t=21, etc.
ps.repeat(5.0, slow_task)
```

**Note:** Prefer `@ps.effect(interval=...)` for polling within State classes:

```python
class AutoRefresh(ps.State):
    data: list = []

    @ps.effect(interval=10.0)
    async def poll(self):
        self.data = await api.fetch()
```

## ps.CSSProperties

Type alias for inline styles. Accepts any CSS property as string key.

```python
CSSProperties = dict[str, Any]
```

```python
@ps.component
def Card():
    style: ps.CSSProperties = {
        "backgroundColor": "#fff",
        "padding": "16px",
        "borderRadius": "8px",
        "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
    }
    return ps.div(style=style, children="Content")
```

Use camelCase for CSS properties (same as React):

```python
# Correct
{"backgroundColor": "red", "fontSize": "14px"}

# Wrong
{"background-color": "red", "font-size": "14px"}
```

Numeric values for pixel properties:

```python
{"width": 100, "padding": 16}  # Becomes "100px", "16px"
```

## Serialization

### ps.serialize()

Convert Python values to Pulse's version 5 JSON-compatible wire format.

```python
serialized = ps.serialize(data)
```

Supported values include `None`, booleans, strings, finite floats, safe integers, lists,
tuples, string-keyed dictionaries, `ps.WireMap`, sets, dataclasses, dates, and
aware datetimes. Arbitrary objects require an adapter.

```python
from datetime import datetime, timezone

data = {
    "user": "alice",
    "created": datetime(2026, 7, 16, 12, 30, tzinfo=timezone.utc),
    "tags": {"admin", "user"},
    "items": [1, 2, 3],
}

wire = ps.serialize(data)
# Ready for JSON transport
```

Dates become midnight UTC timestamps. Dates and datetimes become JavaScript
`Date`; values coming back always become aware UTC `datetime`. Datetimes must be
aware and have exact millisecond precision. `NaN` becomes `None`; infinity,
negative zero, unsafe integers, invalid Unicode, and non-string keys fail.
Shared references and cycles are preserved.

### ps.deserialize()

Reconstruct Python values from wire format.

```python
data = ps.deserialize(serialized)
```

```python
original = {
    "items": [1, 2],
    "timestamp": datetime(2026, 7, 16, 12, 30, tzinfo=timezone.utc),
}
wire = ps.serialize(original)
restored = ps.deserialize(wire)
# restored["timestamp"] is datetime (UTC-aware)
```

### Custom values

Configure adapters on an app-owned serializer:

```python
from decimal import Decimal
import pulse as ps

decimal_adapter = ps.SerializerAdapter(
    type=Decimal,
    serialize=str,
)

app = ps.App(
    routes=[...],
    serializer=ps.Serializer([decimal_adapter]),
)
```

Adapters are one-way projections. Decoding returns the projected value, not the
original class. Classes that own their wire projection can subclass
`ps.PulseSerializable` and implement `to_pulse()`.

## Event Handler Types

Type aliases for callbacks with varying argument counts. Useful for typing component props.

```python
EventHandler0 = Callable[[], Any]
EventHandler1[T] = Callable[[], Any] | Callable[[T], Any]
EventHandler2[T1, T2] = ... | Callable[[T1, T2], Any]
# ... up to EventHandler10
```

```python
from pulse import EventHandler1, MouseEvent

def MyButton(
    label: str,
    onClick: EventHandler1[MouseEvent] | None = None,
):
    return ps.button(label, onClick=onClick)

# All valid:
MyButton("Click", onClick=lambda: print("clicked"))
MyButton("Click", onClick=lambda e: print(e["clientX"]))
```

The union types allow handlers to accept 0 to N arguments:

```python
# EventHandler2[str, int] accepts:
lambda: ...           # 0 args
lambda name: ...      # 1 arg
lambda name, idx: ... # 2 args
```

## Internal Utilities

These are used internally but available if needed:

### RepeatHandle

```python
class RepeatHandle:
    task: asyncio.Task | None
    cancelled: bool

    def cancel(self) -> None: ...
```

### Disposable

Base class for objects with cleanup:

```python
class Disposable(ABC):
    __disposed__: bool = False

    @abstractmethod
    def dispose(self) -> None: ...
```

Subclasses get automatic double-dispose protection in dev mode.

## See Also

- `reactive.md` - Effect with interval option
- `state.md` - State lifecycle and disposal
- `hooks.md` - ps.init and ps.setup
