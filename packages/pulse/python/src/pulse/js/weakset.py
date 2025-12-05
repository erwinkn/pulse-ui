"""
JavaScript WeakSet builtin module.

Usage:
    import pulse.js.weakset as WeakSet
    WeakSet()                     # -> new WeakSet()
    WeakSet([obj1, obj2])        # -> new WeakSet([obj1, obj2])

    from pulse.js.weakset import WeakSet
    WeakSet()                     # -> new WeakSet()
"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

from pulse.transpiler.js_module import register_js_module

_T = TypeVar("_T", bound=object)


class WeakSet(Protocol, Generic[_T]):  # pyright: ignore[reportInvalidTypeVarUse]  # pyright: ignore[reportInvalidTypeVarUse]
	"""Protocol for JavaScript WeakSet instances."""

	def __init__(self, iterable: list[_T] | None = None): ...

	def add(self, value: _T) -> WeakSet[_T]: ...
	def delete(self, value: object) -> bool: ...
	def has(self, value: object) -> bool: ...


# Self-register this module as a JS builtin in global scope
register_js_module(name="WeakSet", global_scope=True)
