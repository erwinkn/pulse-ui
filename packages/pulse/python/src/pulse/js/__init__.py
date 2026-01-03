"""JavaScript module bindings for use in @javascript decorated functions (transpiler).

Usage:
    # Import JS classes (for constructors and static methods):
    from pulse.js import Set, Number, Array, Date, Promise, Map, Error
    Set([1, 2, 3])         # -> new Set([1, 2, 3])
    Number.isFinite(42)    # -> Number.isFinite(42)
    Array.isArray(x)       # -> Array.isArray(x)

    # Import JS namespace objects (function-only modules):
    from pulse.js import Math, JSON, console, window, document, navigator
    Math.floor(3.7)        # -> Math.floor(3.7)
    JSON.stringify(obj)    # -> JSON.stringify(obj)
    console.log("hi")      # -> console.log("hi")

    # Alternative: import namespace modules for namespace access:
    import pulse.js.json as JSON
    JSON.stringify(obj)    # -> JSON.stringify(obj)

    # Statement functions:
    from pulse.js import throw
    throw(Error("message"))  # -> throw Error("message");

    # Object literals (plain JS objects instead of Map):
    from pulse.js import obj
    obj(a=1, b=2)          # -> { a: 1, b: 2 }
"""

import importlib as _importlib
from typing import Any as _Any
from typing import NoReturn as _NoReturn

from pulse.transpiler.builtins import obj as obj
from pulse.transpiler.nodes import EXPR_REGISTRY as _EXPR_REGISTRY
from pulse.transpiler.nodes import UNDEFINED as _UNDEFINED

# Namespace modules - return JsModule from registry (handles both builtins and external)
_MODULE_EXPORTS_NAMESPACE: dict[str, str] = {
	"JSON": "pulse.js.json",
	"Math": "pulse.js.math",
	"React": "pulse.js.react",
	"console": "pulse.js.console",
	"window": "pulse.js.window",
	"document": "pulse.js.document",
	"navigator": "pulse.js.navigator",
}

# Class modules - return via getattr to get Class wrapper (emits `new ...`)
_MODULE_EXPORTS_ATTRIBUTE: dict[str, str] = {
	"Array": "pulse.js.array",
	"Date": "pulse.js.date",
	"Error": "pulse.js.error",
	"Map": "pulse.js.map",
	"Object": "pulse.js.object",
	"Promise": "pulse.js.promise",
	"RegExp": "pulse.js.regexp",
	"Set": "pulse.js.set",
	"String": "pulse.js.string",
	"WeakMap": "pulse.js.weakmap",
	"WeakSet": "pulse.js.weakset",
	"Number": "pulse.js.number",
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

	Allows: from pulse.js import Set, Number, Array, etc.
	"""
	# Return cached export if already imported
	if name in _export_cache:
		return _export_cache[name]

	# Namespace modules: return JsModule (handles attribute access via transpile_getattr)
	if name in _MODULE_EXPORTS_NAMESPACE:
		module = _importlib.import_module(_MODULE_EXPORTS_NAMESPACE[name])
		export = _EXPR_REGISTRY[id(module)]
	# Class modules: return Class wrapper via getattr (emits `new ...()`)
	elif name in _MODULE_EXPORTS_ATTRIBUTE:
		module = _importlib.import_module(_MODULE_EXPORTS_ATTRIBUTE[name])
		export = getattr(module, name)
	else:
		raise AttributeError(f"module 'pulse.js' has no attribute '{name}'")

	_export_cache[name] = export
	return export
