# Minimal React Framework for Pulse

Replace React Router with a purpose-built minimal router and SSR system.

## Goals

1. Reduce complexity/overhead from React Router's unused features
2. Full routing: path params, optional segments, catch-alls, nested routes, layouts
3. Automatic code splitting per route
4. Viewport + hover-based prefetching (Next.js style)
5. SSR via separate Bun server
6. Support managed (generated) and exported (user-editable Vite template) modes
7. Lay foundation for embedded "Pulse islands" mode (future work)

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      Python Pulse App                        │
│  - Routes defined via Route/Layout classes                   │
│  - Route matching (fresh implementation, React Router parity)│
│  - Components rendered to VDOM                               │
│  - WebSocket connection for live updates                     │
└──────────────────────────────────────────────────────────────┘
              │                               │
              │ POST /render                  │ WebSocket
              │ {vdom, routeInfo, config}     │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────┐
│   Bun Render Server     │     │   Browser Client            │
│  - Stateless            │     │  - Client-side routing      │
│  - React SSR only       │     │  - Hydration                │
│  - Returns HTML         │     │  - WebSocket updates        │
└─────────────────────────┘     └─────────────────────────────┘
```

**Key insight:** Python already has route matching. For SSR, Python does routing + prerender, then POSTs complete payload to Bun. Bun just renders React and returns HTML. Single roundtrip: Python → Bun → Python. Route matching in JS is only for client-side navigation.

**Unified VDOM Tree:** Python renders the full nested route tree as one VDOM (layouts + pages merged, Outlets filled in). Client has a single `PulseView` at the root. React Context automatically works since it's one React tree. Python still tracks per-route state internally via `RouteMount`, but outputs a merged tree.

## Design Decisions

### Prefetching
- **Viewport prefetch by default** - Links prefetch when entering viewport (Next.js behavior)
- **Hover prefetch fallback** - When `prefetch={false}`, still prefetch on hover
- **Immediate trigger** - No debounce on hover, matches Next.js

### Error Handling
- **Single `ErrorBoundary` component** - Provided by `pulse` Python library
- **Catches Python rendering errors** - Server-side errors during VDOM rendering
- **Renders to React error boundary** - Client-side catches React rendering errors
- **Unified error UI** - Both error types displayed with same component/styling
- **One at root by default** - Single ErrorBoundary wraps entire app (not per-route)
- **Stack trace in dev only** - Full trace in dev, masked error in prod
- **Customizable fallback** - Python `fallback` prop, optional `client_fallback` for JS

### SSR Server
- **Per-project Bun server** - Each `pulse dev` spawns its own Bun SSR on random port
- **Single process** - Scale via container replicas, not built-in clustering
- **HTTP communication** - Unix socket optimization is future work
- **Network isolation** - No auth required, rely on private network
- **renderToString** - Sync rendering, streaming SSR is future work
- **Complete payload** - Full VDOM JSON, streaming request/response is future work
- **Pre-imported registry** - Bun has static component registry, Python references by name

### VDOM Updates
- **Full tree re-render + diff** - Reuse current renderer.py behavior
- **Fine-grained rendering** - Future work

### Offline/Reconnection
- **Proceed with cached data** - Navigate using prefetched data, reconnect in background
- **Match RenderSession lifecycle** - If session active, send queued updates; if idle, re-render full update

### Pulse Context
- **Immutable snapshot** - Values fixed at provide-time, changes require re-render
- **Raise error on missing** - `use_pulse_context(key)` raises if key not provided by any parent
- **Used for parent params** - Child routes access parent params via Pulse Context

### Code Splitting
- **Automatic per-route** - Each route file becomes its own chunk
- **Support lazy()** - Component-level lazy boundaries within routes
- **Client-side Suspense** - Loading states handled client-side only

### Navigation
- **Support relative paths** - Resolve `../sibling` relative to current location
- **Full options** - `replace`, `state`, `preventScrollReset` all supported
- **Navigation state synced to Python** - Full state object sent via WebSocket
- **Built-in hash scroll** - Auto-scroll to element with matching ID
- **Global progress indicator** - Built-in thin top bar, configurable/replaceable
- **Error UI on failure** - Show error component with manual retry (Next.js style)

### Link Component
- **Auto-detect external** - Check if href starts with http:// or different origin
- Default: viewport prefetch, immediate trigger (see Prefetching above)

### Route Matching
- **Fresh implementation** - New router, not port of existing Pulse routing
- **React Router feature parity** - Without data fetching
- **Per-segment specificity** - Compare segment-by-segment (static > dynamic > optional > catch-all)
- **All optional permutations** - Support `/a/:b?/:c?/:d?` with all combinations
- **Catch-all as array** - `params['*'] = ['a', 'b', 'c']`
- **Optional params undefined** - `string | undefined` when segment missing

### Router Context
- **Single merged context** - One `PulseRouterContext` with `{location, params, navigate}`
- **Scoped params** - Each route level sees only its own params
- **Parent params via Pulse Context** - Parent layouts provide params to children

### Layout Behavior
- **Preserve layout state** - Layout React state persists during child navigation
- **Single Outlet** - Named/multiple Outlets is future work
- **Outlet provides context** - Pass data via context, not props

### Scroll Restoration
- **Configurable** - Default to browser native, allow Pulse override per route

### Redirects
- **Context-dependent** - HTTP 3xx for SSR, VDOM instruction for client navigation

### View Transitions
- **Hooks available** - `onBeforeNavigate`/`onAfterNavigate` for custom implementation
- **Built-in View Transitions API** - Future work

### Modes

#### Managed Mode
- `.pulse/web/` directory, gitignored
- **Incremental updates** - Only write changed files on codegen
- **Checksum-based change detection** - Store hash of generated content
- **Warn + overwrite edits** - Show warning if user edited managed files, then overwrite

#### Exported Mode
- `web/` directory, committed
- **Verbatim copy** - Exact copy with comments for user customization
- **Include .gitignore** - Auto-add `pulse/` to `web/.gitignore`

### CLI

Replaces current `pulse run` with separate commands for dev/build/start (Next.js pattern).

#### `pulse dev <app_file>`
Development server with hot reload and live updates.

**Spawns (supervisor manages all):**
- Python server (uvicorn with `--reload`)
- Vite dev server (client HMR)
- Bun SSR server (server rendering)

**Behavior:**
- Runs codegen on startup (managed mode) or validates generated files (exported mode)
- Interleaved output with prefixes: `[python]`, `[vite]`, `[bun]`
- All processes killed if any crashes
- Prints URL, no auto-open browser

**Options:**
- `--port` - Python server port (default: 8000, auto-finds available)
- `--address` - Bind address (default: localhost)
- `--verbose` - Show all logs without filtering
- `--server-only` - Run only Python server (requires `--react-server-address`)
- `--web-only` - Run only Vite + Bun servers

#### `pulse build <app_file>`
Build for production deployment.

**Steps:**
1. Run codegen (generates/updates route files)
2. Type check (TypeScript + Python)
3. Vite production build (minified, optimized bundle)
4. Optionally compile Bun SSR server to single executable

**Options:**
- `--compile` - Compile Bun to single executable (faster cold start)
- `--no-check` - Skip type checking
- `--ci` - CI mode (stricter validation, requires `server_address`)

**Output:**
- `web/dist/` or `.pulse/web/dist/` - Built client assets
- `web/server/` or `.pulse/web/server/` - SSR server (JS or compiled binary)

#### `pulse start <app_file>`
Run production server. Requires prior `pulse build`.

**Spawns:**
- Python server (uvicorn, no reload, production optimizations)
- Bun SSR server (serves pre-built assets)

**Behavior:**
- Fails if build artifacts not found
- Uses uvloop/httptools if available
- No codegen, no file watching

**Options:**
- `--port` - Python server port (default: 8000)
- `--address` - Bind address (default: 0.0.0.0 for production)
- `--workers` - Number of uvicorn workers (default: 1)

#### `pulse init [directory]`
Create new Pulse project.

**Behavior:**
- Creates minimal project structure (exported mode by default)
- No UI library included (bare bones)
- Generates `pyproject.toml`, `app.py`, `web/` directory

**Options:**
- `--managed` - Use managed mode (`.pulse/web/`, gitignored)

#### `pulse export`
Convert managed mode project to exported mode.

**Behavior:**
- Copies `.pulse/web/` to `web/`
- Adds customization comments to editable files
- Updates `.gitignore` (removes `.pulse/`, adds `web/pulse/`)

#### `pulse generate <app_file>`
Generate routes without starting server. Useful for CI/scripts.

**Options:**
- `--ci` - CI mode (requires `server_address`)
- `--prod` - Production mode

#### `pulse check <app_file>`
Check web dependencies are in sync.

**Options:**
- `--fix` - Install missing/outdated dependencies

### HTML/Head
- **Raw meta tags** - Use standard HTML meta/title, React hoists to head
- **Vite handles CSS** - No Python-side critical CSS injection
- **Dev-mode HTML validator** - Check nesting at Element creation, error with line number

### TypeScript
- **Generic params** - `useParams()` returns `Record<string, string | undefined>`
- Exported mode for user TypeScript helpers/components

### Testing
- **RTL for unit tests** - React Testing Library for JS/TS component tests
- **Playwright for E2E** - Full browser tests involving Pulse server

### Examples
- **Exported mode** - Allows reusing same React project folder

### Future Work
- View Transitions API built-in support
- Navigation events exposed to Python (general event system)
- Unix socket transport optimization
- Streaming SSR (request + response)
- Route-level data preloading (async)
- Named/multiple Outlets
- Pulse islands mode (shared state via Python)
- Fine-grained re-rendering

## Components to Build

### 1. Minimal Router (`packages/pulse/js/src/router/`)

**Files:**
- `match.ts` - Route matching algorithm (React Router feature parity)
- `context.tsx` - PulseRouterContext (injected by Python), useLocation, useParams, useNavigate
- `link.tsx` - Link component with viewport/hover prefetch
- `progress.tsx` - Default navigation progress indicator
- `index.ts` - Public exports

**Key Design Decisions:**
- Fresh route matching implementation with React Router feature parity
- Single merged context with `{location, params, navigate}`
- Viewport prefetch by default, hover fallback when `prefetch={false}`
- Per-segment specificity comparison for route priority
- Auto-detect external links

**Unified Tree Approach:**
- Python renders full nested tree as one VDOM (Outlet filled in server-side)
- Client has single `PulseView` at root - renders one React tree
- React Context automatically flows (Mantine theme, etc.) - no special handling needed
- Python tracks per-route state via `RouteMount`, outputs merged VDOM

**Router Context Injection:**
- Python wraps each route boundary with `PulseRouterContext` component in VDOM
- Client-side `PulseRouterContext` provides React context for `useLocation`/`useParams`
- Scoped params per route level (parent params via Pulse Context)

```
Python renders:                        Client VDOM:
  Layout (params: {org})                 <PulseRouterContext location={...} params={{org}}>
    ↓ Outlet filled in                     <LayoutContent />
  Page (params: {org, id})                 <PulseRouterContext params={{org, id}}>
                                             <PageContent />
                                           </PulseRouterContext>
                                         </PulseRouterContext>
