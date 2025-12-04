"""Python module transpilation system for javascript_v2.

Provides infrastructure for mapping Python modules (like `math`) to JavaScript equivalents.
For direct JavaScript module bindings, use the pulse.js.* module system instead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any, TypeAlias, override

from pulse.javascript_v2.errors import JSCompilationError
from pulse.javascript_v2.nodes import JSExpr

# Type alias for module transpilers - either a PyModule class or a dict
PyModuleTranspiler: TypeAlias = dict[str, "JSExpr | Callable[..., JSExpr]"]


@dataclass
class PyModuleExpr(JSExpr):
	"""JSExpr for a Python module imported as a whole (e.g., `import math`).

	Holds a transpiler dict mapping attribute names to JSExpr or callables.
	Attribute access looks up the attr in the dict and returns the result.
	"""

	transpiler: dict[str, JSExpr | Callable[..., JSExpr]]

	@override
	def emit(self) -> str:
		raise JSCompilationError("PyModuleExpr cannot be emitted directly")

	@override
	def emit_call(self, args: list[JSExpr], kwargs: dict[str, JSExpr]) -> JSExpr:
		raise JSCompilationError("PyModuleExpr cannot be called directly")

	@override
	def emit_subscript(self, indices: list[JSExpr]) -> JSExpr:
		raise JSCompilationError("PyModuleExpr cannot be subscripted")

	@override
	def emit_getattr(self, attr: str) -> JSExpr:
		method = self.transpiler.get(attr)
		if method is None:
			raise JSCompilationError(f"Module has no attribute '{attr}'")
		if isinstance(method, JSExpr):
			return method
		# It's a callable (function) - wrap in PyModuleFuncExpr for call
		return PyModuleFuncExpr(method)


@dataclass
class PyModuleFuncExpr(JSExpr):
	"""JSExpr for a function imported from a Python module (e.g., `from math import log`).

	Holds the emit callable that generates the JS AST when called.
	"""

	emit_fn: Callable[..., JSExpr]

	@override
	def emit(self) -> str:
		raise JSCompilationError("PyModuleFuncExpr cannot be emitted directly")

	@override
	def emit_call(self, args: list[JSExpr], kwargs: dict[str, JSExpr]) -> JSExpr:
		if kwargs:
			return self.emit_fn(*args, **kwargs)
		return self.emit_fn(*args)

	@override
	def emit_subscript(self, indices: list[JSExpr]) -> JSExpr:
		raise JSCompilationError("PyModuleFuncExpr cannot be subscripted")

	@override
	def emit_getattr(self, attr: str) -> JSExpr:
		raise JSCompilationError("PyModuleFuncExpr cannot have attributes")


class PyModule:
	"""Base class for Python module transpilation mappings.

	Subclasses define static methods and class attributes that map Python module
	functions and constants to their JavaScript equivalents.

	Example:
		class PyMath(PyModule):
			# Constants - JSExpr values
			pi = JSMember(JSIdentifier("Math"), "PI")

			# Functions - return JSExpr
			@staticmethod
			def floor(x: JSExpr) -> JSExpr:
				return JSMemberCall(JSIdentifier("Math"), "floor", [x])
	"""


PY_MODULES: dict[ModuleType, PyModuleTranspiler] = {}

# Map from id(value) -> JSExpr or Callable[..., JSExpr]
# For constants: id(math.pi) -> JSMember("Math", "PI")
# For functions: id(math.log) -> PyMath.log (the callable that emits JS)
PY_MODULE_VALUES: dict[int, JSExpr | Any] = {}  # Any = Callable[..., JSExpr]


def _pymodule_to_dict(pymodule_class: type[PyModule]) -> PyModuleTranspiler:
	"""Convert a PyModule class to a dictionary."""
	result: PyModuleTranspiler = {}
	for attr_name in dir(pymodule_class):
		if attr_name.startswith("_"):
			continue
		attr = getattr(pymodule_class, attr_name, None)
		if attr is None:
			continue
		if isinstance(attr, JSExpr) or callable(attr):
			result[attr_name] = attr  # pyright: ignore[reportArgumentType]
	return result


def register_module(
	module: ModuleType, transpilation: type[PyModule] | PyModuleTranspiler
) -> None:
	"""Register a Python module for transpilation.

	Args:
		module: The Python module to register (e.g., `math`, `pulse.html.tags`)
		transpilation: Either a PyModule subclass or a dict mapping attribute names
			to JSExpr (for constants) or Callable[..., JSExpr] (for functions)
	"""
	# Convert PyModule class to dict if needed
	if isinstance(transpilation, dict):
		transpiler_dict = transpilation
	else:
		transpiler_dict = _pymodule_to_dict(transpilation)

	# Store as dict
	PY_MODULES[module] = transpiler_dict

	# Register values and functions from the transpilation
	for attr_name, attr in transpiler_dict.items():
		module_value = getattr(module, attr_name, None)
		if module_value is None:
			continue
		if isinstance(attr, JSExpr) or callable(attr):
			PY_MODULE_VALUES[id(module_value)] = attr
