"""
JavaScript Number builtin module.

Usage:
    import pulse.js2.number as Number
    Number.isFinite(42)       # -> Number.isFinite(42)
    Number.MAX_SAFE_INTEGER   # -> Number.MAX_SAFE_INTEGER

    from pulse.js2.number import isFinite, EPSILON
    isFinite(42)              # -> Number.isFinite(42)
    EPSILON                   # -> Number.EPSILON
"""

from typing import Any as _Any
from typing import ClassVar as _ClassVar

from pulse.transpiler_v2.js_module import JsModule


class Number:
	"""JavaScript Number constructor and namespace."""

	def __init__(self, value: _Any) -> None: ...

	EPSILON: _ClassVar[float]
	MAX_SAFE_INTEGER: _ClassVar[int]
	MAX_VALUE: _ClassVar[float]
	MIN_SAFE_INTEGER: _ClassVar[int]
	MIN_VALUE: _ClassVar[float]
	NaN: _ClassVar[float]
	NEGATIVE_INFINITY: _ClassVar[float]
	POSITIVE_INFINITY: _ClassVar[float]

	@staticmethod
	def isFinite(value: float) -> bool: ...

	@staticmethod
	def isInteger(value: float) -> bool: ...

	@staticmethod
	def isNaN(value: float) -> bool: ...

	@staticmethod
	def isSafeInteger(value: float) -> bool: ...

	@staticmethod
	def parseFloat(string: str) -> float: ...

	@staticmethod
	def parseInt(string: str, radix: int = 10) -> int: ...


# Self-register this module as a JS builtin
JsModule.register(name="Number")
