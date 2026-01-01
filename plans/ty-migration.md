# Plan: Migrate from basedpyright to ty

## Overview
Replace basedpyright with ty for type checking across the entire repository, using ty's default strictness level.

## Error Summary (616 total)

| Category | Count | Resolution |
|----------|-------|------------|
| `invalid-return-type` | 299 | 248 from pulse/js/ (file-level ignores), 51 other fixes |
| `invalid-argument-type` | 123 | Type annotation fixes |
| `unresolved-attribute` | 79 | Fix typos, add missing exports |
| `invalid-assignment` | 28 | Type annotation adjustments |
| `invalid-method-override` | 19 | Match base class signatures |
| `invalid-parameter-default` | 12 | @overload patterns or type fixes |
| Other errors | ~20 | Various fixes |

---

## Configuration Changes

### 1. Create `ty.toml` at repo root
```toml
[environment]
python-version = "3.12"
```

### 2. Update `Makefile`
Change `make typecheck` from `basedpyright` to `uvx ty check`

### 3. Update `CLAUDE.md`
Replace basedpyright references with ty

### 4. Update `pyproject.toml`
Remove basedpyright from dev dependencies

### 5. Delete `pyrightconfig.json`

---

## Code Changes

### Phase 1: pulse/js/ Module (248 errors)
Add file-level ignore comment to each file in `packages/pulse/python/src/pulse/js/`:

**Files to modify (18 files):**
- `array.py`, `console.py`, `date.py`, `document.py`, `error.py`
- `json.py`, `map.py`, `math.py`, `navigator.py`, `number.py`
- `object.py`, `promise.py`, `regexp.py`, `set.py`, `string.py`
- `weakmap.py`, `weakset.py`, `window.py`

**Comment to add at top of each:** `# ty: ignore[invalid-return-type]`

### Phase 2: Method Override Fixes (~19 errors)
**File:** `packages/pulse/python/src/pulse/reactive_extensions.py`

Fix method signatures to match base class:
- `ReactiveDict.__contains__` - change `key: T1` to `key: object`
- `ReactiveDict.__ior__` - adjust return type
- `ReactiveList.__getitem__` - adjust signature
- `ReactiveList.__setitem__` - adjust signature
- Other override methods as needed

### Phase 3: Sentinel Default Fixes (~12 errors)
**Files:**
- `packages/pulse/python/src/pulse/queries/query.py` (lines 81, 252, 515)
- `packages/pulse/python/src/pulse/queries/store.py` (line 32)
- `packages/pulse/python/src/pulse/hooks/core.py` (lines 218, 281)
- `packages/pulse/python/src/pulse/reactive_extensions.py` (line 254)
- `packages/pulse/python/src/pulse/components/if_.py` (line 38)

**Resolution options per location:**
1. Use `@overload` pattern instead of sentinel
2. Change type annotation to include sentinel type
3. Add inline ignore comment

### Phase 4: Callable __name__ Access (~5 errors)
**File:** `packages/pulse/python/src/pulse/decorators.py` (lines 46, 50, 52, 150, 157)

Change `fn.__name__` to `getattr(fn, "__name__", "")` or use proper typing.

### Phase 5: Example File Fixes

**Fix typos/missing exports:**
- `examples/js_exec_demo.py:16` - change `states` to `state`
- `examples/pulse-mantine/05-css-modules.py` - `ps.CssImport` doesn't exist
- `examples/registry_demo.py` - `ps.CssImport` doesn't exist
- `packages/pulse-lucide/scripts/test.py` - `ps.registered_react_components` doesn't exist

**Fix deprecated datetime:**
- `examples/forms.py:44,55` - change `datetime.utcnow()` to `datetime.now(datetime.timezone.utc)`

### Phase 6: Remove Legacy Type Comments
Search for and remove unnecessary pyright/type ignore comments:
- `# pyright: ignore` comments (no longer needed with ty)
- `# type: ignore` comments (evaluate if still necessary)
- `# pyright:` configuration comments

**Search commands:**
```bash
grep -r "pyright:" packages/
grep -r "type: ignore" packages/
```

### Phase 7: Remaining Type Fixes (~50+ errors)

**invalid-argument-type errors:**
- `packages/pulse/python/src/pulse/form.py:267` - TypedDict update pattern
- `packages/pulse/python/src/pulse/component.py` - flatten_children argument
- Various example files with list comprehensions passed to tag functions

**invalid-assignment errors:**
- `packages/pulse/python/src/pulse/middleware.py:38` - Ok payload type
- `packages/pulse/python/src/pulse/helpers.py:158` - dispose wrapper type
- Query files with union type assignments

**no-matching-overload errors:**
- `packages/pulse/python/src/pulse/app.py:746,748` - dict() constructor usage
- `packages/pulse/python/src/pulse/form.py:267` - props.update()

---

## Execution Order

1. Configuration changes (ty.toml, Makefile, delete pyrightconfig.json)
2. Phase 1: Add file-level ignores to pulse/js/ (fixes 248 errors)
3. Run `uvx ty check --python-version 3.12` to verify remaining errors
4. Phase 2-5: Fix type errors iteratively
5. Phase 6: Remove legacy pyright:/type: comments
6. Phase 7: Fix remaining type errors
7. Final `uvx ty check` to confirm zero errors
8. Update CLAUDE.md and pyproject.toml

---

## Files to Modify Summary

**Config files:**
- `ty.toml` (new)
- `Makefile`
- `CLAUDE.md`
- `pyproject.toml`
- `pyrightconfig.json` (delete)

**Core library:**
- `packages/pulse/python/src/pulse/js/*.py` (18 files)
- `packages/pulse/python/src/pulse/reactive_extensions.py`
- `packages/pulse/python/src/pulse/decorators.py`
- `packages/pulse/python/src/pulse/queries/query.py`
- `packages/pulse/python/src/pulse/queries/store.py`
- `packages/pulse/python/src/pulse/hooks/core.py`
- `packages/pulse/python/src/pulse/components/if_.py`
- `packages/pulse/python/src/pulse/form.py`
- `packages/pulse/python/src/pulse/middleware.py`
- `packages/pulse/python/src/pulse/helpers.py`
- `packages/pulse/python/src/pulse/app.py`
- `packages/pulse/python/src/pulse/component.py`

**Examples:**
- `examples/js_exec_demo.py`
- `examples/forms.py`
- `examples/pulse-mantine/05-css-modules.py`
- `examples/registry_demo.py`
- `packages/pulse-lucide/scripts/test.py`
- Various tutorial files
