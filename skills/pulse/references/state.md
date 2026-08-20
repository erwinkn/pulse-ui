# State Management

Reactive state classes with computed properties and effects.

## `ps.State` Base Class

Define state with type-annotated attributes. Attributes become reactive (trigger re-renders on change).

```python
class CounterState(ps.State):
    count: int = 0
    name: str = "Counter"

    def increment(self):
        self.count += 1
```

### Reactive vs Non-Reactive Attributes

```python
class MyState(ps.State):
    # Reactive - triggers re-renders
    count: int = 0
    items: list[str] = []

    # Non-reactive - private attributes
    _cache: dict = {}  # Underscore prefix = not reactive

    def __init__(self):
        self._internal = "private"  # Also not reactive
```

**Rules:**
- Public type-annotated attributes become reactive
- Private attributes (underscore prefix) stay plain Python
- Cannot add new public attributes after init (raises `AttributeError`)
- Annotate a field as `ps.QueryParam[T]` to two-way sync it with a URL query parameter (see `routing.md`)

### Constructor Arguments

```python
class FormState(ps.State):
    value: str = ""
    submitted: bool = False

    def __init__(self, initial: str, readonly: bool = False):
        self.value = initial
        self._readonly = readonly  # Private, non-reactive
```

## `@ps.computed` on State Methods

Derived values that auto-update when dependencies change. Cached until dependencies change.

```python
class CartState(ps.State):
    items: list[dict] = []
    tax_rate: float = 0.1

    @ps.computed
    def subtotal(self) -> float:
        return sum(item["price"] * item["qty"] for item in self.items)

    @ps.computed
    def total(self) -> float:
        return self.subtotal * (1 + self.tax_rate)
```

**Rules:**
- Read-only (cannot assign to computed properties)
- Only recalculates when dependencies change
- Dependencies tracked automatically
- Can depend on other computed properties
- Each instance caches one computed per descriptor; fresh same-name subclass descriptors get separate entries, including through `super()`
- Assigning one descriptor object to multiple members or classes raises `TypeError`; create a fresh descriptor for each member
- Descriptors must be defined in the class body; assigning one to an existing State class raises `TypeError`

### When to Use

- Derived values from other state
- Expensive calculations you want cached
- Values used in multiple places

## `@ps.effect` on State Methods

Side effects that run when dependencies change.

```python
class TrackerState(ps.State):
    query: str = ""
    results: list[dict] = []

    @ps.effect
    def log_query(self):
        print(f"Query changed: {self.query}")

    @ps.effect
    async def fetch_results(self):
        if self.query:
            self.results = await api.search(self.query)
```

### Cleanup Pattern

Return a cleanup function from effects:

```python
class SubscriptionState(ps.State):
    channel: str = "default"

    @ps.effect
    def subscribe(self):
        unsub = event_bus.subscribe(self.channel, self.handle_event)
        return unsub  # Called before next run or disposal

    def handle_event(self, data):
        print(f"Received: {data}")
```

### Effect Options

```python
@ps.effect(
    immediate=True,      # Run sync instead of batched (sync only)
    lazy=True,           # Don't run on creation
    interval=5.0,        # Re-run every N seconds (polling)
)
def my_effect(self):
    pass
```

### Async Effects

```python
class DataState(ps.State):
    user_id: int = 1
    user: dict | None = None

    @ps.effect
    async def load_user(self):
        self.user = await api.get_user(self.user_id)
```

Async effects auto-cancel previous task when dependencies change.

## `@ps.global_state` Decorator

Create session-wide state shared across components. The instance is scoped to the
render session (one browser tab) and disposed when it closes — never shared
across tabs or users. Use `ps.session()` to coordinate a single user's tabs.

```python
@ps.global_state
class AppSettings(ps.State):
    theme: str = "light"
    language: str = "en"

# Usage in any component
settings = AppSettings()
settings.theme = "dark"  # Changes reflect everywhere
```

### With Constructor Arguments

```python
@ps.global_state
class UserCache(ps.State):
    data: dict = {}

    def __init__(self, user_id: str):
        self._user_id = user_id

# Call with args - first call creates, subsequent calls return same instance
cache = UserCache(user_id="123")
```

### ID-Based Instances

Keep one instance per entity, within the session:

```python
session_counter = ps.global_state(CounterState)
room_counter = ps.global_state(CounterState)

# One instance for the whole session (no id)
a = session_counter(label="Session")

# One instance per id
b = room_counter("room-1", label="Room")  # Distinct from...
c = room_counter("room-2", label="Room")  # ...this one
```

`id` is a keying discriminator *within* the session, not a scope switch: two
tabs (or two users) never see each other's instances. Cross-user shared state is
not supported.

### Factory Function

```python
def create_config() -> ConfigState:
    state = ConfigState()
    state.load_defaults()
    return state

get_config = ps.global_state(create_config)

# Usage
config = get_config()
```

The default accessor identity is the factory module plus qualified name. Factories created repeatedly from the same lexical definition need unique, non-empty keys:

```python
def make_config_accessor(namespace: str):
    def create_config() -> ConfigState:
        state = ConfigState()
        state.load_defaults()
        return state

    return ps.global_state(create_config, key=f"config:{namespace}")

tenant_config = make_config_accessor("tenant")
admin_config = make_config_accessor("admin")
```

## State Lifecycle

### Creation with `ps.init`

```python
@ps.component
def MyComponent():
    with ps.init():
        state = MyState()  # Created once, persists across renders

    return ps.div(str(state.count))
```

Variables inside `ps.init()` persist across re-renders. Use `key=` when the init block depends on an input and should run again when that input changes.

