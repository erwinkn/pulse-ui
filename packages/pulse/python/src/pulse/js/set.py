"""
JavaScript Set builtin module.

Usage:
	import pulse.js.set as Set
	Set()                         # -> new Set()
	Set([1, 2, 3])               # -> new Set([1, 2, 3])

	from pulse.js.set import Set
	Set()                         # -> new Set()
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Generic, TypeVar

from pulse.transpiler.js_module import register_js_module

_T = TypeVar("_T", covariant=True)


class Set(Generic[_T]):
	"""Class for JavaScript Set instances."""

	def __init__(self, iterable: Iterable[_T] | None = None): ...

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
register_js_module(name="Set", global_scope=True)
