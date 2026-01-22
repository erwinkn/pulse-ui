# Middleware

Request lifecycle hooks for auth, logging, redirects, and request modification.

## Middleware Class

Inherit from `ps.PulseMiddleware` and override methods:

```python
from typing import override
import pulse as ps
from pulse.middleware import ConnectResponse, Ok, Redirect, NotFound, Deny
from pulse.request import PulseRequest
from pulse.routing import RouteInfo


class AuthMiddleware(ps.PulseMiddleware):
    @override
    async def connect(
        self,
        *,
        request: PulseRequest,
        session: dict,
        next,
    ) -> ConnectResponse:
        # WebSocket connection handshake
        token = request.headers.get("authorization")
        if not self._validate_token(token):
            return Deny("Invalid token")
        session["user"] = self._decode_token(token)
        return await next()

    @override
    async def prerender_route(
        self,
        *,
        path: str,
        route_info: RouteInfo,
        request: PulseRequest,
        session: dict,
        next,
    ) -> ps.RoutePrerenderResponse:
        # Before rendering route (SSR)
        if path.startswith("/admin") and not session.get("is_admin"):
            return Redirect("/login")
        return await next()

    @override
    async def message(
        self,
        *,
        data: dict,
        session: dict,
        next,
    ) -> Ok | Deny:
        # Every WebSocket message
        return await next()
```

## Lifecycle Hooks

### `prerender`

Called before batch SSR prerender for all paths in the request. Modify the payload, inject session data, or return early with redirects.

```python
from pulse.messages import PrerenderPayload, Prerender

@override
async def prerender(
    self,
    *,
    payload: PrerenderPayload,
    request: PulseRequest,
    session: dict,
    next,
) -> ps.PrerenderResponse:
    # payload.paths: list of paths being prerendered
    # payload.routeInfo: route metadata

    # Inject data into session before render
    session["user"] = await get_user(request)

    # Continue to render
    result = await next()

    # Can modify the Prerender result
    if isinstance(result, Ok):
        prerender: Prerender = result.payload
        # prerender["views"]: dict of path -> ServerInitMessage
        # prerender["directives"]: headers and socketio config

    return result

    # Or short-circuit with redirect/404:
    # return Redirect("/login")
    # return NotFound()
```

**Returns:** `await next()`, `Redirect(path)`, `NotFound()`, `Ok(Prerender)`

**Payload fields:**
- `paths`: List of paths being prerendered
- `routeInfo`: Route metadata (params, query, etc.)
- `ttlSeconds`: Optional cache TTL
- `renderId`: Optional render correlation ID

### `connect`

Called on WebSocket connection. Validate auth, set session data.

```python
@override
async def connect(
    self,
    *,
    request: PulseRequest,
    session: dict,
    next,
) -> ConnectResponse:
    # Extract auth from headers/cookies
    token = request.cookies.get("auth_token")
    if not token:
        return Deny("Not authenticated")

    user = await verify_token(token)
    session["user"] = user
    session["user_id"] = user["id"]

    return await next()  # Continue to app
```

**Returns:** `await next()` or `Deny(reason)`

### `prerender_route`

Called before SSR render. Redirect unauthenticated users, inject session data.

```python
@override
async def prerender_route(
    self,
    *,
    path: str,
    route_info: RouteInfo,
    request: PulseRequest,
    session: dict,
    next,
) -> ps.RoutePrerenderResponse:
    # Protected routes
    protected = ["/dashboard", "/settings", "/admin"]
    if any(path.startswith(p) for p in protected):
        if not session.get("user"):
            return Redirect("/login")

    # Admin-only
    if path.startswith("/admin"):
        user = session.get("user", {})
        if not user.get("is_admin"):
            return NotFound()

    return await next()
```

**Returns:** `await next()`, `Redirect(path)`, `NotFound()`, `Ok(response)`

### `message`

Called on every WebSocket message (callbacks, navigation, etc.).

```python
@override
async def message(
    self,
    *,
    data: dict,
    session: dict,
    next,
) -> Ok | Deny:
    msg_type = data.get("type")

    # Rate limiting
    if not self._check_rate_limit(session):
        return Deny("Rate limited")

    # Logging
    print(f"[{session.get('user_id')}] {msg_type}")

    return await next()
```

**Returns:** `await next()` or `Deny(reason)`

### `channel`

Called when channel messages are received. Authorize by channel, event, or payload.

```python
from typing import Any

@override
async def channel(
    self,
    *,
    channel_id: str,
    event: str,
    payload: Any,
    request_id: str | None,
    session: dict,
    next,
) -> Ok | Deny:
    # Authorize based on channel
    if channel_id.startswith("admin:"):
        if not session.get("is_admin"):
            return Deny()

    # Authorize based on event type
    if event == "delete" and not session.get("can_delete"):
        return Deny()

    # Check payload
    if payload.get("sensitive") and not session.get("verified"):
        return Deny()

    return await next()
```