```python
@ps.component
def UserComponent(user_id: str):
    with ps.init(key=user_id):
        state = MyState(user_id)

    return ps.div(str(state.count))
```

`ps.init()` owns states and effects created inside its block. It disposes them before re-running for a new key, if initialization raises, and when the component unmounts. `ps.setup()` applies the same rules to its initializer and `ps.setup_key()`.

States passed into an initializer or obtained through `ps.state()` / `ps.global_state()` keep their existing owners. Accessing a shared state does not tie it to the initializer's lifetime.

### Creation with `ps.state`

For inline state with caching by callsite:

```python
@ps.component
def Counter():
    state = ps.state(CounterState())  # Cached by code location
    return ps.button(str(state.count), onClick=state.increment)
```

With explicit key for loops:

```python
@ps.component
def ItemList():
    with ps.init():
        items = ["a", "b", "c"]

    for item in items:
        # key= required in loops to disambiguate
        item_state = ps.state(lambda: ItemState(item), key=item)
        # ...
```

### Disposal

Component-owned state is disposed when its owning hook is replaced or the component unmounts. Global state remains alive until its render session closes. A state owns the resources (effects, nested states) created in its constructor, plus any unowned resource assigned to one of its attributes later (e.g. `self._poller = Effect(...)` from an event handler); disposing the state disposes them all. Assigning over an owned resource disposes the replaced one. Override `on_dispose()` for cleanup beyond that (`dispose()` itself cannot be overridden):

```python
class ConnectionState(ps.State):
    _conn: Connection | None = None

    def connect(self):
        self._conn = create_connection()

    def on_dispose(self):
        if self._conn:
            self._conn.close()
```

### Manual Disposal

```python
state = MyState()
# ... use state ...
state.dispose()  # Clean up effects and resources
```

## Introspection Methods

Access underlying reactive primitives:

```python
state = MyState()

# Iterate reactive properties (Signals)
for signal in state.properties():
    print(signal.name, signal.value)

# Iterate computed properties
for computed in state.computeds():
    print(computed.name, computed.read())

# Iterate effects
for effect in state.effects():
    print(effect.name)
```

## Best Practices

### Structuring State Classes

```python
# Group related state together
class FormState(ps.State):
    # Data fields
    email: str = ""
    password: str = ""
    remember: bool = False

    # UI state
    is_submitting: bool = False
    error: str | None = None

    # Computed
    @ps.computed
    def is_valid(self) -> bool:
        return len(self.email) > 0 and len(self.password) >= 8

    # Actions
    async def submit(self):
        self.is_submitting = True
        self.error = None
        try:
            await api.login(self.email, self.password)
        except Exception as e:
            self.error = str(e)
        finally:
            self.is_submitting = False
```

### State vs Simple Primitives

**Use `ps.State` when:**
- Multiple related values
- Need computed properties
- Need effects for side effects
- Complex update logic (methods)
- Shared across components

**Use `ps.Signal` when:**
- Single independent value
- Simple counter or toggle
- Temporary UI state

```python
# Simple: Signal
@ps.component
def Toggle():
    with ps.init():
        show = ps.Signal(False)

    return ps.button(
        "Show" if not show() else "Hide",
        onClick=lambda: show.write(not show()),
    )

# Complex: State
@ps.component
def UserProfile():
    with ps.init():
        state = UserProfileState()

    return ps.div(...)
```

### Form Patterns

```python
class TodoForm(ps.State):
    text: str = ""
    items: list[str] = []

    def update_text(self, value: str):
        self.text = value

    def add(self):
        if self.text.strip():
            self.items.append(self.text.strip())
            self.text = ""

    def remove(self, index: int):
        if 0 <= index < len(self.items):
            self.items.pop(index)

@ps.component
def TodoApp():
    with ps.init():
        state = TodoForm()

    return ps.div(
        ps.input(
            value=state.text,
            onChange=lambda e: state.update_text(e["target"]["value"]),
        ),
        ps.button("Add", onClick=state.add),
        ps.ul(
            ps.For(
                state.items,
                lambda item, idx: ps.li(
                    item,
                    ps.button("x", onClick=lambda: state.remove(idx)),
                    key=f"{idx}-{item}",
                ),
            ),
        ),
    )
```

### List State Patterns

```python
class ListState(ps.State):
    items: list[dict] = []

    def add(self, item: dict):
        self.items.append(item)

    def remove(self, item_id: str):
        self.items = [i for i in self.items if i["id"] != item_id]

    def update(self, item_id: str, **updates):
        for item in self.items:
            if item["id"] == item_id:
                item.update(updates)
                break
        # Trigger reactivity by reassigning
        self.items = list(self.items)
```

### Async Data Patterns

For async data fetching, prefer `@ps.query` (see queries reference):

```python
class UserState(ps.State):
    user_id: int = 1

    @ps.query
    async def user(self) -> dict:
        return await api.get_user(self.user_id)

    @user.key
    def _user_key(self):
        return ("user", self.user_id)
```

For simple cases, effects work:

```python
class DataState(ps.State):
    query: str = ""
    data: list = []
    loading: bool = False
    error: str | None = None

    @ps.effect
    async def fetch(self):
        if not self.query:
            self.data = []
            return

        self.loading = True
        self.error = None
        try:
            self.data = await api.search(self.query)
        except Exception as e:
            self.error = str(e)
        finally:
            self.loading = False
```

## See Also

- `hooks.md` - ps.init, ps.state, and inline effects
- `reactive.md` - Low-level Signal, Computed, Effect primitives
- `queries.md` - @ps.query for async data fetching
