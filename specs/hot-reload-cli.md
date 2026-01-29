# Hot Reload CLI + Process Reload

## Goals
- Enable hot reload by default in dev.
- Keep uvicorn reload only for process restart fallback.
- No new supervisor process.

## CLI flags
- Add to `pulse run`:
  - `--hot-reload/--no-hot-reload` (default: dev=true, prod=false).
  - `--hot-reload-dir` (repeatable).
  - `--hot-reload-exclude` (repeatable).
- Env mirrors:
  - `PULSE_HOT_RELOAD`, `PULSE_HOT_RELOAD_DIRS`, `PULSE_HOT_RELOAD_EXCLUDES`.

## Trigger file
- Path default:
  - `web_root/.pulse/hot-reload.trigger` if web_root exists.
  - else `app_dir/.pulse/hot-reload.trigger`.
- Ensure `.pulse/` is gitignored (reuse `ensure_gitignore_has`).
- Expose to server via `PULSE_HOT_RELOAD_TRIGGER`.

## build_uvicorn_command changes
- If hot reload enabled:
  - Keep `--reload` on.
  - Add `--reload-include` for trigger filename only.
  - Add `--reload-exclude "*.py"` to suppress default include.
  - Ensure `--reload-dir` contains trigger parent dir.
- If hot reload disabled:
  - Use current uvicorn reload behavior.

## Server start hook
- In `App.setup()` or `App.asgi_factory()`:
  - If hot reload enabled, start `HotReloadManager`.
  - Pass watch roots + excludes from env.
  - Pass trigger path from env.

## Fallback behavior
- On `requires_process_reload`:
  - server touches trigger file.
  - uvicorn reload restarts process.

## Tests
- CLI arg wiring sets env vars.
- Trigger file created + gitignored.
- Hot reload on -> uvicorn reload only fires on trigger.
