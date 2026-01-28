# Routing

Client-side routing with React Router. Supports nested layouts, dynamic segments, and query parameters.

## Route Definition

### `ps.Route`

Maps URL paths to components:

```python
ps.Route(
    path="/users",          # URL path pattern
    render=users_page,      # Component function (zero-arg)
    children=[...],         # Optional nested routes
    dev=False,              # Dev-only route (excluded in prod)
)
```

### Path Syntax

```python
# Static path
ps.Route("/about", render=about_page)

# Dynamic segment (:name)
ps.Route("/users/:id", render=user_detail)

# Optional segment (:name?)
ps.Route("/users/:id/:tab?", render=user_page)

# Catch-all (*) - must be last segment
ps.Route("/files/*", render=file_browser)

# Combined
ps.Route("/dynamic/:route_id/:optional?/*", render=dynamic_page)
```

## Layout Patterns

### `ps.Layout`

Wraps child routes with shared UI. Must render `ps.Outlet()` for child content:

```python
@ps.component
def AppLayout():
    return ps.div(
        ps.header(ps.nav(ps.Link("Home", to="/"))),
        ps.main(ps.Outlet()),  # Child routes render here
        ps.footer("Footer"),
    )

app = ps.App(
    routes=[
        ps.Layout(
            render=AppLayout,
            children=[
                ps.Route("/", render=home),
                ps.Route("/about", render=about),
            ],
        )
    ]
)
```

### `ps.Outlet`

Placeholder where matched child route content renders:

```python
@ps.component
def Layout():
    return ps.div(
        ps.nav("Navigation"),
        ps.Outlet(),  # Child route renders here
    )
```

### Multiple Layout Levels

Layouts can be nested for multiple wrappers:

```python
ps.Layout(
    render=AppShell,
    children=[
        ps.Route("/", render=home),
        ps.Layout(
            render=DashboardLayout,
            children=[
                ps.Route("/dashboard", render=dashboard),
                ps.Route("/dashboard/settings", render=settings),
            ],
        ),
    ],
)
```

## Route Context

### `ps.route()`

Get current route information inside components:

```python
@ps.component
def UserProfile():
    info = ps.route()

    # Properties
    info["pathname"]      # "/users/123" - current URL path
    info["hash"]          # "section1" - URL hash (without #)
    info["query"]         # "page=2&sort=name" - raw query string (without ?)
    info["queryParams"]   # {"page": "2", "sort": "name"} - parsed query params
    info["pathParams"]    # {"id": "123"} - dynamic path parameters
    info["catchall"]      # ["a", "b"] - catch-all segments as list

    return ps.div(f"User ID: {info['pathParams'].get('id')}")
```

### Example: Dynamic Route Info

```python
@ps.component
def dynamic_route():
    route = ps.route()
    return ps.ul(
        ps.li(f"Pathname: {route['pathname']}"),
        ps.li(f"Hash: {route['hash']}"),
        ps.li(f"Query: {route['query']}"),
        ps.li(f"Query Params: {route['queryParams']}"),
        ps.li(f"Path Params: {route['pathParams']}"),
        ps.li(f"Catchall: {route['catchall']}"),
    )
```

### `ps.pulse_route()`

Get the current route definition inside components:

```python
@ps.component
def route_meta():
    definition = ps.pulse_route()
    return ps.div(f"Route: {definition.path}")
```

## Navigation APIs

### `ps.navigate(path)`

Programmatic navigation from event handlers:

```python
async def handle_login():
    await api.login(username, password)
    ps.navigate("/dashboard")

# With options
ps.navigate("/dashboard", replace=True)  # Replace history entry
ps.navigate("/external", hard=True)      # Full page reload
```

**Note**: Must be called from a Pulse callback context (event handler, effect), not during render.

### `ps.redirect(path)`

Redirect during render. Interrupts rendering immediately:

```python
@ps.component
def protected_page():
    user = get_current_user()
    if not user:
        ps.redirect("/login")  # Interrupts render, never returns

    return ps.div(f"Welcome, {user.name}")
```

```python
# With replace option
ps.redirect("/login", replace=True)
```

**Note**: Raises `RedirectInterrupt` internally - code after `redirect()` never executes.

### `ps.not_found()`

Trigger 404 during render:

```python
@ps.component
def user_page():
    ctx = ps.route()
    user = db.get_user(ctx.pathParams["id"])
    if not user:
        ps.not_found()  # Shows 404 page

    return ps.div(user.name)
```

### `ps.Link`

Client-side navigation link (no full page reload):

```python
# Basic
ps.Link("Home", to="/")
ps.Link("User", to=f"/users/{user_id}")

# With options
ps.Link(
    "Dashboard",
    to="/dashboard",
    prefetch="intent",     # Prefetch on hover (default)
    replace=True,          # Replace history entry
    className="nav-link",
)

# Children syntax
ps.Link(to="/about", className="btn")[
    ps.span("About Us"),
]
```

