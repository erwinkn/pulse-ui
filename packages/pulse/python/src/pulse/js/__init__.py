"""JavaScript module bindings for use in @javascript decorated functions (transpiler).

## Usage

Import JS classes (for constructors and static methods):

```python
from pulse.js import Set, Number, Array, Date, Promise, Map, Error
Set([1, 2, 3])         # -> new Set([1, 2, 3])
Number.isFinite(42)    # -> Number.isFinite(42)
Array.isArray(x)       # -> Array.isArray(x)
```

Import JS namespace objects (function-only modules):

```python
from pulse.js import Math, JSON, console, window, document, navigator
Math.floor(3.7)        # -> Math.floor(3.7)
JSON.stringify(obj)    # -> JSON.stringify(obj)
console.log("hi")      # -> console.log("hi")
```

Alternative: import namespace modules for namespace access:

```python
import pulse.js.json as JSON
JSON.stringify(obj)    # -> JSON.stringify(obj)
```

Statement functions:

```python
from pulse.js import throw
throw(Error("message"))  # -> throw Error("message");
```

Object literals (plain JS objects instead of Map):

```python
from pulse.js import obj
obj(a=1, b=2)          # -> { a: 1, b: 2 }
```
"""

import importlib as _importlib
from typing import Any as _Any
from typing import NoReturn as _NoReturn

from pulse.js.obj import obj as obj
from pulse.transpiler.nodes import EXPR_REGISTRY as _EXPR_REGISTRY
from pulse.transpiler.nodes import UNDEFINED as _UNDEFINED

# Namespace modules - return JsModule from registry (handles both builtins and external)
_MODULE_EXPORTS_NAMESPACE: dict[str, str] = {
	"Intl": "pulse.js.intl",
	"JSON": "pulse.js.json",
	"Math": "pulse.js.math",
	"React": "pulse.js.react",
	"console": "pulse.js.console",
	"crypto": "pulse.js.crypto",
	"window": "pulse.js.window",
	"document": "pulse.js.document",
	"navigator": "pulse.js.navigator",
}

# Class modules - return via getattr to get Class wrapper (emits `new ...`)
_MODULE_EXPORTS_ATTRIBUTE: dict[str, str] = {
	"AbortController": "pulse.js.abort_controller",
	"AbortSignal": "pulse.js.abort_controller",
	"Array": "pulse.js.array",
	"ArrayBuffer": "pulse.js.array_buffer",
	"BigInt64Array": "pulse.js.array_buffer",
	"BigUint64Array": "pulse.js.array_buffer",
	"Blob": "pulse.js.blob",
	"CustomEvent": "pulse.js.custom_event",
	"DOMParser": "pulse.js.dom_parser",
	"DataView": "pulse.js.array_buffer",
	"Date": "pulse.js.date",
	"Error": "pulse.js.error",
	"File": "pulse.js.file",
	"FileReader": "pulse.js.file_reader",
	"Float32Array": "pulse.js.array_buffer",
	"Float64Array": "pulse.js.array_buffer",
	"FormData": "pulse.js.form_data",
	"Headers": "pulse.js.fetch_api",
	"Int16Array": "pulse.js.array_buffer",
	"Int32Array": "pulse.js.array_buffer",
	"Int8Array": "pulse.js.array_buffer",
	"IntersectionObserver": "pulse.js.intersection_observer",
	"Map": "pulse.js.map",
	"MutationObserver": "pulse.js.mutation_observer",
	"Object": "pulse.js.object",
	"PerformanceObserver": "pulse.js.performance_observer",
	"Promise": "pulse.js.promise",
	"Request": "pulse.js.fetch_api",
	"ResizeObserver": "pulse.js.resize_observer",
	"Response": "pulse.js.fetch_api",
	"React": "pulse.js.react",
	"RegExp": "pulse.js.regexp",
	"Set": "pulse.js.set",
	"String": "pulse.js.string",
	"TextDecoder": "pulse.js.text_encoding",
	"TextEncoder": "pulse.js.text_encoding",
	"URL": "pulse.js.url",
	"URLSearchParams": "pulse.js.url",
	"Uint16Array": "pulse.js.array_buffer",
	"Uint32Array": "pulse.js.array_buffer",
	"Uint8Array": "pulse.js.array_buffer",
	"Uint8ClampedArray": "pulse.js.array_buffer",
	"WeakMap": "pulse.js.weakmap",
	"WeakSet": "pulse.js.weakset",
	"XMLSerializer": "pulse.js.dom_parser",
	"fetch": "pulse.js.fetch_api",
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
