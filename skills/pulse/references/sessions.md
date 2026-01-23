# Sessions

User session management, cookies, and session stores.

## `ps.session()`

Get the current user's session data. Returns a reactive dict persisted across navigations.

```python
def dashboard():
    sess = ps.session()
    sess["last_visited"] = datetime.now()
    visits = sess.get("visit_count", 0)
    return m.Text(f"Visit #{visits}")
```

**Returns:** `ReactiveDict[str, Any]` — mutable session dict

**Storage:**
- Keep data lightweight (<4KB for cookie sessions)
- Store IDs/references, not large objects
- Session data persists across page navigations and reconnects

**Raises:** `RuntimeError` if called outside session context

## `ps.session_id()`

Get the unique session identifier.

```python
def log_action(action: str):
    sid = ps.session_id()
    logger.info(f"[{sid}] User performed: {action}")
```

**Returns:** `str` — 32-char hex UUID

**Use cases:**
- Logging and debugging
- Correlating actions across requests
- External system references

## `ps.websocket_id()`

Get the current WebSocket connection identifier.

```python
def connection_info():
    ws_id = ps.websocket_id()
    sid = ps.session_id()
    return m.Text(f"Session: {sid}, Connection: {ws_id}")
```

**Returns:** `str` — unique connection ID

**Difference from session_id:**
- One session can have multiple WebSocket connections (multiple tabs)
- `session_id` is stable across reconnects
- `websocket_id` changes on each new connection

**Use cases:**
- Track active connections per user
- Per-tab state management
- Connection-specific logging

## Cookie Configuration

### `ps.Cookie`

Configure session cookie behavior at app level.

```python
app = ps.App(
    routes=[...],
    cookie=ps.Cookie(
        name="myapp.sid",
        secure=True,
        samesite="strict",
        max_age_seconds=24 * 3600,  # 1 day
    ),
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | `"pulse.sid"` | Cookie name |
| `domain` | `str \| None` | `None` | Cookie domain (auto-set in subdomain mode) |
| `secure` | `bool \| None` | `None` | HTTPS-only (auto-resolved from server address) |
| `samesite` | `"lax" \| "strict" \| "none"` | `"lax"` | SameSite attribute |
| `max_age_seconds` | `int` | `604800` | Cookie lifetime (7 days) |

**Security notes:**
- `secure=None` auto-resolves from `server_address` scheme
- Production requires HTTPS (`secure=True`)
- Cookies are always `httponly=True` and `path="/"`

## `ps.set_cookie()`

Set custom cookies on the client.

```python
async def set_preferences():
    await ps.set_cookie(
        name="theme",
        value="dark",
        max_age_seconds=365 * 24 * 3600,  # 1 year
    )
```

**Signature:**

```python
async def set_cookie(
    name: str,
    value: str,
    domain: str | None = None,
    secure: bool = True,
    samesite: Literal["lax", "strict", "none"] = "lax",
    max_age_seconds: int = 7 * 24 * 3600,
) -> None
```

**Notes:**
- Must be called within a session context
- Cookie is queued and sent with the next response
- For session cookie updates, modify `ps.session()` instead

## Session Stores

### `ps.CookieSessionStore`

Default store. Session data encoded in signed cookie.

```python
# Uses PULSE_SECRET env var
app = ps.App(
    routes=[...],
    session_store=ps.CookieSessionStore(),
)

