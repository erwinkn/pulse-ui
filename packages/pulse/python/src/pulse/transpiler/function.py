from __future__ import annotations

import ast
import inspect
import textwrap
import types as pytypes
from typing import (
	Any,
	Callable,
	ClassVar,
	Generic,
	Literal,
	ParamSpec,
	TypeAlias,
	TypeVar,
	TypeVarTuple,
	overload,
	override,
)

# Import module registrations to ensure they're available for dependency analysis
import pulse.transpiler.modules  # noqa: F401
from pulse.helpers import getsourcecode
from pulse.transpiler.builtins import BUILTINS
from pulse.transpiler.constants import JsConstant, const_to_js
from pulse.transpiler.context import is_interpreted_mode
from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.ids import generate_id
from pulse.transpiler.imports import Import
from pulse.transpiler.js_module import JS_MODULES
from pulse.transpiler.jsx import JSXCallExpr, build_jsx_props, convert_jsx_child
from pulse.transpiler.nodes import JSEXPR_REGISTRY, JSExpr, JSTransformer
from pulse.transpiler.py_module import (
	PY_MODULES,
	PyModuleExpr,
)
from pulse.transpiler.transpiler import JsTranspiler

Args = TypeVarTuple("Args")
P = ParamSpec("P")
R = TypeVar("R")


AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any, ...], Any]"

# Global cache for deduplication across all transpiled functions
# Registered BEFORE analyzing deps to handle mutual recursion
FUNCTION_CACHE: dict[Callable[..., Any], AnyJsFunction] = {}

# Cache for JSX functions (separate from regular functions)
AnyJsxFunction: TypeAlias = "JsxFunction[..., Any]"
JSX_FUNCTION_CACHE: dict[Callable[..., Any], AnyJsxFunction] = {}


class JsFunction(JSExpr, Generic[*Args, R]):
	is_primary: ClassVar[bool] = True

	fn: Callable[[*Args], R]
	id: str
	deps: dict[str, JSExpr]

	def __init__(self, fn: Callable[[*Args], R]) -> None:
		self.fn = fn
		# Generate ID first so we can register before analyzing deps (handles cycles)
		self.id = generate_id()
		# Register self in cache BEFORE analyzing deps (handles cycles)
		FUNCTION_CACHE[fn] = self
		# Now analyze and build deps (may recursively call javascript() which will find us in cache)
		self.deps = analyze_js_deps(fn)

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this function."""
		return f"{self.fn.__name__}_{self.id}"

	@override
	def emit(self) -> str:
		"""Emit JS code for this function reference.

		In normal mode: returns the unique JS name (e.g., "myFunc_1")
		In interpreted mode: returns a get_object call (e.g., "get_object('myFunc_1')")
		"""
		base = self.js_name
		if is_interpreted_mode():
			return f"get_object('{base}')"
		return base

	def imports(self) -> dict[str, Import]:
		"""Get all Import dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, Import)}

	def functions(self) -> dict[str, AnyJsFunction]:
		"""Get all JsFunction dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsFunction)}

	def constants(self) -> dict[str, JsConstant]:
		"""Get all JsConstant dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsConstant)}

	def modules(self) -> dict[str, PyModuleExpr]:
		"""Get all PyModuleExpr dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, PyModuleExpr)}

	def module_functions(self) -> dict[str, JSTransformer]:
		"""Get all module function JSTransformer dependencies (named imports from modules)."""
		from pulse.transpiler.builtins import BUILTINS

		return {
			k: v
			for k, v in self.deps.items()
			if isinstance(v, JSTransformer) and v.name not in BUILTINS
		}

	def transpile(self) -> str:
		"""Transpile this JsFunction to JavaScript code.

		Returns the complete JavaScript function code.
		"""
		return _transpile_js_function(self.fn, self.deps, self.js_name)


class JsxFunction(JSExpr, Generic[P, R]):
	"""Component function - emits JSX when called."""

	is_primary: ClassVar[bool] = True

	fn: Callable[P, Any]
	id: str
	deps: dict[str, JSExpr]

	def __init__(self, fn: Callable[P, Any]) -> None:
		self.fn = fn
		# Generate ID first so we can register before analyzing deps (handles cycles)
		self.id = generate_id()
		# Register self in cache BEFORE analyzing deps (handles cycles)
		JSX_FUNCTION_CACHE[fn] = self
		# Now analyze and build deps (may recursively call component() which will find us in cache)
		self.deps = analyze_js_deps(fn)

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this function."""
		return f"{self.fn.__name__}_{self.id}"

	@override
	def emit(self) -> str:
		"""Emit JS code for this function reference.

		In normal mode: returns the unique JS name (e.g., "myComp_1")
		In interpreted mode: returns a get_object call (e.g., "get_object('myComp_1')")
		"""
		base = self.js_name
		if is_interpreted_mode():
			return f"get_object('{base}')"
		return base

	@override
	def emit_call(self, args: list[Any], kwargs: dict[str, Any]) -> JSExpr:
		"""Handle JSX-style calls: positional args are children, kwargs are props."""
		props = build_jsx_props(kwargs)
		children = [convert_jsx_child(c) for c in args]
		return JSXCallExpr(self, tuple(props), tuple(children))

	def imports(self) -> dict[str, Import]:
		"""Get all Import dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, Import)}

	def functions(self) -> dict[str, AnyJsFunction]:
		"""Get all JsFunction dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsFunction)}

	def constants(self) -> dict[str, JsConstant]:
		"""Get all JsConstant dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsConstant)}

	def modules(self) -> dict[str, PyModuleExpr]:
		"""Get all PyModuleExpr dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, PyModuleExpr)}

	def module_functions(self) -> dict[str, JSTransformer]:
		"""Get all module function JSTransformer dependencies (named imports from modules)."""
		from pulse.transpiler.builtins import BUILTINS

		return {
			k: v
			for k, v in self.deps.items()
			if isinstance(v, JSTransformer) and v.name not in BUILTINS
		}

	def transpile(self) -> str:
		"""Transpile this JsxFunction to JavaScript code.

		Returns the complete JavaScript function code.
		"""
		return _transpile_js_function(self.fn, self.deps, self.js_name)


