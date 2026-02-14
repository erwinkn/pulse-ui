# Pulse Error Routing Overhaul (Final, Consolidated)

## Summary
1. `PulseContext.errors` is the only reporting path.
2. Reporter derives `render`/`route` from `PulseContext` only (no manual render/path args).
3. Transport uses a single `error.code` field (remove `phase`).
4. Never use asyncio loop exception handler for reporting.
5. Add `api` code and catch user-defined FastAPI route errors.
6. API reporting uses current context only; no `x-pulse-route-path` header.

## Final Codes
1. `render`
2. `render.loop`
3. `callback`
4. `navigate`
5. `ref.mount`
6. `ref.unmount`
7. `timer.later`
8. `timer.repeat`
9. `channel`
10. `form`
11. `api`
12. `middleware.prerender`
13. `middleware.connect`
14. `middleware.message`
15. `middleware.channel`
16. `setup`
17. `init`
18. `plugin.startup`
19. `plugin.setup`
20. `plugin.shutdown`
21. `query.handler`
22. `mutation.handler`
23. `system`

## Behavior Rules
1. Context must always exist after `App()` creation. Missing context is a hard failure.
2. Route is optional in the model.
3. For route-bound user surfaces (callback/render/ref/form/channel/middleware), missing route with render is treated as internal bug.
4. For `api`, route can be absent:
- `ctx.render` + `ctx.route` => render-scoped report to client route.
- `ctx.render` + no `ctx.route` => render-associated global report/log.
- no `ctx.render` => app-global report/log.
5. Query/mutation fetch failures remain state-managed only.
6. Query/mutation lifecycle handler failures are reported (`query.handler`, `mutation.handler`).
7. Debounce is folded into `callback` with details (`debounced`, `delay_ms`).

## Public Interface Changes
1. `/Users/erwin/.codex/worktrees/50f0/pulse-ui/packages/pulse/python/src/pulse/errors.py`
- Replace `ErrorType` with `ErrorCode`.
- `Errors.report(exc, *, code, details=None, message=None)`.
- Remove asyncio loop exception-handler calls.
2. `/Users/erwin/.codex/worktrees/50f0/pulse-ui/packages/pulse/python/src/pulse/context.py`
- Add `errors` field to `PulseContext`.
- Ensure `PulseContext.update(...)` keeps reporter context-consistent.
3. `/Users/erwin/.codex/worktrees/50f0/pulse-ui/packages/pulse/python/src/pulse/messages.py`
- `ServerErrorInfo` uses `code`, removes `phase`.
4. `/Users/erwin/.codex/worktrees/50f0/pulse-ui/packages/pulse/js/src/messages.ts`
- Add `ErrorCode` union and switch `ServerError` to `code`.
5. `/Users/erwin/.codex/worktrees/50f0/pulse-ui/packages/pulse/python/src/pulse/render_session.py`
- Remove `RenderSession.report_error`.
- All callsites use `PulseContext.get().errors.report(...)`.

## Implementation Steps
1. Core reporter/context refactor.
- Wire base context in `App.__init__` (not first in `setup`).
- Centralize stack formatting from exception object.
2. Migrate runtime callsites.
- `render_session.py`, `refs.py`, `scheduling.py`, `debounce.py`, `forms.py`, `channel.py`, `hooks/setup.py`, `hooks/init.py`, query/mutation handler paths, plugin lifecycle paths, middleware paths.
3. API route handling.
- In `app.py` HTTP middleware, catch user-defined API route exceptions and report as `api`.
- No route header propagation.
4. Remove all `call_exception_handler(` usage in Pulse runtime source.
5. Keep expected control-flow exceptions silent; remove defensive catches that hide unexpected failures.
6. Use `system` only for expected recoverable internal paths that intentionally continue.

## Stack/Details Contract
1. Always include full captured stack trace.
2. Include locator details when available: callback key, handler/event, middleware method, endpoint, plugin name, query key, mutation name.
3. Include `render_id`/route metadata when present in context.

## Tests
1. Update `/Users/erwin/.codex/worktrees/50f0/pulse-ui/packages/pulse/python/tests/test_errors.py` for `code` contract and no loop-handler behavior.
2. Add API tests:
- user API error with render+route
- user API error with render but no route
- user API error with no render
3. Extend existing module tests for new codes in:
- `test_render_session.py`
- `test_scheduling.py`
- `test_renderer.py`
- `test_debounce.py`
- `test_channels.py`
- query/mutation tests for handler-failure codes
4. Add parity test: Python `ErrorCode` literals == TS `ErrorCode` literals.
5. Add regression test: no `call_exception_handler(` in Pulse runtime.
6. Run `make test` and `make all`.

## Handoff Artifact
1. Write this plan to `/Users/erwin/.codex/worktrees/50f0/pulse-ui/plans/error-routing-overhaul.md` for implementation handoff.
2. Keep `/Users/erwin/.codex/worktrees/50f0/pulse-ui/plans/ref-task-error-routing.md` untouched as prior draft context.

## Assumptions
1. `effect`/`computed` dedicated codes are deferred to follow-up instrumentation.
2. Plan mode is active; file write is performed once execution mode is enabled.
