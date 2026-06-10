# App Configuration

Configure your Pulse application with routes, sessions, middleware, and deployment settings.

## Constructor

```python
import pulse as ps

app = ps.App(
    routes=[
        ps.Route("/", render=home),
        ps.Route("/users/:id", render=user_detail),
    ],
)
```

### Required Parameters

- `routes`: List of `ps.Route` or `ps.Layout` objects defining your app's pages.

### Optional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `codegen` | `CodegenConfig` | `CodegenConfig()` | React Router code generation settings |
| `middleware` | `PulseMiddleware \| list` | `None` | Request middleware |
| `plugins` | `list[Plugin]` | `None` | Application plugins |
| `cookie` | `Cookie` | Auto | Session cookie configuration |
| `session_store` | `SessionStore` | `CookieSessionStore()` | Session storage backend |
| `server_address` | `str` | `None` | Public server URL (required in prod/ci) |
| `dev_server_address` | `str` | `"http://localhost:8000"` | Dev server URL |
| `internal_server_address` | `str` | `None` | Internal URL for SSR fetches |
| `not_found` | `str` | `"/not-found"` | 404 page path |
| `mode` | `"single-server" \| "subdomains"` | `"single-server"` | Deployment mode |
| `api_prefix` | `str` | `"/_pulse"` | API route prefix |
| `cors` | `CORSOptions` | Auto | CORS configuration |
| `fastapi` | `dict` | `None` | FastAPI constructor options |
| `session_timeout` | `float` | `60.0` | Session cleanup timeout (seconds) |

## Deployment Modes

### Single-Server Mode (Default)

Python and React served from the same origin. Pulse proxies non-API requests to React Router.

```python
app = ps.App(
    routes=[...],
    mode="single-server",  # Default
)
```

Use when:
- Simple deployments
- Single domain (e.g., `example.com`)
- Development

### Subdomains Mode

Python API on a subdomain (e.g., `api.example.com`), React on main domain.

```python
app = ps.App(
    routes=[...],
    mode="subdomains",
    server_address="https://api.example.com",
)
```

Use when:
- API and frontend on different subdomains
- CDN hosting for frontend
- Separate scaling requirements

Cookie domain is auto-configured (e.g., `.example.com` for cross-subdomain access).

## Server Address

Required in production. Tells Pulse where the server is accessible.

```python
# Production
app = ps.App(
    routes=[...],
    server_address="https://api.example.com",
)

# With internal address for SSR
app = ps.App(
    routes=[...],
    server_address="https://api.example.com",
    internal_server_address="http://localhost:8000",  # For server-side fetches
)
```

In dev mode, `server_address` is auto-resolved from CLI flags or defaults to `dev_server_address`.

## Codegen Configuration

Control where React Router files are generated.

```python
app = ps.App(
    routes=[...],
    codegen=ps.CodegenConfig(
        web_dir="frontend",      # Default: "web"
        pulse_dir="generated",   # Default: "pulse"
        base_dir=Path("/app"),   # Auto-resolved if not set
    ),
)
# Generated files: frontend/app/generated/
```

### Properties

- `web_dir`: Root directory for web output
- `pulse_dir`: Subdirectory name for generated Pulse files
- `base_dir`: Base directory for resolving relative paths

## Session Configuration

### Cookie-Based Sessions (Default)

Session data stored in signed cookies. Best for stateless deployments.

```python
app = ps.App(
    routes=[...],
    session_store=ps.CookieSessionStore(
        secret="your-secret-key",  # Or set PULSE_SECRET env var
    ),
)
```

Requires `PULSE_SECRET` environment variable in production.

### Server-Backed Sessions

Implement `ps.SessionStore` for custom storage (Redis, database, etc.).

```python
class RedisSessionStore(ps.SessionStore):
    async def init(self) -> None:
        self.redis = await aioredis.from_url("redis://localhost")

    async def get(self, sid: str) -> dict | None:
        data = await self.redis.get(f"session:{sid}")
        return json.loads(data) if data else None

    async def create(self, sid: str) -> dict:
        await self.save(sid, {})
        return {}

    async def save(self, sid: str, session: dict) -> None:
        await self.redis.set(f"session:{sid}", json.dumps(session))

    async def delete(self, sid: str) -> None:
        await self.redis.delete(f"session:{sid}")

app = ps.App(
    routes=[...],
    session_store=RedisSessionStore(),
)
```

