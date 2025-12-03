from __future__ import annotations

import ast
import builtins
import inspect
import textwrap
import types
from typing import Any, Callable, Generic, TypeAlias, TypeVar, TypeVarTuple

# Import module registrations to ensure they're available for dependency analysis
import pulse.javascript_v2.modules  # noqa: F401
from pulse.javascript_v2.constants import JsConstant, const_to_js
from pulse.javascript_v2.errors import JSCompilationError
from pulse.javascript_v2.ids import generate_id
from pulse.javascript_v2.imports import Import
from pulse.javascript_v2.module import (
	PY_MODULE_VALUES,
	PY_MODULES,
	JsModule,
	PyModuleTranspiler,
)
from pulse.javascript_v2.nodes import JSExpr
from pulse.javascript_v2.transpiler import JsTranspiler

Args = TypeVarTuple("Args")
R = TypeVar("R")


AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any, ...], Any]"
JsDep: TypeAlias = "AnyJsFunction | JsConstant | Import | PyBuiltin | PyModuleRef | PyModuleFunctionRef | JSExpr"

# Global cache for deduplication across all transpiled functions
# Registered BEFORE analyzing deps to handle mutual recursion
FUNCTION_CACHE: dict[Callable[..., object], AnyJsFunction] = {}


class PyBuiltin:
	"""Placeholder for Python builtins that need JS equivalents."""

	name: str

	def __init__(self, name: str) -> None:
		self.name = name


class PyModuleRef:
	"""Reference to a registered Python module for transpilation.

	When a function uses `import math`, we create a PyModuleRef that tracks
	the module and its transpiler (either a PyModule class or a dict).
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


class JsFunction(Generic[*Args, R]):
	fn: Callable[[*Args], R]
	id: str
	deps: dict[str, JsDep]

	def __init__(self, fn: Callable[[*Args], R]) -> None:
		self.fn = fn
		self.id = generate_id()

		# Register self in cache BEFORE analyzing deps (handles cycles)
		FUNCTION_CACHE[fn] = self

		# Analyze dependencies in a single pass
		self.deps = _analyze_function_deps(fn)

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

		# Build rename map, builtins set, and modules map from dependencies
		rename: dict[str, str] = {}
		builtins: set[str] = set()
		modules: dict[str, type | dict[str, Any]] = {}
		module_funcs: dict[str, Callable[..., JSExpr]] = {}
		inline_exprs: dict[str, JSExpr] = {}
		for name, dep in self.deps.items():
			if isinstance(dep, (JsFunction, JsConstant)):
				rename[name] = dep.js_name
			elif isinstance(dep, PyBuiltin):
				# PyBuiltins go to the builtins set
				builtins.add(name)
			elif isinstance(dep, PyModuleRef):
				# PyModuleRefs go to the modules map
				modules[name] = dep.transpiler
			elif isinstance(dep, PyModuleFunctionRef):
				# PyModuleFunctionRef: map the local name to the emit callable
				module_funcs[name] = dep.emit
			elif isinstance(dep, JSExpr):
				# Direct JSExpr (e.g., module constants like math.pi -> Math.PI)
				inline_exprs[name] = dep
			elif hasattr(dep, "js_name"):
				rename[name] = dep.js_name

		# Transpile
		visitor = JsTranspiler(
			fndef,
			args=arg_names,
			rename=rename,
			builtins=builtins,
			modules=modules,
			module_funcs=module_funcs,
			inline_exprs=inline_exprs,
		)
		js_fn = visitor.transpile(name=self.js_name)
		return js_fn.emit()

	def __call__(self, *args: *Args) -> JsFunctionCall[*Args]:
		return JsFunctionCall(self, args)


class JsFunctionCall(Generic[*Args]):
	fn: JsFunction[*Args, Any]
	args: tuple[*Args]

	def __init__(self, fn: JsFunction[*Args, Any], args: tuple[*Args]) -> None:
		self.fn = fn
		self.args = args


def _analyze_function_deps(fn: Callable[..., object]) -> dict[str, JsDep]:
	"""Analyze function dependencies in a single pass through code objects.

	Returns a dict mapping global names to their JsDep representations.
	Raises JSCompilationError for unhandled cases (e.g., callable objects).
	"""
	code = fn.__code__

	# Collect all names from code object and nested functions in one pass
	seen_codes: set[int] = set()
	all_names: set[str] = set()

	def walk_code(c: types.CodeType) -> None:
		if id(c) in seen_codes:
			return
		seen_codes.add(id(c))
		all_names.update(c.co_names)
		all_names.update(c.co_freevars)  # Include closure variables
		for const in c.co_consts:
			if isinstance(const, types.CodeType):
				walk_code(const)

	walk_code(code)

	# Build effective globals dict: start with function's globals, then add closure values
	fn_globals = dict(fn.__globals__)

	# Resolve closure variables from closure cells
	if code.co_freevars and fn.__closure__:
		closure = fn.__closure__
		for i, freevar_name in enumerate(code.co_freevars):
			if i < len(closure):
				cell = closure[i]
				# Get the value from the closure cell
				try:
					fn_globals[freevar_name] = cell.cell_contents
				except ValueError:
					# Cell is empty (unbound), skip it
					pass

	# Categorize names in a single pass
	builtin_dict = builtins.__dict__
	deps: dict[str, JsDep] = {}

	for name in all_names:
		if name in fn_globals:
			value = fn_globals[name]

			# Handle known types
			if isinstance(value, (JsFunction, Import)):
				deps[name] = value
			elif isinstance(value, type) and issubclass(value, JsModule):
				# JsModule classes - planned for future handling
				# For now, skip (will be handled separately)
				continue
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

	return deps


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
