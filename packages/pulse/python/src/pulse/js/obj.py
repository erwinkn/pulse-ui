"""
JavaScript object literal creation.

Usage:
    from pulse.js import obj

    # Create plain JS objects (not Maps):
    obj(a=1, b=2)          # -> { a: 1, b: 2 }

    # With spread syntax:
    obj(**base, c=3)       # -> { ...base, c: 3 }
    obj(a=1, **base)       # -> { a: 1, ...base }

    # Empty object:
    obj()                  # -> {}

Unlike dict() which transpiles to new Map(), obj() creates plain JavaScript
object literals. Use this for React props, style objects, and anywhere you
need a plain JS object.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from pulse.transpiler.errors import TranspileError
from pulse.transpiler.nodes import (
	Arrow,
	Binary,
	Call,
	Expr,
	Identifier,
	Member,
	Object,
	Spread,
	Ternary,
)
from pulse.transpiler.vdom import VDOMNode

if TYPE_CHECKING:
	from pulse.transpiler.transpiler import Transpiler


@dataclass(slots=True)
class ObjTransformer(Expr):
	"""Transformer for obj() with **spread support.

	obj(key=value, ...) -> { key: value, ... }
	obj(**base, key=value) -> { ...base, key: value }

	Creates a plain JavaScript object literal.
	Use this instead of dict() when you need a plain object (e.g., for React props).
	"""

	@override
	def emit(self, out: list[str]) -> None:
		raise TypeError("obj cannot be emitted directly - must be called")

	@override
	def render(self) -> VDOMNode:
		raise TypeError("obj cannot be rendered - must be called")

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		keywords: list[ast.keyword],
		ctx: Transpiler,
	) -> Expr:
		if args:
			raise TranspileError("obj() only accepts keyword arguments")

		props: list[tuple[str, Expr] | Spread] = []
		for kw in keywords:
			if kw.arg is None:
				# **spread syntax - wrap in Object.fromEntries if Map (dict literals transpile to Map)
				spread_expr = ctx.emit_expr(kw.value)
				# IIFE to evaluate spread_expr once: (($s) => $s instanceof Map ? Object.fromEntries($s) : $s)(spread_expr)
				s = Identifier("$s")
				is_map = Binary(s, "instanceof", Identifier("Map"))
				as_obj = Call(Member(Identifier("Object"), "fromEntries"), [s])
				props.append(
					Spread(
						Call(Arrow(["$s"], Ternary(is_map, as_obj, s)), [spread_expr])
					)
				)
			else:
				# key=value
				props.append((kw.arg, ctx.emit_expr(kw.value)))

		return Object(props)


# Create singleton instance for use as a callable
obj = ObjTransformer()
