# Plan

Add a curated set of advanced browser/JS builtins to `pulse.js` for power users, following existing binding patterns and verified API shapes via context7. The work is focused on Python stubs + transpiler coverage + docs/tests, not runtime polyfills.

## Scope
- In: new `pulse.js` bindings, types, tests, and docs for selected advanced builtins.
- Out: polyfills, runtime shims, or server-side JS execution changes.

## Action items
[ ] Confirm the initial builtin list + order (e.g., URL/URLSearchParams, AbortController, fetch/Request/Response/Headers, FormData/Blob/File/FileReader, TextEncoder/Decoder, ArrayBuffer/typed arrays, Intersection/Resize/PerformanceObserver, DOMParser/XMLSerializer/CustomEvent, Intl, crypto).
[ ] Use context7 (MDN) to capture constructor signatures, methods, and option objects for each builtin.
[ ] Review `examples/` and existing bindings in `packages/pulse/python/src/pulse/js/` for patterns and naming.
[ ] Implement one module per builtin in `packages/pulse/python/src/pulse/js/`, add minimal Protocol/TypedDict types (module-local or in `_types.py` as needed), and register with `JsModule`.
[ ] Export new bindings from `packages/pulse/python/src/pulse/js/__init__.py` and update stubs in `packages/pulse/python/src/pulse/js/__init__.pyi`.
[ ] Add transpiler coverage in `packages/pulse/python/tests/transpiler/test_js.py` for constructors, static methods, and typical usage (including `obj(...)` for option objects).
[ ] Update docs in `docs/content/docs/reference/pulse-js/builtins.mdx`, `docs/content/docs/reference/pulse-js/index.mdx`, and `docs/content/docs/reference/pulse/js-interop.mdx` (and glossary if new terms are introduced).
[ ] Validate with `make test`; run `make all` before commit.
[ ] Check edge cases: keyword-escaped names (e.g., `from_`, `is_`), dict vs `obj()` in options, global vs namespace binding decisions.

## Open questions
- Which builtins should ship first, and should we batch by theme (networking, DOM observers, binary)?
- Should `fetch` be exposed as a global function binding or via a namespace (e.g., `window.fetch`)?
- Preferred location for shared types (`_types.py` vs module-local stubs) for DOM-heavy APIs?
