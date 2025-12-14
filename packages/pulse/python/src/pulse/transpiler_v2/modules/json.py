"""Python json module transpilation to JavaScript JSON."""

from __future__ import annotations

from typing import Any, final

from pulse.transpiler_v2.nodes import Call, Expr, Identifier, Member
from pulse.transpiler_v2.py_module import PyModule
from pulse.transpiler_v2.transpiler import Transpiler

_JSON = Identifier("JSON")


@final
class PyJson(PyModule):
	"""Provides transpilation for Python json functions to JavaScript."""

	@staticmethod
	def dumps(obj: Any, *, ctx: Transpiler) -> Expr:
		return Call(Member(_JSON, "stringify"), [ctx.emit_expr(obj)])

	@staticmethod
	def loads(s: Any, *, ctx: Transpiler) -> Expr:
		return Call(Member(_JSON, "parse"), [ctx.emit_expr(s)])
