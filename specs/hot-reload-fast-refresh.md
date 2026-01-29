# Hot Reload Fast Refresh (state preservation)

## Goal
- Keep component state when code changes are compatible.
- Remount only the components that become incompatible.

## Non-goals
- Preserve state across class layout changes for `State` subclasses.
- Support dynamic component factories without source.

## Component identity
- Add to `Component`:
  - `component_id: str` = `"{module}:{qualname}"`.
  - `signature_hash: str | None`.
- Add to `PulseNode`:
  - `component_id: str`.
  - `signature_hash: str | None` (copied from component).
- Add registries in `component.py`:
  - `COMPONENT_BY_ID: dict[str, Component]`.
  - `COMPONENT_ID_BY_CODE: dict[CodeType, str]`.
- When `Component` is created:
  - register `component_id`.
  - register `fn.__code__` -> `component_id`.

## Renderer changes
- `same_node()`:
  - For `PulseNode`, compare `component_id` + `key` (ignore `fn` equality).
- `reconcile_component()`:
  - If `previous.signature_hash != current.signature_hash`:
    - `unmount_element(previous)`.
    - render fresh tree (reset hooks/state).
  - Else reuse `previous.hooks` and `previous.contents`.

## Signature computation
- New helper: `pulse.hot_reload.signatures.compute_component_signature(fn)`.
- Steps:
  - `inspect.getsource(fn)`; if missing -> return `None`.
  - `ast.parse` and locate function body node.
  - Walk AST and collect hook calls in order:
    - `ps.state(...)`
    - `ps.effect(...)` (decorator or inline)
    - `ps.init()`
    - `ps.setup(...)`
  - Each entry: `kind`, `key_literal` (if constant), `lineno`, `col`.
  - `signature_hash = sha1(json.dumps(list))`.
- Store `signature_hash` on Component.

## Component dependency analysis
- Goal: only refresh components whose direct/indirect deps changed.
- New helper: `pulse.hot_reload.deps.compute_component_deps(fn) -> set[str]` where values are module names.
- Inputs:
  - AST import walk (like `hooks.init` uses AST) to capture local imports inside component body.
  - `pulse.transpiler.function.analyze_deps(fn)` to capture referenced globals/functions/modules.
- Output rules:
  - Only include reloadable, local modules (ModuleIndex.reloadable).
  - Resolve symbols to module names via `inspect.getmodule(obj)` fallback to globals.
  - If resolution fails, mark component as `unknown_deps=True` (forces refresh on any dirty module).
- Store on Component:
  - `deps: set[str]`
  - `unknown_deps: bool`

## Using dependency info
- During hot reload:
  - Compute dirty module set from ModuleGraph.
  - Refresh signature only for components where:
    - `component.unknown_deps` is True, or
    - `component.deps` intersects dirty set, or
    - component’s own module is dirty.
  - Components not in scope keep existing hooks + contents unchanged.

## Hook identity for dev
- Add to `HookContext`:
  - `component_id: str | None`.
  - `hook_index: int`.
  - `hot_reload_mode: bool`.
- In `Renderer.render_component()`:
  - Set `component_id` + `hook_index=0` on `HookContext`.
  - Set `hot_reload_mode` only when HotReloadManager is active.
- In `ps.state()` + inline `ps.effect()` + `ps.init()`:
  - If `hot_reload_mode` and `component_id` set and signature is known:
    - use `(component_id, hook_index, key)` as identity.
    - increment `hook_index` per hook call.
  - Else fallback to current callsite-based identity.
- If `signature_hash` is `None`: force remount on hot reload.

## Compatibility rules
- If signature hash unchanged: preserve state and hooks.
- If signature changed: remount component.
- If component id changed (rename/move): remount.
- If `State` subclass layout changed (fields/computed/effect names):
  - keep instance if class name + module unchanged,
  - but reset computed/effect instances on next access.

## Logging
- When remounting due to signature mismatch:
  - log `component_id`, old/new hash, file.

## Tests
- Edit component body (no hook changes) -> state preserved.
- Add/remove `ps.state` call -> component remount.
- `ps.state(key=...)` preserves state even if hook order changes.
- `ps.init()` state preserved when signature stable.
