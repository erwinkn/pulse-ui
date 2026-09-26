# Pulse custom framework redesign

Status: in progress (June 2026). This spec drives the rebuild of Pulse's
client/server foundation: removing React Router, making routing and navigation
Python-native, anchoring every rendered view to a unique ID, fine-grained
rendering, and client-side prefetching.

## Goals

1. **Custom React framework.** Replace React Router (framework mode, loaders,
   SSR pipeline) with a small purpose-built router + SSR setup. React Router is
   retrofitted into an unusual use case today; we only need route matching,
   history management, outlets, links, and code splitting.
2. **Python-native routing & navigation.** The Python route tree is the single
   source of truth. Navigation flows through the Pulse protocol (WebSocket)
   instead of React Router client loaders + HTTP prerender fetches.
3. **View identity.** Rename backend "mount" to **view**. Every view has a
   unique server-generated ID. All view-scoped protocol messages carry the view
   ID instead of a route path, eliminating the (path, mount_id) workarounds.
4. **Fine-grained rendering.** Each server component gets its own reactive
   render effect; state changes re-render only the affected component subtree,
   not the whole route. VDOM + expressions stay seamlessly interwoven in the
   wire format.
5. **Prefetching.** Links can prefetch both the route's JS chunks and the
   server-rendered VDOM (on hover/viewport), making navigation instant.

## Prior art in this repo

- `origin/minimal-react`: complete React Router removal experiment (Jan 2026,
  on a stale base). Source for the router (`js/src/router/`), SSR entries,
  codegen templates. Ported, not merged.
- `origin/minimal-pulse-router`: POC + `code-review.md` documenting issues to
  fix (initial module load, nav races, popstate unknown routes,
  protocol-relative URLs, error surfacing).
- `origin/fine-grained-rerender`: plan doc for per-component render effects.
- split/02..09 PR stack (merged into this branch): renderable serialization,
  channel lifecycle + hooks, reconnect resume, route-local hydration,
  notification payload cleanup.

## Architecture

### View identity (server)

- `View` replaces `RouteMount` (`render_session.py`). A view = one rendered
  route/layout instance for one client, identified by `View.id` (uuid hex),
  created at prerender/navigation time.
- `RenderSession.views: dict[str, View]` keyed by view ID. Path remains an
  attribute (`view.route_path` pattern + `view.route` runtime info).
- View lifecycle states stay: `pending → active → idle/closed`, with pending
  queues + TTL (reused for prefetch).
- Channels bind to `view.id` (replaces `(route_path, mount_id)` pair from
  split/04). Detach/remount produces a new view ID, so stale actors are
  rejected naturally.
- Resume handshake declares views by ID.

### Protocol

All view-scoped messages carry `view` (the ID):

- server → client: `vdom_init {view, vdom}`, `vdom_update {view, ops}`,
  `js_exec {view, ...}`, `server_error {view?, ...}`, `attach_ack {view}`.
- client → server: `attach {view, routeInfo}`, `callback {view, key, args}`,
  `update {view, routeInfo}`, `detach {view}`.
- Channel messages carry `view` when route-bound (replaces `path`).
- `navigate_to` (server-initiated) carries the origin `view` for staleness
  checks.

### Navigation (WS-native)

- Client router matches locally (mirror matcher) to know which JS chunks to
  load, then sends `navigate {nav, url, routeInfo, keep: [viewIds]}` over the
  socket. `nav` is a client sequence number; stale responses are dropped.
- Server: matches the URL against the Python route tree, runs redirect
  middleware, computes the view set (reusing `keep` views whose route pattern
  still matches — layouts persist across sibling navigation), renders new
  views, and replies `server_navigate {nav, location, views: [{id, routePath,
  vdom?}]}`. Removed views are disposed server-side; the client detaches them
  implicitly.
- Because everything flows on one socket, updates to surviving views and the
  navigation response are naturally ordered (the old HTTP prerender + WS
  update combination had no ordering guarantee).
- First load stays HTTP: SSR fetches `/_pulse/prerender`, which returns the
  same view-set payload + directives; the client attaches by view ID after
  connecting.
- Server-initiated `navigate_to` is handled by the client router exactly like
  a link click.

### Custom router (client)

`packages/pulse/js/src/router/`, adapted from minimal-react with the POC
review fixes:

- `match.ts` — mirrors Python matching: static > dynamic `:x` > optional
  `:x?` > splat `*`; layouts are pathless nodes; deepest static-preferred
  match wins.
- `context.tsx` — `PulseRouterProvider`: location state machine, popstate
  handling, navigation sequencing (token per navigation, out-of-order
  completions dropped), error surfacing.
- `link.tsx` — `Link` with `prefetch` prop (`intent` | `viewport` | `render` |
  `none`).
- `outlet.tsx`, `scroll.ts` (restoration), `hash.ts`, navigation progress UI.
- Fixes from POC review: initial modules loaded before first render (no blank
  page), popstate to unknown route → hard navigation, `//host` treated as
  external, navigation errors surface in UI + revert.

### Codegen

`web/app/pulse/` now contains:

- `routes.ts` — `pulseRouteTree` (serializable data) + `routeLoaders`
  (`{ [routeId]: () => import("./routes/...") }`) as code-splitting points.
- Per-route modules — default-export components rendering `<PulseView>` with
  their registry (unchanged in spirit).
- `app.tsx` — `PulseApp` shell composing `PulseRouterProvider` →
  `PulseProvider` → `PulseRoutes`.
- No `_layout.tsx` loaders, no `@react-router/dev` route config.

### SSR + dev server

- `web/` gets `index.html`, `src/entry-client.tsx`, `src/entry-server.tsx`,
  `server/ssr.ts` (Bun), plain Vite config (no react-router plugin).
- Dev (`pulse run`): Python server + Bun SSR server with Vite middleware mode
  (HMR preserved for user components). Python proxies page requests to SSR.
- Prod (`pulse build` / `pulse start`): Vite client + SSR builds; Python
  serves static assets, Bun SSR renders HTML from the manifest. Fixes the
  minimal-react prod 404 (`/src/entry-client.tsx`) by emitting hashed bundle
  references from the manifest.

### Fine-grained rendering (server)

Per the fine-grained plan doc:

- `RenderEffect(Effect)` per `PulseNode`, created on first render, immediate
  on creation, batched on schedule.
- Batch flush dedupe: a scheduled render effect is skipped when an ancestor
  render effect is also scheduled (the parent re-render covers it).
- Component runtime: stable `path`, `hooks`, `effect`; reconciliation moves
  rebase paths and callback registry keys (prefix pruning).
- Ops from component effects accumulate on the owning `View` and flush as one
  `vdom_update` per reactive batch.
- The wire format (VDOM + exprs + callbacks + render props interwoven) is
  unchanged; ops just get more precise paths.

### Prefetching

- Chunks: `Link` warms `routeLoaders` imports on intent/viewport.
- VDOM: `prefetch {url, routeInfo}` over WS → server creates **pending** views
  (TTL'd, queueing updates) and returns the same payload shape as
  `server_navigate`, minus the location commit. The client caches it keyed by
  URL (short TTL). A subsequent navigation consumes the cache and attaches,
  which activates the pending views and flushes whatever queued.
- Races: prefetch responses are keyed by URL, never alter location; a
  navigation always re-validates against the live route tree server-side.

## Implementation order

1. View identity rename + protocol (server, client, channels, resume).
2. Custom router + codegen + SSR/dev-server (React Router removed).
3. WS-native navigation.
4. Prefetching.
5. Fine-grained rendering.
6. Examples, docs, browser-verified QA at each step.