# Explicit secret
app = ps.App(
    routes=[...],
    session_store=ps.CookieSessionStore(secret="your-secret-key"),
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `secret` | `str \| None` | `None` | HMAC signing secret (uses `PULSE_SECRET` env if not provided) |
| `salt` | `str` | `"pulse.session"` | HMAC salt |
| `digestmod` | `str` | `"sha256"` | Hash algorithm |
| `max_cookie_bytes` | `int` | `3800` | Max cookie size (truncates if exceeded) |

**Environment:**
- `PULSE_SECRET` — required in production
- In dev, ephemeral secret auto-generated (sessions lost on restart)

**Characteristics:**
- Stateless server (no server-side storage)
- Session travels with cookie (keep data small)
- Signed with HMAC-SHA256, compressed with zlib
- Tamper-proof (invalid signatures rejected)

### `ps.InMemorySessionStore`

Development-only store. Sessions in server memory.

```python
app = ps.App(
    routes=[...],
    session_store=ps.InMemorySessionStore(),
)
```

**Characteristics:**
- Sessions lost on server restart
- No size limit (unlike cookies)
- Single-server only (no horizontal scaling)
- Good for development and testing

### Custom Session Store

Implement `ps.SessionStore` for custom backends (Redis, database, etc.).

```python
class RedisSessionStore(ps.SessionStore):
    async def init(self) -> None:
        # Called on app start
        self.redis = await aioredis.from_url("redis://localhost")

    async def close(self) -> None:
        # Called on app shutdown
        await self.redis.close()

    async def get(self, sid: str) -> dict[str, Any] | None:
        data = await self.redis.get(f"session:{sid}")
        return json.loads(data) if data else None

    async def create(self, sid: str) -> dict[str, Any]:
        session = {}
        await self.save(sid, session)
        return session

    async def save(self, sid: str, session: dict[str, Any]) -> None:
        await self.redis.set(
            f"session:{sid}",
            json.dumps(session),
            ex=7 * 24 * 3600,  # 7 day TTL
        )

    async def delete(self, sid: str) -> None:
        await self.redis.delete(f"session:{sid}")
```

**Required methods:**

| Method | Description |
|--------|-------------|
| `get(sid)` | Retrieve session by ID, return `None` if not found |
| `create(sid)` | Create new session, return empty dict |
| `save(sid, session)` | Persist session data |
| `delete(sid)` | Remove session |

**Optional methods:**

| Method | Description |
|--------|-------------|
| `init()` | Async setup on app start |
| `close()` | Async cleanup on app shutdown |

## Session Lifecycle

### Creation

Session created on first request:
1. Check for existing session cookie
2. If valid cookie found, load session
3. Otherwise, generate new `sid` (UUID4) and create empty session

### Persistence

**Cookie store:** Session encoded and signed on every change, sent to client.

**Server stores:** Session saved asynchronously via reactive effect when data changes.

### Expiration

- Cookie `max_age_seconds` controls client-side expiration
- For server stores, implement TTL in your storage backend
- Expired cookies are ignored, new session created

### Per-Request Flow

```
1. HTTP request arrives
2. Session cookie parsed
3. Session loaded/created
4. Request processed (session available via ps.session())
5. Session changes auto-saved
6. Response includes updated session cookie
```

### Multiple Connections

Single session can have multiple WebSocket connections:
- Each tab opens new WebSocket
- All share same `session_id`
- Each has unique `websocket_id`
- Session changes sync across connections

## Middleware Integration

Access session in middleware:

```python
class AuthMiddleware(ps.PulseMiddleware):
    @override
    async def connect(self, *, request, session, next):
        token = request.headers.get("authorization")
        if token:
            user = await verify_token(token)
            session["user"] = user
        return await next()

    @override
    async def prerender_route(self, *, path, session, **kwargs):
        if path.startswith("/admin") and not session.get("user"):
            return Redirect("/login")
        return await kwargs["next"]()
```

Access in components:

```python
def protected_page():
    sess = ps.session()
    user = sess.get("user")
    if not user:
        ps.redirect("/login")
    return m.Text(f"Welcome, {user['name']}")
```

## Common Patterns

### User Authentication

```python
class AuthMiddleware(ps.PulseMiddleware):
    @override
    async def connect(self, *, request, session, next):
        token = request.cookies.get("auth_token")
        if token:
            try:
                session["user"] = await verify_jwt(token)
            except Exception:
                pass
        return await next()

def logout():
    sess = ps.session()
    sess.pop("user", None)
    ps.navigate("/login")
```

### Flash Messages

```python
def show_flash():
    sess = ps.session()
    msg = sess.pop("flash", None)
    if msg:
        return m.Alert(msg)
    return None

async def save_item():
    await api.save()
    sess = ps.session()
    sess["flash"] = "Item saved successfully"
    ps.navigate("/items")
```

### Visit Tracking

```python
def track_visit():
    sess = ps.session()
    sess["visit_count"] = sess.get("visit_count", 0) + 1
    sess["last_visit"] = datetime.now().isoformat()
```

## See Also

- `middleware.md` - Session access in middleware hooks
- `app.md` - Session store and cookie configuration
- `routing.md` - Auth redirects with session checks
