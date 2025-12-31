"""Python typing module transpilation - mostly no-ops for type hints."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import final, override

from pulse.transpiler.nodes import Expr
from pulse.transpiler.py_module import PyModule
from pulse.transpiler.transpiler import Transpiler
from pulse.transpiler.vdom import VDOMNode


@dataclass(slots=True)
class TypeHint(Expr):
	"""A type hint that should never be emitted directly.

	Used for typing constructs like Any that can be passed to cast() but
	shouldn't appear in generated code.
	"""

	name: str

	@override
	def emit(self, out: list[str]) -> None:
		raise TypeError(
			f"Type hint '{self.name}' cannot be emitted as JavaScript. "
			+ "It should only be used with typing.cast() or similar."
		)

	@override
	def render(self) -> VDOMNode:
		raise TypeError(
			f"Type hint '{self.name}' cannot be rendered. "
			+ "It should only be used with typing.cast() or similar."
		)

	@override
	def transpile_subscript(self, key: ast.expr, ctx: Transpiler) -> Expr:
		# List[int], Optional[str], etc. -> still a type hint
		return TypeHint(f"{self.name}[...]")


@final
class PyTyping(PyModule):
	"""Provides transpilation for Python typing functions."""

	# Type constructs used with cast() - error if emitted directly
	Any = TypeHint("Any")
	Optional = TypeHint("Optional")
	Union = TypeHint("Union")
	List = TypeHint("List")
	Dict = TypeHint("Dict")
	Set = TypeHint("Set")
	Tuple = TypeHint("Tuple")
	FrozenSet = TypeHint("FrozenSet")
	Type = TypeHint("Type")
	Callable = TypeHint("Callable")

	@staticmethod
	def cast(_type: ast.expr, val: ast.expr, *, ctx: Transpiler) -> Expr:
		"""cast(T, val) -> val (type cast is a no-op at runtime)."""
		return ctx.emit_expr(val)
