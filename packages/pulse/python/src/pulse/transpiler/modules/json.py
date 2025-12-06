"""Python json module transpilation to JavaScript JSON."""

from pulse.transpiler.nodes import JSExpr, JSIdentifier, JSMemberCall
from pulse.transpiler.py_module import PyModule


def JSONCall(name: str, *args: JSExpr) -> JSExpr:
	return JSMemberCall(JSIdentifier("JSON"), name, list(args))


class PyJson(PyModule):
	"""Provides transpilation for Python json functions to JavaScript."""

	@staticmethod
	def dumps(obj: JSExpr) -> JSExpr:
		return JSONCall("stringify", obj)

	@staticmethod
	def loads(s: JSExpr) -> JSExpr:
		return JSONCall("parse", s)
