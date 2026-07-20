# App configuration

Configure routes, sessions, middleware, plugins, and process composition with `ps.App`.

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

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `routes` | `Sequence[Route \| Layout]` | `None` | Page routes |
| `codegen` | `CodegenConfig` | `CodegenConfig()` | React Router output paths |
| `middleware` | `PulseMiddleware \| Sequence` | `None` | Request middleware |
| `plugins` | `Sequence[Plugin]` | `None` | App plugins |
| `cookie` | `Cookie` | `session_cookie()` | Host-only session cookie |
| `session_store` | `SessionStore` | `CookieSessionStore()` | Session persistence |
| `public_origin` | `str` | `None` | Optional canonical browser origin for absolute server-side URLs |
| `not_found` | `str` | `"/not-found"` | 404 page path |
| `proxy` | `WebProxyConfig` | `WebProxyConfig()` | Optional internal web proxy tuning |
| `socketio_options` | `dict[str, Any]` | `None` | Extra Socket.IO server options (e.g. `cors_allowed_origins` when a fronting proxy cannot forward `Host`/`X-Forwarded-Proto`) |
| `session_timeout` | `float` | `60.0` | Disconnected render retention in seconds |
| `prerender_queue_timeout` | `float` | `60.0` | Unattached prerender retention in seconds |
| `disconnect_queue_timeout` | `float` | `300.0` | Disconnected update queue duration in seconds |
| `connection_status` | `ConnectionStatusConfig` | defaults | Client connection UI delays |
| `render_loop_limit` | `int` | `50` | Maximum render loops before failure |

Pulse reserves `/_pulse/*`. Socket.IO uses `/_pulse/socket.io`. Browser requests are always same-origin and use relative URLs. Socket.IO accepts only same-origin connections: a fronting proxy must forward `Host` (or `X-Forwarded-Host`) and `X-Forwarded-Proto`, or you must override via `socketio_options={"cors_allowed_origins": ...}`.

## Public origin

Most apps leave `public_origin` unset. Configure it only for integrations that need an absolute callback URL:

```python
app = ps.App(
    routes=[...],
    public_origin="https://app.example.com",
)
```

`PULSE_PUBLIC_ORIGIN` is the runtime fallback. The value must be an HTTP(S) origin without a path, query, credentials, or fragment. Production and CI require HTTPS.

Do not join this value onto browser links or API paths. Use `/auth/login`, `/api/users`, and other origin-relative URLs.

## Process composition

Pulse supports one browser origin with either one combined deployment or independently scaled processes.

```bash
# Pulse + React Router, with the CLI wiring private addresses
uv run pulse run app.py --prod

# Pulse/FastAPI only; no React Router process or web proxy
uv run pulse run app.py --prod --backend-only

# React Router only; SSR calls the private Pulse address
uv run pulse run app.py --prod --web-only \
  --ssr-backend-url http://pulse-backend:8000
```

For separate processes, an ingress sends `/_pulse/*` and app API routes to Pulse, then sends page and asset requests to React Router. Put the `/_pulse` rule before the frontend catch-all.

Environment variables:

| Variable | Purpose |
| --- | --- |
| `PULSE_PUBLIC_ORIGIN` | Optional canonical browser origin |
| `PULSE_WEB_UPSTREAM` | Optional private React Router URL used by Pulse's `WebProxy` |
| `PULSE_SSR_BACKEND_URL` | Private Pulse URL used by React Router SSR |

No `PULSE_WEB_UPSTREAM` means backend-only. Codegen never embeds any of these addresses.

## Web proxy

`App(proxy=...)` tunes the optional internal `WebProxy`:

```python
app = ps.App(
    routes=[...],
    proxy=ps.WebProxyConfig(
        max_concurrency=200,
        connect_timeout=15.0,
    ),
)
```

Pulse creates the proxy only when `PULSE_WEB_UPSTREAM` is set. Framework routes and user FastAPI routes win over the catch-all proxy. Internal upstream redirects are rewritten to origin-relative locations.

## Codegen

```python
app = ps.App(
    routes=[...],
    codegen=ps.CodegenConfig(
        web_dir="frontend",
        pulse_dir="generated",
        base_dir=Path("/app"),
    ),
)

app.run_codegen()
```

Generated browser requests use `/_pulse` on the current origin. React Router reads `PULSE_SSR_BACKEND_URL` at request time.

## Cookies and sessions

```python
app = ps.App(
    routes=[...],
    cookie=ps.Cookie(
        "pulse.sid",
        secure=True,
        samesite="lax",
        max_age_seconds=7 * 24 * 3600,
    ),
    session_store=ps.CookieSessionStore(secret="your-secret-key"),
)
```

Pulse cookies are host-only; there is no domain setting. `secure=None` always resolves to `True` in production and CI. Pulse rejects explicitly insecure cookies in those environments.

Implement `ps.SessionStore` for Redis or database-backed sessions. See `sessions.md` for the interface.

## Middleware and plugins

```python
app = ps.App(
    routes=[...],
    middleware=[LoggingMiddleware(), AuthMiddleware()],
    plugins=[AuthPlugin()],
)
```

Plugins can contribute routes and middleware, then receive:

- `on_setup(app)` after framework routes are registered
- `on_startup(app)` when the ASGI lifespan starts
- `on_shutdown(app)` during shutdown

Pulse does not install CORS middleware. The framework transport is same-origin. If user-owned FastAPI endpoints intentionally serve another origin, add and own FastAPI CORS configuration for those endpoints.

## Running as ASGI

```bash
PULSE_ENV=prod uvicorn app:app.asgi_factory --factory --host 0.0.0.0 --port 8000
```

Use `app.asgi_factory`, not `app.asgi`, when the process must run setup and codegen.

## See also

- `routing.md` — Route and Layout definitions
- `middleware.md` — middleware lifecycle
- `sessions.md` — stores and cookies
- `context.md` — runtime context
