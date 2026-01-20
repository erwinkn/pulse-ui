---
name: pulse
description: Full-stack Python framework for interactive web apps. Server-driven React UI with WebSocket sync. This skill should be used when building Pulse applications, components, state management, data fetching, routing, forms, or real-time features.
---

# Pulse Framework

Full-stack Python web framework. Server renders React components over WebSocket. All logic runs in Python—no JavaScript required.

## Import Convention

Canonical Pulse style: `import pulse as ps`, then access everything from `ps`. The only modules with exports not available through `pulse` are `pulse.js` (React/JS placeholders for transpilation) and `pulse.transpiler`.

## Quick Start

```python
import pulse as ps

class Counter(ps.State):
    count: int = 0
    def increment(self): self.count += 1

@ps.component
def App():
    with ps.init():
        state = Counter()
    return ps.div(
        ps.button("Click", onClick=state.increment),
        ps.span(f"Count: {state.count}"),
    )

app = ps.App([ps.Route("/", App)])
```

`pulse run app.py` → dev server on `:8000`

## Core Concepts

### Components

Functions decorated with `@ps.component`. Return VDOM elements. Called on every render.

```python
@ps.component
def Greeting(name: str):
    return ps.h1(f"Hello, {name}!")

# Usage: Greeting("World") or Greeting(name="World")
```

**Rules:**
- Always use `@ps.component` decorator
- Props are function parameters
- Use `key=` kwarg for list reconciliation
- Components can nest other components

### HTML Elements

All standard HTML/SVG tags available as `ps.<tag>()`:

```python
ps.div(*children, className="", style=ps.CSSProperties(...), onClick=handler, ...)
ps.input(value=val, onChange=handler, type="text", placeholder="...")
ps.button(*children, onClick=handler, disabled=False, ...)
ps.a(*children, href="...", target="_blank", ...)
ps.img(src="...", alt="...", width=100, ...)
ps.form(*children, onSubmit=handler, ...)
```

**Syntax variants:**
```python
# Positional children
ps.div(ps.h1("Title"), ps.p("Body"))
# Bracket syntax for children
ps.div(className="container")[ps.h1("Title"), ps.p("Body")]
# Mixed
ps.div(className="wrap")[ps.span("text")]
```

**Common props:** `className`, `style`, `id`, `key`, `onClick`, `onChange`, `onSubmit`, `disabled`, `placeholder`, `value`, `checked`, `href`, `src`, `alt`

### State

Class inheriting from `ps.State`. Attributes become reactive—changes trigger re-renders.

```python
class TodoState(ps.State):
    items: list[str] = []
    draft: str = ""

    def add(self):
        if self.draft.strip():
            self.items.append(self.draft)
            self.draft = ""

    def remove(self, idx: int):
        self.items.pop(idx)

    @ps.computed
    def count(self) -> int:
        return len(self.items)

    @ps.effect
    def log_changes(self):
        print(f"Items: {self.count}")
```

**Initialize in components with `ps.init()`:**
```python
@ps.component
def TodoApp():
    with ps.init():
        state = TodoState()
    # state persists across renders
    return ps.div(...)
```

**Rules:**
- Define fields with type annotations and defaults
- Methods mutate state directly (`self.field = value`)
- `@ps.computed` for derived values (cached, auto-updates)
- `@ps.effect` for side effects (runs when dependencies change)
- `on_dispose()` method for cleanup when component unmounts

### Hooks

#### `ps.init()` — Preserve state across renders

```python
@ps.component
def MyComponent():
    with ps.init():
        state = MyState()      # Created once
        other = OtherState()   # Multiple states OK
    # state/other persist across re-renders
```

#### `ps.setup(fn, *args)` — One-time initialization with args

```python
def create_api(user_id: int):
    return {"user_id": user_id}

@ps.component
def UserView(user_id: int):
    meta = ps.setup(create_api, user_id)  # Re-runs if user_id changes
    return ps.div(f"User: {meta['user_id']}")
```

#### `ps.state(arg, *, key=None)` — Inline state instances

```python
@ps.component
def Counter():
    # Simple usage - identified by code location
    counter = ps.state(CounterState())
    return ps.button(f"Count: {counter.count}", onClick=counter.increment)

# In loops - use key parameter
@ps.component
def UserList(user_ids: list[str]):
    items = []
    for uid in user_ids:
        user = ps.state(lambda uid=uid: UserState(uid), key=uid)
        items.append(ps.li(user.name, key=uid))
    return ps.ul(*items)
```

#### `@ps.effect` — Inline effects (auto-registered in components)

