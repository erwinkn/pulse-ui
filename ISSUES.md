# Issues

1) ASGI proxy routing uses `StarletteRoute` with an ASGI callable.
   - Risk: `Route` expects a request handler (Request -> Response). If Starlette doesn’t auto-wrap ASGI apps in this version, the proxy never runs or errors at runtime.
   - Recommended fix: Use `self.fastapi.mount("/", proxy_handler)`, and keep it last in the router. If mounting, ensure websocket scopes are handled/closed to avoid hangs.

2) Proxy drops `root_path` when building upstream URL.
   - Risk: Deployments behind a subpath (reverse proxy) will miss the prefix and 404 upstream.
   - Recommended fix: Build URL via `URL(scope=scope)` and use `url.path` / `url.query` so `root_path` is preserved.

3) Request error handling misses `asyncio.TimeoutError`.
   - Risk: connect/read timeouts raise `asyncio.TimeoutError`, returning 500 instead of a gateway error.
   - Recommended fix: catch `asyncio.TimeoutError` (and optionally `TimeoutError`) alongside `aiohttp.ClientError` and return 502/504.

4) `test_close_closes_active_responses` is a no-op.
   - Risk: test never executes proxy call; task is created inside `send`, which is never invoked.
   - Recommended fix: create the proxy task outside `send`, wait a tick, call `proxy.close()`, then assert response closed after task completes.

5) `stress-proxy.py --disable-codegen` default makes flag always True.
   - Risk: users cannot enable codegen; CLI flag is misleading.
   - Recommended fix: default to False for `--disable-codegen`, or invert the flag (`--enable-codegen` with `store_true`).

6) Proxy only proxies websocket connections in dev.
   - Risk: websocket requests outside dev are ignored/hang if mounted catch-all receives them.
   - Recommended fix: either handle websocket scope in the proxy (`__call__` dispatches to `proxy_websocket`) or explicitly close websocket scopes with a clear status/reason.

7) Proxy structure is split into base + subclass.
   - Risk: extra indirection makes flow harder to follow and maintain.
   - Recommended fix: collapse into a single `ReactProxy` class with shared helpers as private methods.
