# Pulse CLI Refactor Plan

## Goals
- Decouple the `run` command into readable, testable units where the top-level function only orchestrates control flow.
- Replace implicit environment-variable signalling with explicit return values passed between helpers.
- Isolate heavyweight logic (dependency resolution, PTY handling, secret management) into focused modules.

## Target Structure
- `packages/pulse/python/src/pulse/cli/cmd.py`
  - Keep Typer command definitions and high-level orchestration.
  - Delegate to helpers for parsing flags, preparing contexts, building commands, and running processes.
- `packages/pulse/python/src/pulse/cli/helpers.py`
  - Return structured results for app loading (e.g., `AppLoadResult` with `app`, `app_file`, `app_dir`, `server_cwd`).
  - Eliminate environment side effects; callers set `env` values explicitly when needed.
- New module `packages/pulse/python/src/pulse/cli/secrets.py`
  - Provide `resolve_dev_secret(app_path: Path) -> str | None` encapsulating `.pulse` handling and gitignore updates.
- New module `packages/pulse/python/src/pulse/cli/dependencies.py`
  - Encapsulate registered component inspection, version resolution, and Bun commands. Export `prepare_web_dependencies(...) -> list[str] | None`.
  - Offer custom exception types for user-facing error messages.
- New module `packages/pulse/python/src/pulse/cli/processes.py`
  - House PTY management (`run_with_pty`) and Windows fallback. Accepts the command list and logging hooks.
- Optional utility module `packages/pulse/python/src/pulse/cli/models.py`
  - Define lightweight dataclasses/TypedDicts (`AppContext`, `CommandSpec`) shared across modules.

## Refactor Steps
1. **Introduce data models**
   - Define `AppLoadResult` and `CommandSpec` dataclasses.
   - Update `helpers.py` to populate and return `AppLoadResult` without mutating `env`.
2. **Rework app loading callers**
   - Adjust `cmd.py` (`run` and `generate`) to use `AppLoadResult`.
   - Set `env` fields in `run` just before building command specs.
3. **Extract secret management**
   - Move the `.pulse/secret` logic into `secrets.py`.
   - Replace inline code in `run` with a call to `resolve_dev_secret`.
4. **Isolate dependency resolution**
   - Move JS dependency logic into `dependencies.py`.
   - Provide a function returning the Bun command plus friendly errors; call it from `run`.
5. **Modularize process execution**
   - Move `run_with_pty` into `processes.py`; expose a simple `execute_commands(...)` API handling console output and cleanup.
   - Update `cmd.py` to call the new helper.
6. **Command assembly helpers**
   - Introduce small builders (`build_uvicorn_command`, `build_web_command`) to convert context into `CommandSpec`.
   - Ensure extra CLI flags are applied in one place.
7. **Cleanup and tests**
   - Update imports and typing across modules.
   - Add targeted unit tests for new helpers (app loading, dependency planner, PTY runner if feasible).
   - Run `make format`, `make lint`, and relevant tests.

## Test Updates
- All CLI helper tests live in `packages/pulse/python/tests/test_cli.py`. Update or add coverage for:
  - Revised `parse_app_target` behaviour and the new `AppLoadResult` shape.
  - `load_app_from_target` returning structured data without mutating global env.
  - `resolve_dev_secret` scenarios (new helper) including secret creation, reuse, and error handling.
  - `dependencies.prepare_web_dependencies` ensuring correct Bun commands and conflict reporting. Use monkeypatching to stub `registered_react_components`.
  - `processes.execute_commands` (PTY runner) to confirm tagging, streaming, and cleanup logic; rely on lightweight stubs or monkeypatching to avoid real processes.
- Augment `packages/pulse/python/tests/conftest.py` with fixtures/helpers needed by the consolidated tests (temporary web roots, fake components, etc.).

## Notes
- Windows-specific process handling can be revisited later; initial refactor will focus on UNIX PTY behaviour.
