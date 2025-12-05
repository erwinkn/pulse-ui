"""
JavaScript Number builtin module.

Usage:
    import pulse.js.number as Number
    Number.isFinite(42)       # -> Number.isFinite(42)
    Number.MAX_SAFE_INTEGER   # -> Number.MAX_SAFE_INTEGER

    from pulse.js.number import isFinite, EPSILON
    isFinite(42)              # -> Number.isFinite(42)
    EPSILON                   # -> Number.EPSILON
"""

from __future__ import annotations

from pulse.transpiler.js_module import register_js_module

# Constants (type stubs for IDE support)
EPSILON: float
MAX_SAFE_INTEGER: int
MAX_VALUE: float
MIN_SAFE_INTEGER: int
MIN_VALUE: float
NaN: float
NEGATIVE_INFINITY: float
POSITIVE_INFINITY: float


# Static Methods (type stubs for IDE support)
def isFinite(value: float) -> bool: ...
def isInteger(value: float) -> bool: ...
def isNaN(value: float) -> bool: ...
def isSafeInteger(value: float) -> bool: ...
def parseFloat(string: str) -> float: ...
def parseInt(string: str, radix: int = 10) -> int: ...


# Self-register this module as a JS builtin
register_js_module(name="Number")
