"""
JavaScript Map builtin module.

Usage:
    import pulse.js.map as Map
    Map()                         # -> new Map()
    Map([["a", 1]])              # -> new Map([["a", 1]])

    from pulse.js.map import Map
    Map()                         # -> new Map()
"""

from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import register_js_module as _register_js_module

_K = _TypeVar("_K")
_V = _TypeVar("_V")


class Map(_Generic[_K, _V]):
	"""Class for JavaScript Map instances."""

	def __init__(self, iterable: list[tuple[_K, _V]] | None = None): ...

	def clear(self) -> None: ...
	def delete(self, key: object) -> bool: ...
	def get(self, key: object) -> _V | None: ...
	def has(self, key: object) -> bool: ...
	def set(self, key: _K, value: _V) -> "Map[_K, _V]": ...

	@property
	def size(self) -> int: ...

	def entries(self) -> object: ...
	def forEach(self, callbackfn: object, thisArg: object | None = None) -> None: ...
	def keys(self) -> object: ...
	def values(self) -> object: ...


# Self-register this module as a JS builtin in global scope
_register_js_module(name="Map", global_scope=True)
