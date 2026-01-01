"""
JavaScript Set builtin module.

Usage:
    from pulse.js import Set
    Set()                         # -> new Set()
    Set([1, 2, 3])               # -> new Set([1, 2, 3])

    # Or import from module directly:
    from pulse.js.set import Set
"""

from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from collections.abc import Iterator as _Iterator
from typing import Any as _Any
from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import JsModule

T = _TypeVar("T")


class Set(_Generic[T]):
	"""JavaScript Set - a collection of unique values.

	Set[T] stores unique values of type T in insertion order.
	"""

	def __init__(self, iterable: _Iterable[T] | None = None, /) -> None: ...

	@property
	def size(self) -> int:
		"""The number of values in the Set."""
		...

	def add(self, value: T) -> "Set[T]":
		"""Add a value to the Set. Returns the Set for chaining."""
		...

	def clear(self) -> None:
		"""Remove all values from the Set."""
		...

	def delete(self, value: T) -> bool:
		"""Remove a value. Returns True if the value existed."""
		...

	def has(self, value: T) -> bool:
		"""Return True if the value exists in the Set."""
		...

	def forEach(
		self,
		callback: _Callable[[T, T, "Set[T]"], None],
		thisArg: _Any | None = None,
		/,
	) -> None:
		"""Execute a function for each value.

		Note: callback receives (value, value, set) for compatibility with Map.
		"""
		...

	def keys(self) -> _Iterable[T]:
		"""Return an iterator of values (same as values())."""
		...

	def values(self) -> _Iterable[T]:
		"""Return an iterator of values."""
		...

	def entries(self) -> _Iterable[tuple[T, T]]:
		"""Return an iterator of [value, value] pairs."""
		...

	def __iter__(self) -> _Iterator[T]:
		"""Iterate over values."""
		...

	def __len__(self) -> int:
		"""Return the number of values (same as size)."""
		...

	def __contains__(self, value: T) -> bool:
		"""Check if value exists in the Set (same as has)."""
		...

	# ES2024 Set methods
	def union(self, other: "Set[T]") -> "Set[T]":
		"""Return a new Set with values from both sets (ES2024)."""
		...

	def intersection(self, other: "Set[T]") -> "Set[T]":
		"""Return a new Set with values in both sets (ES2024)."""
		...

	def difference(self, other: "Set[T]") -> "Set[T]":
		"""Return a new Set with values in this but not other (ES2024)."""
		...

	def symmetricDifference(self, other: "Set[T]") -> "Set[T]":
		"""Return a new Set with values in either but not both (ES2024)."""
		...

	def isSubsetOf(self, other: "Set[T]") -> bool:
		"""Return True if all values are in other (ES2024)."""
		...

	def isSupersetOf(self, other: "Set[T]") -> bool:
		"""Return True if all values of other are in this (ES2024)."""
		...

	def isDisjointFrom(self, other: "Set[T]") -> bool:
		"""Return True if no values are in common (ES2024)."""
		...


# Self-register this module as a JS builtin (global identifiers)
JsModule.register(name=None)
