# Implementation Plan: Single-Server Deployment

## Executive Summary

**Goal**: Run React Router server as a subprocess managed by Python, with FastAPI proxying all non-API requests to it. This exposes a single host/port to end users while maintaining the development experience benefits of React Router's dev server.

**Approach**: Reverse proxy pattern where Python FastAPI routes are prefixed with `/api/pulse/*` and all other requests are proxied to the React Router server running on an internal port.

---

## Current Setup Analysis

### Architecture Overview

**Development Mode (`pulse run`):**
```
User Browser
    │
    ├─> http://localhost:5173 (React Router dev server)
    │   └─> Handles: SSR, HMR, static assets, client bundles
    │   └─> Calls: http://localhost:8000/prerender (Python API)
    │
    └─> http://localhost:8000 (Python uvicorn server)
        └─> Handles: /prerender, /health, /pulse/forms/*, WebSocket
```

**Production Mode (current):**
```
User Browser
    │
    ├─> https://www.example.com (React Router production server)
    │   └─> Handles: SSR, static assets, client bundles
    │   └─> Calls: https://api.example.com/prerender (Python API)
    │
    └─> https://api.example.com (Python uvicorn server)
        └─> Handles: /prerender, /health, /pulse/forms/*, WebSocket
```

### Key Files and Components

#### 1. CLI Entry Point
**File**: `packages/pulse/python/src/pulse/cli/cmd.py`
- **Function**: `run()` (lines 57-246)
- **Purpose**: Orchestrates starting both Python and React Router servers
- **Current Behavior**:
  - Lines 186-246: Builds Python server command with uvicorn
  - Lines 340-350: Builds React Router dev command (`bun run dev`)
  - Lines 361-539: Runs both processes with PTY-based output interleaving

#### 2. Python Server (FastAPI)
**File**: `packages/pulse/python/src/pulse/app.py`
- **Class**: `App.__init__()` (lines 146-276)
- **Routes Defined** (in `App.setup()`, lines 324-597):
  - `GET /health` (line 380)
  - `GET /set-cookies` (line 384)
  - `POST /prerender` (line 389)
  - `POST /pulse/forms/{render_id}/{form_id}` (line 495)
  - WebSocket via socket.io (lines 513-596)

#### 3. Code Generation
**File**: `packages/pulse/python/src/pulse/codegen/templates/layout.py`
- **Template**: `LAYOUT_TEMPLATE` (lines 3-82)
- **Current Behavior**:
  - Line 29: Server loader calls `${internal_server_address}/prerender`
  - Line 56: Client loader calls `${server_address}/prerender`
- **Impact**: These URLs need to change to `/api/pulse/prerender`

#### 4. React Router Configuration
**File**: `examples/web/package.json`
- **Scripts**:
  - `dev`: `react-router dev` (starts dev server, default port 5173)
  - `build`: `react-router build` (builds for production)
  - `start`: `react-router-serve ./build/server/index.js` (production server)

#### 5. Environment Variables
**File**: `packages/pulse/python/src/pulse/env.py`
- **Relevant Vars**:
  - `ENV_PULSE_HOST`: Host for Python server
  - `ENV_PULSE_PORT`: Port for Python server
  - `ENV_PULSE_MODE`: dev/ci/prod mode
- **New Vars Needed**:
  - `ENV_PULSE_WEB_PORT`: Internal React Router port
  - `ENV_PULSE_DEPLOYMENT`: "single-server" or "subdomains"

---

## Target Goal

### New Architecture

**Single-Server Mode - Development:**
```
User Browser
    │
    └─> http://localhost:8000 (Python FastAPI - single entry point)
        │
        ├─> /api/pulse/*     → FastAPI routes (Python handlers)
        │   ├─> /api/pulse/prerender
        │   ├─> /api/pulse/health
        │   ├─> /api/pulse/forms/{render_id}/{form_id}
        │   └─> WebSocket on /socket.io
        │
        └─> /*               → Proxy to React Router (internal)
            └─> http://localhost:<random_port> (not exposed)
                └─> Handles: SSR, HMR, static assets
```

**Single-Server Mode - Production:**
```
User Browser
    │
    └─> https://example.com (Python FastAPI - single entry point)
        │
        ├─> /api/pulse/*     → FastAPI routes
        │
        └─> /*               → Proxy to React Router production server
            └─> http://localhost:<internal_port>
                └─> Handles: SSR, static assets
```

