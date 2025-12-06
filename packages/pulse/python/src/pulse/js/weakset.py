"""
JavaScript WeakSet builtin module.

Usage:
    import pulse.js.weakset as WeakSet
    WeakSet()                     # -> new WeakSet()
    WeakSet([obj1, obj2])        # -> new WeakSet([obj1, obj2])

    from pulse.js.weakset import WeakSet
    WeakSet()                     # -> new WeakSet()
"""

from collections.abc import Iterable as _Iterable
from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import register_js_module as _register_js_module

T = _TypeVar("T")  # Values must be objects in JS, but we can't enforce that statically


class WeakSet(_Generic[T]):
	"""JavaScript WeakSet - a collection of objects with weak references.

	WeakSet[T] holds weak references to values, allowing garbage collection.
	Values must be objects (not primitives).
	"""

	def __init__(self, iterable: _Iterable[T] | None = None) -> None: ...

	def add(self, value: T) -> "WeakSet[T]":
		"""Add a value to the WeakSet. Returns the WeakSet for chaining."""
		...

	def delete(self, value: T) -> bool:
		"""Remove a value. Returns True if the value existed."""
		...

	def has(self, value: T) -> bool:
		"""Return True if the value exists in the WeakSet."""
		...


# Self-register this module as a JS builtin in global scope
_register_js_module(name="WeakSet", global_scope=True)
