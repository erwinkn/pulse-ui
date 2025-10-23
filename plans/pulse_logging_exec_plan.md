# Implement Pulse Logging Overhaul

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain this plan in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After completing this work, Pulse developers and app authors will see uniform, timestamp-free logs tagged with their source (`[server]`, `[framework]`, `[user]`) and severity level (`INFO`, `WARNING`, etc.). Users can call `ps.log("message")` or `ps.log.warning("...")` from their apps and have those lines show up under the `[user]` tag with consistent coloring. The CLI will no longer print Rich timestamps, and app authors can opt into timestamps or customize colors through a new logging configuration on `pulse.app.App`. The behavior is observable by running `pulse run examples/main.py` and viewing the terminal output.

## Progress

- [ ] (YYYY-MM-DD HH:MMZ) Baseline audit of current logging and stdout usage across CLI and runtime.
- [ ] (YYYY-MM-DD HH:MMZ) New logging utilities implemented with callable `ps.log` and stdout interceptor.
- [ ] (YYYY-MM-DD HH:MMZ) CLI `pulse run` updated to set up logging in-process and call uvicorn programmatically.
- [ ] (YYYY-MM-DD HH:MMZ) App logging configuration surfaces colors and timestamp toggle.
- [ ] (YYYY-MM-DD HH:MMZ) Tests and manual validation completed; plan ready for retrospective.

## Surprises & Discoveries

- Observation: (fill in once work uncovers surprises)
  Evidence: …

## Decision Log

- Decision: Initial ExecPlan created to guide Pulse logging overhaul.
  Rationale: Capture end-to-end scope, context, and execution details for future contributors following `.agent/PLANS.md`.
  Date/Author: YYYY-MM-DD Codex

## Outcomes & Retrospective

Pending implementation. Summaries of efficacy, open issues, and lessons learned will be recorded here upon completion.

## Context and Orientation

Pulse’s CLI entry point lives in `packages/pulse/python/src/pulse/cli/cmd.py`. The `run` command orchestrates app loading, dependency checks, and starts uvicorn by constructing a subprocess command via `build_uvicorn_command`. Logs from spawned commands are streamed by `packages/pulse/python/src/pulse/cli/processes.py`, which currently prefixes lines with `[server]` or `[web]` but still prints Rich timestamps for CLI-initiated messages. The Pulse runtime (`packages/pulse/python/src/pulse/app.py`, `packages/pulse/python/src/pulse/user_session.py`, etc.) uses the standard `logging` module, while user code often prints directly to `stdout`. There is no unified logging configuration or helper exposed to users today.

The goal is to replace ad-hoc printing with a centralized logging layer. We will create a `pulse.logging` package that supplies:
* A formatter rendering `[source] LEVEL: message` without timestamps unless enabled by configuration.
* Color handling for each source, configurable per app.
* A callable logger `ps.log` for user code, exposing level attributes (`info`, `warning`, etc.) and defaulting to the `[user]` source.
* A stdout/stderr interceptor that captures user `print` statements, tagging them as `[user]`, while allowing internal framework loggers to bypass the interceptor.

We must also modify `App` in `packages/pulse/python/src/pulse/app.py` so instances accept a logging configuration struct with fields for color overrides and timestamp toggling.

## Plan of Work

1. Audit existing logging usage. Read `cmd.py`, `processes.py`, and runtime modules (`pulse/app.py`, `pulse/user_session.py`, `pulse/proxy.py`, etc.) to catalog current console outputs, `logging.getLogger` calls, and `print` statements. Document the findings in `Surprises & Discoveries` if unexpected complexities emerge (for example, third-party loggers already configured by uvicorn).

