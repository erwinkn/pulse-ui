"""
JavaScript Map builtin module.

Usage:
    import pulse.js.map as Map
    Map()                         # -> new Map()
    Map([["a", 1]])              # -> new Map([["a", 1]])

    from pulse.js.map import Map
    Map()                         # -> new Map()
"""

from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from typing import Any as _Any
from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import register_js_module as _register_js_module

K = _TypeVar("K")
V = _TypeVar("V")


class Map(_Generic[K, V]):
	"""JavaScript Map - a collection of keyed data items.

	Map[K, V] preserves insertion order and allows keys of any type.
	"""

	def __init__(self, iterable: _Iterable[tuple[K, V]] | None = None) -> None: ...

	@property
	def size(self) -> int:
		"""The number of key/value pairs in the Map."""
		...

	def clear(self) -> None:
		"""Remove all key/value pairs."""
		...

	def delete(self, key: K) -> bool:
		"""Remove a key and its value. Returns True if the key existed."""
		...

	def get(self, key: K) -> V | None:
		"""Return the value for a key, or None if not present."""
		...

	def has(self, key: K) -> bool:
		"""Return True if the key exists in the Map."""
		...

	def set(self, key: K, value: V) -> "Map[K, V]":
		"""Set a key/value pair. Returns the Map for chaining."""
		...

	def forEach(
		self,
		callback: _Callable[[V, K, "Map[K, V]"], None],
		thisArg: _Any | None = None,
	) -> None:
		"""Execute a function for each key/value pair."""
		...

	def keys(self) -> _Iterable[K]:
		"""Return an iterator of keys."""
		...

	def values(self) -> _Iterable[V]:
		"""Return an iterator of values."""
		...

	def entries(self) -> _Iterable[tuple[K, V]]:
		"""Return an iterator of [key, value] pairs."""
		...

	def __iter__(self) -> _Iterable[tuple[K, V]]:
		"""Iterate over [key, value] pairs."""
		...


# Self-register this module as a JS builtin in global scope
_register_js_module(name="Map", global_scope=True)
