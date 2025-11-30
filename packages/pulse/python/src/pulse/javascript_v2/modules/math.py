from collections.abc import Sequence

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


def MathMethod(name: str, args: Sequence[JSExpr]):
	return JSMemberCall(JSIdentifier("Math"), name, args)


class Math(JsModule):
	@staticmethod
	def abs(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("abs", [jsify(x)])

	@staticmethod
	def acos(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("acos", [jsify(x)])

	@staticmethod
	def acosh(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("acosh", [jsify(x)])

	@staticmethod
	def asin(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("asin", [jsify(x)])

	@staticmethod
	def asinh(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("asinh", [jsify(x)])

	@staticmethod
	def atan(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("atan", [jsify(x)])

	@staticmethod
	def atan2(y: int | float | JSExpr, x: int | float | JSExpr) -> JSExpr:
		return MathMethod("atan2", [jsify(y), jsify(x)])

	@staticmethod
	def atanh(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("atanh", [jsify(x)])

	@staticmethod
	def cbrt(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("cbrt", [jsify(x)])

	@staticmethod
	def ceil(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("ceil", [jsify(x)])

	@staticmethod
	def clz32(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("clz32", [jsify(x)])

	@staticmethod
	def cos(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("cos", [jsify(x)])

	@staticmethod
	def cosh(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("cosh", [jsify(x)])

	@staticmethod
	def exp(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("exp", [jsify(x)])

	@staticmethod
	def expm1(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("expm1", [jsify(x)])

	@staticmethod
	def floor(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("floor", [jsify(x)])

	@staticmethod
	def fround(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("fround", [jsify(x)])

	@staticmethod
	def hypot(*values: int | float | JSExpr) -> JSExpr:
		return MathMethod("hypot", [jsify(v) for v in values])

	@staticmethod
	def imul(x: int | float | JSExpr, y: int | float | JSExpr) -> JSExpr:
		return MathMethod("imul", [jsify(x), jsify(y)])

	@staticmethod
	def log(value: int | float | JSExpr) -> JSExpr:
		return MathMethod("log", [jsify(value)])

	@staticmethod
	def log10(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("log10", [jsify(x)])

	@staticmethod
	def log1p(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("log1p", [jsify(x)])

	@staticmethod
	def log2(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("log2", [jsify(x)])

	@staticmethod
	def max(*values: int | float | JSExpr) -> JSExpr:
		return MathMethod("max", [jsify(v) for v in values])

	@staticmethod
	def min(*values: int | float | JSExpr) -> JSExpr:
		return MathMethod("min", [jsify(v) for v in values])

	@staticmethod
	def pow(x: int | float | JSExpr, y: int | float | JSExpr) -> JSExpr:
		return MathMethod("pow", [jsify(x), jsify(y)])

	@staticmethod
	def random() -> JSExpr:
		return MathMethod("random", [])

	@staticmethod
	def round(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("round", [jsify(x)])

	@staticmethod
	def sign(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("sign", [jsify(x)])

	@staticmethod
	def sin(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("sin", [jsify(x)])

	@staticmethod
	def sinh(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("sinh", [jsify(x)])

	@staticmethod
	def sqrt(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("sqrt", [jsify(x)])

	@staticmethod
	def tan(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("tan", [jsify(x)])

	@staticmethod
	def tanh(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("tanh", [jsify(x)])

	@staticmethod
	def trunc(x: int | float | JSExpr) -> JSExpr:
		return MathMethod("trunc", [jsify(x)])

	# Constants
	@staticmethod
	def E() -> JSExpr:
		return JSMember(JSIdentifier("Math"), "E")

	@staticmethod
	def LN2() -> JSExpr:
		return JSMember(JSIdentifier("Math"), "LN2")

	@staticmethod
	def LN10() -> JSExpr:
		return JSMember(JSIdentifier("Math"), "LN10")

	@staticmethod
	def LOG2E() -> JSExpr:
		return JSMember(JSIdentifier("Math"), "LOG2E")

	@staticmethod
	def LOG10E() -> JSExpr:
		return JSMember(JSIdentifier("Math"), "LOG10E")

	@staticmethod
	def PI() -> JSExpr:
		return JSMember(JSIdentifier("Math"), "PI")

	@staticmethod
	def SQRT1_2() -> JSExpr:
		return JSMember(JSIdentifier("Math"), "SQRT1_2")

	@staticmethod
	def SQRT2() -> JSExpr:
		return JSMember(JSIdentifier("Math"), "SQRT2")


class PyMath(PyModule):
	"Provides transpilation for Python math functions"

	@staticmethod
	def acos(x: int | float | JSExpr) -> JSExpr:
		return Math.acos(x)

	@staticmethod
	def acosh(x: int | float | JSExpr) -> JSExpr:
		return Math.acosh(x)

	@staticmethod
	def asin(x: int | float | JSExpr) -> JSExpr:
		return Math.asin(x)

	@staticmethod
	def asinh(x: int | float | JSExpr) -> JSExpr:
		return Math.asinh(x)

	@staticmethod
	def atan(x: int | float | JSExpr) -> JSExpr:
		return Math.atan(x)

	@staticmethod
	def atan2(y: int | float | JSExpr, x: int | float | JSExpr) -> JSExpr:
		return Math.atan2(y, x)

	@staticmethod
	def atanh(x: int | float | JSExpr) -> JSExpr:
		return Math.atanh(x)

	@staticmethod
	def cbrt(x: int | float | JSExpr) -> JSExpr:
		return Math.cbrt(x)

	@staticmethod
	def ceil(x: int | float | JSExpr) -> JSExpr:
		return Math.ceil(x)

	@staticmethod
	def copysign(x: int | float | JSExpr, y: int | float | JSExpr) -> JSExpr:
		# Math.sign(y) * Math.abs(x)
		return JSBinary(Math.sign(y), "*", Math.abs(x))

	@staticmethod
	def cos(x: int | float | JSExpr) -> JSExpr:
		return Math.cos(x)

	@staticmethod
	def cosh(x: int | float | JSExpr) -> JSExpr:
		return Math.cosh(x)

	@staticmethod
	def degrees(x: int | float | JSExpr) -> JSExpr:
		# Convert radians to degrees: x * (180 / π)
		return JSBinary(jsify(x), "*", JSBinary(JSNumber(180), "/", Math.PI()))

	@staticmethod
	def dist(
		p: int | float | JSExpr | list[int | float | JSExpr],
		q: int | float | JSExpr | list[int | float | JSExpr],
	) -> JSExpr:
		# sqrt(sum((px - qx) ** 2 for px, qx in zip(p, q)))
		# This is a simplified version - full implementation would need array handling
		raise NotImplementedError("dist requires array/iterable handling")

	@staticmethod
	def erf(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("erf requires special function implementation")

	@staticmethod
	def erfc(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("erfc requires special function implementation")

	@staticmethod
	def exp(x: int | float | JSExpr) -> JSExpr:
		return Math.exp(x)

	@staticmethod
	def exp2(x: int | float | JSExpr) -> JSExpr:
		# 2 ** x
		return JSBinary(JSNumber(2), "**", jsify(x))

	@staticmethod
	def expm1(x: int | float | JSExpr) -> JSExpr:
		return Math.expm1(x)

	@staticmethod
	def fabs(x: int | float | JSExpr) -> JSExpr:
		return Math.abs(x)

	@staticmethod
	def factorial(x: int | float | JSExpr) -> JSExpr:
		raise NotImplementedError("factorial requires iterative implementation")

	@staticmethod
	def floor(x: int | float | JSExpr) -> JSExpr:
		return Math.floor(x)

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
		return Math.hypot(*coordinates)

	@staticmethod
	def isclose(
		a: int | float | JSExpr,
		b: int | float | JSExpr,
		*,
		rel_tol: int | float | JSExpr = 1e-09,
		abs_tol: int | float | JSExpr = 0.0,
	) -> JSExpr:
		# abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)
		abs_diff = Math.abs(JSBinary(jsify(a), "-", jsify(b)))
		max_abs = MathMethod("max", [Math.abs(jsify(a)), Math.abs(jsify(b))])
		rel_bound = JSBinary(jsify(rel_tol), "*", max_abs)
		max_bound = MathMethod("max", [rel_bound, jsify(abs_tol)])
		return JSBinary(abs_diff, "<=", max_bound)

	@staticmethod
	def isfinite(x: int | float | JSExpr) -> JSExpr:
		# Number.isFinite(x)
		return JSMemberCall(JSIdentifier("Number"), "isFinite", [jsify(x)])

	@staticmethod
	def isinf(x: int | float | JSExpr) -> JSExpr:
		# !Number.isFinite(x) && !Number.isNaN(x)
		is_finite = JSMemberCall(JSIdentifier("Number"), "isFinite", [jsify(x)])
		is_nan = JSMemberCall(JSIdentifier("Number"), "isNaN", [jsify(x)])
		return JSBinary(JSUnary("!", is_finite), "&&", JSUnary("!", is_nan))

	@staticmethod
	def isnan(x: int | float | JSExpr) -> JSExpr:
		# Number.isNaN(x)
		return JSMemberCall(JSIdentifier("Number"), "isNaN", [jsify(x)])

	@staticmethod
	def isqrt(n: int | float | JSExpr) -> JSExpr:
		# Math.floor(Math.sqrt(n))
		return Math.floor(Math.sqrt(n))

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
			return Math.log(value)
		else:
			return JSBinary(Math.log(value), "/", Math.log(base))

	@staticmethod
	def log10(x: int | float | JSExpr) -> JSExpr:
		return Math.log10(x)

	@staticmethod
	def log1p(x: int | float | JSExpr) -> JSExpr:
		return Math.log1p(x)

	@staticmethod
	def log2(x: int | float | JSExpr) -> JSExpr:
		return Math.log2(x)

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
		return Math.pow(x, y)

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
		return JSBinary(jsify(x), "*", JSBinary(Math.PI(), "/", JSNumber(180)))

	@staticmethod
	def remainder(x: int | float | JSExpr, y: int | float | JSExpr) -> JSExpr:
		# x - n * y where n is the nearest integer to x/y
		n = Math.round(JSBinary(jsify(x), "/", jsify(y)))
		return JSBinary(jsify(x), "-", JSBinary(n, "*", jsify(y)))

	@staticmethod
	def sin(x: int | float | JSExpr) -> JSExpr:
		return Math.sin(x)

	@staticmethod
	def sinh(x: int | float | JSExpr) -> JSExpr:
		return Math.sinh(x)

	@staticmethod
	def sqrt(x: int | float | JSExpr) -> JSExpr:
		return Math.sqrt(x)

	@staticmethod
	def sumprod(
		p: int | float | JSExpr | list[int | float | JSExpr],
		q: int | float | JSExpr | list[int | float | JSExpr],
	) -> JSExpr:
		raise NotImplementedError("sumprod requires iterable handling")

	@staticmethod
	def tan(x: int | float | JSExpr) -> JSExpr:
		return Math.tan(x)

	@staticmethod
	def tanh(x: int | float | JSExpr) -> JSExpr:
		return Math.tanh(x)

	@staticmethod
	def trunc(x: int | float | JSExpr) -> JSExpr:
		return Math.trunc(x)

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
