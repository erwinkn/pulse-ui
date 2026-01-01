"""
JavaScript Object builtin module.

Usage:
    from pulse.js import Object
    Object.keys({"a": 1})         # -> Object.keys({"a": 1})
    Object.assign({}, {"a": 1})   # -> Object.assign({}, {"a": 1})
    Object.is_(x, y)              # -> Object.is(x, y)

    # Or import from module directly:
    from pulse.js.object import Object
"""

from collections.abc import Iterable as _Iterable
from typing import Any as _Any
from typing import TypedDict as _TypedDict
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import JsModule

T = _TypeVar("T")
K = _TypeVar("K", bound=str)  # Object keys are always strings in JS


# Property descriptor type - JS uses a plain object with specific keys
class PropertyDescriptor(_TypedDict, total=False):
	"""Type for Object.defineProperty descriptor."""

	value: _Any
	writable: bool
	get: _Any  # Callable[[], T] but we use _Any for flexibility
	set: _Any  # Callable[[T], None]
	configurable: bool
	enumerable: bool


class Object:
	"""JavaScript Object namespace - static methods for object manipulation.

	Note: Object is primarily used as a namespace for static methods.
	The types here are as precise as JavaScript's dynamic nature allows.
	"""

	@staticmethod
	def assign(target: T, *sources: _Any) -> T:
		"""Copy properties from sources to target. Returns target."""
		...

	@staticmethod
	def create(
		proto: _Any | None,
		propertiesObject: dict[str, PropertyDescriptor] | None = None,
		/,
	) -> _Any:
		"""Create a new object with the specified prototype."""
		...

	@staticmethod
	def defineProperty(
		obj: T, prop: str, descriptor: PropertyDescriptor | dict[str, _Any]
	) -> T:
		"""Define a property on an object. Returns the object."""
		...

	@staticmethod
	def defineProperties(
		obj: T, props: dict[str, PropertyDescriptor | dict[str, _Any]]
	) -> T:
		"""Define multiple properties on an object. Returns the object."""
		...

	@staticmethod
	def entries(obj: dict[str, T]) -> list[tuple[str, T]]:
		"""Return an array of [key, value] pairs."""
		...

	@staticmethod
	def freeze(obj: T) -> T:
		"""Freeze an object (prevent modifications). Returns the object."""
		...

	@staticmethod
	def fromEntries(entries: _Iterable[tuple[str, T]]) -> dict[str, T]:
		"""Create an object from an iterable of [key, value] pairs."""
		...

	@staticmethod
	def getOwnPropertyDescriptor(obj: _Any, prop: str) -> PropertyDescriptor | None:
		"""Return the property descriptor for a property."""
		...

	@staticmethod
	def getOwnPropertyDescriptors(obj: _Any) -> dict[str, PropertyDescriptor]:
		"""Return all own property descriptors."""
		...

	@staticmethod
	def getOwnPropertyNames(obj: _Any) -> list[str]:
		"""Return all own property names (including non-enumerable)."""
		...

	@staticmethod
	def getOwnPropertySymbols(obj: _Any) -> list[_Any]:
		"""Return all own Symbol properties."""
		...

	@staticmethod
	def getPrototypeOf(obj: _Any) -> _Any | None:
		"""Return the prototype of an object."""
		...

	@staticmethod
	def hasOwn(obj: _Any, prop: str) -> bool:
		"""Return True if the object has the specified own property."""
		...

	@staticmethod
	def is_(value1: _Any, value2: _Any) -> bool:
		"""Determine if two values are the same value (SameValue algorithm)."""
		...

	@staticmethod
	def isExtensible(obj: _Any) -> bool:
		"""Return True if the object is extensible."""
		...

	@staticmethod
	def isFrozen(obj: _Any) -> bool:
		"""Return True if the object is frozen."""
		...

	@staticmethod
	def isSealed(obj: _Any) -> bool:
		"""Return True if the object is sealed."""
		...

	@staticmethod
	def keys(obj: dict[str, _Any]) -> list[str]:
		"""Return an array of enumerable property names."""
		...

	@staticmethod
	def preventExtensions(obj: T) -> T:
		"""Prevent new properties from being added. Returns the object."""
		...

	@staticmethod
	def seal(obj: T) -> T:
		"""Seal an object (prevent adding/removing properties). Returns the object."""
		...

	@staticmethod
	def setPrototypeOf(obj: T, prototype: _Any | None) -> T:
		"""Set the prototype of an object. Returns the object."""
		...

	@staticmethod
	def values(obj: dict[str, T]) -> list[T]:
		"""Return an array of enumerable property values."""
		...

	@staticmethod
	def groupBy(items: _Iterable[T], keyFn: _Any) -> dict[str, list[T]]:
		"""Group items by key function result (ES2024)."""
		...


# Self-register this module as a JS builtin (global identifier)
JsModule.register(name=None)
