"""Python typing module transpilation - mostly no-ops for type hints."""

from typing import Any as _Any
from typing import final, override

from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.nodes import JSExpr
from pulse.transpiler.py_module import PyModule


class JSTypeHint(JSExpr):
	"""A type hint that should never be emitted directly.

	Used for typing constructs like Any that can be passed to cast() but
	shouldn't appear in generated code.
	"""

	name: str

	def __init__(self, name: str) -> None:
		self.name = name

	@override
	def emit(self) -> str:
		raise JSCompilationError(
			f"Type hint '{self.name}' cannot be emitted as JavaScript. "
			+ "It should only be used with typing.cast() or similar."
		)

	@override
	def emit_subscript(self, indices: list[_Any]) -> JSExpr:
		# List[int], Optional[str], etc. -> still a type hint
		args = ", ".join("..." for _ in indices)
		return JSTypeHint(f"{self.name}[{args}]")


@final
class PyTyping(PyModule):
	"""Provides transpilation for Python typing functions."""

	# Type constructs used with cast() - error if emitted directly
	Any = JSTypeHint("Any")
	Optional = JSTypeHint("Optional")
	Union = JSTypeHint("Union")
	List = JSTypeHint("List")
	Dict = JSTypeHint("Dict")
	Set = JSTypeHint("Set")
	Tuple = JSTypeHint("Tuple")
	FrozenSet = JSTypeHint("FrozenSet")
	Type = JSTypeHint("Type")
	Callable = JSTypeHint("Callable")

	@staticmethod
	def cast(_type: _Any, val: _Any) -> JSExpr:
		"""cast(T, val) -> val (type cast is a no-op at runtime).

		The type argument is completely ignored - we don't try to convert it.
		"""
		return JSExpr.of(val)
