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

from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from typing import Any as _Any
from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import register_js_module as _register_js_module

T = _TypeVar("T")
U = _TypeVar("U")
S = _TypeVar("S")


class Array(_Generic[T]):
	"""JavaScript Array - a generic indexed collection.

	Array[T] represents a JavaScript array containing elements of type T.
	All instance methods preserve the expected generic types.
	"""

	def __init__(self, *args: T | int) -> None:
		"""Create an Array.

		- No arguments: empty array
		- Single int: array with that length
		- Multiple args: array with those elements
		"""
		...

	# Static methods
	@staticmethod
	def isArray(value: _Any) -> bool:
		"""Determine whether the passed value is an Array."""
		...

	@staticmethod
	def from_(
		arrayLike: _Iterable[T],
		mapFn: _Callable[[T, int], U] | None = None,
		thisArg: _Any | None = None,
	) -> "list[U] | list[T]":
		"""Create a new Array from an array-like or iterable object."""
		...

	@staticmethod
	def of(*elements: T) -> "list[T]":
		"""Create a new Array from a variable number of arguments."""
		...

	# Accessor properties
	@property
	def length(self) -> int:
		"""The number of elements in the array."""
		...

	# Mutator methods (modify the array in place)
	def push(self, *items: T) -> int:
		"""Add elements to the end; returns new length."""
		...

	def pop(self) -> T | None:
		"""Remove and return the last element."""
		...

	def shift(self) -> T | None:
		"""Remove and return the first element."""
		...

	def unshift(self, *items: T) -> int:
		"""Add elements to the beginning; returns new length."""
		...

	def splice(
		self, start: int, deleteCount: int | None = None, *items: T
	) -> "list[T]":
		"""Remove/replace elements and optionally insert new ones."""
		...

	def reverse(self) -> "Array[T]":
		"""Reverse the array in place."""
		...

	def sort(self, compareFn: _Callable[[T, T], int] | None = None) -> "Array[T]":
		"""Sort the array in place."""
		...

	def fill(self, value: T, start: int = 0, end: int | None = None) -> "Array[T]":
		"""Fill all elements with a static value."""
		...

	def copyWithin(
		self, target: int, start: int = 0, end: int | None = None
	) -> "Array[T]":
		"""Copy part of the array to another location within it."""
		...

	# Accessor methods (return new arrays or values)
	def concat(self, *items: T | "_Iterable[T]") -> "list[T]":
		"""Merge arrays and/or values into a new array."""
		...

	def slice(self, start: int = 0, end: int | None = None) -> "list[T]":
		"""Return a shallow copy of a portion of the array."""
		...

	def join(self, separator: str = ",") -> str:
		"""Join all elements into a string."""
		...

	def indexOf(self, searchElement: T, fromIndex: int = 0) -> int:
		"""Return first index of element, or -1 if not found."""
		...

	def lastIndexOf(self, searchElement: T, fromIndex: int | None = None) -> int:
		"""Return last index of element, or -1 if not found."""
		...

	def includes(self, searchElement: T, fromIndex: int = 0) -> bool:
		"""Determine whether the array contains the element."""
		...

	def at(self, index: int) -> T | None:
		"""Return element at index (supports negative indexing)."""
		...

	def flat(self, depth: int = 1) -> "list[_Any]":
		"""Flatten nested arrays to the specified depth."""
		...

	def flatMap(
		self, callback: _Callable[[T, int, "Array[T]"], _Iterable[U]]
	) -> "list[U]":
		"""Map then flatten the result by one level."""
		...

	def toReversed(self) -> "list[T]":
		"""Return a new reversed array (ES2023)."""
		...

	def toSorted(self, compareFn: _Callable[[T, T], int] | None = None) -> "list[T]":
		"""Return a new sorted array (ES2023)."""
		...

	def toSpliced(
		self, start: int, deleteCount: int | None = None, *items: T
	) -> "list[T]":
		"""Return a new array with elements spliced (ES2023)."""
		...

	def with_(self, index: int, value: T) -> "list[T]":
		"""Return a new array with element at index replaced (ES2023)."""
		...

	# Iteration methods
	def forEach(self, callback: _Callable[[T, int, "Array[T]"], None]) -> None:
		"""Execute a function for each element."""
		...

	def map(self, callback: _Callable[[T, int, "Array[T]"], U]) -> "list[U]":
		"""Create a new array with results of calling callback on each element."""
		...

	def filter(self, callback: _Callable[[T, int, "Array[T]"], bool]) -> "list[T]":
		"""Create a new array with elements that pass the test."""
		...

	def reduce(
		self,
		callback: _Callable[[U, T, int, "Array[T]"], U],
		initialValue: U | None = None,
	) -> U:
		"""Reduce array to a single value (left to right).

		If no initialValue is provided, the first element is used.
		"""
		...

	def reduceRight(
		self,
		callback: _Callable[[U, T, int, "Array[T]"], U],
		initialValue: U | None = None,
	) -> U:
		"""Reduce array to a single value (right to left).

		If no initialValue is provided, the last element is used.
		"""
		...

	def find(self, callback: _Callable[[T, int, "Array[T]"], bool]) -> T | None:
		"""Return first element satisfying the callback."""
		...

	def findIndex(self, callback: _Callable[[T, int, "Array[T]"], bool]) -> int:
		"""Return index of first element satisfying the callback, or -1."""
		...

	def findLast(self, callback: _Callable[[T, int, "Array[T]"], bool]) -> T | None:
		"""Return last element satisfying the callback (ES2023)."""
		...

	def findLastIndex(self, callback: _Callable[[T, int, "Array[T]"], bool]) -> int:
		"""Return index of last element satisfying the callback, or -1 (ES2023)."""
		...

	def every(self, callback: _Callable[[T, int, "Array[T]"], bool]) -> bool:
		"""Test whether all elements pass the callback."""
		...

	def some(self, callback: _Callable[[T, int, "Array[T]"], bool]) -> bool:
		"""Test whether at least one element passes the callback."""
		...

	# Iterator methods
	def keys(self) -> _Iterable[int]:
		"""Return an iterator of array indices."""
		...

	def values(self) -> _Iterable[T]:
		"""Return an iterator of array values."""
		...

	def entries(self) -> _Iterable[tuple[int, T]]:
		"""Return an iterator of [index, value] pairs."""
		...

	# String conversion
	def toString(self) -> str:
		"""Return a string representing the array."""
		...

	def toLocaleString(self) -> str:
		"""Return a localized string representing the array."""
		...


# Self-register this module as a JS builtin
_register_js_module(name="Array", global_scope=True)
