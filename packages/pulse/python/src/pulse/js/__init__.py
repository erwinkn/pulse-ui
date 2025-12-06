"""JavaScript module bindings for use in @javascript decorated functions.

Usage:
    # For builtins (no import needed in JS):
    import pulse.js.math as Math
    Math.PI  # -> Math.PI

    from pulse.js.math import floor
    floor(x)  # -> Math.floor(x)

    # Direct import of builtins from pulse.js:
    from pulse.js import Set, Number, Array, Math, Date, Promise
    Set([1, 2, 3])  # -> new Set([1, 2, 3])
    Number.isFinite(42)  # -> Number.isFinite(42)

    # Statement functions:
    from pulse.js import throw
    throw(Error("message"))  # -> throw Error("message");

    # For external modules:
    from pulse.js.lodash import chunk
    chunk(arr, 2)  # -> import { chunk } from "lodash"; chunk(arr, 2)

    import pulse.js.lodash as _
    _.debounce(fn, 100)  # -> import _ from "lodash"; _.debounce(fn, 100)
"""

import importlib as _importlib
from typing import Any as _Any
from typing import NoReturn as _NoReturn

from pulse.transpiler.nodes import (
	JSIdentifier as _JSIdentifier,
)
from pulse.transpiler.nodes import (
	JSStmtExpr as _JSStmtExpr,
)
from pulse.transpiler.nodes import (
	JSThrow as _JSThrow,
)
from pulse.transpiler.nodes import (
	JSUndefined as _JSUndefined,
)
from pulse.transpiler.nodes import (
	js_transformer as _js_transformer,
)

# Namespace modules that resolve to JSIdentifier
_MODULE_EXPORTS_IDENTIFIER: dict[str, str] = {
	"JSON": "pulse.js.json",
	"Math": "pulse.js.math",
	"console": "pulse.js.console",
	"window": "pulse.js.window",
	"document": "pulse.js.document",
	"navigator": "pulse.js.navigator",
}

# Regular modules that resolve via getattr
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
@_js_transformer("throw")
def throw(x: _Any) -> _NoReturn:
	# x is typed as _Any for users, but at transpile time it's JSExpr
	return _JSStmtExpr(_JSThrow(x), name="throw")  # pyright: ignore[reportGeneralTypeIssues]


# JS primitive values
undefined = _JSUndefined()


# Cache for exported values
_export_cache: dict[str, _Any] = {}


def __getattr__(name: str) -> _Any:
	"""Lazily import and return JS builtin modules.

	Allows: from pulse.js import Set, Number, Array, etc.
	"""
	# Return cached export if already imported
	if name in _export_cache:
		return _export_cache[name]

	# Check which dict contains the name
	if name in _MODULE_EXPORTS_IDENTIFIER:
		module = _importlib.import_module(_MODULE_EXPORTS_IDENTIFIER[name])
		export = _JSIdentifier(name)
	elif name in _MODULE_EXPORTS_ATTRIBUTE:
		module = _importlib.import_module(_MODULE_EXPORTS_ATTRIBUTE[name])
		export = getattr(module, name)
	else:
		raise AttributeError(f"module 'pulse.js' has no attribute '{name}'")

	_export_cache[name] = export
	return export
