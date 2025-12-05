"""
JavaScript Set builtin module.

Usage:
	import pulse.js.set as Set
	Set()                         # -> new Set()
	Set([1, 2, 3])               # -> new Set([1, 2, 3])

	from pulse.js.set import Set
	Set()                         # -> new Set()
"""

from collections.abc import Iterable as _Iterable
from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import register_js_module as _register_js_module

_T = _TypeVar("_T", covariant=True)


class Set(_Generic[_T]):
	"""Class for JavaScript Set instances."""

	def __init__(self, iterable: _Iterable[_T] | None = None): ...

	@property
	def size(self) -> int: ...

	def add(self, value: object) -> None: ...
	def clear(self) -> None: ...
	def delete(self, value: object) -> bool: ...
	def has(self, value: object) -> bool: ...
	def entries(self) -> object: ...
	def forEach(self, callbackfn: object, thisArg: object | None = None) -> None: ...
	def keys(self) -> object: ...
	def values(self) -> object: ...


# Self-register this module as a JS builtin in global scope
_register_js_module(name="Set", global_scope=True)