def analyze_code_object(
	fn: Callable[..., object],
) -> tuple[dict[str, Any], set[str]]:
	"""Analyze code object and resolve globals + closure variables.

	Returns a tuple of:
	    - effective_globals: dict mapping names to their values (includes closure vars)
	    - all_names: set of all names referenced in the code (including nested functions)
	"""
	code = fn.__code__

	# Collect all names from code object and nested functions in one pass
	seen_codes: set[int] = set()
	all_names: set[str] = set()

	def walk_code(c: pytypes.CodeType) -> None:
		if id(c) in seen_codes:
			return
		seen_codes.add(id(c))
		all_names.update(c.co_names)
		all_names.update(c.co_freevars)  # Include closure variables
		for const in c.co_consts:
			if isinstance(const, pytypes.CodeType):
				walk_code(const)

	walk_code(code)

	# Build effective globals dict: start with function's globals, then add closure values
	effective_globals = dict(fn.__globals__)

	# Resolve closure variables from closure cells
	if code.co_freevars and fn.__closure__:
		closure = fn.__closure__
		for i, freevar_name in enumerate(code.co_freevars):
			if i < len(closure):
				cell = closure[i]
				# Get the value from the closure cell
				try:
					effective_globals[freevar_name] = cell.cell_contents
				except ValueError:
					# Cell is empty (unbound), skip it
					pass

	return effective_globals, all_names


