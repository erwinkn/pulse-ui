# Pulse Logging Improvements Plan

## Goals
- Standardize the developer-facing logs emitted by the CLI and server so every line is left-aligned, timestamp-free, and categorized as `[server]`, `[framework]`, or `[user]`.
- Highlight the “Pulse running at …” announcement with intentional indentation while keeping all other output flush-left.
- Encode both the source and severity level (debug/info/warning/error/critical) in every rendered line so it reads like `[server] INFO …`.
- Offer an ergonomic API for app authors to emit colored logs (and optionally auto-upgrade plain `print` usage) that show up under the `[user]` tag via a callable `ps.log`.
- Expose a logging configuration on `App` that lets users opt into timestamps and override the per-source color palette.

## Current Pain Points
- `packages/pulse/python/src/pulse/cli/cmd.py` uses `rich.Console.log`, which injects timestamps and varies indentation.
- `packages/pulse/python/src/pulse/cli/processes.py` prints `[tag]` prefixes, but the formatting logic is duplicated and hard-coded to two tags.
- Inside the server process, Pulse modules rely on the standard `logging` module while user apps commonly use bare `print`, so their output inherits uvicorn’s default format and is interleaved with reload watcher noise.
- There is no central place to configure colors or categories, making it hard to expand beyond the current `[server]/[web]` split.

## Proposed Architecture
- Introduce a `pulse.logging` package that exposes:
  - A shared ANSI-aware formatter that renders `[tag] LEVEL: message` without timestamps.
  - Utility functions (`log_server`, `log_framework`, `log_user`) plus a factory returning standard `logging.Logger` objects wired to the formatter.
  - A callable `ps.log` object that can be used directly (`ps.log("Loaded widgets")`) or via level-specific attributes (`ps.log.info("...")`, `ps.log.warning("...")`, etc.), defaulting to the `[user]` source.
  - A dual-purpose `StdStreamInterceptor` that can wrap `sys.stdout`/`sys.stderr` and forward captured text to the `[user]` channel while preserving flush semantics, but can be bypassed internally by framework loggers.
- Update the CLI to create a single `PulseConsole` instance responsible for all informational output, ensuring consistent indentation rules and color mapping.
- Replace the direct `python -m uvicorn` invocation with a thin Pulse-managed entrypoint that:
  - Applies the shared logging configuration (covering uvicorn loggers, `pulse.*`, and user interceptors) before delegating to uvicorn.
  - Installs the stdout/stderr interceptor so user `print` calls (and other writes) appear as `[user]`.
- Extend `execute_commands` so it defers to the shared formatter, supports the new `[framework]`/`[user]` tags.

## Implementation Steps
1. **Inventory & acceptance criteria**
   - Audit existing `Console.log` and `logging.getLogger` usage across `packages/pulse/python/src/pulse/**` to list the call sites that must move onto the new API.
   - Document the expected color palette for each tag (e.g. `[server]` cyan, `[framework]` magenta, `[user]` green) so validations are clear.
2. **Shared logging utilities**
   - Add `packages/pulse/python/src/pulse/logging/__init__.py` (or similar) defining the formatter, color map, category helpers, and stdout interceptor.
   - Provide a lightweight user-facing helper (e.g. `pulse.log("message")` or `pulse.logger("topic")`) that pipes through the `[user]` channel unless overridden.
3. **CLI output refactor**
   - Swap `Console.log` calls in `packages/pulse/python/src/pulse/cli/cmd.py` (and helpers such as `dependencies.py`) with the new `PulseConsole`, configuring it with `log_time=False` and the shared formatter.
   - Adjust `_announce()` so only the “Pulse running at …” block keeps indentation, while surrounding lines leverage the new helper for left-aligned output.
   - Update `_run_dependency_plan` and error paths to emit `[server]`-tagged messages via the centralized logger.
4. **Process runner cleanup**
   - Rework `_write_tagged_line` in `packages/pulse/python/src/pulse/cli/processes.py` to use the shared formatter and expand the color map to `{server, framework, user}`.
   - Ensure PTY and non-PTY flows both normalize whitespace (strip trailing `\r`, collapse multi-line chunks) without reintroducing timestamps.
5. **Server entrypoint & uvicorn integration**
   - Keep `pulse run` in a single process: perform Pulse logging setup inside `cmd.py` immediately before invoking uvicorn programmatically.
   - Replace the external `python -m uvicorn` subprocess with a call to `uvicorn.main.main()` (or `uvicorn.run`) after initialization so we still support reload and extra args.
   - Patch the uvicorn logging configuration so uvicorn access/error logs map to `[server]`, while `logging.getLogger("pulse")` and children map to `[framework]`.
   - Ensure framework loggers emit directly to the configured handler (bypassing `StdStreamInterceptor`) so intercepted stdout/stderr is reserved for user output.
   - Feed server-wide logging preferences from the app configuration (colors, optional timestamps) into the setup routine.
6. **Framework adoption & configurability**
- Add a logging configuration to `pulse.app.App` (e.g. `logging=PulseLoggingConfig(...)`) with defaults that disable timestamps and set color overrides for server/framework/user.
- Propagate the config through the logging setup so CLI and server runners respect per-app preferences.
- Replace plain `logging.getLogger(__name__)` calls in Pulse modules with the new logger factory so they default to the `[framework]` tag while emitting level metadata.
- Evaluate existing `print` calls (e.g. `user_session.py`) and convert them to explicit framework or user log calls as appropriate.
7. **User experience polish**
   - Expose documentation (README snippet or docstring) explaining how users can:
     - Opt into the provided logger helper for structured logs, and
     - Disable/override automatic `print` interception if needed.
   - Confirm that `pulse generate` and other CLI commands retain sensible output using the same infrastructure.
8. **Validation & cleanup**
   - Write unit tests for the formatter and stdout interceptor (multi-line handling, color stripping for tests, presence of level labels).
   - Extend CLI integration tests (`packages/pulse/python/tests/test_cli.py`) to assert the absence of timestamps and presence of the correct tags.
   - Manual smoke test by running `pulse run examples/main.py` and verifying log categories, colors, indentation, and the `[user]` capture with sample `print` statements.

## Testing Strategy
- `uv run pytest packages/pulse/python/tests/test_cli.py` plus targeted new tests under `packages/pulse/python/tests/test_logging.py`.
- `pulse run examples/main.py` (dev mode) to visually confirm formatting, then `pulse run --server-only` to ensure no regressions with omitted web process.
- `make lint` / `make format` before submitting the final patchset.