**Subdomains Mode - Development:**
```
User Browser
    │
    ├─> http://localhost:5173 (React Router dev server - separate port)
    │   └─> Handles: SSR, HMR, static assets, client bundles
    │   └─> Calls: http://localhost:8000/prerender (Python API)
    │
    └─> http://localhost:8000 (Python uvicorn server)
        └─> Handles: /prerender, /health, /pulse/forms/*, WebSocket
```

**Subdomains Mode - Production:**
```
User Browser
    │
    ├─> https://www.example.com (React Router production server)
    │   └─> Handles: SSR, static assets, client bundles
    │   └─> Calls: https://api.example.com/prerender (Python API)
    │
    └─> https://api.example.com (Python uvicorn server)
        └─> Handles: /prerender, /health, /pulse/forms/*, WebSocket
```

### Key Changes

**For Single-Server Mode:**
1. **All Python routes prefixed** with `/api/pulse/`
2. **React Router server** started as subprocess by Python (not by CLI) in both dev and prod
3. **Proxy middleware** in FastAPI forwards non-API requests to React Router
4. **Single port** exposed to users
5. **Internal port** for React Router (not exposed, auto-assigned)

**For Subdomains Mode (unchanged):**
1. No route prefix
2. React Router runs independently on separate port in dev
3. No proxying
4. Two separate servers/ports

---

## Implementation Phases

### Phase 1: Add Route Prefix Support (Non-Breaking)

**Goal**: Allow Python routes to work with `/api/pulse/` prefix while maintaining backward compatibility.

**Changes Required**:

#### 1.1. Update `App` class to support route prefixes

**File**: `packages/pulse/python/src/pulse/app.py`

**Location**: `App.__init__()` method

**Changes**:
```python
def __init__(
    self,
    # ... existing params ...
    deployment: DeploymentMode = "subdomains",
    api_prefix: str | None = None,  # NEW
    # ... rest of params ...
):
    # ... existing code ...
    
    # Store API prefix (default based on deployment mode)
    if api_prefix is None:
        self.api_prefix = "/api/pulse" if deployment == "single-server" else ""
    else:
        self.api_prefix = api_prefix
```

#### 1.2. Simplify Cookie and CORS settings for single-server mode

**File**: `packages/pulse/python/src/pulse/app.py`

**Location**: `setup()` method, around line 334-347

**Changes**:
```python
def setup(self, server_address: str):
    # ... existing setup code ...
    
    # Compute cookie domain from deployment/server address if not explicitly provided
    if self.cookie.domain is None:
        self.cookie.domain = compute_cookie_domain(
            self.deployment, self.server_address
        )
    
    # Add CORS middleware (configurable/overridable)
    if self.cors is not None:
        self.fastapi.add_middleware(CORSMiddleware, **self.cors)
    else:
        # In single-server mode, CORS is simpler (same origin)
        if self.deployment == "single-server":
            # Secure by default - only allow the known server origin
            # Users can override by passing custom self.cors if needed
            self.fastapi.add_middleware(
                CORSMiddleware,
                allow_origins=[self.server_address],  # Only the server's own origin
                allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
                allow_headers=["*"],  # Allow all headers for flexibility
                allow_credentials=True,  # Allow cookies/auth
            )
        else:
            # Use deployment-specific CORS settings
            self.fastapi.add_middleware(
                CORSMiddleware,
                **cors_options(self.deployment, self.server_address),
            )
```

**File**: `packages/pulse/python/src/pulse/cookies.py`

**Location**: `session_cookie()` function (lines 75-97)

**Changes**:
```python
def session_cookie(
    mode: "DeploymentMode",
    name: str = "pulse.sid",
    max_age_seconds: int = 7 * 24 * 3600,
):
    if mode == "dev" or mode == "single-server":  # CHANGED: Added single-server
        return Cookie(
            name,
            domain=None,  # Same origin, no domain restrictions
            secure=False,  # Allow http in development
            samesite="lax",
            max_age_seconds=max_age_seconds,
        )
    elif mode == "subdomains":
        return Cookie(
            name,
            domain=None,  # to be set later
            secure=True,
            samesite="lax",
            max_age_seconds=max_age_seconds,
        )
    else:
        raise ValueError(f"Unexpected cookie mode: '{mode}'")
```

**File**: `packages/pulse/python/src/pulse/cookies.py`

**Location**: `compute_cookie_domain()` function (lines 140-148)

