"""Function transpilation system for transpiler_v2.

Provides the @javascript decorator for marking Python functions for JS transpilation,
and JsFunction which wraps transpiled functions with their dependencies.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import types as pytypes
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import (
	Any,
	Generic,
	Literal,
	ParamSpec,
	TypeAlias,
	TypeVar,
	TypeVarTuple,
	cast,
	overload,
	override,
)

from pulse.helpers import getsourcecode
from pulse.transpiler_v2.errors import TranspileError
from pulse.transpiler_v2.id import next_id, reset_id_counter
from pulse.transpiler_v2.imports import Import
from pulse.transpiler_v2.nodes import (
	EXPR_REGISTRY,
	Expr,
	Function,
	Jsx,
	Ref,
	Return,
	clear_ref_registry,
)
from pulse.transpiler_v2.transpiler import Transpiler

Args = TypeVarTuple("Args")
P = ParamSpec("P")
R = TypeVar("R")
AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any, ...], Any]"

# Global cache for deduplication across all transpiled functions
# Registered BEFORE analyzing deps to handle mutual recursion
FUNCTION_CACHE: dict[Callable[..., Any], AnyJsFunction] = {}

# Global registry for hoisted constants: id(value) -> Constant
# Used for deduplication of non-primitive values in transpiled functions
CONSTANT_REGISTRY: dict[int, "Constant"] = {}


def clear_function_cache() -> None:
	"""Clear function/constant/ref caches and reset the shared ID counters."""
	from pulse.transpiler_v2.imports import clear_import_registry

	FUNCTION_CACHE.clear()
	CONSTANT_REGISTRY.clear()
	clear_import_registry()
	clear_ref_registry()
	reset_id_counter()


@dataclass(slots=True, init=False)
class Constant(Expr):
	"""A hoisted constant value with a unique identifier.

	Used for non-primitive values (lists, dicts, sets) referenced in transpiled
	functions. The value is emitted once at module scope, and the function
	references it by name.

	Example:
		ITEMS = [1, 2, 3]

		@javascript
		def foo():
			return ITEMS[0]

		# Emits:
		# const ITEMS_1 = [1, 2, 3];
		# function foo_2() { return ITEMS_1[0]; }
	"""

	value: Any
	expr: Expr
	id: str
	name: str

	def __init__(self, value: Any, expr: Expr, name: str = "") -> None:
		self.value = value
		self.expr = expr
		self.id = next_id()
		self.name = name
		# Register in global cache
		CONSTANT_REGISTRY[id(value)] = self

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this constant."""
		return f"{self.name}_{self.id}" if self.name else f"_const_{self.id}"

	@override
	def emit(self, out: list[str]) -> None:
		"""Emit the unique JS identifier."""
		out.append(self.js_name)

	@staticmethod
	def wrap(value: Any, name: str = "") -> "Constant":
		"""Get or create a Constant for a value (cached by identity)."""
		if (existing := CONSTANT_REGISTRY.get(id(value))) is not None:
			return existing
		expr = Expr.of(value)
		return Constant(value, expr, name)


def registered_constants() -> list[Constant]:
	"""Get all registered constants."""
	return list(CONSTANT_REGISTRY.values())


