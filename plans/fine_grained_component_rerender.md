# Pulse fine-grained component re-render plan

Goal: stop full-route re-render on any state change. Each server component gets its own reactive effect; state changes re-run only affected components. If multiple affected components are ancestor/descendant, only the highest scheduled effect runs (React-like, Solid-style hierarchy).

## Current baseline (summary)
- Route mount has one render Effect in `packages/pulse/python/src/pulse/render_session.py` `_create_render_effect`.
- `RenderTree` renders + reconciles full tree in `packages/pulse/python/src/pulse/renderer.py`.
- Reactive system already has Effect + Scope + parent/child effect hierarchy in `packages/pulse/python/src/pulse/reactive.py`.

## Proposed architecture
### Per-component render effects (RenderEffect subclass)
- Each `PulseNode` owns a **RenderEffect** (subclass of `Effect`) created once and never replaced.
- RenderEffect behavior:
  - **Immediate on creation** for first render (no manual `run()` call)
  - **Immediate on schedule** for updates (no batch delay)
  - Runs component function, reconciles subtree, emits ops scoped to component path
- RenderEffect uses `Scope` to capture deps (signals/computeds read during render) so updates trigger only this component.
- Effect hierarchy mirrors component tree: parent RenderEffect owns child RenderEffects created during its render.

### Effect hierarchy and dedupe
- When multiple render effects are scheduled, only the highest ancestor runs. Descendant render effects are skipped (they will be re-rendered during parent reconcile).
- Implement dedupe in `Batch.flush` by checking `effect.parent` chain for scheduled **RenderEffect** instances.
- **Important:** RenderEffect updates must go through the batch to allow dedupe. Use immediate on **creation**, but override `schedule()` to enqueue instead of running immediately.
- Parent re-render **does not dispose** child render effects unless the child is unmounted/replaced. Dedupe only skips the redundant *queued* run.

### RenderTree becomes update dispatcher
- `RenderTree` becomes responsible for:
  - keeping root element
  - storing callbacks registry
  - collecting ops from component effects
  - ensuring update operations are path-correct

### Path-aware component runtime
- Each component instance needs a stable runtime structure with:
  - `path` (string path in tree)
  - `effect` (RenderEffect, created once)
  - `hooks`
  - current `contents`
- On reconcile, if component moves or re-keys, update `path` and rebase callback keys for its subtree.

### Callback registry maintenance
- Callbacks are keyed by `path.prop`. On subtree re-render, rebuild callbacks for that subtree and drop stale ones for the old path prefix.
- When nodes move via reconciliation, update callback paths for moved subtrees (server side only).

## Design sketch (code examples)

### 1) RenderEffect subclass + stable component runtime (create once, immediate)
```python
# in packages/pulse/python/src/pulse/reactive.py
class RenderEffect(Effect):
    # immediate semantics on creation + schedule
    def __init__(self, fn: EffectFn, *, name: str | None = None, on_error: Callable[[Exception], None] | None = None):
        super().__init__(fn, name=name, immediate=True, lazy=False, on_error=on_error)

    def schedule(self):
        if self.paused:
            return
        rc = REACTIVE_CONTEXT.get()
        rc.batch.register_effect(self)
        self.batch = rc.batch

# in packages/pulse/python/src/pulse/renderer.py
class ComponentRuntime:
    effect: RenderEffect | None
    path: str
    rendered: bool

class PulseNode:
    # add fields
    runtime: ComponentRuntime | None

class Renderer:
    def _ensure_component_runtime(self, node: PulseNode, path: str) -> ComponentRuntime:
        if node.runtime is None:
            node.runtime = ComponentRuntime(effect=None, path=path, rendered=False)
        else:
            node.runtime.path = path
        return node.runtime

    def render_component(self, component: PulseNode, path: str) -> tuple[VDOM, PulseNode]:
        rt = self._ensure_component_runtime(component, path)
        if component.hooks is None:
            component.hooks = HookContext()

        def run_component() -> None:
            with component.hooks:
                rendered = component.fn(*component.args, **component.kwargs)
            if component.contents is None:
                vdom, normalized = self.render_tree(rendered, path)
                component.contents = normalized
                rt.rendered = True
                rt._last_vdom = vdom
            else:
                component.contents = self.reconcile_tree(component.contents, rendered, path)
                # ops emitted by reconcile_tree

        if rt.effect is None:
            rt.effect = RenderEffect(run_component, name=f"component:{component.name or 'anon'}")

        # Initial render is handled by immediate run in RenderEffect.__init__
        return rt._last_vdom, component
```

### 2) RenderEffect on reconcile (component-only update)
```python
# in reconcile_component
rt = self._ensure_component_runtime(current, path)
if rt.effect is None:
    rt.effect = RenderEffect(lambda: self._rerender_component(current, path), name=...)

# schedule on state change (effect deps captured during render)
# on reconcile, run once now; later state changes schedule
self._rerender_component(current, path)
```