```

- `useLocation()` - returns location from nearest context
- `useParams()` - returns params from nearest route boundary (scoped)

### 2. ErrorBoundary (`packages/pulse/python/src/pulse/error_boundary.py` + `packages/pulse/js/src/error-boundary.tsx`)

**Python API:**
```python
from pulse import ErrorBoundary

# Default - built-in error UI (identical on server/client)
ErrorBoundary(
    App()
)

# Custom server fallback, built-in client fallback
ErrorBoundary(
    App(),
    fallback=lambda err, reset: div(
        p(f"Error: {err.message}"),
        button("Retry", on_click=reset)
    )
)

# Custom both sides
ErrorBoundary(
    App(),
    fallback=my_python_fallback,
    client_fallback="MyErrorFallback"  # Registered JS component
)
```

**Props:**
- `children` - Content to wrap
- `fallback` - Python component `(err: Error, reset: Callable) -> VdomNode` for server-side errors
- `client_fallback` - JS component name for client-side errors (optional)

**Behavior:**
- **Server-side Python error**: Python catches during VDOM rendering, renders `fallback` (or built-in default)
- **Client-side React error**: React error boundary catches, uses priority:
  1. `client_fallback` JS component if specified
  2. Call Python via WebSocket to render `fallback` if connected
  3. Built-in default error component

**Built-in Default Error UI:**
- Identical visuals on Python and JS sides
- Shows: error message, stack trace (dev only), retry button
- Minimal styling, works without CSS framework

**Files:**
- `packages/pulse/python/src/pulse/error_boundary.py` - Python ErrorBoundary component
- `packages/pulse/js/src/error-boundary.tsx` - React error boundary + default fallback UI

### 4. Bun Render Server (`packages/pulse/js/src/server/`)

**Files:**
- `server.ts` - `Bun.serve()` entry point with POST /render endpoint
- `render.tsx` - Server-side React rendering with renderToString
- `dev.ts` - Development mode with Vite middleware (for client bundle HMR)

**SSR Flow (simplified - Python drives):**
1. Browser → Python: HTTP request
2. Python: Route match (fresh implementation)
3. Python: Prerender VDOM for matched routes
4. Python → Bun: POST `/render` with `{vdom, routeInfo, config, matches}` (full match info)
5. Bun: `renderToString()` with RouterProvider + PulseProvider
6. Bun → Python: HTML string (or HTTP 500 on error)
7. Python: Wrap HTML in shell, inject `<script id="__PULSE_DATA__">`
8. Python → Browser: Complete HTML response
9. Browser: Auto-hydrate on DOMContentLoaded with embedded data

**Bun server is stateless** - no routing logic, no prerender calls, just React rendering.

### 5. Updated Codegen (`packages/pulse/python/src/pulse/codegen/`)

**Changes:**
- New `layout.py` template without React Router imports
- New `route.py` template using custom router
- New `routes.ts` format for custom router
- Add mode support: `managed` vs `exported`
- Checksum-based change detection for incremental updates
- Warn on user edits to managed files

### 6. Pulse Context (`packages/pulse/python/src/pulse/context.py`)

Server-side context system that works across route hierarchy (like React Context but Python-side).

**API Concept:**
```python
# In a layout component
@component
def AuthLayout():
    user = get_current_user()

    # Provide context to all child routes (including params like org_id)
    with pulse_context(user=user, permissions=user.permissions, org_id=params['org']):
        return div(Outlet())

