from __future__ import annotations

import ast
import inspect
import textwrap
import types as pytypes
from typing import (
	Any,
	Callable,
	Generic,
	Never,
	TypeAlias,
	TypeVar,
	TypeVarTuple,
	cast,
	override,
)

# Import module registrations to ensure they're available for dependency analysis
import pulse.transpiler.modules  # noqa: F401
from pulse.helpers import getsourcecode
from pulse.transpiler.builtins import BUILTIN_EMITTERS
from pulse.transpiler.constants import JsConstant, const_to_js
from pulse.transpiler.context import is_interpreted_mode
from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.ids import generate_id
from pulse.transpiler.imports import Import
from pulse.transpiler.js_module import JS_MODULES
from pulse.transpiler.nodes import JSExpr, JSTransformer
from pulse.transpiler.py_module import (
	PY_MODULE_VALUES,
	PY_MODULES,
	PyModuleExpr,
)
from pulse.transpiler.transpiler import JsTranspiler

Args = TypeVarTuple("Args")
R = TypeVar("R")


AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any, ...], Any]"

# Global cache for deduplication across all transpiled functions
# Registered BEFORE analyzing deps to handle mutual recursion
FUNCTION_CACHE: dict[Callable[..., object], AnyJsFunction] = {}


class JsFunction(JSExpr, Generic[*Args, R]):
	is_primary: bool = True

	fn: Callable[[*Args], R]
	id: str
	deps: dict[str, JSExpr]

	def __init__(self, fn: Callable[[*Args], R]) -> None:
		self.fn = fn
		self.id = generate_id()

		# Register self in cache BEFORE analyzing deps (handles cycles)
		FUNCTION_CACHE[fn] = self

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
				if name in BUILTIN_EMITTERS:
					deps[name] = BUILTIN_EMITTERS[name]
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

			elif id(value) in PY_MODULE_VALUES:
				# PY_MODULE_VALUES always contains JSExpr (wrapping happens in py_module.py)
				deps[name] = PY_MODULE_VALUES[id(value)]
			elif inspect.isfunction(value):
				deps[name] = javascript(value)
			elif callable(value):
				raise JSCompilationError(
					f"Callable object '{name}' (type: {type(value).__name__}) is not supported. "
					+ "Only functions can be transpiled."
				)
			else:
				deps[name] = const_to_js(value, name)

		self.deps = deps

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
		from pulse.transpiler.builtins import BUILTIN_EMITTERS

		return {
			k: v
			for k, v in self.deps.items()
			if isinstance(v, JSTransformer) and v.name not in BUILTIN_EMITTERS
		}

	def transpile(self) -> str:
		"""Transpile this JsFunction to JavaScript code.

		Returns the complete JavaScript function code.
		"""

		# Get source code
		src = getsourcecode(self.fn)
		src = textwrap.dedent(src)

		# Parse to AST
		module = ast.parse(src)
		fndefs = [n for n in module.body if isinstance(n, ast.FunctionDef)]
		if not fndefs:
			raise JSCompilationError("No function definition found in source")
		fndef = fndefs[-1]

		# Get argument names
		arg_names = [arg.arg for arg in fndef.args.args]

		# Transpile - pass deps directly, transpiler handles dispatch
		visitor = JsTranspiler(fndef, args=arg_names, deps=self.deps)
		js_fn = visitor.transpile(name=self.js_name)
		return js_fn.emit()

	@override
	def __call__(self, *args: *Args, **kwargs: Never) -> R:  # pyright: ignore[reportIncompatibleMethodOverride]
		if kwargs:
			raise JSCompilationError("Keyword arguments not supported")
		return cast(R, JsFunctionCall(self, args))


class JsFunctionCall(Generic[*Args]):
	fn: JsFunction[*Args, Any]
	args: tuple[*Args]

	def __init__(self, fn: JsFunction[*Args, Any], args: tuple[*Args]) -> None:
		self.fn = fn
		self.args = args


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


def javascript(fn: Callable[[*Args], R]) -> JsFunction[*Args, R]:
	"""Decorator to convert a function into a JsFunction.

	Usage:
	    @javascript
	    def my_func(x: int) -> int:
	        return x + 1

	    # my_func is now a JsFunction instance
	"""
	result = FUNCTION_CACHE.get(fn)
	if not result:
		result = JsFunction(fn)
		FUNCTION_CACHE[fn] = result
	return result  # pyright: ignore[reportReturnType]


def registered_functions() -> list[AnyJsFunction]:
	"""Get all registered JS functions."""
	return list(FUNCTION_CACHE.values())


X = JsFunction[int]
