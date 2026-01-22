# Hooks

Functions for preserving state, running setup code, and managing side effects across renders.

## ps.init()

Context manager for one-time initialization. Variables assigned inside persist across re-renders.

```python
@ps.component
def Counter():
    with ps.init():
        state = CounterState()
        config = load_config()
        expensive = compute_initial_value()

    # state, config, expensive retain values on re-render
    return ps.div(f"Count: {state.count}")
```

**Rules:**
- Only at top level of component (not in `if`, `for`, nested functions)
- No control flow inside block (no `if`, `for`, `while`, `try`, `with`, `match`)
- No `as` binding (`with ps.init() as ctx:` not allowed)
- Only once per component

**Inside vs Outside:**
```python
@ps.component
def Example():
    with ps.init():
        # Runs once on first render:
        state = MyState()
        initial_data = fetch_data()

    # Runs every render:
    current_time = time.time()
    formatted = f"Count: {state.count}"

    return ps.div(formatted)
```

**Multiple inits are not allowed:**
```python
@ps.component
def Bad():
    with ps.init():
        state1 = StateA()
    with ps.init():  # Error! Only one ps.init() per component
        state2 = StateB()
```

Put all initialization in one block:
```python
@ps.component
def Good():
    with ps.init():
        state1 = StateA()
        state2 = StateB()
    return ps.div(...)
```

**Notes:**
- Uses AST rewriting via `@ps.component` decorator
- If source unavailable (some deployments), use `ps.setup()` instead

## ps.setup()

Lower-level one-time setup. No AST magic, works everywhere.

**Signature:** `ps.setup(fn, *args, **kwargs) -> T`

```python
@ps.component
def Editor():
    def init():
        config = load_config()
        return EditorState(config)

    state = ps.setup(init)
    return ps.div(state.content)
```

**With arguments:**
```python
def create_connection(host, port):
    return DatabaseConnection(host, port)

@ps.component
def Dashboard():
    conn = ps.setup(create_connection, "localhost", port=5432)
    return ps.div(...)
```

Arguments are tracked via reactive signals. Changes update the signals but don't re-run setup.

**Cleanup via return value:**
```python
def init_with_cleanup():
    ws = WebSocket("ws://server")
    ws.connect()
    # Cleanup happens when component unmounts
    return ws  # If ws has dispose(), it's called

state = ps.setup(init_with_cleanup)
```

**ps.setup_key() for re-initialization:**
```python
@ps.component
def UserProfile(user_id: str):
    ps.setup_key(user_id)  # Re-runs setup when user_id changes
    data = ps.setup(lambda: fetch_user(user_id))
    return ps.div(data.name)
```

**When to use ps.setup() vs ps.init():**
- Use `ps.init()` for simple variable assignment (cleaner syntax)
- Use `ps.setup()` when:
  - Source code unavailable in deployment
  - Need explicit cleanup logic
  - Need re-initialization via key
  - Complex initialization with conditionals

## ps.state()

Inline state instances persisted across renders.

**Signature:** `ps.state(factory, *, key=None) -> State`

```python
@ps.component
def Counter():
    counter = ps.state(lambda: CounterState())
    # Or pass instance directly:
    # counter = ps.state(CounterState())
    return ps.button(f"Count: {counter.count}", onClick=counter.increment)
```

Multiple states at different locations work automatically:
```python
@ps.component
def Dashboard():
    stats = ps.state(StatsState())       # Location A
    settings = ps.state(SettingsState()) # Location B - different state
    return ps.div(...)
```

**CRITICAL: key parameter for loops:**
```python
@ps.component
def UserList():
    with ps.init():
        user_ids = ["alice", "bob", "charlie"]

    items = []
    for user_id in user_ids:
        # Key required! Same code location runs multiple times
        user = ps.state(lambda uid=user_id: UserState(uid), key=user_id)
        items.append(ps.li(user.name, key=user_id))

    return ps.ul(*items)
```

Without `key`, you get:
```
RuntimeError: `pulse.state` can only be called once per component render
at the same location. Use the `key` parameter to disambiguate.
```

**Factory with captured variables:**
```python
# Use default arg to capture loop variable
for item_id in items:
    state = ps.state(lambda id=item_id: ItemState(id), key=item_id)
```

**Dynamic key for reset behavior:**
```python
@ps.component
def UserProfile(user_id: int):
    # State recreated when user_id changes
    state = ps.state(lambda: UserState(user_id), key=f"user-{user_id}")
    return ps.div(f"User: {state.name}")
```

Old state is disposed, fresh state created when key changes.

