"""
JavaScript WeakSet builtin module.

Usage:
    import pulse.js.weakset as WeakSet
    WeakSet()                     # -> new WeakSet()
    WeakSet([obj1, obj2])        # -> new WeakSet([obj1, obj2])

    from pulse.js.weakset import WeakSet
    WeakSet()                     # -> new WeakSet()
"""

from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import register_js_module as _register_js_module

_T = _TypeVar("_T", bound=object)


class WeakSet(_Generic[_T]):
	"""Class for JavaScript WeakSet instances."""

	def __init__(self, iterable: list[_T] | None = None): ...

	def add(self, value: _T) -> "WeakSet[_T]": ...
	def delete(self, value: object) -> bool: ...
	def has(self, value: object) -> bool: ...


# Self-register this module as a JS builtin in global scope
_register_js_module(name="WeakSet", global_scope=True)
