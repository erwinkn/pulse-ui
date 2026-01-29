# Plan

Using create-plan skill, implement React-like re-rendering: track deps per component, mark dirty on signal changes, and run a single render pass from each route root with bailouts and dirty-desc traversal.

## Scope
- In: component runtime tree, DirtyObserver dep tracking, root render pass scheduler, callback/path fixes, tests.
- Out: full Solid ownership semantics for all effects, public API changes, JS client changes.

## Action items
[ ] Add `ComponentRuntime` to `PulseNode` (parent/children/dirty/has_dirty_desc/observer/path) and wire lifecycle/unmount in `packages/pulse/python/src/pulse/transpiler/nodes.py` and `packages/pulse/python/src/pulse/renderer.py`.
[ ] Implement `DirtyObserver` in `packages/pulse/python/src/pulse/reactive.py` and allow `Signal.obs`/`Computed.obs` to include it (subscribe/unsubscribe + last_change bookkeeping).
[ ] Wrap component render in `Scope()` in `packages/pulse/python/src/pulse/renderer.py`, update observer deps after each render, and keep runtime tree in sync with reconciliation.
[ ] Add React-like render traversal (dirty + has_dirty_desc) and op aggregation in `packages/pulse/python/src/pulse/renderer.py` (or helper class), ensuring clean parent still descends into dirty children.
[ ] Replace route-level render Effect with a coalesced scheduler in `packages/pulse/python/src/pulse/render_session.py` that triggers a single render pass per tick per route mount.
[ ] Handle keyed moves: update runtime paths and prune/rebuild callback registry for moved subtrees in `packages/pulse/python/src/pulse/renderer.py`.
[ ] Update tests: dirty parent+child renders once, clean parent+dirty child renders child only, observer dep updates, callback keys after reorder (`packages/pulse/python/tests/test_renderer.py`, `packages/pulse/python/tests/test_render_session.py`, `packages/pulse/python/tests/test_reactive.py`).
[ ] Document new render model in `packages/pulse/python/README.md` or `notes.md`.

## Open questions
- Per-route scheduler only, or allow a shared global scheduler?
- Any feature flag needed for rollout or benchmarking?
- Do we need a dev-mode trace to show dirty traversal for debugging?
