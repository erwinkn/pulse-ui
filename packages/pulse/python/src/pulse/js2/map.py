"""
JavaScript Map builtin module.

Usage:
    from pulse.js2 import Map
    Map()                         # -> new Map()
    Map([["a", 1]])              # -> new Map([["a", 1]])

    # Or import from module directly:
    from pulse.js2.map import Map
"""

from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from collections.abc import Iterator as _Iterator
from typing import Any as _Any
from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler_v2.js_module import JsModule

K = _TypeVar("K")
V = _TypeVar("V")


class Map(_Generic[K, V]):
	"""JavaScript Map - a collection of keyed data items.

	Map[K, V] preserves insertion order and allows keys of any type.
	"""

	def __init__(self, iterable: _Iterable[tuple[K, V]] | None = None, /) -> None: ...

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
		/,
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

	def __iter__(self) -> _Iterator[tuple[K, V]]:
		"""Iterate over [key, value] pairs."""
		...

	def __len__(self) -> int:
		"""Return the number of key/value pairs (same as size)."""
		...

	def __contains__(self, key: K) -> bool:
		"""Check if key exists in the Map (same as has)."""
		...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
