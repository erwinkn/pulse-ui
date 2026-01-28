# Hook Callsite Identity

## Goal
- Centralize callsite identity logic.
- Let hooks opt into automatic callsite identity when `key=None`.
- Keep helper for compositional/manual use.

## API
```
hook = ps.hooks.create("pkg:hook", ..., identity="key" | "callsite")

hook()                                  # identity="callsite" -> callsite identity
hook("foo")                             # explicit string key
hook(ps.hooks.callsite_identity())      # explicit callsite identity
```

Helper:
```
ps.hooks.callsite_identity(*, skip=0, frame=None) -> HookIdentity
```

## Design
- Move `collect_component_identity` into `pulse/hooks/core.py` as
  `callsite_identity`; keep same algorithm:
  - walk frames to component code
  - identity is tuple of `(code_obj, offset)` per frame
  - offset uses `f_lasti` else `f_lineno`
- `hooks.create(..., identity="key"|"callsite")`
  - default `"key"` (current behavior)
  - `"callsite"` computes identity when `key is None`
- `Hook.__call__(key=None)`
  - `key` may be `str | HookIdentity | None`
  - if `key is None` and hook identity is callsite, use
    `callsite_identity(skip=1)`
  - if `key` is a `HookIdentity`, use it directly
- `HookNamespace` keys use tagged tuples (or `HookKey` dataclass)
  to avoid collisions: `("default", …)`, `("key", …)`, `("callsite", …)`

## Wiring
- `pulse/hooks/state.py`: delete local `collect_component_identity`,
  use `hooks.callsite_identity` for callsite keying.
- `pulse/decorators.py`: use `hooks.callsite_identity` for `@ps.effect`.
- Keep existing `key=` semantics and error messages.

## Tests
- New core hook test:
- hook with `identity="callsite"` returns same state across renders for same
  callsite, different state for different callsites.
- `key` string overrides callsite identity.
- passing `callsite_identity()` via `key` uses explicit identity.
- Existing inline effect/state tests should still pass; add one small test to
  ensure helper identity matches prior behavior if needed.

## Files
- `packages/pulse/python/src/pulse/hooks/core.py`
- `packages/pulse/python/src/pulse/hooks/state.py`
- `packages/pulse/python/src/pulse/decorators.py`
- `packages/pulse/python/tests/...`