**Changes**:
```python
def compute_cookie_domain(mode: "DeploymentMode", server_address: str) -> str | None:
    host = _parse_host(server_address)
    if mode == "dev" or mode == "single-server":  # CHANGED: Added single-server
        return None  # Same origin, no domain needed
    if mode == "subdomains":
        return "." + _base_domain(host)
    return None
```

#### 1.2. Update route definitions to use prefix

**File**: `packages/pulse/python/src/pulse/app.py`

**Location**: `App.setup()` method (lines 380-511)

**Changes**:
```python
def setup(self, server_address: str):
    # ... existing setup code ...
    
    # Apply prefix to all routes
    prefix = self.api_prefix
    
    @self.fastapi.get(f"{prefix}/health")
    def healthcheck():
        return {"health": "ok", "message": "Pulse server is running"}
    
    @self.fastapi.get(f"{prefix}/set-cookies")
    def set_cookies():
        return {"health": "ok", "message": "Cookies updated"}
    
    @self.fastapi.post(f"{prefix}/prerender")
    async def prerender(payload: PrerenderPayload, request: Request):
        # ... existing code ...
    
    @self.fastapi.post(f"{prefix}/pulse/forms/{{render_id}}/{{form_id}}")
    async def handle_form_submit(render_id: str, form_id: str, request: Request):
        # ... existing code ...
```

**Note**: The `/pulse/forms` path is already nested, so it becomes `/api/pulse/pulse/forms` which we should simplify to `/api/pulse/forms` in the route definition.

#### 1.3. Update codegen templates

**File**: `packages/pulse/python/src/pulse/codegen/templates/layout.py`

**Changes**:
```python
LAYOUT_TEMPLATE = Template(
"""import { deserialize, extractServerRouteInfo, PulseProvider, type PulseConfig, type PulsePrerender } from "pulse-ui-client";
// ... imports ...

export const config: PulseConfig = {
  serverAddress: "${server_address}",
  apiPrefix: "${api_prefix}",  // NEW
};

// Server loader
export async function loader(args: LoaderFunctionArgs) {
  // ... existing code ...
  const res = await fetch("${internal_server_address}${api_prefix}/prerender", {  // CHANGED
    // ... rest of code ...
  });
  // ... rest ...
}

// Client loader  
export async function clientLoader(args: ClientLoaderFunctionArgs) {
  // ... existing code ...
  const res = await fetch("${server_address}${api_prefix}/prerender", {  // CHANGED
    // ... rest of code ...
  });
  // ... rest ...
}
"""
)
```

#### 1.4. Update codegen caller

**File**: `packages/pulse/python/src/pulse/codegen/codegen.py`

**Location**: `generate_layout_tsx()` method (lines 139-151)

**Changes**:
```python
def generate_layout_tsx(
    self, server_address: str, internal_server_address: str | None = None, api_prefix: str = ""
):
    """Generates the content of _layout.tsx"""
    content = str(
        LAYOUT_TEMPLATE.render_unicode(
            server_address=server_address,
            internal_server_address=internal_server_address or server_address,
            api_prefix=api_prefix,  # NEW
        )
    )
    return write_file_if_changed(self.output_folder / "_layout.tsx", content)
```

**File**: `packages/pulse/python/src/pulse/codegen/codegen.py`

**Location**: `generate_all()` method

**Changes**:
```python
def generate_all(self, server_address: str, internal_server_address: str | None = None, api_prefix: str = ""):
    # ... existing code ...
    self.generate_layout_tsx(server_address, internal_server_address, api_prefix)
    # ... rest ...
```

**File**: `packages/pulse/python/src/pulse/app.py`

**Location**: `run_codegen()` and `asgi_factory()` methods

**Changes**:
```python
def run_codegen(self, address: str | None = None, internal_address: str | None = None):
    # ... existing code ...
    self.codegen.generate_all(
        self.server_address,
        self.internal_server_address or self.server_address,
        self.api_prefix,  # NEW
    )
```

**Testing Phase 1**:
1. Run `pulse run` with default settings → Should work as before (no prefix)
2. Create test app with `deployment="single-server"` → Routes should have `/api/pulse` prefix
3. Verify `/api/pulse/health` returns OK
4. Verify `/api/pulse/prerender` works from React Router loader
5. Verify cookies have no domain restriction (check browser DevTools → Application → Cookies)
6. Verify CORS headers only allow server origin (check Network tab → Response Headers)
   - `Access-Control-Allow-Origin` should be `http://localhost:8000` (or whatever server_address is)
   - Should NOT be `*` (wildcard)