### Cookie Configuration

```python
app = ps.App(
    routes=[...],
    cookie=ps.Cookie(
        name="pulse.sid",       # Cookie name
        domain=".example.com",  # Auto-set in subdomains mode
        secure=True,            # HTTPS only (auto from server_address)
        samesite="lax",         # "lax", "strict", or "none"
        max_age_seconds=7*24*3600,  # 7 days
    ),
)
```

## Middleware

Add request lifecycle hooks for auth, logging, redirects.

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

See [middleware.md](./middleware.md) for full API.

## Plugin System

Plugins extend app functionality with routes, middleware, and lifecycle hooks.

```python
class AuthPlugin(ps.Plugin):
    priority = 10  # Higher runs first

    def routes(self) -> list[ps.Route | ps.Layout]:
        return [ps.Route("/login", render=login_page)]

    def middleware(self) -> list[ps.PulseMiddleware]:
        return [AuthMiddleware()]

    def on_startup(self, app: ps.App) -> None:
        print("Auth plugin started")

    def on_setup(self, app: ps.App) -> None:
        # Called after FastAPI routes configured
        pass

    def on_shutdown(self, app: ps.App) -> None:
        # Cleanup on shutdown
        pass

app = ps.App(
    routes=[...],
    plugins=[AuthPlugin()],
)
```

### Lifecycle Hooks

- `on_setup(app)`: After FastAPI routes configured, before serving
- `on_startup(app)`: When server starts accepting connections
- `on_shutdown(app)`: When server is stopping

## CORS Configuration

Auto-configured based on mode. Override for custom settings.

```python
app = ps.App(
    routes=[...],
    cors={
        "allow_origins": ["https://example.com"],
        "allow_methods": ["*"],
        "allow_headers": ["*"],
        "allow_credentials": True,
        "allow_origin_regex": r"^https://.*\.example\.com$",
        "expose_headers": ["X-Custom-Header"],
        "max_age": 600,
    },
)
```

### CORSOptions Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allow_origins` | `list[str]` | `()` | Allowed origins. `["*"]` for all |
| `allow_methods` | `list[str]` | `("GET",)` | Allowed HTTP methods |
| `allow_headers` | `list[str]` | `()` | Allowed headers |
| `allow_credentials` | `bool` | `False` | Allow cookies/auth headers |
| `allow_origin_regex` | `str` | `None` | Regex pattern for origins |
| `expose_headers` | `list[str]` | `()` | Headers exposed to browser |
| `max_age` | `int` | `600` | CORS cache duration (seconds) |

## Running the App

### CLI (Recommended)

```bash
uv run pulse run app.py
uv run pulse run app.py --port 3000
uv run pulse run app.py --address 0.0.0.0 --port 8080
```

### Programmatic

```python
if __name__ == "__main__":
    app.run(
        address="localhost",  # Host to bind
        port=8000,            # Port number
        find_port=True,       # Auto-find available port
        reload=True,          # Auto-reload on changes
    )
```

### ASGI Factory

For production with uvicorn/gunicorn:

```python
# app.py
app = ps.App(
    routes=[...],
    server_address="https://api.example.com",
)

# Used by: uvicorn app:app.asgi_factory --factory
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PULSE_ENV` | Environment: `dev`, `ci`, or `prod` |
| `PULSE_SECRET` | Session signing secret (required in prod) |
| `PULSE_HOST` | Server host (set by CLI) |
| `PULSE_PORT` | Server port (set by CLI) |

## Complete Example

```python
import pulse as ps

class AuthMiddleware(ps.PulseMiddleware):
    async def connect(self, *, request, session, next):
        token = request.headers.get("authorization")
        if token:
            session["user"] = decode_token(token)
        return await next()

app = ps.App(
    routes=[
        ps.Route("/", render=home),
        ps.Route("/dashboard", render=dashboard),
        ps.Route("/users/:id", render=user_detail),
    ],
    middleware=[AuthMiddleware()],
    server_address="https://api.example.com",
    mode="subdomains",
    session_timeout=120.0,
)

if __name__ == "__main__":
    app.run()
```

## See Also

- `routing.md` - Route and Layout definitions
- `middleware.md` - Middleware configuration
- `sessions.md` - Session stores and cookies
