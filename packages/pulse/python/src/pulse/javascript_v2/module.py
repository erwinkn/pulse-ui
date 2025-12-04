"""Python module transpilation system for javascript_v2.

Provides infrastructure for mapping Python modules (like `math`) to JavaScript equivalents.
For direct JavaScript module bindings, use the pulse.js.* module system instead.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from pulse.javascript_v2.nodes import JSExpr
from pulse.javascript_v2.types import PyModuleTranspiler


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
