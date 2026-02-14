# Ref/Task Error Routing Plan

## Goal

Unify background error reporting so render-owned ref/task/timer failures are user-visible (`server_error`) and still flow to loop-level diagnostics.

## Current Gaps

- Multiple ad hoc paths: direct `loop.call_exception_handler` in refs/scheduling/debounce.
- No single owner for routing policy.
- Context ownership can drift between schedule time and run time.
- Python/JS `ServerErrorPhase` types are out of sync.

## Target Design

1. Add `Errors` service to context.
- `PulseContext.errors: Errors`.
- API: `scope(...)` + `report(...)`.
- Single policy point for routing.

2. Route by ownership.
- If scoped to live render + path: call `render.report_error(...)`.
- Always also call loop exception handler with structured context.
- If app/global scope only: loop handler + logger, no user `server_error`.

3. Preserve creation-time context for async work.
- Snapshot context at task/timer/repeat/later/call_soon creation.
- Execute callback/task creation inside captured context.
- Ensure thread-hop paths keep same captured context.

4. Move refs/timers/debounce to `Errors`.
- Replace direct loop-handler calls with `ctx.errors.report(...)`.
- Keep cancellation as non-error path.

5. Normalize phase contract.
- Align Python + JS `ServerErrorPhase`.
- Add explicit phases for ref/timer/task (or agreed equivalent).

## Implementation Steps

1. Introduce `Errors` type/module and wire into `PulseContext` construction/update.
2. Add scoped reporter creation in render/session paths (path + phase metadata).
3. Refactor scheduling registries to capture/run with creation-time context snapshot.
4. Refactor refs + debounce to report through `Errors`.
5. Update message typings in Python + JS for phase alignment.
6. Add/adjust tests for:
- ref handler error => `server_error` + loop handler context
- timer/later/repeat/debounced error => same behavior
- app-global timer error => loop-only behavior
- context snapshot correctness when current context changes before execution
- phase typing parity (py/js)

## Validation

1. `make test`
2. `make all`

## Risks / Decisions

- Decide final phase names before wiring tests broadly.
- Ensure no duplicate user errors when same exception is surfaced from multiple callbacks.
- Ensure closed render/session handling degrades cleanly to loop/log sink only.