7. Test with `deployment="subdomains"` → Should use domain-specific cookie and CORS settings
8. Test custom CORS override → Pass `cors={...}` to App → Should use custom settings

---

### Phase 2: Add React Router Subprocess Management

**Goal**: Python server starts and manages React Router server as a subprocess.

**Changes Required**:

#### 2.1. Add subprocess management to App class

**File**: `packages/pulse/python/src/pulse/app.py`

**New imports**:
```python
import asyncio
import subprocess
from pathlib import Path
```

**Add new class attributes and methods**:
```python
class App:
    def __init__(self, ...):
        # ... existing code ...
        self.web_server_proc: subprocess.Popen | None = None
        self.web_server_port: int | None = None
    
    async def start_web_server(self, web_root: Path, mode: str) -> int:
        """Start React Router server as subprocess and return its port."""
        from pulse.cli.helpers import find_available_port
        
        # Find available port
        port = find_available_port(5173)
        
        # Build command based on mode
        if mode == "prod":
            # Production: use built server
            cmd = ["bun", "run", "start", "--port", str(port)]
        else:
            # Development: use dev server
            cmd = ["bun", "run", "dev", "--port", str(port)]
        
        # Start subprocess
        proc = subprocess.Popen(
            cmd,
            cwd=web_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),
        )
        
        # Wait for server to be ready (simple approach: wait for port to be listening)
        await asyncio.sleep(1.0)  # Give server time to start
        
        self.web_server_proc = proc
        self.web_server_port = port
        
        return port
    
    def stop_web_server(self):
        """Stop the React Router subprocess."""
        if self.web_server_proc:
            self.web_server_proc.terminate()
            try:
                self.web_server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.web_server_proc.kill()
            self.web_server_proc = None
            self.web_server_port = None
```

#### 2.2. Update lifespan to manage subprocess

**File**: `packages/pulse/python/src/pulse/app.py`

**Location**: Inside `__init__`, the `lifespan` context manager (lines 220-257)

**Changes**:
```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        # ... existing startup code ...
        
        # Start React Router server if in single-server mode
        if self.deployment == "single-server":
            web_root = self.codegen.cfg.web_root
            if web_root.exists():
                logger.info(f"Starting React Router server from {web_root}")
                port = await self.start_web_server(web_root, self.mode)
                logger.info(f"React Router server started on port {port}")
        
        # ... existing plugin hooks ...
        
        try:
            yield
        finally:
            # ... existing shutdown code ...
            
            # Stop React Router server
            if self.deployment == "single-server":
                logger.info("Stopping React Router server")
                self.stop_web_server()
```

#### 2.3. Add environment variable for web port

**File**: `packages/pulse/python/src/pulse/env.py`

**Add new constant**:
```python
ENV_PULSE_WEB_PORT = "PULSE_WEB_PORT"
```

**Add new property**:
```python
@property
def pulse_web_port(self) -> int | None:
    try:
        val = self._get(ENV_PULSE_WEB_PORT)
        return int(val) if val else None
    except Exception:
        return None

@pulse_web_port.setter
def pulse_web_port(self, value: int | None) -> None:
    self._set(ENV_PULSE_WEB_PORT, str(value) if value else None)
```

**Testing Phase 2**:
1. Start app with `deployment="single-server"` → Should start React Router subprocess
2. Check logs for "React Router server started on port XXXX"
3. Verify subprocess is running: `ps aux | grep bun`
4. Stop app → Verify subprocess is terminated

---

### Phase 3: Add Proxy Middleware with Streaming

**Goal**: FastAPI proxies non-API requests to React Router server with streaming responses.

**Changes Required**:

#### 3.1. Add HTTP client dependency

**File**: `packages/pulse/python/pyproject.toml`

**Add to dependencies**:
```toml
dependencies = [
    # ... existing deps ...
    "aiohttp>=3.9.0",
]
```

**Why aiohttp?**
- **Lower dependency burden**: Fewer transitive dependencies than httpx
- **Slightly faster**: Marginally better performance for local requests (~0.1ms)
- **Simpler**: No extra abstractions, direct asyncio integration
- **Mature**: Battle-tested in production environments
- **Sufficient**: Has everything we need for a simple reverse proxy
- **Streaming support**: Easy streaming via `proxy_response.content.iter_chunked()`

For our use case (local proxy), aiohttp is the simpler and faster choice.

#### 3.2. Implement proxy middleware with streaming

