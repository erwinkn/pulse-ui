"""JavaScript module bindings for use in @javascript decorated functions (transpiler_v2).

Usage:
    # For builtins (no import needed in JS):
    import pulse.js2.math as Math
    Math.PI  # -> Math.PI

    from pulse.js2.math import floor
    floor(x)  # -> Math.floor(x)

    # Direct import of builtins from pulse.js2:
    from pulse.js2 import Set, Number, Array, Math, Date, Promise
    Set([1, 2, 3])  # -> new Set([1, 2, 3])
    Number.isFinite(42)  # -> Number.isFinite(42)

    # Statement functions:
    from pulse.js2 import throw
    throw(Error("message"))  # -> throw Error("message");
"""

import importlib as _importlib
from typing import Any as _Any
from typing import NoReturn as _NoReturn

from pulse.transpiler_v2.nodes import UNDEFINED as _UNDEFINED
from pulse.transpiler_v2.nodes import Identifier as _Identifier

# Namespace modules that resolve to Identifier
_MODULE_EXPORTS_IDENTIFIER: dict[str, str] = {
	"JSON": "pulse.js2.json",
	"Math": "pulse.js2.math",
	"console": "pulse.js2.console",
	"window": "pulse.js2.window",
	"document": "pulse.js2.document",
	"navigator": "pulse.js2.navigator",
}

# Regular modules that resolve via getattr
_MODULE_EXPORTS_ATTRIBUTE: dict[str, str] = {
	"Array": "pulse.js2.array",
	"Date": "pulse.js2.date",
	"Error": "pulse.js2.error",
	"Map": "pulse.js2.map",
	"Object": "pulse.js2.object",
	"Promise": "pulse.js2.promise",
	"RegExp": "pulse.js2.regexp",
	"Set": "pulse.js2.set",
	"String": "pulse.js2.string",
	"WeakMap": "pulse.js2.weakmap",
	"WeakSet": "pulse.js2.weakset",
	"Number": "pulse.js2.number",
}


# Statement-like functions (not classes/objects, but callable transformers)
# Note: throw needs special handling in the transpiler to convert from expression to statement
class _ThrowExpr:
	"""Wrapper for throw that can be detected and converted to a statement."""

	def __call__(self, x: _Any) -> _NoReturn:
		# This will be replaced during transpilation
		# The transpiler should detect this and emit as a Throw statement
		raise RuntimeError("throw() can only be used in @javascript functions")


throw = _ThrowExpr()


# JS primitive values
undefined = _UNDEFINED


# Cache for exported values
_export_cache: dict[str, _Any] = {}


def __getattr__(name: str) -> _Any:
	"""Lazily import and return JS builtin modules.

	Allows: from pulse.js2 import Set, Number, Array, etc.
	"""
	# Return cached export if already imported
	if name in _export_cache:
		return _export_cache[name]

	# Check which dict contains the name
	if name in _MODULE_EXPORTS_IDENTIFIER:
		module = _importlib.import_module(_MODULE_EXPORTS_IDENTIFIER[name])
		export = _Identifier(name)
	elif name in _MODULE_EXPORTS_ATTRIBUTE:
		module = _importlib.import_module(_MODULE_EXPORTS_ATTRIBUTE[name])
		export = getattr(module, name)
	else:
		raise AttributeError(f"module 'pulse.js2' has no attribute '{name}'")

	_export_cache[name] = export
	return export