**Conditional states:**
```python
@ps.component
def ConditionalDemo():
    with ps.init():
        show = ps.Signal(True)

    if show():
        counter = ps.state(CounterState())  # Cached even when hidden
    else:
        counter = None

    return ps.div(
        ps.button("Toggle", onClick=lambda: show.write(not show())),
        counter and ps.span(f"Count: {counter.count}"),
    )
```

States in conditionals are not disposed when condition becomes false - they remain cached.

## ps.stable()

Stable reference wrapper that always delegates to the latest value.

```python
@ps.component
def Editor(on_save):
    # Problem: EditorState captures old on_save
    with ps.init():
        state = EditorState(on_save)  # on_save may change!
```

Fix with `ps.stable()`:
```python
@ps.component
def Editor(on_save):
    # on_save_ref always calls latest on_save
    on_save_ref = ps.stable("on_save", on_save)

    with ps.init():
        state = EditorState(on_save_ref)  # Safe!
    return ps.div(...)
```

**Signature:** `ps.stable(key, value?) -> wrapper`

- With value: Updates stored value, returns wrapper
- Without value: Returns existing wrapper (raises if not found)

**For callbacks (performance):**
```python
@ps.component
def ItemList():
    with ps.init():
        state = ListState()

    # Without stable: new function every render
    # With stable: same reference, prevents child re-renders
    handle_select = ps.stable("select", lambda id: state.select(id))

    return ps.For(
        state.items,
        lambda item, _: ItemRow(item, on_select=handle_select),
    )
```

**For non-functions:**
```python
config_ref = ps.stable("config", current_config)
value = config_ref()  # Call to get current value
```

## Inline @ps.effect

Effects inside component functions. Auto-registered during render.

```python
@ps.component
def Logger():
    with ps.init():
        state = LogState()

    @ps.effect
    def log_changes():
        print(f"Value: {state.value}")
        return lambda: print("Cleanup")  # Optional cleanup

    return ps.div(...)
```

**key parameter for loops:**
```python
@ps.component
def ItemLogger():
    with ps.init():
        items = ["a", "b", "c"]

    for item in items:
        @ps.effect(key=item)  # Required in loops!
        def log_item(item=item):  # Capture via default arg
            print(f"Item: {item}")

    return ps.div(...)
```

**Disposal on conditional false:**
```python
@ps.component
def ConditionalEffect():
    with ps.init():
        show = ps.Signal(True)

    if show():
        @ps.effect(immediate=True)
        def active_effect():
            print("Effect running")
            return lambda: print("Effect disposed")
    # When show() becomes False, effect is disposed
    # When show() becomes True again, new effect created

    return ps.button("Toggle", onClick=lambda: show.write(not show()))
```

Unlike `ps.state()`, effects ARE disposed when their conditional becomes false.

**Effect options:**
```python
@ps.effect(
    immediate=True,    # Run sync (not batched)
    lazy=True,         # Don't run on creation
    interval=5.0,      # Polling interval in seconds
    key="unique-key",  # For loops/dynamic creation
)
def my_effect():
    ...
```

**Dynamic key for effect recreation:**
```python
@ps.component
def VersionedEffect():
    with ps.init():
        version = ps.Signal("v1")

    @ps.effect(key=version())  # Effect recreated when version changes
    def versioned():
        print(f"Running version: {version()}")
        return lambda: print(f"Disposing: {version()}")

    return ps.button("New Version", onClick=lambda: version.write("v2"))
```

## Hook Rules

**Must be called during render:**
```python
# Good
@ps.component
def Good():
    state = ps.state(MyState())  # During render
    return ps.div(...)

# Bad
def handler():
    state = ps.state(MyState())  # Error! Not during render
```

**Order consistency:**
Hooks track state by call order/location. Don't change which hooks run:
```python
# Bad - hooks depend on condition
@ps.component
def Bad(show_extra: bool):
    state1 = ps.state(State1())
    if show_extra:
        state2 = ps.state(State2())  # Inconsistent!
    return ps.div(...)
```

**Key requirements in loops:**
```python
# Always use key in loops
for item in items:
    # ps.state needs key
    state = ps.state(lambda: ItemState(), key=item.id)

    # @ps.effect needs key
    @ps.effect(key=item.id)
    def track(item=item):
        print(item)
```

## Summary Table

| Hook | Purpose | Runs | Key Support |
|------|---------|------|-------------|
| `ps.init()` | Preserve variables | Once | No |
| `ps.setup()` | One-time setup with cleanup | Once (re-run with setup_key) | Via setup_key() |
| `ps.state()` | Inline state instances | Factory once | Yes |
| `ps.stable()` | Stable callback/value refs | Every render (updates ref) | Yes (the first arg) |
| `@ps.effect` | Side effects | On deps change | Yes |

## See Also

- `state.md` - State class with computed and effects
- `reactive.md` - Low-level reactive primitives
- `queries.md` - Query hooks for data fetching
