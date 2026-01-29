# Pulse Router Replacement Review

## High Risk / Correctness
- **Initial route module load never triggers a render** (`packages/pulse/js/src/router.tsx:518`, `packages/pulse/js/src/router.tsx:548`). `PulseRoutes` only reads `routeModuleCache`, but initial modules are loaded in a `useEffect` without any state update. On first load (and SSR) the cache is empty, so `PulseRoutes` returns `null` and can stay blank unless some unrelated state change happens. On SSR, the effect never runs, so the route component is never rendered.
  - **Fix**: load initial modules before first render (synchronous `use`/`React.lazy` + `Suspense`), or track a `routesLoadedVersion` state that updates when preload resolves. Consider wiring module loading into Router state instead of a global cache.

- **Async navigation races can revert to older locations** (`packages/pulse/js/src/router.tsx:428`, `packages/pulse/python/src/pulse/codegen/templates/layout.py:75`). `navigate()` fires `applyNavigation()` without awaiting or sequencing. If users navigate quickly, a slower earlier `onNavigate` (prerender fetch) can complete after a later one and overwrite `location`/`matchState` with stale data.
  - **Fix**: add a navigation sequence token and ignore out-of-order completions, or use `AbortController` and cancel inflight prerenders.

- **Popstate with unknown route leaves URL/UI out of sync** (`packages/pulse/js/src/router.tsx:428`). When a `popstate` location doesn’t match the route tree, `applyNavigation` returns early and *does not* update state or hard-navigate. The browser URL changes, but the UI stays on the previous route.
  - **Fix**: for `pop` + no match, either hard-navigate (`window.location.assign`) or set a “not found” route state.

- **Protocol-relative URLs (`//example.com`) are treated as in-app paths** (`packages/pulse/js/src/router.tsx:369`). `resolveHref` treats any string starting with `/` as a pathname. `//host` ends up being parsed as a local path and then navigates to `/`, not to the external host.
  - **Fix**: explicitly treat `to.startsWith("//")` as external (similar to `navigate_to` handling in the client).

## Medium Risk / Brittleness
- **Prerender re-init in `PulseView` is a band-aid and leaks renderer state** (`packages/pulse/js/src/pulse.tsx:221`). The `hasRendered` hack resets the tree when `initialView` changes, but keeps the same `VDOMRenderer` instance (and its `#callbackCache`/`#inputOverrides`). On dynamic route changes with the same route ID, stale callbacks and input overrides can leak across pages.
  - **Fix**: make renderer lifecycle align with the prerender payload (recreate or reset renderer on routeInfo change), or make cache keys include a stable route-instance id.

- **Input override logic is heuristic and loses edits** (`packages/pulse/js/src/renderer.tsx:224`). The `startsWith` heuristic for `value` overrides only preserves prefix edits. Typing in the middle, replacing selections, or non-string inputs will get clobbered by server updates and the override is cleared on server updates.
  - **Fix**: treat client input overrides as authoritative until server confirms a matching value, or tie overrides to a monotonic “input version” from the server. Avoid the prefix heuristic.

- **Moved nodes rebind callbacks but not input overrides** (`packages/pulse/js/src/renderer.tsx:539`). `#rebindCallbacksInSubtree` updates callback paths on reconciliation moves, but `#inputOverrides` remain keyed by old paths. This can attach old typed values to the wrong nodes after list reorders.
  - **Fix**: migrate input overrides alongside rebind, or key overrides by a stable VDOM key instead of path.

- **Unhandled errors during navigation** (`packages/pulse/js/src/router.tsx:428`, `packages/pulse/python/src/pulse/codegen/templates/layout.py:75`). Errors in `preloadRoutesForPath` or `onNavigate` propagate as unhandled rejections (`navigate()` uses `void`). This can leave the router in an inconsistent state without user feedback.
  - **Fix**: catch and surface navigation errors (error boundary, fallback UI, or revert to previous location).

## Low Risk / Cleanup
- **Global `routeModuleCache` can become stale across HMR or multi-app usage** (`packages/pulse/js/src/router.tsx:59`). The cache is shared across all Router instances and never invalidated. In dev, old modules can persist; in multi-app contexts, modules can collide by `id`.
  - **Fix**: scope cache to `PulseRouterProvider` or key by route tree identity/version.

- **`PulseProvider` depends on router context** (`packages/pulse/js/src/pulse.tsx:82`). `PulseProvider` now calls `useNavigate()`, which throws if mounted without `PulseRouterProvider`. That’s a breaking coupling for any non-router embedding use.
  - **Fix**: make navigation optional (`useNavigate` fallback) or inject a no-op navigate when router isn’t present.

- **`usePulsePrerender` throws hard on missing view** (`packages/pulse/js/src/pulse.tsx:56`). Any mismatch between `prerender.views` and `PulseView` rendering will crash the app instead of showing a placeholder.
  - **Fix**: return a fallback or a clearer error boundary to avoid a hard crash.

## Architectural Concerns
- **Route matching logic is duplicated in JS and Python** (`packages/pulse/js/src/router.tsx`, `packages/pulse/python/src/pulse/routing.py`). The algorithms are currently similar, but any future changes risk drift. There are no conformance tests to ensure parity.
  - **Fix**: generate matchers from a shared spec, or add cross-language tests that assert identical match results for a shared corpus.

## Tests & Coverage Gaps
- Only `matchRoutes` is covered (`packages/pulse/js/src/router.test.ts`). There are no tests for:
  - navigation races and cancellation
  - `PulseRoutes` initial module loading / SSR hydration
  - popstate behavior with unmatched paths
  - `Link` external/protocol-relative URLs
  - `PulseView` rerender semantics when route params change

