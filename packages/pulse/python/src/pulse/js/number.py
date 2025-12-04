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

from pulse.js._core import JsModuleConfig, setup_js_module

# Module configuration - Number is a JavaScript builtin (no import needed)
__js__ = JsModuleConfig.builtin("Number")

# Constants
EPSILON: float
MAX_SAFE_INTEGER: int
MAX_VALUE: float
MIN_SAFE_INTEGER: int
MIN_VALUE: float
NaN: float
NEGATIVE_INFINITY: float
POSITIVE_INFINITY: float


# Static Methods
def isFinite(value: float) -> bool: ...
def isInteger(value: float) -> bool: ...
def isNaN(value: float) -> bool: ...
def isSafeInteger(value: float) -> bool: ...
def parseFloat(string: str) -> float: ...
def parseInt(string: str, radix: int = 10) -> int: ...


# Replace stubs with JsValue markers at runtime
setup_js_module()
