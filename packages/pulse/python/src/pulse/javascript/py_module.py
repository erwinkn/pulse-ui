"""Python module transpilation system for javascript_v2.

Provides infrastructure for mapping Python modules (like `math`) to JavaScript equivalents.
For direct JavaScript module bindings, use the pulse.js.* module system instead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import TypeAlias, cast, override

from pulse.javascript.errors import JSCompilationError
from pulse.javascript.nodes import JSExpr

# Type alias for module transpilers - either a PyModule class or a dict
# The dict can contain JSExpr or Callable[..., JSExpr] during construction,
# but will be normalized to only JSExpr before storage
PyModuleTranspiler: TypeAlias = dict[str, JSExpr]


@dataclass
class PyModuleExpr(JSExpr):
	"""JSExpr for a Python module imported as a whole (e.g., `import math`).

	Holds a transpiler dict mapping attribute names to JSExpr.
	Attribute access looks up the attr in the dict and returns the result.
	"""

	transpiler: dict[str, JSExpr]

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
		value = self.transpiler.get(attr)
		if value is None:
			raise JSCompilationError(f"Module has no attribute '{attr}'")
		# transpiler always contains JSExpr (wrapping happens in register_module)
		return value


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

# Map from id(value) -> JSExpr
# For constants: id(math.pi) -> JSMember("Math", "PI")
# For functions: id(math.log) -> PyModuleFuncExpr(callable)
PY_MODULE_VALUES: dict[int, JSExpr] = {}


def register_module(
	module: ModuleType,
	transpilation: type[PyModule] | dict[str, JSExpr | Callable[..., JSExpr]],
) -> None:
	"""Register a Python module for transpilation.

	Args:
		module: The Python module to register (e.g., `math`, `pulse.html.tags`)
		transpilation: Either a PyModule subclass or a dict mapping attribute names
			to JSExpr (for constants) or Callable[..., JSExpr] (for functions).
			Callables will be wrapped in PyModuleFuncExpr during registration.
	"""
	# Convert PyModule class to dict if needed (wraps callables)
	transpiler_dict: PyModuleTranspiler = {}

	# Get items to iterate over - either from dict or PyModule class
	if isinstance(transpilation, dict):
		items = transpilation.items()
	else:
		# Convert PyModule class to (name, attr) pairs
		items = (
			(attr_name, getattr(transpilation, attr_name, None))
			for attr_name in dir(transpilation)
			if not attr_name.startswith("_")
		)

	# Normalize: wrap callables in PyModuleFuncExpr and register in PY_MODULE_VALUES
	for attr_name, attr in items:
		if isinstance(attr, JSExpr):
			attr = attr
		elif callable(attr):
			# Wrap callables in PyModuleFuncExpr so result always contains JSExpr
			attr = PyModuleFuncExpr(cast(Callable[..., JSExpr], attr))
		else:
			# Skip non-JSExpr, non-callable values
			continue

		transpiler_dict[attr_name] = attr
		PY_MODULE_VALUES[id(getattr(module, attr_name, None))] = attr

	# Store as dict (now normalized to only JSExpr)
	PY_MODULES[module] = transpiler_dict
