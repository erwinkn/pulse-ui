"""
JavaScript Array builtin module.

Usage:
    import pulse.js.array as Array
    Array.isArray([1, 2, 3])      # -> Array.isArray([1, 2, 3])
    Array.from([1, 2, 3])         # -> Array.from([1, 2, 3])

    # Note: For 'from' (Python keyword), use namespace import:
    # import pulse.js.array as Array; Array.from(...)
    # Or use the underscore version for direct import:
    from pulse.js.array import isArray, from_
    isArray([1, 2, 3])            # -> Array.isArray([1, 2, 3])
    from_([1, 2, 3])              # -> Array.from([1, 2, 3])
"""

from __future__ import annotations

from pulse.transpiler.js_module import register_js_module


# Static Methods (type stubs for IDE support)
def isArray(value: object) -> bool: ...
def from_(
	arrayLike: object, mapFn: object | None = None, thisArg: object | None = None
) -> list[object]: ...
def of(*elements: object) -> list[object]: ...


# Self-register this module as a JS builtin
register_js_module(name="Array", global_scope=True)
