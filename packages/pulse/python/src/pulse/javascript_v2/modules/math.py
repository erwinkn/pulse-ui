"""JavaScript Math module bindings."""

from typing import ClassVar

from pulse.javascript_v2.constants import jsify
from pulse.javascript_v2.module import JsModule, PyModule
from pulse.javascript_v2.nodes import (
	JSBinary,
	JSExpr,
	JSIdentifier,
	JSMember,
	JSMemberCall,
	JSNumber,
	JSUnary,
)


class Math(JsModule):
	"""JavaScript Math object bindings.

	Type hints match Python semantics for use in @javascript functions.
	At runtime, accessing any method/property raises JsModuleError.
	"""

	# Constants
	E: ClassVar[float]
	LN2: ClassVar[float]
	LN10: ClassVar[float]
	LOG2E: ClassVar[float]
	LOG10E: ClassVar[float]
	PI: ClassVar[float]
	SQRT1_2: ClassVar[float]
	SQRT2: ClassVar[float]

	# Methods
	@staticmethod
	def abs(x: float) -> float: ...

	@staticmethod
	def acos(x: float) -> float: ...

	@staticmethod
	def acosh(x: float) -> float: ...

	@staticmethod
	def asin(x: float) -> float: ...

	@staticmethod
	def asinh(x: float) -> float: ...

	@staticmethod
	def atan(x: float) -> float: ...

	@staticmethod
	def atan2(y: float, x: float) -> float: ...

	@staticmethod
	def atanh(x: float) -> float: ...

	@staticmethod
	def cbrt(x: float) -> float: ...

	@staticmethod
	def ceil(x: float) -> int: ...

	@staticmethod
	def clz32(x: int) -> int: ...

	@staticmethod
	def cos(x: float) -> float: ...

	@staticmethod
	def cosh(x: float) -> float: ...

	@staticmethod
	def exp(x: float) -> float: ...

	@staticmethod
	def expm1(x: float) -> float: ...

	@staticmethod
	def floor(x: float) -> int: ...

	@staticmethod
	def fround(x: float) -> float: ...

	@staticmethod
	def hypot(*values: float) -> float: ...

	@staticmethod
	def imul(x: int, y: int) -> int: ...

	@staticmethod
	def log(x: float) -> float: ...

	@staticmethod
	def log10(x: float) -> float: ...

	@staticmethod
	def log1p(x: float) -> float: ...

	@staticmethod
	def log2(x: float) -> float: ...

	@staticmethod
	def max(*values: float) -> float: ...

	@staticmethod
	def min(*values: float) -> float: ...

	@staticmethod
	def pow(x: float, y: float) -> float: ...

	@staticmethod
	def random() -> float: ...

	@staticmethod
	def round(x: float) -> int: ...

	@staticmethod
	def sign(x: float) -> int: ...

	@staticmethod
	def sin(x: float) -> float: ...

	@staticmethod
	def sinh(x: float) -> float: ...

	@staticmethod
	def sqrt(x: float) -> float: ...

	@staticmethod
	def tan(x: float) -> float: ...

	@staticmethod
	def tanh(x: float) -> float: ...

	@staticmethod
	def trunc(x: float) -> int: ...


# Helper for generating Math method calls during transpilation
def MathCall(name: str, *args: int | float | JSExpr) -> JSExpr:
	return JSMemberCall(JSIdentifier("Math"), name, [jsify(a) for a in args])


def MathProp(name: str) -> JSExpr:
	return JSMember(JSIdentifier("Math"), name)