2. Define logging infrastructure.
   * Add `packages/pulse/python/src/pulse/logging/__init__.py` (or a dedicated module structure) that declares:
     - A `PulseLoggingConfig` dataclass describing `enable_timestamps: bool` and color overrides for `server`, `framework`, and `user`.
     - A `PulseFormatter` class or function to format records as `[source] LEVEL: message`, applying colors via ANSI escape codes.
     - A `LogSource` enumeration or constants describing the three categories.
     - A callable object `PulseUserLogger` implementing `__call__` and level methods. It should funnel messages into the shared logger while tagging them as `[user]`.
     - A `StdStreamInterceptor` that wraps a text stream and forwards completed lines to the user logger, while providing a `bypass_context()` method that temporarily disables interception for framework-level writes.
     - A helper `setup_logging(config: PulseLoggingConfig, console: PulseConsoleLike)` that installs handlers on Python’s logging module, configures `ps.log`, and returns the configured handlers.
   * Ensure this module has no Rich dependency so it can be reused across CLI and runtime.

3. Update Pulse public API.
   * Expose `ps.log` via `packages/pulse/python/src/pulse/__init__.py`, ensuring the import path remains stable for user applications. Document how `ps.log` becomes available after the logging setup runs.
   * Implement the callable behavior using the `PulseUserLogger` defined earlier.

4. Enhance CLI console output.
   * Replace each `console.log` call in `cmd.py` and related helpers (`dependencies.py`, `_run_dependency_plan`, etc.) with calls into the new logging helpers, ensuring CLI output is left-aligned and timestamp-free.
   * In `build_uvicorn_command`, remove subprocess execution. Instead, restructure `run` so after preparing app context and dependencies, it:
     - Installs the logging configuration (respecting `App.logging` defaults and CLI overrides if any).
     - Configures uvicorn programmatically inside the same process, passing reload flags, host, and port. If live reload requires running uvicorn via `uvicorn.main.main()` with CLI args, use `uvicorn.main.main(args)` after hooking logging.
     - Continues to launch the web dev server via the existing subprocess infrastructure when needed, preserving watch functionality.
   * Adjust `execute_commands` in `processes.py` so it accepts expanded tag colors, respects the new color map, and strips timestamps uniformly. Update `_write_tagged_line` to rely on the shared formatter or to delegate to a helper in the logging package for consistent rendering.

5. Extend `App` with logging configuration.
   * Define a `PulseLoggingConfig` dataclass (or reuse the one from the logging package) and add a `logging: PulseLoggingConfig | None` attribute to the `App` constructor with defaults disabling timestamps and using the default color palette.
   * Ensure the CLI reads `app.logging` when configuring the logging subsystem so per-app overrides take effect regardless of how `pulse run` is invoked.
   * Update runtime modules (`user_session.py`, `proxy.py`, etc.) to fetch loggers via the new factory, not `logging.getLogger(__name__)`, so the source is tagged `[framework]`.

6. Implement stdout interception.
   * Install the `StdStreamInterceptor` when the Pulse server starts so user `print` statements are captured as `[user] INFO` logs. Provide a clear mechanism for framework loggers to bypass this interception (for example, context manager or writing directly to the logging handler).
   * Verify that uvicorn’s access/error logs and WatchFiles reload messages flow through `[server]`.

7. Update tests and write new coverage.
   * Add unit tests under `packages/pulse/python/tests/test_logging.py` to confirm formatting, callable logger behavior, and stdout interception.
   * Adjust CLI tests (e.g., `packages/pulse/python/tests/test_cli.py`) to assert that log lines contain the expected prefixes and no timestamps.
   * If necessary, add fixtures in `packages/pulse/python/tests/conftest.py` for capturing log output in tests.

8. Documentation and ergonomics.
   * Update relevant README sections or docstrings to explain `ps.log`, logging configuration, and how to customize colors or re-enable timestamps. If the repository includes user-facing docs, add a short section that demonstrates usage.

## Concrete Steps

1. Working directory: `/Users/erwin/Code/pulse-ui`. Read existing files with `rg` and `sed` to inventory logging calls.