### 3) Dedupe in reactive batch (RenderEffect only)
```python
# in packages/pulse/python/src/pulse/reactive.py
# in Batch.flush
scheduled = list(self.effects)
# drop child render effects if ancestor render effect is also scheduled
filtered: list[Effect] = []
for eff in scheduled:
    if not isinstance(eff, RenderEffect):
        filtered.append(eff)
        continue
    parent = eff.parent
    skip = False
    while parent is not None:
        if isinstance(parent, RenderEffect) and parent in self.effects:
            skip = True
            break
        parent = parent.parent
    if not skip:
        filtered.append(eff)
self.effects = filtered
```

### 4) Callback registry path pruning
```python
# in RenderTree or Renderer

def drop_callbacks_with_prefix(prefix: str) -> None:
    for key in list(self.callbacks.keys()):
        if key == prefix or key.startswith(prefix + "."):
            del self.callbacks[key]
```

## Implementation phases

### Phase 0: Prep + invariants
- Add `ComponentRuntime` container + fields on `PulseNode` in `packages/pulse/python/src/pulse/transpiler/nodes.py`.
- Add clear lifecycle: `unmount_element` disposes component runtime effect and hook context.
- Add guardrails: ensure `PulseContext` is set during render/effect; keep existing error routing in render session.

Files:
- `packages/pulse/python/src/pulse/transpiler/nodes.py`
- `packages/pulse/python/src/pulse/renderer.py`
- `packages/pulse/python/src/pulse/context.py` (if new helpers needed)

Tests:
- extend `packages/pulse/python/tests/test_renderer.py` unmount cases to assert effect disposed.

### Phase 1: Component-level render effects
- Refactor `Renderer.render_component` + `reconcile_component` to:
  - set up runtime
  - run component with `HookContext`
  - create RenderEffect once (no replacement)
  - RenderEffect uses immediate semantics on schedule but does not auto-run in `__init__`
- Ensure effect captures deps by running component in `Scope` inside `Effect._execute` (already in reactive system).

Files:
- `packages/pulse/python/src/pulse/renderer.py`
- `packages/pulse/python/src/pulse/reactive.py`

Tests:
- add test: state change inside nested component triggers only that component ops (no parent ops). Use small test state + inspect ops length.

### Phase 2: Replace route-level render effect
- In `RenderSession._create_render_effect`, stop creating a single effect per route.
- Instead create only initial render for root + rely on component effects for updates.
- Ensure `RenderSession.flush()` still flushes reactive batch to deliver queued component effects.
- Keep mount idle/pause: pause all component effects in route mount when idle; resume on attach.

Files:
- `packages/pulse/python/src/pulse/render_session.py`
- `packages/pulse/python/src/pulse/renderer.py` (add `pause_all_effects`/`resume_all_effects` traversal helpers)

Tests:
- update `packages/pulse/python/tests/test_render_session.py` to assert updates still emitted.

### Phase 3: Effect hierarchy dedupe
- Set `effect.parent` links using reactive `Scope` already built; ensure render effects created inside parent render effect so hierarchy matches component tree.
- Implement render-effect dedupe in `Batch.flush` (skip child render effects when parent scheduled).
- Add test: when both parent and child deps change in same batch, only parent effect runs (assert child effect run count stays same).

Files:
- `packages/pulse/python/src/pulse/reactive.py`

Tests:
- new tests in `packages/pulse/python/tests/test_reactive.py` or new test file for render-effect hierarchy.

### Phase 4: Callback registry + path moves
- On reconcile moves, update component runtime `path` and prune old callback keys for that subtree, rebuild during render.
- Ensure reconciliation that reuses nodes updates callback paths for moved subtrees (server-side mirror of JS `rebindCallbacksInSubtree`).

Files:
- `packages/pulse/python/src/pulse/renderer.py`
- `packages/pulse/python/src/pulse/renderer.py` tests for callback rebind after reorder

Tests:
- extend `test_renderer.py` to assert callback keys update after keyed reorder.

### Phase 5: Cleanup + docs
- Update internal docs or comments in `packages/pulse/python/README.md` if necessary.
- Add developer note in `notes.md` if needed.

## Affected files (expected)
- `packages/pulse/python/src/pulse/renderer.py`
- `packages/pulse/python/src/pulse/transpiler/nodes.py`
- `packages/pulse/python/src/pulse/reactive.py`
- `packages/pulse/python/src/pulse/render_session.py`
- `packages/pulse/python/tests/test_renderer.py`
- `packages/pulse/python/tests/test_render_session.py`
- `packages/pulse/python/tests/test_reactive.py` (new or existing)

## Test plan
- `make test` (or targeted: `uv run pytest packages/pulse/python/tests/test_renderer.py` + render_session + reactive)
- Add new unit tests:
  - component-only re-render
  - parent+child deps change in same batch => only parent effect runs
  - callback paths updated on keyed reorder
  - pause/resume stops/starts component effects

## Open questions
- Should render effects be immediate or lazy? (recommend lazy; explicit render on mount + manual schedule on dep changes)
- Should route idle state dispose effects or pause? (recommend pause to preserve state; dispose on detach)
- How to handle render effects created in query/state effects? Ensure render effects only created during component render, not in computed.