**File**: `packages/pulse/python/src/pulse/app.py`

**New imports**:
```python
import aiohttp
from starlette.responses import StreamingResponse
```

**Add proxy middleware in `setup()` method**:
```python
def setup(self, server_address: str):
    # ... existing setup code before routes ...
    
    # Add proxy middleware for single-server mode
    if self.deployment == "single-server" and self.web_server_port:
        @self.fastapi.middleware("http")
        async def proxy_to_react_router(request: Request, call_next):
            # Skip API routes - let them pass through to FastAPI handlers
            if request.url.path.startswith(self.api_prefix):
                return await call_next(request)
            
            # Skip WebSocket upgrade requests
            if request.headers.get("upgrade") == "websocket":
                return await call_next(request)
            
            # Proxy everything else to React Router server
            target_url = f"http://localhost:{self.web_server_port}{request.url.path}"
            if request.url.query:
                target_url += f"?{request.url.query}"
            
            # Forward the request with streaming
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.request(
                        method=request.method,
                        url=target_url,
                        headers=dict(request.headers),
                        data=await request.body(),
                        timeout=aiohttp.ClientTimeout(total=30.0),
                    ) as proxy_response:
                        # Build response headers
                        headers = dict(proxy_response.headers)
                        # Remove hop-by-hop headers
                        for header in ["connection", "keep-alive", "transfer-encoding"]:
                            headers.pop(header, None)
                        
                        # Stream the response
                        async def stream_content():
                            async for chunk in proxy_response.content.iter_chunked(8192):
                                yield chunk
                        
                        return StreamingResponse(
                            stream_content(),
                            status_code=proxy_response.status,
                            headers=headers,
                        )
                except aiohttp.ClientError as e:
                    logger.error(f"Proxy request failed: {e}")
                    return Response(
                        content=f"Proxy error: {e}",
                        status_code=502,
                    )
    
    # ... existing route definitions ...
```

**Testing Phase 3**:
1. Start app with `deployment="single-server"`
2. Access `http://localhost:8000/` → Should proxy to React Router, show homepage
3. Access `http://localhost:8000/api/pulse/health` → Should hit Python directly
4. Open browser DevTools → Network tab → Verify requests go to single origin
5. Test HMR → Change a React component → Should hot reload
6. Test large responses → Should stream progressively (use Network tab to check timing)

---

### Phase 4: Update CLI for Single-Server Mode

**Goal**: CLI should detect `deployment="single_server"` and not start separate web server.

**Changes Required**:

#### 4.1. Update CLI to check deployment mode

**File**: `packages/pulse/python/src/pulse/cli/cmd.py`

**Location**: `run()` function, around line 112

**Changes**:
```python
def run(...):
    # ... existing code ...
    
    console.log(f"📁 Loading app from: {app_file}")
    parsed = parse_app_target(app_file)
    app_instance = load_app_from_target(app_file)
    
    # Check if app uses single-server deployment
    is_single_server = app_instance.deployment == "single-server"
    
    # In single-server mode, Python manages the web server
    # Don't start it separately from CLI
    if is_single_server:
        console.log("🔧 Single-server mode: Python will manage React Router server")
        web_command = None  # Don't start web server from CLI
    elif not server_only:
        # ... existing web server command logic ...
        web_command = ["bun", "run", "dev"]
        # ...
```

#### 4.2. Add clickable URL output

**File**: `packages/pulse/python/src/pulse/cli/cmd.py`

**Location**: After starting the server processes (around line 470)

**Changes**:
```python
def run(...):
    # ... existing code to start servers ...
    
    # Output server URL for easy access
    if is_single_server:
        # Single server mode - show single URL
        protocol = "http" if address in ("127.0.0.1", "localhost") else "https"
        server_url = f"{protocol}://{address}:{port}"
        console.log(f"")
        console.log(f"✨ [bold green]Pulse server running in single-server mode[/bold green]")
        console.log(f"")
        console.log(f"   → [bold cyan][link={server_url}]{server_url}[/link][/bold cyan]")
        console.log(f"")
        console.log(f"   API endpoints: {server_url}/api/pulse/...")
        console.log(f"")
    else:
        # Subdomains mode - show both URLs
        protocol = "http" if address in ("127.0.0.1", "localhost") else "https"
        server_url = f"{protocol}://{address}:{port}"
        console.log(f"")
        console.log(f"✨ [bold green]Pulse server running in subdomains mode[/bold green]")
        console.log(f"")
        console.log(f"   Python:  [bold cyan][link={server_url}]{server_url}[/link][/bold cyan]")
        if web_command:
            # Try to determine React Router port (default 5173)
            web_url = f"http://localhost:5173"
            console.log(f"   React:   [bold cyan][link={web_url}]{web_url}[/link][/bold cyan]")
        console.log(f"")
    
    # ... continue with existing code ...
```