**Props**:
- `to` - Target URL path
- `prefetch` - `"intent"` (default), `"render"`, `"viewport"`, `"none"`
- `replace` - Replace history instead of push
- `reloadDocument` - Force full page navigation
- `viewTransition` - Enable View Transitions API

## Query Parameters

### Reading Query Params

```python
@ps.component
def search_page():
    ctx = ps.route()
    query = ctx.queryParams.get("q", "")
    page = int(ctx.queryParams.get("page", "1"))
    return ps.div(f"Searching for: {query}, page {page}")
```

### Setting Query Params via Navigation

```python
def search(query: str):
    ps.navigate(f"/search?q={query}")

def next_page(current: int):
    ps.navigate(f"/search?page={current + 1}")
```

### Link with Query Params

```python
ps.Link("Page 2", to="/search?q=test&page=2")
ps.Link("Dynamic", to=f"/dynamic/example?q1=x&q2=y")
```

## Path Parameters

### Defining Dynamic Segments

```python
# Single param
ps.Route("/users/:id", render=user_page)

# Multiple params
ps.Route("/users/:user_id/posts/:post_id", render=post_page)

# Optional param
ps.Route("/products/:id/:variant?", render=product_page)
```

### Accessing Path Params

```python
@ps.component
def user_page():
    ctx = ps.route()
    user_id = ctx.pathParams.get("id")
    return ps.div(f"User: {user_id}")

@ps.component
def post_page():
    ctx = ps.route()
    user_id = ctx.pathParams["user_id"]
    post_id = ctx.pathParams["post_id"]
    return ps.div(f"Post {post_id} by user {user_id}")
```

## Catch-All Routes

Match remaining path segments with `*`:

```python
# Route definition
ps.Route("/docs/*", render=docs_page)

# Accessing catch-all
@ps.component
def docs_page():
    ctx = ps.route()
    segments = ctx.catchall  # ["guides", "getting-started"] for /docs/guides/getting-started
    return ps.div(f"Doc path: {'/'.join(segments)}")
```

## Nested Routes

Child routes are relative to parent path:

```python
ps.Route(
    "/counter",
    render=counter,
    children=[
        ps.Route("details", render=counter_details),  # Matches /counter/details
    ],
)
```

### Parent Component with Outlet

```python
@ps.component
def counter():
    # ... counter content
    return ps.div(
        ps.h1("Counter"),
        ps.div(counter_ui),
        ps.div(
            ps.Outlet(),  # Nested route content renders here
            className="mt-4",
        ),
    )
```

### Conditional Nested Route Display

```python
@ps.component
def counter():
    route_info = ps.route()

    return ps.div(
        ps.h1("Counter"),
        route_info.pathname == "/counter"
        and ps.button("Show Details", onClick=lambda: ps.navigate("/counter/details"))
        or ps.Link("Hide Details", to="/counter"),
        ps.Outlet(),  # details renders here when path matches
    )
```

## Full Example

```python
import pulse as ps

@ps.component
def AppLayout():
    return ps.div(
        ps.nav(
            ps.Link("Home", to="/"),
            ps.Link("Users", to="/users"),
        ),
        ps.main(ps.Outlet()),
    )

@ps.component
def home():
    return ps.h1("Welcome")

@ps.component
def users_list():
    return ps.div(
        ps.h1("Users"),
        ps.Link("View User 1", to="/users/1"),
        ps.Outlet(),
    )

@ps.component
def user_detail():
    ctx = ps.route()
    user_id = ctx.pathParams["id"]
    tab = ctx.pathParams.get("tab", "profile")
    return ps.div(f"User {user_id} - {tab}")

app = ps.App(
    routes=[
        ps.Layout(
            render=AppLayout,
            children=[
                ps.Route("/", render=home),
                ps.Route(
                    "/users",
                    render=users_list,
                    children=[
                        ps.Route(":id", render=user_detail),
                        ps.Route(":id/:tab", render=user_detail),
                    ],
                ),
            ],
        )
    ]
)
```

## Dev-Only Routes

Routes with `dev=True` are excluded in production:

```python
ps.Route("/debug", render=debug_page, dev=True)
ps.Layout(render=DevTools, dev=True, children=[...])
```

## Auth Pattern

Redirect to login if not authenticated:

```python
@ps.component
def protected_page():
    user = ps.session().get("user")
    if not user:
        ctx = ps.route()
        ps.redirect(f"/login?next={ctx.pathname}")

    return ps.div(f"Welcome, {user['name']}")
```

## See Also

- `dom.md` - HTML elements and Link component
- `middleware.md` - Route guards and auth redirects
- `sessions.md` - Session-based authentication