---

If you want, I can turn the high-risk items into a concrete refactor plan and PR-sized changes.

---

# Branch-Specific Architecture Overview (Router + Vite)

## Minimal React “Framework” (new router layer)
Files: `packages/pulse/js/src/router.tsx`, `packages/pulse/js/src/pulse.tsx`, `packages/pulse/js/src/client.tsx`
- **What replaced React Router**: `PulseRouterProvider`, `PulseRoutes`, `Outlet`, `Link`, `useNavigate/useRouteInfo`. No `<Routes>/<Route>` elements; routing is pure data + generated route modules.
- **Route tree input**: `PulseRoute[]` is generated by Python codegen (see below). Nodes include `id`, `path`, `index`, `children`.
- **Matching**: `matchRoutes()` mirrors Python route matching:
  - layout nodes are `path == null && !index`
  - supports static, dynamic `:id`, optional `?`, splat `*`
  - scoring prefers static > dynamic; deeper match wins ties
- **Navigation pipeline**:
  - `navigate()` resolves relative paths, then `applyNavigation()`
  - `applyNavigation()` preloads route modules, calls `onNavigate` (prerender fetch), pushes history, updates router state
  - `popstate` funnels through same pipeline
- **Render pipeline**:
  - `PulseRoutes` renders top match only after its module is loaded (from `routeModuleCache`)
  - `Outlet` renders nested match via `OutletIndexContext`
- **Server integration points**:
  - `PulseProvider` now depends on router `useNavigate()`; it injects router-aware navigation into `PulseSocketIOClient` so server `navigate_to` messages can do SPA nav.
  - `PulseView` uses `useRouteInfo()` and calls `client.updateRoute()` on nav so server route context stays in sync.

## Codegen: Route Modules + Loader Map
Files: `packages/pulse/python/src/pulse/codegen/codegen.py`, `.../templates/routes_ts.py`, `.../templates/route.py`, `.../templates/layout.py`
- **`routes.ts` output**:
  - `pulseRouteTree`: serializable route tree used by matcher.
  - `routeLoaders`: `{ [routeId]: () => import(...) }` for dynamic imports.
- **Route modules** (generated per route/layout):
  - default export renders `<PulseView path=... registry=... />`
  - `registry` bundles all client-side imports/consts/functions needed by that route.
- **App shell** (`_layout.tsx`):
  - `PulseApp` composes `PulseRouterProvider` → `PulseProvider` → `PulseRoutes`.
  - `onNavigate` does the prerender fetch (`/prerender`) using matched route IDs.
  - Stores directives in `sessionStorage` and injects into prerender fetch headers.

## Vite: Bundling, Code Splitting, SSR
Reference: `examples/web/vite.config.ts`, `examples/web/src/entry-client.tsx`, `examples/web/src/entry-server.tsx`, `examples/web/server/ssr.ts`
- **Bundling config**:
  - Plugins: React, Tailwind, tsconfig paths, devtools JSON.
  - `resolve.conditions` includes `@pulse/source` so source is used when available.
  - `ssr.noExternal` bundles `pulse-*` packages into SSR build.
  - Client build: `dist/client` + `manifest.json` and `ssrManifest`.
  - SSR build: `dist/server` (entry-server output).
- **Code splitting**:
  - `routeLoaders` dynamic imports are the split points; each route module becomes a separate chunk.
  - `preloadRoutesForPath()` loads matched route modules (client + server).
  - `Link` prefetch uses `prefetchRouteModules()` to warm chunks on hover/viewport.
- **SSR render pipeline**:
  - `entry-server.tsx`:
    - `preloadRoutesForPath()` for the request path before `renderToString`
    - in prod, reads Vite `manifest.json` to emit `<link rel="modulepreload">` + CSS + `<script type=module>`
    - in dev, injects Vite client + React Refresh preamble
  - `entry-client.tsx`:
    - reads `window.__PULSE_PRERENDER__`, `preloadRoutesForPath()`, then `hydrateRoot()`.
- **SSR server (Bun)**:
  - dev: uses Vite dev server in middleware mode + `ssrLoadModule("/src/entry-server.tsx")`
  - prod: imports `dist/server/entry-server.js`

## Pulse Server Integration (dev + prod)
Files: `packages/pulse/python/src/pulse/app.py`, `packages/pulse/python/src/pulse/proxy.py`, `packages/pulse/python/src/pulse/cli/cmd.py`
- **Dev stack (`pulse dev`)**:
  - Starts Vite dev server (`bun run dev`) + SSR server (`bun run ssr`) + Python server.
  - Python server proxies asset requests + HMR websocket to Vite (`DevServerProxy`).
  - Python server calls SSR server to render HTML (`/render`).
- **Prod build (`pulse build` / `pulse start`)**:
  - Vite builds client + SSR bundles; Python serves `dist/client` static assets.
  - Python calls SSR server (Bun) which uses `dist/server/entry-server.js`.
- **Route handshake**:
  - Python SSR path match → routes list + `routeInfo`
  - Client router updates `routeInfo` on SPA nav; server uses it for route context and prerender.

## Mental Model: What Changed vs React Router
- Route tree is data from codegen, not JSX.
- Router is a tiny state machine: match → preload → prerender fetch → render module.
- Code splitting is now aligned to routes via dynamic imports in `routeLoaders`.
- SSR relies on `preloadRoutesForPath()` to ensure route modules are loaded on server + client before render/hydrate.
