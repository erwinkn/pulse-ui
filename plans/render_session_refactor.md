# RenderSession Refactor Plan

## Goals
- Introduce `RenderSession.receive` as the single entry point for client messages, routing to private helpers instead of exposing `mount`, `navigate`, `execute_callback`, etc.
- Simplify rendering primitives so the session only performs “render” and “rerender” operations, eliminating the ad-hoc `prerender_mount_capture` flow.
- Stop storing `server_address` / `client_address` on `RenderSession`; rely on `PulseContext.get().app` whenever we need those values.

## Proposed Design

### Message Dispatch
- Add `RenderSession.receive(self, message: ClientPulseMessage) -> None` that normalizes/validates incoming payloads and then calls private `_mount`, `_rerender`, `_navigate`, `_unmount`, `_handle_callback`, `_handle_api_result`, etc.
- Convert current public helpers (`mount`, `execute_callback`, `navigate`, `unmount`, `handle_api_result`) into private methods; adjust internal callers and tests accordingly.
- Update `App._handle_pulse_message` to delegate to `render.receive(msg)` so middleware stays in `App`, but RenderSession owns the dispatch details.
- Align tests that previously called the public helpers directly so they exercise `receive` (or the new private methods via test hooks/mocks as needed).

### Rendering Lifecycle
- Replace `prerender_mount_capture` with a cohesive rendering pipeline:
  - `render_route(path, route_info, *, mode="initial" | "prerender") -> RenderResult` creates the mount (if needed), installs the render `Effect`, runs the initial render, and returns a structured response (`RenderInit` with vdom, callbacks, css). When the session is not yet connected (prerender), the effect still queues messages against the buffer; we only avoid mutating `_send_message` while capturing the init payload.
  - `rerender_route(path) -> RenderUpdate | None` runs diffs on an already mounted route and returns the update ops (or `None` if no changes).
  - `RenderResult` objects will be simple dataclasses/TypedDicts used by both websocket mounts and HTTP prerender.
- Mount effects call into `render_route`/`rerender_route` instead of manually duplicating render logic. Effect body becomes a thin wrapper that decides between init vs diff and emits the appropriate server message.
- `App.prerender` reuses these helpers: create the session as today, call `render.render_route(..., mode="prerender")`, run `render.flush()` if needed, and return the captured `RenderInit`.

### Address Resolution
- Remove `_server_address` / `_client_address` from `RenderSession` and drop the corresponding `server_address`/`client_address` properties.
- Wherever address data is required (e.g., `RenderSession.call_api`, hooks in `pulse.hooks.runtime`, forms middleware), resolve them via `PulseContext.get().app.server_address` / `PulseContext.get().app.client_address`.
- Ensure contexts are established before those lookups (prerender/middleware already wraps calls in `PulseContext.update`); add explicit error messages when the context is missing.
- Update `App.create_render` to stop providing addresses to the constructor; instead it should stash the latest client address on the session or app as needed for context access.

## Implementation Steps
1. Introduce `RenderResult` / `RenderUpdate` data structures and refactor render logic to produce them (initial and diff phases).
2. Replace `prerender_mount_capture` with the new render helpers; update `App.prerender` and any other callers.
3. Add `RenderSession.receive`, convert existing message handlers into private methods, and adjust `App._handle_pulse_message` plus unit tests.
4. Remove address fields from `RenderSession`, migrate `call_api` (and any other access sites, including runtime hooks) to use `PulseContext.get().app`.
5. Refresh or expand tests for render flows (prerender, mount, rerender, callbacks) and address-sensitive features to cover the new API surface.

## Open Questions / Risks
- Validate that middleware still gets a chance to short-circuit messages before `RenderSession.receive` executes (plan assumes middleware runs in `App` before delegating).
- Ensure prerender contexts continue to flush effects deterministically after render refactor; may require explicit `flush_effects()` calls in tests.
- Confirm we can reliably access the most recent client address once it moves off the session (e.g., read it from `PulseContext.app`).