**Returns:** `await next()` or `Deny()`

**Parameters:**
- `channel_id`: Channel identifier (e.g., `"chat:room-123"`)
- `event`: Event name (e.g., `"message"`, `"typing"`)
- `payload`: Event data
- `request_id`: Correlation ID if client awaits response (for request/response pattern)
- `session`: Session data dictionary

## Response Types

```python
from pulse.middleware import Ok, Redirect, NotFound, Deny

Ok(response)      # Success with custom response
Redirect(path)    # Redirect to path
Redirect(path, replace=True)  # Replace history
NotFound()        # 404 response
Deny(reason)      # Reject request
```

## Request Object

```python
request.method     # str — HTTP method
request.url        # URL object
request.headers    # dict-like headers
request.cookies    # dict of cookies
request.client     # (ip, port) tuple or None
request.query_params  # Query string params
```

## Session Object

Mutable dict persisted across requests:

```python
# Set in middleware
session["user_id"] = 123
session["role"] = "admin"

# Access in components
@ps.component
def Dashboard():
    sess = ps.session()
    user_id = sess.get("user_id")
    if not user_id:
        ps.redirect("/login")
    return ps.div(f"User: {user_id}")
```

## Multiple Middleware

Chain multiple middleware in order:

```python
app = ps.App(
    routes=[...],
    middleware=[
        LoggingMiddleware(),
        AuthMiddleware(),
        RateLimitMiddleware(),
    ],
)
```

Executes in order. Each calls `await next()` to continue chain.

## Built-in Middleware

### `ps.LatencyMiddleware`

Adds artificial latency for testing:

```python
app = ps.App(
    routes=[...],
    middleware=[ps.LatencyMiddleware()],  # Dev only
)
```

## Middleware Stack

Combine middleware programmatically:

```python
from pulse.middleware import stack

combined = stack(
    LoggingMiddleware(),
    AuthMiddleware(),
)

app = ps.App(routes=[...], middleware=combined)
```

## Common Patterns

### Auth Check

```python
class AuthMiddleware(ps.PulseMiddleware):
    @override
    async def connect(self, *, request, session, next):
        token = request.headers.get("authorization", "").replace("Bearer ", "")
        if token:
            try:
                user = await verify_jwt(token)
                session["user"] = user
            except Exception:
                pass
        return await next()

    @override
    async def prerender_route(self, *, path, session, **kwargs):
        public = ["/", "/login", "/signup", "/public"]
        if path not in public and not session.get("user"):
            return Redirect("/login")
        return await kwargs["next"]()
```

### Logging

```python
class LoggingMiddleware(ps.PulseMiddleware):
    @override
    async def prerender_route(self, *, path, request, **kwargs):
        start = time.time()
        result = await kwargs["next"]()
        duration = time.time() - start
        print(f"[{request.client[0]}] {path} {duration:.3f}s")
        return result
```

### Role-Based Access

```python
class RBACMiddleware(ps.PulseMiddleware):
    ADMIN_PATHS = ["/admin", "/settings/admin"]

    @override
    async def prerender_route(self, *, path, session, **kwargs):
        if any(path.startswith(p) for p in self.ADMIN_PATHS):
            user = session.get("user", {})
            if user.get("role") != "admin":
                return NotFound()
        return await kwargs["next"]()
```

### CORS Headers

Usually handled by FastAPI, but custom headers:

```python
class CORSMiddleware(ps.PulseMiddleware):
    @override
    async def prerender_route(self, *, request, **kwargs):
        result = await kwargs["next"]()
        if isinstance(result, Ok):
            result.response.headers["Access-Control-Allow-Origin"] = "*"
        return result
```

## Session Stores

Configure session persistence:

```python
# In-memory (dev only, lost on restart)
app = ps.App(
    routes=[...],
    session_store=ps.InMemorySessionStore(),
)

# Cookie-based (production)
app = ps.App(
    routes=[...],
    session_store=ps.CookieSessionStore(
        secret_key="your-secret-key-min-32-chars",
    ),
)
```

## Cookie Configuration

```python
app = ps.App(
    routes=[...],
    cookie=ps.Cookie(
        name="pulse_session",
        domain=".example.com",
        secure=True,        # HTTPS only
        samesite="lax",     # or "strict", "none"
        http_only=True,
        max_age=7*24*3600,  # 7 days
    ),
)

## See Also

- `sessions.md` - Session stores and cookie configuration
- `queries.md` - QueryClient session cache
- `app.md` - Middleware configuration in App
```
