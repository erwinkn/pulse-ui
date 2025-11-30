from __future__ import annotations

import inspect
from typing import Any, Callable, Generic, TypeAlias, TypeVar, TypeVarTuple

from pulse.codegen.imports import Import
from pulse.javascript_v2.constants import const_to_js
from pulse.javascript_v2.introspection import get_function_refs, validate_no_nonlocals
from pulse.javascript_v2.nodes import JSExpr

Args = TypeVarTuple("Args")
R = TypeVar("R")

AnyJsFunction: TypeAlias = "JsFunction[*tuple[Any, ...], Any]"

# Global cache for deduplication across all transpiled functions
# Registered BEFORE analyzing deps to handle mutual recursion
FUNCTION_CACHE: dict[Callable[..., object], AnyJsFunction] = {}


def _get_or_create_function(fn: Callable[..., object]) -> AnyJsFunction:
	"""Get cached JsFunction or create and cache it."""
	if fn not in FUNCTION_CACHE:
		JsFunction(fn)  # Constructor registers in cache
	return FUNCTION_CACHE[fn]


class JsFunction(Generic[*Args, R]):
	fn: Callable[[*Args], R]

	# Raw mapping: global name -> value (for codegen to process)
	globals: dict[str, object]
	builtins: dict[str, object]

	def __init__(self, fn: Callable[[*Args], R]) -> None:
		self.fn = fn
		self.globals = {}
		self.builtins = {}

		# Ensure the function isn't a closure (no captured nonlocals)
		validate_no_nonlocals(fn)

		# Register self in cache BEFORE analyzing deps (handles cycles)
		FUNCTION_CACHE[fn] = self

		# Get all references including those in nested functions
		refs = get_function_refs(fn)

		# Store raw mappings - codegen will categorize and dedupe
		self.globals = dict(refs.globals)
		self.builtins = dict(refs.builtins)

		# Eagerly analyze function dependencies to populate cache
		# (ensures cycle handling works)
		for value in refs.globals.values():
			if isinstance(value, JsFunction):
				pass  # Already wrapped
			elif inspect.isfunction(value):
				_get_or_create_function(value)

	def __call__(self, *args: *Args) -> JsFunctionCall[*Args]:
		return JsFunctionCall(self, args)

	def get_function_deps(self) -> dict[str, AnyJsFunction]:
		"""Get all function dependencies (wrapped in JsFunction)."""
		result: dict[str, AnyJsFunction] = {}
		for name, value in self.globals.items():
			if isinstance(value, JsFunction):
				result[name] = value
			elif inspect.isfunction(value):
				result[name] = FUNCTION_CACHE[value]
		return result

	def get_constant_deps(self) -> dict[str, JSExpr]:
		"""Get all constant dependencies (converted to JSExpr, deduplicated)."""
		result: dict[str, JSExpr] = {}
		for name, value in self.globals.items():
			# Skip non-constants
			if (
				isinstance(value, (JsFunction, Import))
				or inspect.isfunction(value)
				or inspect.ismodule(value)
				or callable(value)
			):
				continue
			result[name] = const_to_js(value)  # pyright: ignore[reportArgumentType]
		return result

	def get_import_deps(self) -> dict[str, Import]:
		"""Get all Import dependencies."""
		return {
			name: value
			for name, value in self.globals.items()
			if isinstance(value, Import)
		}

	def get_module_deps(self) -> dict[str, object]:
		"""Get all module dependencies."""
		return {
			name: value
			for name, value in self.globals.items()
			if inspect.ismodule(value)
		}


class JsFunctionCall(Generic[*Args]):
	fn: JsFunction[*Args, Any]
	args: tuple[*Args]

	def __init__(self, fn: JsFunction[*Args, Any], args: tuple[*Args]) -> None:
		self.fn = fn
		self.args = args