# In a child route - can access parent's context
@component
def DashboardPage():
    user = use_pulse_context("user")  # From parent AuthLayout
    org_id = use_pulse_context("org_id")  # Parent param
    return div(f"Welcome {user.name} to org {org_id}")
```

**Implementation:**
- `RenderSession` tracks mounted route hierarchy
- Context values stored per-session, scoped by route path
- Child routes inherit parent contexts
- Immutable snapshot - changes require re-render
- Raises error if key not found in any parent context

### 7. CLI Updates (`packages/pulse/python/src/pulse/cli/`)

**Commands (replaces `pulse run`):**
- `pulse dev` - Development server (supervisor for Python + Vite + Bun SSR)
- `pulse build` - Production build (codegen + typecheck + Vite build + optional `--compile`)
- `pulse start` - Production server (requires prior build)
- `pulse init` - Create new project (bare bones, exported mode by default)
- `pulse export` - Convert managed → exported mode
- `pulse generate` - Generate routes (keep for CI)
- `pulse check` - Check dependencies (keep for CI)

## File Structure

### Managed Mode
```
my-app/
├── app.py
├── .pulse/                    # Gitignored
│   └── web/
│       ├── .checksums.json    # For change detection
│       ├── src/
│       │   ├── entry-server.tsx
│       │   ├── entry-client.tsx
│       │   ├── app.tsx
│       │   └── pulse/         # Generated routes
│       ├── index.html
│       ├── vite.config.ts
│       └── package.json
└── pyproject.toml
```

### Exported Mode
```
my-app/
├── app.py
├── web/                       # Committed
│   ├── .gitignore             # Ignores pulse/
│   ├── src/
│   │   ├── entry-server.tsx
│   │   ├── entry-client.tsx
│   │   ├── app.tsx           # User-editable
│   │   ├── components/       # User components
│   │   └── pulse/            # Gitignored, generated
│   ├── index.html
│   ├── vite.config.ts        # User-editable
│   └── package.json          # User-editable
└── pyproject.toml
```

## Critical Files to Modify

### Python
- `packages/pulse/python/src/pulse/app.py` - Add SSR endpoint that calls Bun render server
- `packages/pulse/python/src/pulse/error_boundary.py` - New file: ErrorBoundary component
- `packages/pulse/python/src/pulse/context.py` - New file: Pulse Context system
- `packages/pulse/python/src/pulse/render_session.py` - Track route hierarchy for context
- `packages/pulse/python/src/pulse/codegen/codegen.py` - Add mode support, new templates, checksums
- `packages/pulse/python/src/pulse/codegen/templates/layout.py` - Remove React Router
- `packages/pulse/python/src/pulse/codegen/templates/route.py` - Use custom router
- `packages/pulse/python/src/pulse/codegen/templates/routes_ts.py` - New route format
- `packages/pulse/python/src/pulse/cli/cmd.py` - New CLI commands
- `packages/pulse/python/src/pulse/vdom/element.py` - Dev-mode HTML nesting validator

### JavaScript
- `packages/pulse/js/src/pulse.tsx` - Replace React Router hooks with custom router
- `packages/pulse/js/src/client.tsx` - Update NavigateFn type, navigation state sync
- `packages/pulse/js/src/error-boundary.tsx` - New file: React error boundary + default fallback UI
- `packages/pulse/js/src/router/` - New directory (router implementation)
- `packages/pulse/js/src/server/` - New directory (Bun SSR server)

### New Files
- `packages/pulse/python/src/pulse/error_boundary.py` - ErrorBoundary component
- `packages/pulse/python/src/pulse/context.py` - Pulse Context system
- `packages/pulse/js/src/error-boundary.tsx` - React error boundary + default fallback
- `packages/pulse/js/src/router/match.ts`
- `packages/pulse/js/src/router/context.tsx`
- `packages/pulse/js/src/router/link.tsx`
- `packages/pulse/js/src/router/progress.tsx`
- `packages/pulse/js/src/server/server.ts`
- `packages/pulse/js/src/server/render.tsx`

## Implementation Phases

### Phase 1: Router Core
1. Implement route matching algorithm (React Router feature parity, per-segment specificity)
2. Implement `PulseRouterContext` component (single merged context with location/params/navigate)
3. Implement useLocation, useParams (scoped), useNavigate (full options) hooks
4. Implement Link with viewport prefetch + hover fallback, external link detection
5. Implement relative path resolution
6. Implement built-in hash scroll to anchor
7. Implement configurable progress indicator with default thin top bar
8. Register `PulseRouterContext` in pulse-ui-client exports for Python to reference

**Tests:**
- `router/match.test.ts`: Static paths, dynamic params (`:id`), optional segments (`?`) with all permutations, catch-all (`*`) as array, nested routes, specificity comparison
- `router/context.test.tsx`: PulseRouterContext provides merged values, scoped params per route level, hooks return expected values
- `router/link.test.tsx`: Click handling, viewport prefetch, hover prefetch fallback, external URL detection, relative path resolution

### Phase 2: ErrorBoundary
1. Implement Python `ErrorBoundary` component that catches rendering errors
2. Implement React error boundary component with default fallback UI
3. Implement built-in default error UI (identical on Python and JS)
4. Wire Python ErrorBoundary to render as React error boundary in VDOM
5. Implement WebSocket fallback: client errors call Python to render custom fallback
6. Add root-level ErrorBoundary wrapper in app initialization

**Tests:**
- `test_error_boundary.py`: Python catches render errors, fallback prop works, client_fallback prop works
- `error-boundary.test.tsx`: React catches errors, default UI renders, custom fallback works, WebSocket fallback triggers

### Phase 3: Unified VDOM Tree
1. Update Python renderer to merge nested routes into single VDOM tree
2. Implement Outlet substitution - replace Outlet nodes with child route's VDOM
3. Implement Outlet context pass-through
4. Wrap each route boundary with `PulseRouterContext` in VDOM (location, scoped params)
5. Update `RenderSession` to coordinate multi-route rendering
6. Ensure full tree re-render + diff works correctly on merged tree

**Tests:**
- `test_unified_vdom.py`: Layout + page merging, deeply nested routes, multiple layouts
- `test_outlet_substitution.py`: Outlet replacement, Outlet context pass-through, missing Outlet handling
- `test_router_context_injection.py`: PulseRouterContext wraps routes, scoped params per level
- `test_vdom_updates.py`: Full tree re-render + diff, navigation updates

### Phase 4: SSR Integration
1. Create Bun render server with POST /render endpoint (network isolation, no auth)
2. Implement React SSR rendering with renderToString (receives complete payload from Python)
3. Update Python app to call Bun for SSR (HTTP communication)
4. Implement HTML shell injection in Python
5. Implement auto-hydration on DOMContentLoaded
6. Set up Vite integration for dev mode (client bundle HMR)
7. Error handling: HTTP 500 from Bun, stack trace in dev only

**Tests:**
- `server/render.test.tsx`: VDOM → React → HTML rendering, registry resolution
- `test_ssr_integration.py`: Python → Bun → HTML roundtrip, error handling (HTTP 500), redirects (context-dependent)
- `test_hydration.ts`: Client auto-hydrates without mismatch, event handlers work post-hydration

### Phase 5: Pulse Context
1. Implement `pulse_context()` context manager for providing values (immutable snapshot)
2. Implement `use_pulse_context()` hook for consuming values (raises on missing key)
3. Wire context inheritance through parent-child routes
4. Use Pulse Context for parent route params access

**Tests:**
- `test_pulse_context.py`: Provide/consume, nested contexts, context override, missing context error
- `test_parent_params.py`: Child accesses parent params via Pulse Context

### Phase 6: Codegen Updates
1. Create new layout template without React Router
2. Create new route template using custom router
3. Update routes.ts generation (automatic per-route code splitting)
4. Add CodegenConfig.mode support (managed vs exported)
5. Implement checksum-based change detection for managed mode
6. Implement warn + overwrite for user edits to managed files

**Tests:**
- `test_codegen.py`: Generated files match expected output, mode switching, route tree generation
- `test_checksums.py`: Incremental updates, edit detection, warning output

### Phase 7: CLI and Build System
1. Implement `pulse dev` - supervisor for Python + Vite + Bun SSR (interleaved output, kill-all-on-crash)
2. Implement `pulse build` - codegen + typecheck + Vite build + optional `--compile` for Bun executable
3. Implement `pulse start` - production server (validates build exists, spawns Python + Bun SSR)
4. Implement `pulse init` - bare bones project scaffold (exported mode by default, `--managed` option)
5. Implement `pulse export` - convert managed → exported (copy files, add comments, update .gitignore)
6. Remove `pulse run` command (replaced by dev/start)
7. Provide standard Dockerfile template

**Tests:**
- `test_cli_dev.py`: Supervisor spawns all processes, interleaved output, crash kills all
- `test_cli_build.py`: Codegen runs, Vite builds, `--compile` produces binary
- `test_cli_start.py`: Fails if not built, spawns production processes
- `test_cli_init.py`: Creates correct structure for both modes
- `test_cli_export.py`: Moves files, adds comments, updates .gitignore

### Phase 8: Navigation Features
1. Implement navigation state sync to Python (full state object via WebSocket)
2. Implement configurable scroll restoration (browser default, Pulse override per route)
3. Implement navigation error UI with manual retry
4. Handle offline navigation with cached/prefetched data, match RenderSession lifecycle on reconnect

**Tests:**
- `test_nav_state.py`: State synced to Python, available in handlers
- `test_scroll_restoration.py`: Browser default, Pulse override
- `test_offline_nav.py`: Cached data navigation, reconnection behavior

### Phase 9: Dev Mode Features
1. Implement dev-mode HTML nesting validator (check at Element creation, error with line number)
2. Integrate with existing Pulse middleware for caching headers

**Tests:**
- `test_html_validator.py`: Detects invalid nesting, points to code line

### Phase 10: Migration and Cleanup
1. Update examples to use new system (exported mode)
2. Remove React Router dependency
3. Update documentation

**Tests:**
- E2E test suite on `examples/web`: Full navigation flow, nested layouts, dynamic routes, WebSocket updates, error boundaries

## Final Verification Checklist

After all phases complete:
- [ ] `make test` passes (all unit + integration tests)
- [ ] E2E tests pass on `examples/web`
- [ ] `pulse dev` starts and app is navigable
- [ ] Browser devtools: no React Router in network/bundle
- [ ] React Context works across nested routes (e.g., Mantine theme)
- [ ] Pulse Context works across nested routes
- [ ] Parent route params accessible via Pulse Context
- [ ] SSR produces valid HTML, hydration has no mismatch warnings
- [ ] Root ErrorBoundary catches Python rendering errors
- [ ] Root ErrorBoundary catches React client-side errors
- [ ] Custom fallback props work (server and client)
- [ ] Prefetch works (viewport + hover fallback)
- [ ] Navigation state syncs to Python
- [ ] Progress indicator shows during navigation
- [ ] Dev-mode HTML validator catches nesting errors

## Open Questions Resolved

- **SSR Server**: Bun (per-project, single process, HTTP, network isolation)
- **Export Model**: Vite template (verbatim + comments)
- **Routing**: Fresh implementation with React Router feature parity
- **Route Matching**: Per-segment specificity comparison
- **Islands Mode**: Deferred entirely (future work with shared state via Python)
- **Code Splitting**: Automatic per route + support lazy()
- **Prefetching**: Viewport default + hover fallback (Next.js style)
- **Error Handling**: Single root ErrorBoundary, catches Python + React errors, unified UI, customizable via `fallback`/`client_fallback` props
- **Context**: Immutable snapshots, raise on missing, used for parent params
- **Navigation**: Full options, state synced to Python, relative paths supported
- **Scroll**: Configurable (browser default or Pulse override)
- **Progress**: Built-in default, configurable/replaceable
- **HTML Validation**: Dev-mode check at Element creation
- **Managed Mode**: Incremental updates, checksum detection, warn + overwrite