def analyze_js_deps(fn: Callable[..., object]) -> dict[str, JSExpr]:
	"""Shared init: analyze function, return deps.

	This helper extracts the common initialization logic for both JsFunction
	and JsxFunction. The ID should be generated by the caller before calling
	this function, and the function should be registered in the cache before
	calling this (to handle mutual recursion).
	"""
	# Analyze code object and resolve globals + closure vars
	effective_globals, all_names = analyze_code_object(fn)

	# Build dependencies dictionary - all values are JSExpr
	deps: dict[str, JSExpr] = {}

	for name in all_names:
		value = effective_globals.get(name)

		if value is None:
			# Not in globals - check builtins (allows user to shadow builtins)
			# Note: co_names includes both global names AND attribute names (e.g., 'input'
			# from 'tags.input'). We only add supported builtins; unsupported ones are
			# skipped since they might be attribute accesses handled during transpilation.
			if name in BUILTINS:
				deps[name] = BUILTINS[name]
			continue

		# Already a JSExpr (JsFunction, JsConstant, Import, JSMember, etc.)
		if isinstance(value, JSExpr):
			deps[name] = value
		elif inspect.ismodule(value):
			if value in JS_MODULES:
				# import pulse.js.math as Math -> JSIdentifier or Import
				deps[name] = JS_MODULES[value].to_js_expr()
			elif value in PY_MODULES:
				deps[name] = PyModuleExpr(PY_MODULES[value])
			else:
				raise JSCompilationError(
					f"Could not resolve JavaScript module import for '{name}' (value: {value!r}). "
					+ "Neither a registered Python module nor a known JS wrapper. "
					+ "Check your import statement and module configuration."
				)

		elif id(value) in JSEXPR_REGISTRY:
			# JSEXPR_REGISTRY always contains JSExpr (wrapping happens in JSExpr.register)
			deps[name] = JSEXPR_REGISTRY[id(value)]
		elif inspect.isfunction(value):
			# Check both caches first, then fall back to javascript() (creates JsFunction)
			if value in FUNCTION_CACHE:
				deps[name] = FUNCTION_CACHE[value]
			elif value in JSX_FUNCTION_CACHE:
				deps[name] = JSX_FUNCTION_CACHE[value]
			else:
				deps[name] = JsFunction(value)
		elif callable(value):
			raise JSCompilationError(
				f"Callable object '{name}' (type: {type(value).__name__}) is not supported. "
				+ "Only functions can be transpiled."
			)
		else:
			deps[name] = const_to_js(value, name)

	return deps


def _transpile_js_function(
	fn: Callable[..., object], deps: dict[str, JSExpr], name: str
) -> str:
	"""Shared transpilation: parse and transpile function to JS."""
	# Get source code
	src = getsourcecode(fn)
	src = textwrap.dedent(src)

	# Parse to AST
	module = ast.parse(src)
	fndefs = [
		n for n in module.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
	]
	if not fndefs:
		raise JSCompilationError("No function definition found in source")
	fndef = fndefs[-1]

	# Get argument names
	arg_names = [arg.arg for arg in fndef.args.args]

	# Transpile - pass deps directly, transpiler handles dispatch
	visitor = JsTranspiler(fndef, args=arg_names, deps=deps)
	return visitor.transpile(name=name).emit()


@overload
def javascript(fn: Callable[[*Args], R]) -> Callable[[*Args], R]: ...


@overload
def javascript(
	*, component: Literal[False]
) -> Callable[[Callable[[*Args], R]], Callable[[*Args], R]]: ...


@overload
def javascript(
	*, component: Literal[True]
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def javascript(fn: Callable[..., Any] | None = None, *, component: bool = False) -> Any:
	"""Decorator to convert a function into a JsFunction or JsxFunction.

	When component=False (default), operates over Callable[[*Args], R] and returns JsFunction.
	When component=True, operates over Callable[P, R] and returns JsxFunction.

	Usage:
	    @javascript
	    def my_func(x: int) -> int:
	        return x + 1

	    @javascript(component=True)
	    def MyComp(name: str):
	        return div()[f"Hello {name}"]

	    # my_func is now a JsFunction instance
	    # MyComp is now a JsxFunction instance
	"""

	def decorator(f: Callable[..., Any]) -> Any:
		if component:
			result = JSX_FUNCTION_CACHE.get(f)
			if not result:
				result = JsxFunction(f)
				JSX_FUNCTION_CACHE[f] = result
			return result
		else:
			result = FUNCTION_CACHE.get(f)
			if not result:
				result = JsFunction(f)
				FUNCTION_CACHE[f] = result
			return result

	if fn:
		return decorator(fn)
	else:
		return decorator


def registered_functions() -> list[AnyJsFunction]:
	"""Get all registered JS functions."""
	return list(FUNCTION_CACHE.values())
