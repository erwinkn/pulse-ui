"""Type definitions for JavaScript transpilation dependencies.

This module contains the types used to represent dependencies in transpiled functions.
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING, Callable, TypeAlias

if TYPE_CHECKING:
	from pulse.javascript_v2.constants import JsConstant
	from pulse.javascript_v2.imports import Import
	from pulse.javascript_v2.nodes import JSExpr
	from pulse.js._core import JsModuleConfig


class PyBuiltin:
	"""Placeholder for Python builtins that need JS equivalents."""

	name: str

	def __init__(self, name: str) -> None:
		self.name = name


class JsModuleRef:
	"""Reference to a pulse.js.* module imported as a whole.

	Example: `import pulse.js.math as Math`

	The config contains all information needed to generate the JS code:
	- config.name: The JS identifier (e.g., "Math")
	- config.src: Import source for external modules (None for builtins)
	- config.kind: Import kind (named, default, namespace)
	"""

	module: types.ModuleType
	config: JsModuleConfig

	def __init__(self, module: types.ModuleType, config: JsModuleConfig) -> None:
		self.module = module
		self.config = config


class PyModuleRef:
	"""Reference to a registered Python module for transpilation.

	When a function uses `import math`, we create a PyModuleRef that tracks
	the module and its transpiler (a dict mapping attribute names to JSExpr or callables).
	"""

	module: types.ModuleType
	transpiler: PyModuleTranspiler

	def __init__(
		self, module: types.ModuleType, transpiler: PyModuleTranspiler
	) -> None:
		self.module = module
		self.transpiler = transpiler


class PyModuleFunctionRef:
	"""Reference to a function imported from a registered Python module.

	When a function uses `from math import log`, we create a PyModuleFunctionRef
	that holds the emit callable (e.g., PyMath.log) that generates the JS AST.
	"""

	emit: Callable[..., JSExpr]

	def __init__(self, emit: Callable[..., JSExpr]) -> None:
		self.emit = emit


# Type alias for module transpilers - either a PyModule class or a dict
PyModuleTranspiler = dict[
	str, "JSExpr | Callable[..., JSExpr]"
]  # type = PyModule subclass

# Type alias for all possible dependency types
# Note: JsFunction is not included here to avoid circular imports
# It's added to the union in function.py where JsFunction is defined
# JsValue is from pulse.js._core and represents individual values from JS modules
JsDep: TypeAlias = "JsConstant | Import | PyBuiltin | PyModuleRef | PyModuleFunctionRef | JsModuleRef | JSExpr"
