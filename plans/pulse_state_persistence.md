# Pulse State Drain & Hydrate Enablement

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Pulse lacks a durable way to capture the full contents of a state object and recreate it later. Introducing drainage and hydration backed by `cloudpickle` lets developers persist user state across renders, roll deployments with state migrations, and recover from crashes by replaying stored state. Success looks like calling `ps.State.drain()` on an existing instance, serializing its payload, later invoking `ps.MyState.hydrate(...)`, and observing an equivalent instance—even if the class reordered fields, dropped attributes, or introduced new ones with safe defaults.

## Progress

- [x] (2025-10-23 16:08Z) Reviewed the current state system, confirmed requirements with existing code, and drafted this initial ExecPlan.
- [ ] Implementation work to add draining, hydration, migrations, strict mode enforcement, and supporting tests remains pending.

## Surprises & Discoveries

None yet; this section will capture unexpected behavior or design changes uncovered during implementation.

## Decision Log

No plan-level decisions have been made beyond what is documented here; new choices will be recorded as they occur.

## Outcomes & Retrospective

Pending; will summarize once the feature is delivered and validated.

## Context and Orientation

`packages/pulse/python/src/pulse/state.py` defines the `State` base class, its metaclass `StateMeta`, and the `StateProperty` descriptor that turn annotated class attributes into reactive signals. Instances are orchestrated via `StateMeta.__call__`, which runs user initializers and then `_initialize()` to register effects. `State.__setattr__` already rejects writes to undefined public attributes by delegating to descriptors, while names beginning with `_` bypass these guards. No persistence hooks exist today.

`pulse.context.PulseContext` binds the active `App`, `RenderSession`, and `UserSession` so hooks like `ps.global_state` (in `packages/pulse/python/src/pulse/hooks/runtime.py`) can look up or create shared state instances. The `App` class in `packages/pulse/python/src/pulse/app.py` currently has no concept of strict mode, and the Python package does not list `cloudpickle` as a dependency (see `packages/pulse/python/pyproject.toml`). Example states such as `examples/global_state.py` assign private fields in `__init__` without declaring them on the class, which will conflict with the forthcoming requirement that every attribute be defined up front.

## Plan of Work

Phase one focuses on metadata foundations. Extend `StateMeta` so that every subclass records a canonical catalogue of its fields, including reactive signals, query descriptors, underscored private attributes, defaults, and whether a value participates in drainage. While assembling that structure, merge information from base classes, synthesize a default `__version__ = 1` when it is missing, and clone migration maps so parent classes remain immutable. During this phase, introduce plumbing so freshly constructed instances automatically invoke a new optional `__post_init__` hook after user-defined `__init__` completes. Record whether each query sets a new `preserve` flag (default `False`) that marks its results as drainable.

Phase two delivers draining capability. Using the captured metadata, implement `State.drain(self) -> dict[str, Any]` to emit a payload shaped like `{"__version__": cls.__version__, "values": {...}}`, omitting framework internals such as scopes, live effects, or query results whose `preserve` flag is `False`. Ensure the payload copies reactive containers to avoid aliasing and is compatible with `cloudpickle.dumps`. Provide `State.__getstate__` so standard pickling delegates to `drain`, keeping Pulse-specific semantics while remaining compatible with Python tooling.

Phase three implements hydration and migrations. Add `@classmethod State.hydrate(cls, payload: dict[str, Any]) -> State` that accepts drained data, invokes a user-overridable `__migrate__(start_version: int, target_version: int, values: dict[str, Any]) -> dict[str, Any]` hook to transform payloads across version gaps, instantiates the object via `cls.__new__`, restores each tracked attribute (skipping non-preserved queries so they recompute naturally and tolerating missing values for preserved queries), backfills defaults for anything newly added, and finally calls a new `__post_init__` hook before running `_initialize()` so effects register. Hydration must raise a descriptive error when migration coverage is missing, when a required attribute lacks a default, or when a newly introduced field appears without either a declared default or an explicit migration supplying its value. Implement `State.__setstate__` to delegate to `hydrate` for compatibility with Python pickling.

Phase four introduces strict mode enforcement. Augment `State.__setattr__` to consult the active `PulseContext` (or a fallback) for an `App.strict` flag, defaulting to strict behavior in development. When strict mode applies, reject writes to undeclared attributes regardless of underscore prefix and verify each assigned value is `cloudpickle`-serializable, while allowing internal framework attributes like `_scope`, `__pulse_status__`, or the new `_post_initialized` guard.