class PyMath(PyModule):
	"""Provides transpilation for Python math functions to JavaScript."""

	# Constants (as class attributes returning JSExpr)
	pi = MathProp("PI")
	e = MathProp("E")
	tau = JSBinary(JSNumber(2), "*", MathProp("PI"))  # 2 * PI
	inf = JSIdentifier("Infinity")
	nan = JSIdentifier("NaN")

	@staticmethod
	def acos(x: int | float | JSExpr) -> JSExpr:
		return MathCall("acos", x)

	@staticmethod
	def acosh(x: int | float | JSExpr) -> JSExpr:
		return MathCall("acosh", x)

	@staticmethod
	def asin(x: int | float | JSExpr) -> JSExpr:
		return MathCall("asin", x)

	@staticmethod
	def asinh(x: int | float | JSExpr) -> JSExpr:
		return MathCall("asinh", x)

	@staticmethod
	def atan(x: int | float | JSExpr) -> JSExpr:
		return MathCall("atan", x)

	@staticmethod
	def atan2(y: int | float | JSExpr, x: int | float | JSExpr) -> JSExpr:
		return MathCall("atan2", y, x)

	@staticmethod
	def atanh(x: int | float | JSExpr) -> JSExpr:
		return MathCall("atanh", x)

	@staticmethod
	def cbrt(x: int | float | JSExpr) -> JSExpr:
		return MathCall("cbrt", x)

	@staticmethod
	def ceil(x: int | float | JSExpr) -> JSExpr:
		return MathCall("ceil", x)

	@staticmethod
	def copysign(x: int | float | JSExpr, y: int | float | JSExpr) -> JSExpr:
		# Math.sign(y) * Math.abs(x)
		return JSBinary(MathCall("sign", y), "*", MathCall("abs", x))

	@staticmethod
	def cos(x: int | float | JSExpr) -> JSExpr:
		return MathCall("cos", x)

	@staticmethod
	def cosh(x: int | float | JSExpr) -> JSExpr:
		return MathCall("cosh", x)

	@staticmethod
	def degrees(x: int | float | JSExpr) -> JSExpr:
		# Convert radians to degrees: x * (180 / π)
		return JSBinary(jsify(x), "*", JSBinary(JSNumber(180), "/", MathProp("PI")))

	@staticmethod
	def dist(
		p: int | float | JSExpr | list[int | float | JSExpr],
		q: int | float | JSExpr | list[int | float | JSExpr],
	) -> JSExpr:
		raise NotImplementedError("dist requires array/iterable handling")

	@staticmethod
	def erf(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("erf requires special function implementation")

	@staticmethod
	def erfc(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("erfc requires special function implementation")

	@staticmethod
	def exp(x: int | float | JSExpr) -> JSExpr:
		return MathCall("exp", x)

	@staticmethod
	def exp2(x: int | float | JSExpr) -> JSExpr:
		# 2 ** x
		return JSBinary(JSNumber(2), "**", jsify(x))

	@staticmethod
	def expm1(x: int | float | JSExpr) -> JSExpr:
		return MathCall("expm1", x)

	@staticmethod
	def fabs(x: int | float | JSExpr) -> JSExpr:
		return MathCall("abs", x)

	@staticmethod
	def factorial(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("factorial requires iterative implementation")

	@staticmethod
	def floor(x: int | float | JSExpr) -> JSExpr:
		return MathCall("floor", x)

	@staticmethod
	def fmod(x: int | float | JSExpr, y: int | float | JSExpr) -> JSExpr:
		# JavaScript % operator matches Python fmod for most cases
		return JSBinary(jsify(x), "%", jsify(y))

	@staticmethod
	def frexp(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("frexp returns tuple, requires special handling")

	@staticmethod
	def fsum(seq: int | float | JSExpr | list[int | float | JSExpr]) -> JSExpr:
		raise NotImplementedError("fsum requires iterable handling")

	@staticmethod
	def gamma(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("gamma requires special function implementation")

	@staticmethod
	def gcd(*integers: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("gcd requires iterative implementation")

	@staticmethod
	def hypot(*coordinates: int | float | JSExpr) -> JSExpr:
		return MathCall("hypot", *coordinates)

	@staticmethod
	def isclose(
		a: int | float | JSExpr,
		b: int | float | JSExpr,
		*,
		rel_tol: int | float | JSExpr = 1e-09,
		abs_tol: int | float | JSExpr = 0.0,
	) -> JSExpr:
		# abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)
		abs_diff = MathCall("abs", JSBinary(jsify(a), "-", jsify(b)))
		max_abs = JSMemberCall(
			JSIdentifier("Math"),
			"max",
			[MathCall("abs", a), MathCall("abs", b)],
		)
		rel_bound = JSBinary(jsify(rel_tol), "*", max_abs)
		max_bound = JSMemberCall(
			JSIdentifier("Math"), "max", [rel_bound, jsify(abs_tol)]
		)
		return JSBinary(abs_diff, "<=", max_bound)

	@staticmethod
	def isfinite(x: int | float | JSExpr) -> JSExpr:
		return JSMemberCall(JSIdentifier("Number"), "isFinite", [jsify(x)])

	@staticmethod
	def isinf(x: int | float | JSExpr) -> JSExpr:
		is_finite = JSMemberCall(JSIdentifier("Number"), "isFinite", [jsify(x)])
		is_nan = JSMemberCall(JSIdentifier("Number"), "isNaN", [jsify(x)])
		return JSBinary(JSUnary("!", is_finite), "&&", JSUnary("!", is_nan))

	@staticmethod
	def isnan(x: int | float | JSExpr) -> JSExpr:
		return JSMemberCall(JSIdentifier("Number"), "isNaN", [jsify(x)])

	@staticmethod
	def isqrt(n: int | float | JSExpr) -> JSExpr:
		return MathCall("floor", MathCall("sqrt", n))

	@staticmethod
	def lcm(*integers: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("lcm requires iterative implementation")

	@staticmethod
	def ldexp(x: int | float | JSExpr, i: int | float | JSExpr) -> JSExpr:
		# x * (2 ** i)
		return JSBinary(jsify(x), "*", JSBinary(JSNumber(2), "**", jsify(i)))

	@staticmethod
	def lgamma(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("lgamma requires special function implementation")

	@staticmethod
	def log(
		value: int | float | JSExpr,
		base: int | float | JSExpr | None = None,
	) -> JSExpr:
		if base is None:
			return MathCall("log", value)
		return JSBinary(MathCall("log", value), "/", MathCall("log", base))

	@staticmethod
	def log10(x: int | float | JSExpr) -> JSExpr:
		return MathCall("log10", x)

	@staticmethod
	def log1p(x: int | float | JSExpr) -> JSExpr:
		return MathCall("log1p", x)

	@staticmethod
	def log2(x: int | float | JSExpr) -> JSExpr:
		return MathCall("log2", x)

	@staticmethod
	def modf(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("modf returns tuple, requires special handling")

	@staticmethod
	def nextafter(
		x: int | float | JSExpr,
		y: int | float | JSExpr,
		*,
		steps: int | float | JSExpr | None = None,
	) -> JSExpr:
		raise NotImplementedError("nextafter requires special implementation")

	@staticmethod
	def perm(n: int | float | JSExpr, k: int | float | JSExpr | None = None) -> JSExpr:
		raise NotImplementedError("perm requires factorial implementation")

	@staticmethod
	def pow(x: int | float | JSExpr, y: int | float | JSExpr) -> JSExpr:
		return MathCall("pow", x, y)

	@staticmethod
	def prod(
		iterable: int | float | JSExpr | list[int | float | JSExpr],
		*,
		start: int | float | JSExpr = 1,
	) -> JSExpr:
		raise NotImplementedError("prod requires iterable handling")

	@staticmethod
	def radians(x: int | float | JSExpr) -> JSExpr:
		# Convert degrees to radians: x * (π / 180)
		return JSBinary(jsify(x), "*", JSBinary(MathProp("PI"), "/", JSNumber(180)))

	@staticmethod
	def remainder(x: int | float | JSExpr, y: int | float | JSExpr) -> JSExpr:
		# x - n * y where n is the nearest integer to x/y
		n = MathCall("round", JSBinary(jsify(x), "/", jsify(y)))
		return JSBinary(jsify(x), "-", JSBinary(n, "*", jsify(y)))

	@staticmethod
	def sin(x: int | float | JSExpr) -> JSExpr:
		return MathCall("sin", x)

	@staticmethod
	def sinh(x: int | float | JSExpr) -> JSExpr:
		return MathCall("sinh", x)

	@staticmethod
	def sqrt(x: int | float | JSExpr) -> JSExpr:
		return MathCall("sqrt", x)

	@staticmethod
	def sumprod(
		p: int | float | JSExpr | list[int | float | JSExpr],
		q: int | float | JSExpr | list[int | float | JSExpr],
	) -> JSExpr:
		raise NotImplementedError("sumprod requires iterable handling")

	@staticmethod
	def tan(x: int | float | JSExpr) -> JSExpr:
		return MathCall("tan", x)

	@staticmethod
	def tanh(x: int | float | JSExpr) -> JSExpr:
		return MathCall("tanh", x)

	@staticmethod
	def trunc(x: int | float | JSExpr) -> JSExpr:
		return MathCall("trunc", x)

	@staticmethod
	def ulp(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("ulp requires special implementation")

	@staticmethod
	def fma(
		x: int | float | JSExpr,
		y: int | float | JSExpr,
		z: int | float | JSExpr,
	) -> JSExpr:
		# Fused multiply-add: (x * y) + z (with single rounding)
		# JavaScript doesn't have native fma, so we just do the operation
		return JSBinary(JSBinary(jsify(x), "*", jsify(y)), "+", jsify(z))

	@staticmethod
	def comb(n: int | float | JSExpr, k: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("comb requires factorial implementation")