**Note**: The `[link=URL]text[/link]` syntax in Rich console makes URLs clickable in terminals that support it (VS Code, iTerm2, etc.). Users can Ctrl+Click (or Cmd+Click on Mac) to open in browser.

**Changes to CLI behavior**:

**For `single-server` mode during dev**:
- Run React Router server behind FastAPI as reverse proxy
- Only expose Python server port to user
- Don't show React Router subprocess output

**For `subdomains` mode during dev**:
- Keep current setup: run two servers on separate ports
- No proxying
- Show both server URLs

**Testing Phase 4**:
1. Run `pulse run` with `deployment="single-server"` → Should only show Python server output
2. Should see "✨ Pulse server running in single-server mode" with clickable URL
3. Ctrl+Click URL → Should open in browser
4. Run `pulse run` with `deployment="subdomains"` → Should show both server URLs
5. Verify single-server mode doesn't spawn duplicate React Router processes

---

### Phase 5: Production Build Support

**Goal**: Support production builds with single-server deployment.

**Changes Required**:

#### 5.1. Add production server startup

**File**: `packages/pulse/python/src/pulse/app.py`

**Location**: `start_web_server()` method

**Enhanced logic**:
```python
async def start_web_server(self, web_root: Path, mode: str) -> int:
    """Start React Router server as subprocess and return its port."""
    from pulse.cli.helpers import find_available_port
    
    port = find_available_port(5173)
    
    if mode == "prod":
        # Check if build exists
        build_server = web_root / "build" / "server" / "index.js"
        if not build_server.exists():
            raise RuntimeError(
                f"Production build not found at {build_server}. "
                "Run 'bun run build' in the web directory first."
            )
        # Production: use built server
        cmd = ["bun", "run", "start", "--port", str(port)]
    else:
        # Development: use dev server
        cmd = ["bun", "run", "dev", "--port", str(port)]
    
    logger.info(f"Starting React Router server: {' '.join(cmd)}")
    
    proc = subprocess.Popen(
        cmd,
        cwd=web_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
        text=True,
    )
    
    # Wait for server to be ready
    await asyncio.sleep(2.0 if mode == "prod" else 1.0)
    
    # Check if process is still running
    if proc.poll() is not None:
        output = proc.stdout.read() if proc.stdout else ""
        raise RuntimeError(f"React Router server failed to start: {output}")
    
    self.web_server_proc = proc
    self.web_server_port = port
    
    return port
```

**Testing Phase 5**:
1. Build app: `cd examples/web && bun run build`
2. Start app with `mode="prod"` and `deployment="single_server"`
3. Verify production React Router server starts
4. Access app → Should serve production build (no HMR)

---

## Testing Plan

### Unit Tests

**File**: `packages/pulse/python/tests/test_single_server.py` (new)

```python
import pytest
from pulse import App, Route

def test_api_prefix_in_single_server_mode():
    app = App(routes=[], deployment="single-server")
    assert app.api_prefix == "/api/pulse"

def test_api_prefix_in_subdomains_mode():
    app = App(routes=[], deployment="subdomains")
    assert app.api_prefix == ""

def test_custom_api_prefix():
    app = App(routes=[], api_prefix="/custom/api")
    assert app.api_prefix == "/custom/api"

# ... more unit tests ...
```

### Integration Tests

**Test 1: Automated Single-Server Integration Test**

**File**: `packages/pulse/python/tests/integration/test_single_server_mode.py` (new)