```python
@ps.component
def Timer():
    with ps.init():
        state = TimerState()

    @ps.effect  # Auto-registered, no ps.effects() needed
    def log_elapsed():
        print(f"Elapsed: {state.elapsed}")

    return ps.div(str(state.elapsed))

# In loops - use key parameter
@ps.component
def ItemTracker(items: list[str]):
    for item in items:
        @ps.effect(key=item)
        def track(item=item):  # Capture via default arg
            print(f"Tracking: {item}")
    return ps.div(...)
```

#### Runtime hooks

```python
ps.route()          # RouteContext: .pathname, .params, .query, .queryParams
ps.session()        # ReactiveDict of session data
ps.session_id()     # str session ID
ps.navigate(path)   # Client-side navigation
ps.redirect(path)   # Server redirect (throws)
ps.not_found()      # 404 (throws)
```

### Events

Event handlers receive serialized event dict. Common patterns:

```python
# Click - no payload needed
ps.button("Click", onClick=lambda: do_action())
ps.button("Click", onClick=state.method)

# Input change - extract value
ps.input(
    value=state.text,
    onChange=lambda e: setattr(state, "text", e["target"]["value"]),
)

# Form submit
ps.form(onSubmit=lambda e: handle_submit(e))[...]

# Keyboard
ps.input(onKeyDown=lambda e: submit() if e["key"] == "Enter" else None)

# With event data
ps.div(onClick=lambda e: print(e["clientX"], e["clientY"]))
```

**Event types:** `MouseEvent`, `KeyboardEvent`, `ChangeEvent`, `FormEvent`, `FocusEvent`, `DragEvent`, `TouchEvent`, `WheelEvent`

**Async handlers supported:**
```python
async def handle_click():
    await api.fetch_data()
    state.data = result

ps.button("Load", onClick=handle_click)
```

### Lists & Conditionals

#### `ps.For` — Iterate with keys

```python
ps.ul(
    ps.For(
        items,
        lambda item, idx: ps.li(item.name, key=str(item.id)),
    )
)
```

#### `ps.If` — Conditional render

```python
ps.If(
    user is not None,
    then=ps.div(f"Welcome, {user.name}"),
    else_=ps.div("Please login"),
)
```

#### Inline conditionals

```python
# Python and/or
has_items and ps.ul(...)
ps.div(state.loading and "Loading..." or ps.span(state.data))
```

### Routing

```python
app = ps.App([
    ps.Layout(
        AppLayout,  # Wrapper component with ps.Outlet()
        children=[
            ps.Route("/", HomePage),
            ps.Route("/users", UsersPage),
            ps.Route("/users/:id", UserDetail),  # Dynamic param
            ps.Route("/docs/*", DocsPage),       # Catch-all
        ],
    ),
])
```

**Layout component:**
```python
@ps.component
def AppLayout():
    return ps.div(
        ps.nav(ps.Link("Home", to="/"), ps.Link("Users", to="/users")),
        ps.main(ps.Outlet()),  # Child routes render here
    )
```

**Access route info:**
```python
@ps.component
def UserDetail():
    route = ps.route()
    user_id = route.params["id"]
    return ps.div(f"User: {user_id}")
```

**Navigation:**
```python
ps.Link("Go", to="/path")              # Client nav
ps.navigate("/path")                    # Programmatic
ps.redirect("/login")                   # Server redirect (throws)
```

### Forms

#### Declarative form

```python
ps.Form(
    ps.input(name="email", type="email"),
    ps.input(name="password", type="password"),
    ps.button("Submit", type="submit"),
    on_submit=handle_submit,
)

def handle_submit(data: ps.FormData):
    email = data["email"]  # str
    password = data["password"]  # str
```

#### Controlled inputs with state

```python
class LoginState(ps.State):
    email: str = ""
    password: str = ""

    async def submit(self):
        await api.login(self.email, self.password)

@ps.component
def LoginForm():
    with ps.init():
        state = LoginState()
    return ps.form(onSubmit=lambda e: state.submit())[
        ps.input(
            value=state.email,
            onChange=lambda e: setattr(state, "email", e["target"]["value"]),
        ),
        ps.input(
            value=state.password,
            type="password",
            onChange=lambda e: setattr(state, "password", e["target"]["value"]),
        ),
        ps.button("Login"),
    ]
```

### Data Fetching

#### `@ps.query` — Cached async data

```python
class UserState(ps.State):
    user_id: int = 1

    @ps.query
    async def user(self) -> dict:
        return await api.get_user(self.user_id)

    @user.key
    def _user_key(self):
        return ("user", self.user_id)  # Cache key

@ps.component
def UserProfile():
    with ps.init():
        state = UserState()

    if state.user.is_loading:
        return ps.div("Loading...")
    if state.user.is_error:
        return ps.div(f"Error: {state.user.error}")

    user = state.user.data
    return ps.div(user["name"])
```

