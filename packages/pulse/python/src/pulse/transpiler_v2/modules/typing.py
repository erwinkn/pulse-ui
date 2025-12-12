"""Python typing module transpilation - mostly no-ops for type hints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, final, override

from pulse.transpiler_v2.nodes import ExprNode
from pulse.transpiler_v2.py_module import PyModule
from pulse.transpiler_v2.transpiler import Transpiler


@dataclass(slots=True)
class TypeHint(ExprNode):
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
	def emit_subscript(self, key: Any, ctx: Transpiler) -> ExprNode:
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
	def cast(_type: Any, val: Any, *, ctx: Transpiler) -> ExprNode:
		"""cast(T, val) -> val (type cast is a no-op at runtime)."""
		return ctx.emit_expr(val)
