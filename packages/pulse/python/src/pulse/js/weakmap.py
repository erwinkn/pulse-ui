"""
JavaScript WeakMap builtin module.

Usage:
    import pulse.js.weakmap as WeakMap
    WeakMap()                     # -> new WeakMap()
    WeakMap([[obj, "value"]])    # -> new WeakMap([[obj, "value"]])

    from pulse.js.weakmap import WeakMap
    WeakMap()                     # -> new WeakMap()
"""

from typing import Generic as _Generic
from typing import TypeVar as _TypeVar

from pulse.transpiler.js_module import register_js_module as _register_js_module

_K = _TypeVar("_K", bound=object)
_V = _TypeVar("_V")


class WeakMap(_Generic[_K, _V]):
	"""Class for JavaScript WeakMap instances."""

	def __init__(self, iterable: list[tuple[_K, _V]] | None = None): ...

	def delete(self, key: object) -> bool: ...
	def get(self, key: object) -> _V | None: ...
	def has(self, key: object) -> bool: ...
	def set(self, key: _K, value: _V) -> "WeakMap[_K, _V]": ...


# Self-register this module as a JS builtin
_register_js_module(name="WeakMap", global_scope=True)
