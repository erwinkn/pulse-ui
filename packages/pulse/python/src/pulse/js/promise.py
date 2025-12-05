"""
JavaScript Promise builtin module.

Usage:
    import pulse.js.promise as Promise
    Promise.resolve(value)        # -> Promise.resolve(value)
    Promise.reject(reason)        # -> Promise.reject(reason)

    from pulse.js.promise import resolve, reject, all, allSettled, race, any
    resolve(value)                # -> Promise.resolve(value)
    reject(reason)                 # -> Promise.reject(reason)
"""

from __future__ import annotations

from pulse.transpiler.js_module import register_js_module


# Static Methods (type stubs for IDE support)
def all(iterable: list[object]) -> object: ...
def allSettled(iterable: list[object]) -> object: ...
def any(iterable: list[object]) -> object: ...
def race(iterable: list[object]) -> object: ...
def reject(reason: object) -> object: ...
def resolve(value: object) -> object: ...


# Self-register this module as a JS builtin
register_js_module(name="Promise", global_scope=True)