@dataclass(slots=True, init=False)
class JsFunction(Expr, Generic[*Args, R]):
	"""A transpiled JavaScript function.

	Wraps a Python function with:
	- A unique identifier for deduplication
	- Resolved dependencies (other functions, imports, constants, etc.)
	- The ability to transpile to JavaScript code
	- A Ref for registry inclusion (auto-created)

	When emitted, produces the unique JS function name (e.g., "myFunc_1").
	"""

	fn: Callable[[*Args], R]
	id: str
	deps: dict[str, Expr]
	_ref: Ref
	_transpiled: Function | None = field(default=None)

	def __init__(self, fn: Callable[..., Any]) -> None:
		self.fn = fn
		self.id = next_id()
		self._transpiled = None
		# Create ref for registry inclusion (wraps self so it emits the js_name)
		self._ref = Ref(self)
		# Register self in cache BEFORE analyzing deps (handles cycles)
		FUNCTION_CACHE[fn] = self
		# Now analyze and build deps (may recursively call JsFunction() which will find us in cache)
		self.deps = analyze_deps(fn)

	@override
	def __call__(self, *args: *Args) -> R:  # pyright: ignore[reportIncompatibleMethodOverride]
		return super().__call__(*args)  # pyright: ignore[reportReturnType]

	@property
	def registry_ref(self) -> Ref:
		"""Registry reference for this function.

		Named to avoid clashing with Expr.ref() convenience wrapper.
		"""
		return self._ref

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this function."""
		return f"{self.fn.__name__}_{self.id}"

	@override
	def emit(self, out: list[str]) -> None:
		"""Emit this function as its unique JS identifier."""
		out.append(self.js_name)

	def transpile(self) -> Function:
		"""Transpile this function to a v2 Function node.

		Returns the Function node (cached after first call).
		"""
		if self._transpiled is not None:
			return self._transpiled

		# Get and parse source
		src = getsourcecode(self.fn)
		src = textwrap.dedent(src)
		module = ast.parse(src)

		# Find the function definition
		fndefs = [
			n
			for n in module.body
			if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
		]
		if not fndefs:
			raise TranspileError("No function definition found in source")
		fndef = fndefs[-1]

		# Transpile
		transpiler = Transpiler(fndef, self.deps)
		result = transpiler.transpile()

		# Convert Arrow to Function if needed, and set the name
		if isinstance(result, Function):
			result = Function(
				params=result.params,
				body=result.body,
				name=self.js_name,
				is_async=result.is_async,
			)
		else:
			# Arrow - wrap in Function with name
			result = Function(
				params=list(result.params),
				body=[Return(result.body)],
				name=self.js_name,
				is_async=False,
			)

		self._transpiled = result
		return result

	def imports(self) -> dict[str, Expr]:
		"""Get all Import dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, Import)}

	def functions(self) -> dict[str, AnyJsFunction]:
		"""Get all JsFunction dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsFunction)}


@dataclass(slots=True)
class JsxFunction(Expr, Generic[P, R]):
	"""Lightweight JSX wrapper around a cached JsFunction.

	This is purely an ergonomic/typing helper:
	- clear type (JsxFunction)
	- preserves ParamSpec for __call__
	- exposes .transpile() via the underlying JsFunction

	There is still only ONE cache for functions: FUNCTION_CACHE (JsFunction).
	"""

	js_fn: JsFunction[*tuple[Any, ...], Any]

	@property
	def fn(self) -> Callable[..., Any]:
		return self.js_fn.fn

	@property
	def id(self) -> str:
		return self.js_fn.id

	@property
	def deps(self) -> dict[str, Expr]:
		return self.js_fn.deps

	@property
	def js_name(self) -> str:
		return self.js_fn.js_name

	@property
	def registry_ref(self) -> Ref:
		return self.js_fn.registry_ref

	def transpile(self) -> Function:
		return self.js_fn.transpile()

	def imports(self) -> dict[str, Expr]:
		return self.js_fn.imports()

	def functions(self) -> dict[str, AnyJsFunction]:
		return self.js_fn.functions()

	@override
	def emit(self, out: list[str]) -> None:
		self.js_fn.emit(out)

	@override
	def transpile_call(
		self, args: list[ast.expr], kwargs: dict[str, ast.expr], ctx: Transpiler
	) -> Expr:
		# delegate JSX element building to the generic Jsx wrapper
		return Jsx(self.js_fn).transpile_call(args, kwargs, ctx)

	@override
	def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:  # pyright: ignore[reportIncompatibleMethodOverride]
		# runtime/type-checking: produce Element via Jsx wrapper
		return Jsx(self.js_fn)(*args, **kwargs)  # pyright: ignore[reportReturnType]


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


def analyze_deps(fn: Callable[..., object]) -> dict[str, Expr]:
	"""Analyze a function and return its dependencies as Expr instances.

	Walks the function's code object to find all referenced names,
	then resolves them from globals/closure and converts to Expr.
	"""
	# Analyze code object and resolve globals + closure vars
	effective_globals, all_names = analyze_code_object(fn)

	# Build dependencies dictionary - all values are Expr
	deps: dict[str, Expr] = {}

	for name in all_names:
		value = effective_globals.get(name)

		if value is None:
			# Not in globals - could be a builtin or unresolved
			# For now, skip - builtins will be handled by the transpiler
			# TODO: Add builtin support
			continue

		# Already an Expr
		if isinstance(value, Expr):
			deps[name] = value
			continue

		# Check global registry (for registered values like math.floor)
		if id(value) in EXPR_REGISTRY:
			deps[name] = EXPR_REGISTRY[id(value)]
			continue

		# Module imports must be registered (module object itself is in EXPR_REGISTRY)
		if inspect.ismodule(value):
			raise TranspileError(
				f"Could not resolve module '{name}' (value: {value!r}). "
				+ "Register the module (or its values) in EXPR_REGISTRY."
			)

		# Functions - check cache, then create JsFunction
		if inspect.isfunction(value):
			if value in FUNCTION_CACHE:
				deps[name] = FUNCTION_CACHE[value]
			else:
				deps[name] = JsFunction(value)
			continue

		# Skip Expr subclasses (the classes themselves) as they are often
		# used for type hinting or within function scope and handled
		# by the transpiler via other means (e.g. BUILTINS or special cases)
		if isinstance(value, type) and issubclass(value, Expr):
			continue

		# Other callables (classes, methods, etc.) - not supported
		if callable(value):
			raise TranspileError(
				f"Callable '{name}' (type: {type(value).__name__}) is not supported. "
				+ "Only functions can be transpiled."
			)

		# Constants - primitives inline, non-primitives hoisted
		if isinstance(value, (bool, int, float, str)) or value is None:
			deps[name] = Expr.of(value)
		else:
			# Non-primitive: wrap in Constant for hoisting
			try:
				deps[name] = Constant.wrap(value, name)
			except TypeError:
				raise TranspileError(
					f"Cannot convert '{name}' (type: {type(value).__name__}) to Expr"
				) from None

	return deps


@overload
def javascript(fn: Callable[[*Args], R]) -> JsFunction[*Args, R]: ...


@overload
def javascript(
	*, jsx: Literal[False] = ...
) -> Callable[[Callable[[*Args], R]], JsFunction[*Args, R]]: ...


@overload
def javascript(*, jsx: Literal[True]) -> Callable[[Callable[P, R]], Jsx]: ...


def javascript(fn: Callable[[*Args], R] | None = None, *, jsx: bool = False) -> Any:
	"""Decorator to convert a Python function into a JsFunction.

	When jsx=False (default), returns a JsFunction instance.
	When jsx=True, returns Jsx(JsFunction), but caches only the underlying JsFunction.
	"""

	def decorator(f: Callable[[*Args], R]) -> Any:
		result = FUNCTION_CACHE.get(f)
		if result is None:
			result = JsFunction(f)
		if jsx:
			js_fn = cast(JsFunction[*tuple[Any, ...], Any], result)
			# Preserve the original function's type signature for type checkers.
			# Runtime object is JsxFunction.
			return JsxFunction(js_fn).as_(type(f))
		return result

	if fn is not None:
		return decorator(fn)
	return decorator


def registered_functions() -> list[AnyJsFunction]:
	"""Get all registered JS functions."""
	return list(FUNCTION_CACHE.values())


def _unwrap_jsfunction(expr: Expr) -> JsFunction[*tuple[Any, ...], Any] | None:
	# Unwrap common wrappers that may show up in deps
	if isinstance(expr, JsFunction):
		return expr
	if isinstance(expr, JsxFunction):
		return expr.js_fn
	if isinstance(expr, Jsx):
		inner = expr.expr
		if isinstance(inner, Expr):
			return _unwrap_jsfunction(inner)
	return None


def collect_function_graph(
	functions: list[AnyJsFunction] | None = None,
) -> tuple[list[Constant], list[AnyJsFunction]]:
	"""Collect all constants and functions in dependency order (depth-first).

	Args:
		functions: Functions to walk. If None, uses all registered functions.

	Returns:
		Tuple of (constants, functions) in dependency order.
	"""
	if functions is None:
		functions = registered_functions()

	seen_funcs: set[str] = set()
	seen_consts: set[str] = set()
	all_funcs: list[AnyJsFunction] = []
	all_consts: list[Constant] = []

	def walk(fn: AnyJsFunction) -> None:
		if fn.id in seen_funcs:
			return
		seen_funcs.add(fn.id)

		for dep in fn.deps.values():
			if isinstance(dep, Constant):
				if dep.id not in seen_consts:
					seen_consts.add(dep.id)
					all_consts.append(dep)
				continue
			if isinstance(dep, Expr):
				inner_fn = _unwrap_jsfunction(dep)
				if inner_fn is not None:
					walk(inner_fn)

		all_funcs.append(fn)

	for fn in functions:
		walk(fn)

	return all_consts, all_funcs
