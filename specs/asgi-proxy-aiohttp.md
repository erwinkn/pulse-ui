# ASGI-Only React Proxy (aiohttp)

## Goal
Replace FastAPI-style `ReactProxy` with a single ASGI proxy that:
- stops leaking upstream streams/connections
- shuts down cleanly with open dev connections (uvicorn reloads)
- stays in one file, no config system

Target files:
- `packages/pulse/python/src/pulse/proxy.py`
- `packages/pulse/python/src/pulse/app.py`
- `packages/pulse/python/tests/test_proxy_rewrite.py`
- `packages/pulse/python/pyproject.toml`

## Key Decisions
- Use `aiohttp` for upstream HTTP + WebSocket.
- Disable cookie persistence upstream: `aiohttp.DummyCookieJar()`.
- Keep a single proxy class (ASGI-level). Remove mode switching.
- Keep explicit, local helpers in `proxy.py` (no config layer).

## Design (apply asgiproxy learnings)

### Upstream session lifecycle
- Proxy owns one `aiohttp.ClientSession`.
- `cookie_jar=DummyCookieJar()` to avoid cross-user cookie bleed.
- `auto_decompress=False` to preserve upstream bytes/headers.
- Maintain `_closing: asyncio.Event`.
- Track and close:
  - active HTTP responses
  - active upstream websockets
  - active background tasks

### Concurrency and streaming
- Add `asyncio.Semaphore(max_concurrency)` around upstream connects.
- Streaming thresholds:
  - Small incoming bodies: read fully.
  - Large/unknown: stream.
  - Large outgoing: stream; otherwise read.
- Always close upstream responses:
  - normal completion
  - client disconnect
  - proxy shutdown
  - send failure

### Headers
- Strip hop-by-hop headers:
  - `connection`, `upgrade`, `keep-alive`, `proxy-authenticate`, `proxy-authorization`, `te`, `trailers`, `transfer-encoding`
- Rewrite URL-bearing headers:
  - `location`, `content-location`
- Preserve duplicate headers:
  - use raw header lists; do not coerce to dict

### WebSocket proxy
- Connect upstream first, then accept client with negotiated subprotocol.
- Forward both text and bytes in both directions.
- Use two tasks and cancel the sibling on first completion.
- Treat normal close as non-error.
- Ensure shutdown closes upstream and cancels loops.

## Wiring Changes
- In `app.py` single-server mode:
  - always instantiate ASGI proxy
  - always register ASGI catch-all
  - dev websocket catch-all uses same proxy instance
- Deprecate/ignore `PULSE_PROXY_MODE`.

## Tests to Add/Update
- HTTP:
  - disconnect stops stream and closes upstream
  - `close()` closes active upstream responses
  - `location` and `content-location` rewritten
  - duplicate `set-cookie` preserved
- WebSocket (unit-style):
  - bytes and text forwarded
  - shutdown closes upstream websocket

## Acceptance Criteria
- `make test` passes
- `make all` passes
- `uv run pulse run examples/main.py` runs
- agent-browser smoke test succeeds against dev server

