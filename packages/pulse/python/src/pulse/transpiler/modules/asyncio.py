"""Python asyncio module transpilation to JavaScript Promise operations."""

from __future__ import annotations

from typing import Any, cast, final

from pulse.transpiler.nodes import (
	Array,
	Binary,
	Call,
	Expr,
	Identifier,
	Literal,
	Member,
	Ternary,
)
from pulse.transpiler.py_module import PyModule
from pulse.transpiler.transpiler import Transpiler

_Promise = Identifier("Promise")


@final
class PyAsyncio(PyModule):
	"""Provides transpilation for Python asyncio functions to JavaScript Promise methods."""

	@staticmethod
	def gather(*coros: Any, return_exceptions: Any = False, ctx: Transpiler) -> Expr:
		"""Transpile asyncio.gather to Promise.all or Promise.allSettled.

		Args:
			*coros: Variable number of coroutine/promise expressions
			return_exceptions: If True, use Promise.allSettled
			ctx: Transpiler context
		"""
		promises = Array([ctx.emit_expr(c) for c in coros])
		all_call = Call(Member(_Promise, "all"), [promises])
		all_settled_call = Call(Member(_Promise, "allSettled"), [promises])

		# Optimized: literal True -> allSettled
		if return_exceptions is True or (
			isinstance(return_exceptions, Literal) and return_exceptions.value is True
		):
			return all_settled_call

		# Optimized: literal False or default -> all
		if return_exceptions is False or (
			isinstance(return_exceptions, Literal) and return_exceptions.value is False
		):
			return all_call

		# General case: emit ternary on the expression
		return Ternary(
			Binary(ctx.emit_expr(cast(Any, return_exceptions)), "===", Literal(True)),
			all_settled_call,
			all_call,
		)
