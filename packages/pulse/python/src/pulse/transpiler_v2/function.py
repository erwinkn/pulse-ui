"""Function transpilation system for transpiler_v2.

Provides the @javascript decorator for marking Python functions for JS transpilation,
and JsFunction/JsxFunction which wrap transpiled functions with their dependencies.
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
	overload,
	override,
)

from pulse.helpers import getsourcecode
from pulse.transpiler_v2.errors import TranspileError
from pulse.transpiler_v2.imports import Import
from pulse.transpiler_v2.nodes import (
	EXPR_REGISTRY,
	Call,
	Child,
	Element,
	Expr,
	Function,
	Prop,
	Return,
)
from pulse.transpiler_v2.nodes import Literal as LiteralNode
from pulse.transpiler_v2.transpiler import Transpiler

Args = TypeVarTuple("Args")
P = ParamSpec("P")
R = TypeVar("R")
AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any, ...], Any]"
AnyJsxFunction: TypeAlias = "JsxFunction[..., Any]"

# Global cache for deduplication across all transpiled functions
# Registered BEFORE analyzing deps to handle mutual recursion
FUNCTION_CACHE: dict[Callable[..., Any], AnyJsFunction] = {}
JSX_FUNCTION_CACHE: dict[Callable[..., Any], AnyJsxFunction] = {}

# ID counter for unique function names
_id_counter: int = 0


def _next_id() -> str:
	"""Generate a unique function ID."""
	global _id_counter
	_id_counter += 1
	return str(_id_counter)


def clear_function_cache() -> None:
	"""Clear the function cache and reset ID counter."""
	global _id_counter
	FUNCTION_CACHE.clear()
	JSX_FUNCTION_CACHE.clear()
	_id_counter = 0


@dataclass(slots=True, init=False)
class JsFunction(Expr, Generic[*Args, R]):
	"""A transpiled JavaScript function.

	Wraps a Python function with:
	- A unique identifier for deduplication
	- Resolved dependencies (other functions, imports, constants, etc.)
	- The ability to transpile to JavaScript code

	When emitted, produces the unique JS function name (e.g., "myFunc_1").
	"""

	fn: Callable[[*Args], R]
	id: str
	deps: dict[str, Expr]
	_transpiled: Function | None = field(default=None)

	def __init__(self, fn: Callable[..., Any]) -> None:
		self.fn = fn
		self.id = _next_id()
		self._transpiled = None
		# Register self in cache BEFORE analyzing deps (handles cycles)
		FUNCTION_CACHE[fn] = self
		# Now analyze and build deps (may recursively call JsFunction() which will find us in cache)
		self.deps = analyze_deps(fn)

	# Mimic the function signature of the underlying function for ease of use
	@override
	def __call__(self, *args: object, **kwargs: object) -> Call:
		return Call(self, [Expr.of(a) for a in args])

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


@dataclass(slots=True, init=False)
class JsxFunction(Expr, Generic[P, R]):
	"""A transpiled JSX component function.

	Similar to JsFunction, but when called produces JSX elements:
	- Positional args become children
	- Keyword args become props

	When emitted, produces the unique JS function name (e.g., "MyComponent_1").
	"""

	fn: Callable[P, R]
	id: str
	deps: dict[str, Expr]
	_transpiled: Function | None = field(default=None)

	def __init__(self, fn: Callable[..., Any]) -> None:
		self.fn = fn
		self.id = _next_id()
		self._transpiled = None
		# Register self in cache BEFORE analyzing deps (handles cycles)
		JSX_FUNCTION_CACHE[fn] = self
		# Now analyze and build deps (may recursively call JsxFunction() which will find us in cache)
		self.deps = analyze_deps(fn)

	@property
	def js_name(self) -> str:
		"""Unique JS identifier for this function."""
		return f"{self.fn.__name__}_{self.id}"

	@override
	def emit(self, out: list[str]) -> None:
		"""Emit this function as its unique JS identifier."""
		out.append(self.js_name)

	@override
	def transpile_call(
		self,
		args: list[ast.expr],
		kwargs: dict[str, ast.expr],
		ctx: Transpiler,
	) -> Expr:
		"""Handle JSX-style calls: positional args are children, kwargs are props."""
		# Build children from positional args
		children: list[Child] = []
		for a in args:
			children.append(ctx.emit_expr(a))

		# Build props from kwargs
		props: dict[str, Prop] = {}
		key: str | None = None
		for k, v in kwargs.items():
			prop_value = ctx.emit_expr(v)
			if k == "key":
				# Extract key prop
				if isinstance(prop_value, LiteralNode) and isinstance(
					prop_value.value, str
				):
					key = prop_value.value
				else:
					raise TranspileError("key prop must be a string literal")
			else:
				props[k] = prop_value

		return Element(
			tag=f"$${self.js_name}",
			props=props if props else None,
			children=children if children else None,
			key=key,
		)

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

	@override
	def __call__(self, *args: object, **kwargs: object) -> Element:  # pyright: ignore[reportIncompatibleMethodOverride]
		"""Allow calling JsxFunction objects in Python code.

		Returns a placeholder Element for type checking. The actual transpilation
		happens via transpile_call when the transpiler processes the AST.
		"""
		return Element(tag=f"$${self.js_name}", props=None, children=None, key=None)


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

		# Functions - check both caches, then create JsFunction
		if inspect.isfunction(value):
			if value in FUNCTION_CACHE:
				deps[name] = FUNCTION_CACHE[value]
			elif value in JSX_FUNCTION_CACHE:
				deps[name] = JSX_FUNCTION_CACHE[value]
			else:
				deps[name] = JsFunction(value)
			continue

		# Other callables (classes, methods, etc.) - not supported
		if callable(value):
			raise TranspileError(
				f"Callable '{name}' (type: {type(value).__name__}) is not supported. "
				+ "Only functions can be transpiled."
			)

		# Constants - convert via Expr.of()
		try:
			deps[name] = Expr.of(value)
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
def javascript(
	*, jsx: Literal[True]
) -> Callable[[Callable[P, R]], JsxFunction[P, R]]: ...


def javascript(fn: Callable[..., Any] | None = None, *, jsx: bool = False) -> Any:
	"""Decorator to convert a Python function into a JsFunction or JsxFunction.

	When jsx=False (default), the function becomes a JsFunction instance.
	When jsx=True, the function becomes a JsxFunction instance that produces
	JSX elements when called.

	Usage:
	    @javascript
	    def add(a: int, b: int) -> int:
	        return a + b

	    @javascript(jsx=True)
	    def MyComponent(name: str):
	        return div(f"Hello {name}")

	    # add is now a JsFunction instance
	    # MyComponent is now a JsxFunction instance
	"""

	def decorator(f: Callable[..., Any]) -> Any:
		if jsx:
			result = JSX_FUNCTION_CACHE.get(f)
			if result is None:
				result = JsxFunction(f)
			return result
		else:
			result = FUNCTION_CACHE.get(f)
			if result is None:
				result = JsFunction(f)
			return result

	if fn is not None:
		return decorator(fn)
	return decorator


def registered_functions() -> list[AnyJsFunction]:
	"""Get all registered JS functions."""
	return list(FUNCTION_CACHE.values())
