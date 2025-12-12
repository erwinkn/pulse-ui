"""Function transpilation system for transpiler_v2.

Provides the @javascript decorator for marking Python functions for JS transpilation,
and JsFunction which wraps a transpiled function with its dependencies.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import types as pytypes
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeAlias, TypeVar, TypeVarTuple, override

from pulse.helpers import getsourcecode
from pulse.transpiler_v2.nodes import EXPR_REGISTRY, Call, ExprNode, Function
from pulse.transpiler_v2.transpiler import TranspileError, Transpiler

Args = TypeVarTuple("Args")
R = TypeVar("R")
AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any, ...], Any]"

# Global cache for deduplication across all transpiled functions
# Registered BEFORE analyzing deps to handle mutual recursion
FUNCTION_CACHE: dict[Callable[..., Any], AnyJsFunction] = {}

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
	_id_counter = 0


@dataclass(slots=True, init=False)
class JsFunction(ExprNode, Generic[*Args, R]):
	"""A transpiled JavaScript function.

	Wraps a Python function with:
	- A unique identifier for deduplication
	- Resolved dependencies (other functions, imports, constants, etc.)
	- The ability to transpile to JavaScript code

	When emitted, produces the unique JS function name (e.g., "myFunc_1").
	"""

	fn: Callable[[*Args], R]
	id: str
	deps: dict[str, ExprNode]
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
	def __call__(self, *args: *Args) -> R:
		return Call(self, [ExprNode.of(a) for a in args])  # pyright: ignore[reportReturnType]

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
			from pulse.transpiler_v2.nodes import Return

			result = Function(
				params=list(result.params),
				body=[Return(result.body)],
				name=self.js_name,
				is_async=False,
			)

		self._transpiled = result
		return result

	def imports(self) -> dict[str, ExprNode]:
		"""Get all Import dependencies."""
		from pulse.transpiler_v2.imports import Import

		return {k: v for k, v in self.deps.items() if isinstance(v, Import)}

	def functions(self) -> dict[str, AnyJsFunction]:
		"""Get all JsFunction dependencies."""
		return {k: v for k, v in self.deps.items() if isinstance(v, JsFunction)}


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


def analyze_deps(fn: Callable[..., object]) -> dict[str, ExprNode]:
	"""Analyze a function and return its dependencies as ExprNode instances.

	Walks the function's code object to find all referenced names,
	then resolves them from globals/closure and converts to ExprNode.
	"""
	# Analyze code object and resolve globals + closure vars
	effective_globals, all_names = analyze_code_object(fn)

	# Build dependencies dictionary - all values are ExprNode
	deps: dict[str, ExprNode] = {}

	for name in all_names:
		value = effective_globals.get(name)

		if value is None:
			# Not in globals - could be a builtin or unresolved
			# For now, skip - builtins will be handled by the transpiler
			# TODO: Add builtin support
			continue

		# Already an ExprNode
		if isinstance(value, ExprNode):
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

		# Functions - recursively create JsFunction
		if inspect.isfunction(value):
			if value in FUNCTION_CACHE:
				deps[name] = FUNCTION_CACHE[value]
			else:
				deps[name] = JsFunction(value)
			continue

		# Other callables (classes, methods, etc.) - not supported
		if callable(value):
			raise TranspileError(
				f"Callable '{name}' (type: {type(value).__name__}) is not supported. "
				+ "Only functions can be transpiled."
			)

		# Constants - convert via ExprNode.of()
		try:
			deps[name] = ExprNode.of(value)
		except TypeError:
			raise TranspileError(
				f"Cannot convert '{name}' (type: {type(value).__name__}) to ExprNode"
			) from None

	return deps


def javascript(fn: Callable[[*Args], R]) -> JsFunction[*Args, R]:
	"""Decorator to convert a Python function into a JsFunction.

	The decorated function becomes a JsFunction instance that can be:
	- Transpiled to JavaScript code
	- Used as a dependency in other @javascript functions
	- Emitted in JS code generation

	Usage:
	    @javascript
	    def add(a: int, b: int) -> int:
	        return a + b

	    # add is now a JsFunction instance
	    # add.transpile() returns the Function node
	    # add.js_name is "add_1"
	"""
	result = FUNCTION_CACHE.get(fn)
	if result is None:
		result = JsFunction(fn)
	return result  # pyright: ignore[reportReturnType]


def registered_functions() -> list[AnyJsFunction]:
	"""Get all registered JS functions."""
	return list(FUNCTION_CACHE.values())
