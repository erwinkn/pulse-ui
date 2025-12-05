"""Python typing module transpilation - mostly no-ops for type hints."""

from pulse.transpiler.nodes import JSExpr
from pulse.transpiler.py_module import PyModule


class PyTyping(PyModule):
	"""Provides transpilation for Python typing functions."""

	@staticmethod
	def cast(_type: JSExpr, val: JSExpr) -> JSExpr:
		"""cast(T, val) -> val (type cast is a no-op at runtime)."""
		return val