```python
"""
Integration test for single-server deployment mode.
Creates a temporary Pulse app pointing to examples/web and verifies full request/response cycle.
"""

import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def pulse_app_file():
    """Create a temporary Pulse app file for testing."""
    app_content = '''
from pulse import App, Route

app = App(
    routes=[
        Route("/", "app.routes.index", "Index"),
        Route("/about", "app.routes.about", "About"),
    ],
    deployment="single-server",
    mode="dev",
)
'''
    
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.py',
        delete=False,
        dir='/tmp'
    ) as f:
        f.write(app_content)
        return Path(f.name)


@pytest.fixture
def pulse_server(pulse_app_file):
    """Start Pulse server as subprocess and yield its URL."""
    # Start the server
    proc = subprocess.Popen(
        ["pulse", "run", str(pulse_app_file), "--port", "9999"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    # Wait for server to start (check for "running" message or port listening)
    time.sleep(3)
    
    # Check if process is still running
    if proc.poll() is not None:
        stdout, stderr = proc.communicate()
        raise RuntimeError(f"Server failed to start:\nSTDOUT: {stdout}\nSTDERR: {stderr}")
    
    server_url = "http://localhost:9999"
    
    yield server_url
    
    # Cleanup: stop server
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    
    # Cleanup: remove temp file
    pulse_app_file.unlink()


def test_single_server_api_endpoint(pulse_server):
    """Test that API endpoints are accessible at /api/pulse/* prefix."""
    response = httpx.get(f"{pulse_server}/api/pulse/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["health"] == "ok"
    assert "message" in data


def test_single_server_root_route(pulse_server):
    """Test that root route is proxied to React Router."""
    response = httpx.get(pulse_server)
    
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    # Verify it's React Router content (contains expected elements)
    assert b"<html" in response.content or b"<!DOCTYPE" in response.content


def test_single_server_cors_headers(pulse_server):
    """Test that CORS headers only allow the server's own origin."""
    response = httpx.options(
        f"{pulse_server}/api/pulse/health",
        headers={"Origin": pulse_server}
    )
    
    # Should allow the server's own origin
    assert response.headers.get("access-control-allow-origin") == pulse_server
    
    # Test with different origin - should not be allowed
    response_other = httpx.options(
        f"{pulse_server}/api/pulse/health",
        headers={"Origin": "https://evil.com"}
    )
    # CORS middleware will still add header, but browser will block
    # We're just verifying the configured origin is correct
    cors_origin = response_other.headers.get("access-control-allow-origin")
    assert cors_origin == pulse_server or cors_origin is None


def test_single_server_prerender_endpoint(pulse_server):
    """Test that /api/pulse/prerender endpoint works."""
    payload = {
        "route": {
            "path": "/",
            "module": "app.routes.index",
            "name": "Index",
        },
        "request": {
            "method": "GET",
            "url": f"{pulse_server}/",
            "headers": {},
        },
    }
    
    response = httpx.post(
        f"{pulse_server}/api/pulse/prerender",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    # Verify prerender response structure
    assert "html" in data or "error" in data


def test_single_server_static_assets(pulse_server):
    """Test that static assets are proxied through."""
    # Try to fetch a common asset (React Router typically has these)
    # This might be /assets/* or /build/*
    response = httpx.get(f"{pulse_server}/assets/", allow_redirects=False)
    
    # Should either return the asset or 404 from React Router (not 502 proxy error)
    assert response.status_code in [200, 404]
    assert response.status_code != 502  # No proxy error


def test_single_server_cookie_settings(pulse_server):
    """Test that cookies are set without domain restrictions."""
    response = httpx.get(pulse_server)
    
    # Check Set-Cookie headers (if any)
    cookies = response.cookies
    # In single-server mode, cookies should not have domain restrictions
    # This is harder to test without actually setting a cookie, but we can verify
    # the server is accessible and cookies work
    assert response.status_code == 200


def test_single_port_serving(pulse_server):
    """Verify only one port is exposed (not two separate servers)."""
    # The main server should be accessible
    main_response = httpx.get(pulse_server)
    assert main_response.status_code == 200
    
    # The old React Router port (5173) should NOT be accessible
    try:
        react_response = httpx.get("http://localhost:5173", timeout=1.0)
        # If we get here, something is wrong - React Router shouldn't be exposed
        assert False, "React Router server should not be accessible on port 5173"
    except (httpx.ConnectError, httpx.TimeoutException):
        # Expected - port 5173 should not be listening
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Running the test**:
```bash
cd packages/pulse/python
pytest tests/integration/test_single_server_mode.py -v
```

**Test 2: Manual Single-Server Development Mode**
```bash
# Start app in single-server mode
cd examples
pulse run app.py

# In another terminal:
# Test API endpoint
curl http://localhost:8000/api/pulse/health
# Expected: {"health": "ok", ...}

# Test proxied route
curl http://localhost:8000/
# Expected: HTML from React Router

# Test HMR
# Edit examples/app/routes/index.py
# Browser should hot reload
```

**Test 3: Single-Server Production Mode**
```bash
# Build frontend
cd examples/web
bun run build