**Query options:** `stale_time`, `gc_time`, `retries`, `retry_delay`, `keep_previous_data`

**Query methods:** `.refetch()`, `.invalidate()`, `.set_data(val)`, `.wait()`

**Query properties:** `.data`, `.error`, `.status`, `.is_loading`, `.is_fetching`, `.is_success`, `.is_error`

#### `@ps.mutation` — Non-cached operations

```python
@ps.mutation
async def update_user(self, name: str) -> dict:
    result = await api.update_user(self.user_id, name)
    self.user.invalidate()  # Refresh related query
    return result

# Callbacks
@update_user.on_success
def _on_success(self, result):
    print("Updated:", result)

@update_user.on_error
def _on_error(self, error):
    print("Failed:", error)
```

### Global State

Share state across components:

```python
@ps.global_state
class AppSettings(ps.State):
    theme: str = "light"
    def toggle(self):
        self.theme = "dark" if self.theme == "light" else "light"

@ps.component
def Header():
    settings = AppSettings()  # Same instance everywhere
    return ps.button(f"Theme: {settings.theme}", onClick=settings.toggle)
```

## App Configuration

```python
app = ps.App(
    routes=[...],
    middleware=[LoggingMiddleware()],
    session_store=ps.CookieSessionStore(secret_key="..."),  # Production
    server_address="https://app.example.com",  # Required in prod
    mode="single-server",  # or "subdomains"
)
```

## Commands

```bash
uv run pulse run app.py          # Dev server :8000
uv run pulse run app.py --port 3000
make all                         # Format, lint, typecheck, test
```

## Common Patterns

### Counter

```python
class Counter(ps.State):
    count: int = 0
    def inc(self): self.count += 1
    def dec(self): self.count -= 1

@ps.component
def CounterApp():
    with ps.init():
        s = Counter()
    return ps.div(
        ps.button("-", onClick=s.dec),
        ps.span(s.count),
        ps.button("+", onClick=s.inc),
    )
```

### Todo List

```python
class Todos(ps.State):
    items: list[str] = []
    draft: str = ""

    def add(self):
        if self.draft.strip():
            self.items.append(self.draft)
            self.draft = ""

    def remove(self, idx: int):
        self.items.pop(idx)

@ps.component
def TodoApp():
    with ps.init():
        state = Todos()
    return ps.div(
        ps.input(
            value=state.draft,
            onChange=lambda e: setattr(state, "draft", e["target"]["value"]),
            placeholder="Add item...",
        ),
        ps.button("Add", onClick=state.add),
        ps.ul(
            ps.For(
                state.items,
                lambda item, idx: ps.li(
                    item,
                    ps.button("x", onClick=lambda i=idx: state.remove(i)),
                    key=f"{idx}-{item}",
                ),
            )
        ),
    )
```

### Data Table with Loading

```python
class TableState(ps.State):
    page: int = 1

    @ps.query
    async def data(self) -> list[dict]:
        return await api.fetch_page(self.page)

    @data.key
    def _key(self): return ("data", self.page)

@ps.component
def DataTable():
    with ps.init():
        state = TableState()

    if state.data.is_loading:
        return ps.div("Loading...")

    return ps.div(
        ps.table(
            ps.thead(ps.tr(ps.th("Name"), ps.th("Email"))),
            ps.tbody(
                ps.For(
                    state.data.data or [],
                    lambda row, _: ps.tr(
                        ps.td(row["name"]),
                        ps.td(row["email"]),
                        key=str(row["id"]),
                    ),
                )
            ),
        ),
        ps.div(
            ps.button("Prev", onClick=lambda: setattr(state, "page", max(1, state.page - 1))),
            ps.span(f"Page {state.page}"),
            ps.button("Next", onClick=lambda: setattr(state, "page", state.page + 1)),
        ),
    )
```

## Rules & Best Practices

1. **Always use `@ps.component`** for component functions
2. **Always use `ps.init()`** to preserve State across renders
3. **Define State fields** with type annotations and defaults
4. **Use `key=`** on list items for proper reconciliation
5. **Mutate state directly** in methods (`self.field = value`)
6. **Use `@ps.query`** for data fetching with caching
7. **Use `ps.Link`** for internal navigation, not `ps.a`
8. **Access route params** via `ps.route().params`
9. **Clean up** in `on_dispose()` method or effect return
10. **Run `make all`** before committing

## Additional References

For advanced topics, see `references/` folder:
- `reactive.md` — Signal, Computed, Effect, ReactiveDict/List/Set
- `queries.md` — Query options, infinite queries, mutations
- `channels.md` — Real-time bidirectional communication
- `middleware.md` — Request middleware, auth patterns
- `js-interop.md` — React components, JavaScript execution
- `dom.md` — Full HTML elements and events reference
