from __future__ import annotations

import builtins
import inspect
import types
from typing import Any, Callable, Generic, TypeAlias, TypeVar, TypeVarTuple

from pulse.javascript_v2.constants import JsConstant, const_to_js
from pulse.javascript_v2.errors import JSCompilationError
from pulse.javascript_v2.ids import generate_id
from pulse.javascript_v2.imports import Import
from pulse.javascript_v2.module import JsModule

Args = TypeVarTuple("Args")
R = TypeVar("R")

AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any, ...], Any]"
JsDep: TypeAlias = "AnyJsFunction | JsConstant | Import | PyBuiltin"

# Global cache for deduplication across all transpiled functions
# Registered BEFORE analyzing deps to handle mutual recursion
FUNCTION_CACHE: dict[Callable[..., object], AnyJsFunction] = {}


class PyBuiltin:
	"""Placeholder for Python builtins that need JS equivalents."""

	name: str

	def __init__(self, name: str) -> None:
		self.name = name


def _get_or_create_function(fn: Callable[..., object]) -> AnyJsFunction:
	"""Get cached JsFunction or create and cache it."""
	if fn not in FUNCTION_CACHE:
		JsFunction(fn)  # Constructor registers in cache
	return FUNCTION_CACHE[fn]


def javascript(fn: Callable[..., object]) -> AnyJsFunction:
	"""Decorator to convert a function into a JsFunction.

	Usage:
		@javascript
		def my_func(x: int) -> int:
			return x + 1

		# my_func is now a JsFunction instance
	"""
	return JsFunction(fn)


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
				# Python modules - planned for future handling
				# Will be handled separately via PyModule registry
				continue
			elif inspect.isfunction(value):
				deps[name] = _get_or_create_function(value)
			elif callable(value):
				# Callable objects (not functions) are not supported
				raise JSCompilationError(
					f"Callable object '{name}' (type: {type(value).__name__}) is not supported. "
					+ "Only functions can be transpiled."
				)
			else:
				# Constants
				deps[name] = const_to_js(value, name)
		elif name in builtin_dict:
			# Python builtins
			deps[name] = PyBuiltin(name)
		# Unresolved names (e.g., attribute accesses like 'math.pi') are skipped
		# They'll be handled during code generation

	return deps