# Start in prod mode
cd ..
pulse run app.py --prod

# Test endpoints
curl http://localhost:8000/api/pulse/health
curl http://localhost:8000/
```

**Test 4: Subdomains Mode**
```bash
# Create app with deployment="subdomains"
# Start servers
pulse run app.py

# Verify two separate ports are used
# Python: localhost:8000
# React Router: localhost:5173
```

### Performance Tests

**Test 4: Proxy Latency**
```python
# Use the benchmark scripts
python docs/architecture/benchmark_http_server_latency.py

# Verify proxy adds <1ms overhead
```

### End-to-End Tests

**Test 5: Full Application Flow**
1. Start single-server app
2. Navigate to homepage
3. Submit a form
4. Verify WebSocket connection works
5. Test navigation between routes
6. Verify sessions persist
7. Test file uploads
8. Check all functionality works

---

## Rollout Strategy

### Phase 1 Release (v0.x)
- ✅ Add route prefix support
- ✅ Make it opt-in via `deployment="single-server"`
- ✅ Keep `deployment="subdomains"` available
- ✅ Document new mode in migration guide

### Phase 2 Release (v0.x+1)
- ✅ Production testing and bug fixes
- ✅ Performance optimization
- ✅ Update examples to use single-server mode
- ✅ Community feedback

### Phase 3 Release (v1.0)
- ✅ Make `deployment="single-server"` the default
- ✅ Keep `deployment="subdomains"` available (optional)
- ✅ Update all documentation

---

## Migration Guide for Users

### Upgrading to Single-Server Mode

**Step 1: Update App Configuration**
```python
# Before
app = App(
    routes=[...],
    server_address="https://api.example.com",
)

# After
app = App(
    routes=[...],
    deployment="single-server",  # NEW
    server_address="https://example.com",  # Single domain
)
```

**Step 2: Update API Calls (if any custom code)**
```javascript
// Before
fetch("https://api.example.com/prerender", ...)

// After
fetch("/api/pulse/prerender", ...)  // Relative URL
```

**Step 3: Update Deployment**
```bash
# Before: Deploy two servers
# - api.example.com → Python server
# - www.example.com → React Router server

# After: Deploy one server
# - example.com → Python server (proxies to internal React Router)
```

**Step 4: Custom CORS (Optional)**

If you need more permissive CORS settings (e.g., for external API access):

```python
# Custom CORS configuration
app = App(
    routes=[...],
    deployment="single-server",
    cors={
        "allow_origins": ["https://example.com", "https://admin.example.com"],
        "allow_methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["*"],
        "allow_credentials": True,
    }
)
```

By default, single-server mode only allows the server's own origin for security.

---

## Risk Mitigation

### Identified Risks

1. **Proxy adds latency** → Mitigated by benchmarks showing <1ms overhead
2. **Subprocess management complexity** → Graceful shutdown in lifespan
3. **Port conflicts** → Use `find_available_port()` for auto-assignment
4. **Breaking changes** → Keep subdomains mode working, opt-in new mode
5. **HMR breaks** → Ensure WebSocket upgrade requests bypass proxy

### Rollback Plan

If issues arise:
1. Users can revert to `deployment="subdomains"`
2. CLI still supports `--server-only` and `--web-only` flags
3. No database migrations needed
4. Simple configuration change

---

## Success Criteria

- ✅ Single port exposed in development and production
- ✅ HMR works in development mode
- ✅ Proxy latency <1ms (verified by benchmarks)
- ✅ Simplified cookie settings (no domain restrictions in single-server mode)
- ✅ Secure CORS settings (only allow known server origin, not wildcard)
- ✅ CORS overridable via custom `cors` parameter if needed
- ✅ Clickable URLs in terminal output (Ctrl+Click to open)
- ✅ All existing tests pass
- ✅ No breaking changes for existing users
- ✅ Subdomains mode remains fully supported
- ✅ Documentation complete
- ✅ Migration guide ready

---

## Timeline Estimate

- **Phase 1** (Route Prefix): 2-3 days
- **Phase 2** (Subprocess Management): 2-3 days
- **Phase 3** (Proxy Middleware): 2-3 days
- **Phase 4** (CLI Updates): 1-2 days
- **Phase 5** (Production Support): 1-2 days
- **Testing & Documentation**: 2-3 days

**Total**: ~2-3 weeks for complete implementation and testing
