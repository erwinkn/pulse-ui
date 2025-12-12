"""Python math module transpilation to JavaScript Math.

Provides transpilation from Python's `math` module to JavaScript's `Math` object.
"""

from __future__ import annotations

from typing import Any, final

from pulse.transpiler_v2.nodes import (
	Binary,
	Call,
	ExprNode,
	Identifier,
	Literal,
	Member,
)
from pulse.transpiler_v2.py_module import PyModule
from pulse.transpiler_v2.transpiler import Transpiler

# Helpers for building Math.* calls
_Math = Identifier("Math")
_Number = Identifier("Number")


def _math_prop(name: str) -> ExprNode:
	return Member(_Math, name)


def _math_call(name: str, args: list[ExprNode]) -> ExprNode:
	return Call(Member(_Math, name), args)


def _number_call(name: str, args: list[ExprNode]) -> ExprNode:
	return Call(Member(_Number, name), args)


@final
class PyMath(PyModule):
	"""Provides transpilation for Python math functions to JavaScript."""

	# Constants
	pi = _math_prop("PI")
	e = _math_prop("E")
	tau = Binary(Literal(2), "*", _math_prop("PI"))
	inf = Identifier("Infinity")
	nan = Identifier("NaN")

	# Basic functions
	@staticmethod
	def acos(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("acos", [ctx.emit_expr(x)])

	@staticmethod
	def acosh(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("acosh", [ctx.emit_expr(x)])

	@staticmethod
	def asin(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("asin", [ctx.emit_expr(x)])

	@staticmethod
	def asinh(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("asinh", [ctx.emit_expr(x)])

	@staticmethod
	def atan(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("atan", [ctx.emit_expr(x)])

	@staticmethod
	def atan2(y: Any, x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("atan2", [ctx.emit_expr(y), ctx.emit_expr(x)])

	@staticmethod
	def atanh(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("atanh", [ctx.emit_expr(x)])

	@staticmethod
	def cbrt(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("cbrt", [ctx.emit_expr(x)])

	@staticmethod
	def ceil(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("ceil", [ctx.emit_expr(x)])

	@staticmethod
	def copysign(x: Any, y: Any, *, ctx: Transpiler) -> ExprNode:
		# Math.sign(y) * Math.abs(x)
		return Binary(
			_math_call("sign", [ctx.emit_expr(y)]),
			"*",
			_math_call("abs", [ctx.emit_expr(x)]),
		)

	@staticmethod
	def cos(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("cos", [ctx.emit_expr(x)])

	@staticmethod
	def cosh(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("cosh", [ctx.emit_expr(x)])

	@staticmethod
	def degrees(x: Any, *, ctx: Transpiler) -> ExprNode:
		# x * (180 / PI)
		return Binary(
			ctx.emit_expr(x),
			"*",
			Binary(Literal(180), "/", _math_prop("PI")),
		)

	@staticmethod
	def exp(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("exp", [ctx.emit_expr(x)])

	@staticmethod
	def exp2(x: Any, *, ctx: Transpiler) -> ExprNode:
		# 2 ** x
		return Binary(Literal(2), "**", ctx.emit_expr(x))

	@staticmethod
	def expm1(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("expm1", [ctx.emit_expr(x)])

	@staticmethod
	def fabs(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("abs", [ctx.emit_expr(x)])

	@staticmethod
	def floor(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("floor", [ctx.emit_expr(x)])

	@staticmethod
	def fmod(x: Any, y: Any, *, ctx: Transpiler) -> ExprNode:
		return Binary(ctx.emit_expr(x), "%", ctx.emit_expr(y))

	@staticmethod
	def hypot(*coords: Any, ctx: Transpiler) -> ExprNode:
		return _math_call("hypot", [ctx.emit_expr(c) for c in coords])

	@staticmethod
	def isclose(
		a: Any, b: Any, *, rel_tol: Any = 1e-9, abs_tol: Any = 0.0, ctx: Transpiler
	) -> ExprNode:
		# abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)
		a_expr = ctx.emit_expr(a)
		b_expr = ctx.emit_expr(b)
		rel_tol_expr = ctx.emit_expr(rel_tol)
		abs_tol_expr = ctx.emit_expr(abs_tol)

		abs_diff = _math_call("abs", [Binary(a_expr, "-", b_expr)])
		max_abs = _math_call(
			"max", [_math_call("abs", [a_expr]), _math_call("abs", [b_expr])]
		)
		rel_bound = Binary(rel_tol_expr, "*", max_abs)
		max_bound = _math_call("max", [rel_bound, abs_tol_expr])
		return Binary(abs_diff, "<=", max_bound)

	@staticmethod
	def isfinite(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _number_call("isFinite", [ctx.emit_expr(x)])

	@staticmethod
	def isinf(x: Any, *, ctx: Transpiler) -> ExprNode:
		# !Number.isFinite(x) && !Number.isNaN(x)
		x_expr = ctx.emit_expr(x)
		from pulse.transpiler_v2.nodes import Unary

		return Binary(
			Unary("!", _number_call("isFinite", [x_expr])),
			"&&",
			Unary("!", _number_call("isNaN", [x_expr])),
		)

	@staticmethod
	def isnan(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _number_call("isNaN", [ctx.emit_expr(x)])

	@staticmethod
	def isqrt(n: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("floor", [_math_call("sqrt", [ctx.emit_expr(n)])])

	@staticmethod
	def ldexp(x: Any, i: Any, *, ctx: Transpiler) -> ExprNode:
		# x * (2 ** i)
		return Binary(
			ctx.emit_expr(x),
			"*",
			Binary(Literal(2), "**", ctx.emit_expr(i)),
		)

	@staticmethod
	def log(value: Any, base: Any = None, *, ctx: Transpiler) -> ExprNode:
		if base is None:
			return _math_call("log", [ctx.emit_expr(value)])
		return Binary(
			_math_call("log", [ctx.emit_expr(value)]),
			"/",
			_math_call("log", [ctx.emit_expr(base)]),
		)

	@staticmethod
	def log10(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("log10", [ctx.emit_expr(x)])

	@staticmethod
	def log1p(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("log1p", [ctx.emit_expr(x)])

	@staticmethod
	def log2(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("log2", [ctx.emit_expr(x)])

	@staticmethod
	def pow(x: Any, y: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("pow", [ctx.emit_expr(x), ctx.emit_expr(y)])

	@staticmethod
	def radians(x: Any, *, ctx: Transpiler) -> ExprNode:
		# x * (PI / 180)
		return Binary(
			ctx.emit_expr(x),
			"*",
			Binary(_math_prop("PI"), "/", Literal(180)),
		)

	@staticmethod
	def remainder(x: Any, y: Any, *, ctx: Transpiler) -> ExprNode:
		# x - round(x/y) * y
		x_expr = ctx.emit_expr(x)
		y_expr = ctx.emit_expr(y)
		n = _math_call("round", [Binary(x_expr, "/", y_expr)])
		return Binary(x_expr, "-", Binary(n, "*", y_expr))

	@staticmethod
	def sin(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("sin", [ctx.emit_expr(x)])

	@staticmethod
	def sinh(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("sinh", [ctx.emit_expr(x)])

	@staticmethod
	def sqrt(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("sqrt", [ctx.emit_expr(x)])

	@staticmethod
	def tan(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("tan", [ctx.emit_expr(x)])

	@staticmethod
	def tanh(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("tanh", [ctx.emit_expr(x)])

	@staticmethod
	def trunc(x: Any, *, ctx: Transpiler) -> ExprNode:
		return _math_call("trunc", [ctx.emit_expr(x)])

	@staticmethod
	def fma(x: Any, y: Any, z: Any, *, ctx: Transpiler) -> ExprNode:
		# (x * y) + z
		return Binary(
			Binary(ctx.emit_expr(x), "*", ctx.emit_expr(y)),
			"+",
			ctx.emit_expr(z),
		)
