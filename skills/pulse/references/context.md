# Runtime Context

Access to session, route, and connection info within component render and callbacks.

## PulseContext

Dataclass managing per-request state. Accessed via `PulseContext.get()`.

**Always available when a Pulse app is running:**
- `app` - Application instance (always set)

**Mounted contextually:**
- `session` - UserSession (set during HTTP requests and WebSocket connections)
- `render` - RenderSession (set during render sessions)
- `route` - RouteContext (set when rendering a route)

```python
from pulse.context import PulseContext

ctx = PulseContext.get()
app = ctx.app  # Always available
render = ctx.render  # Available during render
```

User code typically uses the `ps.*` functions below instead of accessing PulseContext directly.

## Session Functions

### `ps.session()`

Get current user session data.

```python
def dashboard():
    sess = ps.session()
    sess["theme"] = "dark"           # Set value
    visits = sess.get("count", 0)    # Get with default
    return m.Text(f"Visit #{visits}")
```

**Returns:** `ReactiveDict[str, Any]` - reactive dict persisted across navigations

### `ps.session_id()`

Get unique session identifier.

```python
def log_action():
    sid = ps.session_id()
    logger.info(f"[{sid}] Action performed")
```

**Returns:** `str` - 32-char hex UUID, stable across reconnects

### `ps.websocket_id()`

Get WebSocket connection identifier.

```python
def connection_info():
    ws_id = ps.websocket_id()
    return m.Text(f"Connection: {ws_id}")
```

**Returns:** `str` - unique per connection

**Difference from session_id:**
- One session can have multiple WebSocket connections (multiple tabs)
- `session_id` stable across reconnects, `websocket_id` changes each connection

## Route Context

### `ps.route()`

Get current route info with path params, query params, and URL info.

```python
def user_page():
    r = ps.route()
    user_id = r["pathParams"].get("id")     # From /users/:id
    page = r["queryParams"].get("page", "1") # From ?page=2
    return m.Text(f"User {user_id}, Page {page}")
```

**Returns:** `RouteInfo` with keys:
- `pathname` - Current URL path (e.g., "/users/123")
- `hash` - URL hash fragment (without #)
- `query` - Raw query string (without ?)
- `queryParams` - Parsed query parameters as dict
- `pathParams` - Dynamic path parameters (e.g., `{"id": "123"}`)
- `catchall` - Catch-all segments as list

### `ps.pulse_route()`

Get the current route definition.

```python
def route_def():
    route = ps.pulse_route()
    return m.Text(f"Route: {route.path}")
```

**Returns:** `Route` or `Layout` for the active route.

## Address Functions

### `ps.client_address()`

Get client's IP address.

```python
def show_ip():
    ip = ps.client_address()
    return m.Text(f"Your IP: {ip}")
```

### `ps.server_address()`

Get server's public address.

```python
def build_link():
    base = ps.server_address()  # e.g., "https://example.com"
    return m.Anchor(href=f"{base}/share/123")
```

**Note:** Requires `server_address` configured in `App.run_codegen` or `asgi_factory`.

## Query Client

### `ps.queries`

Singleton for session-level query cache management.

```python
# Get cached data
user = ps.queries.get_data(("user", user_id))

# Set data (optimistic update)
ps.queries.set_data(("user", user_id), updated_user)

# Invalidate by exact key
ps.queries.invalidate(("user", user_id))

# Invalidate by prefix (all users)
ps.queries.invalidate_prefix(("users",))

# Check if fetching
if ps.queries.is_fetching(("user", user_id)):
    show_loading()
```

See `queries.md` for full API.

## Global State

### `ps.global_state()`

Access global state instances (not the decorator).

```python
@ps.global_state
class AppSettings(ps.State):
    theme: str = "light"

def settings_panel():
    # Get shared instance
    settings = AppSettings()
    return m.Select(value=settings.theme, ...)
```

**With instance ID:**

```python
@ps.global_state
class UserCache(ps.State):
    data: dict = {}

def user_profile(user_id: str):
    # Separate instance per user_id
    cache = UserCache(id=user_id)
    return m.Text(cache.data.get("name"))
```

## API Calls

### `ps.call_api()`

Make API calls through client browser (for third-party APIs needing browser cookies).

```python
async def fetch_external():
    result = await ps.call_api(
        "https://api.example.com/data",
        method="GET",
        headers={"X-Custom": "value"},
    )
    return result
```

**Parameters:**
- `path` - URL to call
- `method` - HTTP method (default: "POST")
- `headers` - Optional headers dict
- `body` - Optional request body (JSON serialized)
- `credentials` - Credential mode (default: "include")

**Returns:** `dict[str, Any]` - JSON response

## Context Scope

**Available in:**
- Component render functions
- Event callbacks (`on_click`, `on_change`, etc.)
- Effect functions (`@ps.effect`)
- Query/mutation methods

**NOT available in:**
- Module-level code (app startup)
- Middleware outside request scope
- Background tasks without explicit context

**Example - what works:**

```python
@ps.component
def MyComponent():
    sess = ps.session()      # OK - during render

    def handle_click():
        sess = ps.session()  # OK - in callback
        ps.navigate("/home")

    @ps.effect
    def track():
        sid = ps.session_id()  # OK - in effect

    return m.Button("Click", on_click=handle_click)
```

**Example - what fails:**

```python
# Module level - no context
sess = ps.session()  # RuntimeError!

def startup():
    # Outside request - no context
    ps.session()  # RuntimeError!
```

## See Also

- `sessions.md` - Session stores and cookies
- `routing.md` - Route definitions and navigation
- `queries.md` - Query client details
- `state.md` - Global state decorator