2. Create the new logging module with `apply_patch` or standard editors, adding dataclasses, formatters, and the `StdStreamInterceptor`.

3. Update `pulse/__init__.py`, `App` constructor in `pulse/app.py`, CLI files, and process runner sequentially, using `apply_patch` for targeted modifications.

4. Write or modify tests under `packages/pulse/python/tests`. Use `uv run pytest packages/pulse/python/tests/test_logging.py` and `uv run pytest packages/pulse/python/tests/test_cli.py` as focused checks during development.

5. Once coding is complete, run the full suite:
   * `make format`
   * `make lint`
   * `make typecheck`
   * `make test`

6. Manually verify by running `pulse run examples/main.py` (within the repo) and observing terminal output for correct tags, colors, and absence of timestamps. Capture a short transcript and store it in `Artifacts and Notes` if necessary.

## Validation and Acceptance

Acceptance criteria:
* Running `pulse run examples/main.py` prints log lines formatted as `[server] INFO: ...`, `[framework] INFO: ...`, and `[user] INFO: ...`, with only the “Pulse running at …” block indented. Colors match defaults unless overridden.
* Invoking `ps.log("hello")` within `examples/main.py` outputs `[user] INFO: hello`. Calling `ps.log.warning("uh oh")` shows `[user] WARNING: uh oh`.
* Setting `App(logging=PulseLoggingConfig(enable_timestamps=True, user_color="magenta"))` in an example app introduces timestamps and color changes as configured.
* All updated and new tests pass (`uv run pytest` outputs 0 failures). The global checks `make all` also succeed.
* Manual verification demonstrates that `print("foo")` inside user code becomes a `[user] INFO` log while internal framework logs do not duplicate output or suffer from interception loops.

## Idempotence and Recovery

Each code change is applied via explicit edits. Re-running the tests and manual validation is safe because they only read and write within the repository workspace. If logging configuration causes unexpected behavior, reverting the specific files or re-running git checkout on them (outside of this plan’s purview) restores the previous state. The stdout interceptor should provide a bypass context to disable interception temporarily without restarting the process.

## Artifacts and Notes

Capture key evidence once available, for example:

    Sample output after running `pulse run examples/main.py`:
    [server] INFO: Pulse CLI started with reload=True
    [framework] INFO: Generating routes…
    [user] INFO: hello from ps.log
    [server] INFO: Uvicorn running on http://localhost:8000

Add unit test excerpts or config snippets here as implementation progresses.

## Interfaces and Dependencies

New or updated types and interfaces:

* In `packages/pulse/python/src/pulse/logging/__init__.py`, define:

      @dataclass
      class PulseLoggingConfig:
          enable_timestamps: bool = False
          server_color: str = "cyan"
          framework_color: str = "magenta"
          user_color: str = "green"

      class PulseUserLogger:
          def __call__(self, message: str, *, level: str = "INFO") -> None: ...
          def info(self, message: str) -> None: ...
          def warning(self, message: str) -> None: ...
          def error(self, message: str) -> None: ...

      def setup_logging(config: PulseLoggingConfig, app_context: App) -> PulseLoggingHandles: ...

      class StdStreamInterceptor(TextIOBase):
          def write(self, data: str) -> int: ...
          @contextmanager
          def bypass(self) -> Iterator[None]: ...

* Modify `pulse.app.App` to accept `logging: PulseLoggingConfig | None` and store it.

* Update CLI to utilize `setup_logging` before invoking uvicorn and to expose `ps.log` globally.

Dependencies:
* Continue using Python’s standard `logging` module; avoid adding third-party logging dependencies.
* Ensure compatibility with uvicorn reload functionality by passing through arguments unchanged when calling `uvicorn.main.main`.

This plan must be updated if new insights emerge during implementation. Append future revisions to the `Decision Log` and annotate updates in `Progress`, `Surprises & Discoveries`, and `Outcomes & Retrospective`.
