from __future__ import annotations

import ast
import builtins
import inspect
import textwrap
import types as pytypes
from typing import Any, Callable, Generic, TypeAlias, TypeVar, TypeVarTuple, cast

# Import module registrations to ensure they're available for dependency analysis
import pulse.javascript_v2.modules  # noqa: F401
from pulse.javascript_v2.constants import JsConstant, const_to_js
from pulse.javascript_v2.errors import JSCompilationError
from pulse.javascript_v2.ids import generate_id
from pulse.javascript_v2.imports import Import
from pulse.javascript_v2.module import PY_MODULE_VALUES, PY_MODULES
from pulse.javascript_v2.nodes import JSExpr
from pulse.javascript_v2.transpiler import JsTranspiler
from pulse.javascript_v2.types import (
	JsModuleRef,
	PyBuiltin,
	PyModuleFunctionRef,
	PyModuleRef,
)
from pulse.js._core import JsModuleConfig, JsValue

Args = TypeVarTuple("Args")
R = TypeVar("R")


AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any, ...], Any]"
JsDep: TypeAlias = "AnyJsFunction | JsConstant | Import | PyBuiltin | PyModuleRef | PyModuleFunctionRef | JsModuleRef | JsValue | JSExpr"

# Global cache for deduplication across all transpiled functions
# Registered BEFORE analyzing deps to handle mutual recursion
FUNCTION_CACHE: dict[Callable[..., object], AnyJsFunction] = {}


class JsFunction(Generic[*Args, R]):
	fn: Callable[[*Args], R]
	id: str
	deps: dict[str, JsDep]

	def __init__(self, fn: Callable[[*Args], R]) -> None:
		self.fn = fn
		self.id = generate_id()

		# Register self in cache BEFORE analyzing deps (handles cycles)
		FUNCTION_CACHE[fn] = self

		# Analyze code object and resolve globals + closure vars
		effective_globals, all_names = _analyze_code_object(fn)

		# Build dependencies dictionary
		builtin_dict = builtins.__dict__
		deps: dict[str, JsDep] = {}

		for name in all_names:
			if name in effective_globals:
				value = effective_globals[name]

				# Handle known types
				if isinstance(value, (JsFunction, Import)):
					deps[name] = value
				elif isinstance(value, JsValue):
					# Value/function imported from a pulse.js.* module
					# e.g., `from pulse.js.math import floor, PI`
					deps[name] = value
				elif inspect.ismodule(value) and hasattr(value, "__js__"):
					# pulse.js.* module imported as a whole
					# e.g., `import pulse.js.math as Math`
					config = value.__js__
					if isinstance(config, JsModuleConfig):
						deps[name] = JsModuleRef(value, config)
				elif inspect.ismodule(value):
					if value in PY_MODULES:
						deps[name] = PyModuleRef(value, PY_MODULES[value])
					# Unregistered modules are skipped
				elif id(value) in PY_MODULE_VALUES:
					# Value from a registered module (constant or function)
					transpiler = PY_MODULE_VALUES[id(value)]
					if isinstance(transpiler, JSExpr):
						deps[name] = transpiler
					else:
						# It's a callable emit function
						deps[name] = PyModuleFunctionRef(transpiler)
				elif inspect.isfunction(value):
					deps[name] = javascript(value)
				elif callable(value):
					# Callable objects (not functions) are not supported
					raise JSCompilationError(
						f"Callable object '{name}' (type: {type(value).__name__}) is not supported. "
						+ "Only functions can be transpiled."
					)
				else:
					# Regular constants
					deps[name] = const_to_js(value, name)
			elif name in builtin_dict:
				# Python builtins
				deps[name] = PyBuiltin(name)
			# Unresolved names (e.g., attribute accesses like 'math.pi') are skipped
			# They'll be handled during code generation

		self.deps = deps

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this function."""
		return f"{self.fn.__name__}_{self.id}"

	def imports(self) -> dict[str, Import]:
		"""Get all Import dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, Import)}

	def functions(self) -> dict[str, AnyJsFunction]:
		"""Get all JsFunction dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsFunction)}

	def constants(self) -> dict[str, JsConstant]:
		"""Get all JsConstant dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsConstant)}

	def builtins(self) -> dict[str, PyBuiltin]:
		"""Get all PyBuiltin dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, PyBuiltin)}

	def modules(self) -> dict[str, PyModuleRef]:
		"""Get all PyModuleRef dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, PyModuleRef)}

	def module_functions(self) -> dict[str, PyModuleFunctionRef]:
		"""Get all PyModuleFunctionRef dependencies (named imports from modules)."""
		return {
			k: v for k, v in self.deps.items() if isinstance(v, PyModuleFunctionRef)
		}

	def js_modules(self) -> dict[str, JsModuleRef]:
		"""Get all JsModuleRef dependencies (pulse.js.* modules imported as a whole)."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsModuleRef)}

	def js_values(self) -> dict[str, JsValue]:
		"""Get all JsValue dependencies (values imported from pulse.js.* modules)."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsValue)}

	def transpile(self) -> str:
		"""Transpile this JsFunction to JavaScript code.

		Returns the complete JavaScript function code.
		"""

		# Get source code
		src = inspect.getsource(self.fn)
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

	def __call__(self, *args: *Args) -> R:
		return cast(R, JsFunctionCall(self, args))


class JsFunctionCall(Generic[*Args]):
	fn: JsFunction[*Args, Any]
	args: tuple[*Args]

	def __init__(self, fn: JsFunction[*Args, Any], args: tuple[*Args]) -> None:
		self.fn = fn
		self.args = args


def _analyze_code_object(
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
