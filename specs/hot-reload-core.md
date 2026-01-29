# Hot Reload Core (v1)

## Goals
- Watch app + local framework files.
- Hot patch in-process when safe.
- Default to client or process reload when unsafe.
- Preserve unaffected state and mounts.

## Non-goals
- Perfect state retention across edited components (see fast refresh spec).
- Reloading site-packages or stdlib.
- Prod support.

## Enablement
- Dev only (`env.pulse_env == "dev"`).
- New env:
  - `PULSE_HOT_RELOAD=1|0`.
  - `PULSE_HOT_RELOAD_DIRS` (os.pathsep list).
  - `PULSE_HOT_RELOAD_EXCLUDES` (os.pathsep list of globs).
  - `PULSE_HOT_RELOAD_TRIGGER` (path for process reload trigger).
- New App fields:
  - `App._hot_reload: HotReloadManager | None`.
  - `App._hot_reload_in_progress: bool`.

## New module: `pulse/hot_reload.py`

### Types
- `HotReloadManager`
  - `app: App`
  - `watch_roots: list[Path]`
  - `exclude_globs: list[str]`
  - `debounce_ms: int = 250`
  - `trigger_path: Path | None`
  - `task: asyncio.Task | None`
  - `lock: asyncio.Lock`
  - `last_error: HotReloadError | None`
- `HotReloadPlan`
  - `changed_paths: set[Path]`
  - `python_paths: set[Path]`
  - `module_names: list[str]`
  - `requires_client_reload: bool`
  - `requires_process_reload: bool`
  - `reason: str | None`
- `ModuleIndex`
  - `by_file: dict[Path, ModuleInfo]`
  - `by_name: dict[str, ModuleInfo]`
- `ModuleInfo`
  - `name: str`
  - `file: Path`
  - `package_root: Path`
  - `reloadable: bool`
- `ModuleGraph`
  - `deps: dict[str, set[str]]`  # module -> modules it imports
  - `rdeps: dict[str, set[str]]` # module -> reverse deps
  - `build_from_ast(index: ModuleIndex) -> ModuleGraph`
  - `dirty_set(changed: set[str]) -> set[str]` (transitive rdeps)
- `AppSignature`
  - `mode, api_prefix, not_found`
  - `codegen.web_dir, codegen.pulse_dir`
  - `routes_signature: tuple[...]`
  - `middleware_signature: tuple[str, ...]`
  - `plugin_signature: tuple[str, ...]`

### Watch roots
- Build once at startup:
  - `env.pulse_app_dir` if set.
  - Roots from `sys.modules` where `__file__` is under cwd and not in
    `site-packages` or `dist-packages`.
  - Extra from `PULSE_HOT_RELOAD_DIRS`.
- Exclude globs (always):
  - `**/__pycache__/**`, `**/.git/**`, `**/.venv/**`, `**/node_modules/**`.
  - `web_root/app/<pulse_dir>/**` (generated).
  - `**/.pulse/**`.
- Include by extension:
  - `*.py`, `*.pyi`, `*.toml`, `*.yaml`, `*.yml`, `*.json`.

### Watch loop
- Use `watchfiles.awatch(*watch_roots, stop_event=...)`.
- Coalesce changes within `debounce_ms`.
- Drop empty change sets.

## Plan building
- Normalize paths to `Path.resolve()`.
- Split into:
  - python changes (`.py`, `.pyi`).
  - config changes (`.toml`, `.yaml`, `.yml`, `.json`).
- Map python files to modules via `ModuleIndex`:
  - if missing and under watch root: mark `requires_process_reload=True`.
- Build `ModuleGraph` from AST import statements of reloadable modules.
- Dirty set:
  - `dirty = graph.dirty_set(changed_modules)` (includes rdeps).
  - If cycle or parse error: `requires_process_reload=True`.
- If app target file changed (`env.pulse_app_file`):
  - load new App via new helper `load_app_for_hot_reload()` (no CLI logger).
  - build `AppSignature` for current + new.
  - If `mode`, `api_prefix`, cookie/session config, or middleware/plugins differ:
    - `requires_process_reload=True`.
  - If route tree shape differs:
    - `requires_client_reload=True`.
  - If codegen cfg differs:
    - `requires_client_reload=True`.

## Reload execution
- `HotReloadManager.reload(plan)`
  - Acquire `lock`.
  - Set `app._hot_reload_in_progress=True`.
  - Pause renders:
    - New `RenderSession.pause_updates()` to pause effects + queue renders.
  - Clear transpiler caches:
    - `clear_function_cache()`.
    - `clear_import_registry()`.
    - `clear_asset_registry()`.
  - `importlib.invalidate_caches()`.
- Reload modules:
  - Sort by topo order (deps first). If not possible, fallback to depth order.
  - Reload all in `dirty` set (`importlib.reload`).
  - On exception:
    - `requires_process_reload=True`.
    - store `last_error`.
    - skip patch steps.
  - If reload ok:
    - Refresh `ModuleIndex`.
    - If new App snapshot loaded:
      - `app.routes = new.routes`.
      - `app.codegen.routes = new.routes`.
      - `app.not_found = new.not_found`.
    - Run `app.run_codegen(...)` if not disabled.
    - Re-render:
      - For each `RenderSession` and each active `RouteMount`:
        - `new_root = mount.route.pulse_route.render()`
        - `ops = mount.tree.rerender(new_root)`
        - if `ops`: send `vdom_update`.
      - `session.flush()` to run effects.
  - Resume renders: `RenderSession.resume_updates()`.
  - If `requires_client_reload`: broadcast `ServerReloadMessage`.
  - If `requires_process_reload`:
    - send `ServerReloadMessage` (best-effort).
    - `touch(trigger_path)` if set, else `raise SystemExit(3)`.
  - Clear `app._hot_reload_in_progress`.

## Error handling
- Render errors during hot reload:
  - `render_session.report_error(..., details={"hot_reload": True})`.
- If reload error:
  - log stack once, store on manager for UI.

## Concurrency
- Single reload at a time (`lock`).
- Queue extra change sets; run last one after unlock.
- During reload, drop inbound callbacks or queue to avoid stale state.

## Tests
- Unit
  - `ModuleIndex` maps file->module, excludes site-packages.
  - `AppSignature` diff flags correct reload level.
- Integration
  - Edit component -> hot patch + `vdom_update`, no client reload.
  - Edit route tree -> client reload.
  - Syntax error -> process reload requested.
