# Reactive Primitives

Low-level reactivity system. Most apps use `ps.State` which wraps these internally.

## Signal

Reactive value container. Reading tracks dependency, writing notifies observers.

```python
from pulse import Signal

count = Signal(0)

# Read (tracks dependency)
value = count()       # or count.read()
value = count.unwrap()  # alias

# Write (notifies observers)
count.write(5)

# Direct access without tracking
raw = count.value
```

**Constructor:** `Signal(initial_value, name=None)`

## Computed

Derived value, auto-recalculates when dependencies change. Lazy evaluation.

```python
from pulse import Signal, Computed

count = Signal(10)

doubled = Computed(lambda: count() * 2)

print(doubled())  # 20
count.write(5)
print(doubled())  # 10 (auto-recalculated)
```

**Constructor:** `Computed(fn, name=None)` — `fn` takes no args

**Rules:**
- Never write to signals inside computed
- Automatically tracks which signals are read
- Only recalculates when dirty and accessed

### `@ps.computed` decorator

On State methods:

```python
class Cart(ps.State):
    items: list[dict] = []

    @ps.computed
    def total(self) -> float:
        return sum(item["price"] * item["qty"] for item in self.items)
```

Standalone:

```python
signal = Signal(5)

@ps.computed
def doubled():
    return signal() * 2
```

## Effect

Runs function when dependencies change. For side effects (logging, API calls, subscriptions).

```python
from pulse import Signal, Effect

count = Signal(0)

def log_count():
    print(f"Count: {count()}")
    return lambda: print("Cleanup")  # Optional cleanup

effect = Effect(log_count)
# Prints: "Count: 0"

count.write(5)
# Prints: "Cleanup" then "Count: 5"

effect.dispose()  # Stop watching
```

**Constructor:**
```python
Effect(
    fn,                    # Function to run
    name=None,             # Debug name
    immediate=False,       # Run sync (not batched)
    lazy=False,            # Don't run on creation
    on_error=None,         # Exception callback
    deps=None,             # Explicit deps (disables auto-tracking)
    interval=None,         # Polling interval in seconds
)
```

**Methods:**
- `effect.run()` — Execute immediately
- `effect.schedule()` — Schedule in batch
- `effect.dispose()` — Cleanup and stop
- `effect.pause()` / `effect.resume()` — Pause/resume

### `@ps.effect` decorator

On State methods:

```python
class Tracker(ps.State):
    value: int = 0

    @ps.effect
    def on_change(self):
        print(f"Value: {self.value}")
        return lambda: print("Cleanup")

    @ps.effect(interval=5.0)
    async def poll(self):
        self.value = await api.fetch_value()
```

With options:

```python
@ps.effect(name="fetcher", lazy=True, interval=10.0)
async def fetch_data(self):
    self.data = await api.get_data()
```

## AsyncEffect

Async version of Effect. Cancels previous task when dependencies change.

```python
from pulse import Signal, AsyncEffect

user_id = Signal(1)

async def fetch_user():
    data = await api.get_user(user_id())
    print(f"Fetched: {data}")

effect = AsyncEffect(fetch_user)

# Change triggers cancellation of previous + new fetch
user_id.write(2)

# Wait for completion
await effect.wait()
```

**Properties:** `effect._task` — Current running task

## Batch

Group updates, run effects once at end.

```python
from pulse import Signal, Effect, Batch

a = Signal(0)
b = Signal(0)

# Without batch: effect runs twice
a.write(1)
b.write(2)

# With batch: effect runs once
with Batch():
    a.write(1)
    b.write(2)
# Effects run here
```

## Untrack

Read signals without creating dependency.

```python
from pulse import Signal, Effect, Untrack

count = Signal(0)
other = Signal(0)

def log():
    print(f"Count: {count()}")  # Creates dependency
    with Untrack():
        print(f"Other: {other()}")  # No dependency

Effect(log)
count.write(1)  # Triggers effect
other.write(1)  # Does NOT trigger effect
```

## Scope

Track dependencies created within context.

```python
from pulse import Signal, Scope

a = Signal(1)
b = Signal(2)

with Scope() as scope:
    _ = a()
    _ = b()

print(scope.deps)  # {a: epoch, b: epoch}
```

## Reactive Containers

### ReactiveDict

Dict with per-key reactivity.

```python
from pulse import ReactiveDict

data = ReactiveDict({"name": "Alice", "age": 30})

# Read (tracks dependency)
name = data["name"]
name = data.get("name", "default")

# Write (triggers re-render)
data["age"] = 31
data.set("age", 31)

# Iteration
for key in data.keys(): ...
for val in data.values(): ...
for k, v in data.items(): ...

# Unwrap to plain dict
plain = data.unwrap()
```

### ReactiveList

List with per-index reactivity.

```python
from pulse import ReactiveList

items = ReactiveList([1, 2, 3])

# Access
first = items[0]
length = len(items)

# Mutate
items.append(4)
items[0] = 10
items.pop()
items.insert(0, 0)
items.remove(2)

# Unwrap
plain = list(items)  # or items.unwrap()
```

### ReactiveSet

Set with per-element reactivity.

```python
from pulse import ReactiveSet

tags = ReactiveSet({"python", "web"})

# Access
has_python = "python" in tags
count = len(tags)

# Mutate
tags.add("react")
tags.remove("web")
tags.discard("missing")  # No error if missing

# Set operations
tags.union(other_set)
tags.intersection(other_set)
```

## Utility Functions

### `ps.reactive(value)`

Recursively wrap value in reactive container.

```python
data = ps.reactive({
    "users": [{"name": "Alice"}, {"name": "Bob"}],
    "settings": {"theme": "dark"},
})
# data is ReactiveDict
# data["users"] is ReactiveList
# data["users"][0] is ReactiveDict
```

### `ps.unwrap(value)`

Recursively unwrap reactive containers to plain Python.

```python
plain = ps.unwrap(reactive_data)
# Returns plain dict/list/set
```

## State Integration

`ps.State` uses these primitives internally. Each attribute is a `Signal`, `@ps.computed` creates `Computed`, `@ps.effect` creates `Effect`.

```python
class MyState(ps.State):
    count: int = 0  # Internally a Signal

    @ps.computed
    def doubled(self) -> int:  # Internally a Computed
        return self.count * 2

    @ps.effect
    def logger(self):  # Internally an Effect
        print(self.count)
```

Direct primitive use is rare—prefer `ps.State` for most cases.

## See Also

- `hooks.md` - Inline effects in components
- `state.md` - Effects and computed on State classes
- `queries.md` - Query-based data fetching
