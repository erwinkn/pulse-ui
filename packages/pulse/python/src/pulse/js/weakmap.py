"""
JavaScript WeakMap builtin module.

Usage:
    from pulse.js import WeakMap
    WeakMap()                     # -> new WeakMap()
    WeakMap([[obj, "value"]])    # -> new WeakMap([[obj, "value"]])

    # Or import from module directly:
    from pulse.js.weakmap import WeakMap
"""

from collections.abc import Iterable as _Iterable
from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import JsModule

K = _TypeVar("K")  # Keys must be objects in JS, but we can't enforce that statically
V = _TypeVar("V")


class WeakMap(_Generic[K, V]):
	"""JavaScript WeakMap - a collection of key/value pairs with weak key references.

	WeakMap[K, V] holds weak references to keys, allowing garbage collection.
	Keys must be objects (not primitives).
	"""

	def __init__(self, iterable: _Iterable[tuple[K, V]] | None = None, /) -> None: ...

	def delete(self, key: K) -> bool:
		"""Remove a key and its value. Returns True if the key existed."""
		...

	def get(self, key: K) -> V | None:
		"""Return the value for a key, or None if not present."""
		...

	def has(self, key: K) -> bool:
		"""Return True if the key exists in the WeakMap."""
		...

	def set(self, key: K, value: V) -> "WeakMap[K, V]":
		"""Set a key/value pair. Returns the WeakMap for chaining."""
		...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