Phase five tackles product integration. Update `App.__init__` to accept `strict: bool = True`, store that flag, and expose it through the context so states can determine their enforcement level. Add `cloudpickle` to `packages/pulse/python/pyproject.toml`, import it where picklability checks run, and provide helper utilities for strict-mode defaults when no app context exists.

Phase six cleans up dependents and hardens quality. Sweep core modules, examples, docs, and tests to declare every state attribute (including underscored ones) at class definition time. Update query definitions to opt into the new `preserve` option only where persisted results are desirable. Expand unit coverage in `packages/pulse/python/tests/test_state.py` and related suites for drainage, hydration across schema changes, migration flows, strict-mode failures, and query preservation behavior. Add integration-style coverage ensuring render sessions can round-trip drained state. Close by documenting the new API surface and exporting any required helpers via `pulse/__init__.py`.

## Open Questions & Risks

The repository currently allows private attributes to be introduced inside `__init__`, so mandating class-level declarations may touch numerous examples, tests, and third-party extensions such as `pulse_mantine`. We need to inventory those usages early to avoid a destabilizing sweep during the final phases. Several states perform non-trivial work inside `__init__`; migrating that logic into the forthcoming `__post_init__` hook is required for hydration to mirror construction, so we must communicate the change and update first-party code accordingly. Allowing query preservation introduces a risk of capturing very large result sets; we should verify that developers understand the trade-off and perhaps guard the feature with documentation or size warnings. Finally, serializing every assignment with `cloudpickle.dumps` in dev strict mode could have measurable overhead on hot paths; benchmarks or caching strategies may be needed if developer experience regresses.

## Concrete Steps

After editing `packages/pulse/python/pyproject.toml`, install the added dependency locally using `uv add cloudpickle` (or regenerate the lockfile if the project tracks one). Implement the planned code changes and format the repository with `make format`, then run targeted tests such as `uv run pytest packages/pulse/python/tests/test_state.py` and `uv run pytest packages/pulse/python/tests/test_render_session.py`. Finish with `make all` to confirm formatting, linting, type checking, and tests succeed in aggregate.

## Validation and Acceptance

Validation requires demonstrating that draining a state, serializing the returned payload with `cloudpickle.dumps`, deserializing it, and hydrating via `State.hydrate` yields an object whose defined attributes match the original, modulo attributes intentionally removed or provided by defaults. Additional acceptance criteria include the `__migrate__` hook being exercised for version gaps, hydration raising when a new field lacks both a default and a migration-supplied value, non-preserved queries rerunning automatically while preserved ones restore their cached result if present (or recompute gracefully when absent), `__post_init__` running exactly once for construction and once for hydration without re-invoking user `__init__`, strict mode raising informative errors on undeclared attribute writes or non-picklable values while remaining silent when `strict=False` or outside the `"dev"` environment, and all automated checks passing.

## Idempotence and Recovery

Draining is a read-only operation and can be repeated safely; hydrating rebuilds fresh objects without mutating the source payload, so reruns are safe as well. If strict-mode enforcement halts execution unexpectedly, toggle `App(strict=False)` or adjust the environment to recover while diagnosing the offending attribute.

## Artifacts and Notes

Artifacts such as sample drained payloads or failure traces should be captured here once available.

## Interfaces and Dependencies

Expose three overridable hooks on `State`: `drain(self) -> dict[str, Any]`, `hydrate(cls, payload: dict[str, Any]) -> State`, and a no-argument `__post_init__(self)` that runs after both ordinary construction and hydration. `State.__getstate__` and `State.__setstate__` should delegate to those hooks so integration with Python’s pickling protocol remains seamless while Pulse retains control over versioning and migrations. Provide class attributes `__version__: int` (defaulting to `1`) alongside an overridable `__migrate__(start_version: int, target_version: int, values: dict[str, Any]) -> dict[str, Any]` helper to coordinate upgrades. Query definitions gain a `preserve: bool = False` option controlling whether their cached values participate in drainage. The `App` constructor gains a `strict` parameter defaulting to `True`. The Python package now depends on `cloudpickle`, and runtime code must import it wherever picklability checks are performed.

---

Initial version authored on 2025-10-23 to capture the draining, hydration, and strict-mode roadmap.
