"""Tests for JsFunction dependency analysis."""

from __future__ import annotations

import pytest
from pulse.codegen.imports import Import, clear_import_registry
from pulse.javascript_v2.constants import CONSTANTS_CACHE
from pulse.javascript_v2.function import FUNCTION_CACHE, JsFunction
from pulse.javascript_v2.nodes import JSArray, JSNumber, JSString


# Clear caches between tests
@pytest.fixture(autouse=True)
def clear_caches() -> None:
	FUNCTION_CACHE.clear()
	CONSTANTS_CACHE.clear()
	clear_import_registry()


# =============================================================================
# Module-level test fixtures (to avoid closure issues)
# =============================================================================

# Imports
_test_import = Import("foo", "./foo.js")
_import_a = Import("a", "./a.js")
_import_b = Import.default("b", "./b.js")

# Constants
_MY_CONST = 42
_GREETING = "hello"
_ITEMS = [1, 2, 3]

# Shared constant for dedup test
_SHARED_CONST = 999


# Helper functions
def _helper(x: int) -> int:
	return x + 1


def _add(a: int, b: int) -> int:
	return a + b


def _mul(a: int, b: int) -> int:
	return a * b


def _level2(x: int) -> int:
	return x * 2


def _level1(x: int) -> int:
	return _level2(x) + 1


# Mutually recursive
def _is_even(n: int) -> bool:
	if n == 0:
		return True
	return _is_odd(n - 1)


def _is_odd(n: int) -> bool:
	if n == 0:
		return False
	return _is_even(n - 1)


# Self-recursive
def _factorial(n: int) -> int:
	if n <= 1:
		return 1
	return n * _factorial(n - 1)


# =============================================================================
# Test functions that use module-level fixtures
# =============================================================================


def _fn_uses_import() -> int:
	return _test_import  # pyright: ignore[reportReturnType]


def _fn_uses_multiple_imports() -> tuple[int, str]:
	return _import_a, _import_b  # pyright: ignore[reportReturnType]


def _fn_uses_numeric_const() -> int:
	return _MY_CONST


def _fn_uses_string_const() -> str:
	return _GREETING


def _fn_uses_list_const() -> list[int]:
	return _ITEMS


def _fn_uses_helper(x: int) -> int:
	return _helper(x)


def _fn_uses_add_mul(x: int) -> int:
	return _add(_mul(x, 2), 1)


def _fn_uses_level1(x: int) -> int:
	return _level1(x)


def _fn_nested_deps(items: list[int]) -> list[int]:
	def transform(x: int) -> int:
		return x * _MY_CONST

	return [transform(x) for x in items]


def _fn_uses_shared_const_1() -> int:
	return _SHARED_CONST


def _fn_uses_shared_const_2() -> int:
	return _SHARED_CONST + 1


# =============================================================================
# Tests
# =============================================================================


class TestJsFunctionImports:
	def test_detects_js_import(self) -> None:
		jsfn = JsFunction(_fn_uses_import)
		imports = jsfn.get_import_deps()
		assert "_test_import" in imports
		assert imports["_test_import"] is _test_import

	def test_multiple_imports(self) -> None:
		jsfn = JsFunction(_fn_uses_multiple_imports)
		imports = jsfn.get_import_deps()
		assert len(imports) == 2
		assert imports["_import_a"] is _import_a
		assert imports["_import_b"] is _import_b


class TestJsFunctionConstants:
	def test_detects_numeric_constant(self) -> None:
		jsfn = JsFunction(_fn_uses_numeric_const)
		constants = jsfn.get_constant_deps()
		assert "_MY_CONST" in constants
		assert isinstance(constants["_MY_CONST"], JSNumber)

	def test_detects_string_constant(self) -> None:
		jsfn = JsFunction(_fn_uses_string_const)
		constants = jsfn.get_constant_deps()
		assert "_GREETING" in constants
		assert isinstance(constants["_GREETING"], JSString)

	def test_detects_list_constant(self) -> None:
		jsfn = JsFunction(_fn_uses_list_const)
		constants = jsfn.get_constant_deps()
		assert "_ITEMS" in constants
		assert isinstance(constants["_ITEMS"], JSArray)

	def test_constants_are_cached_globally(self) -> None:
		"""Same constant value should reuse cached JSExpr."""
		jsfn1 = JsFunction(_fn_uses_shared_const_1)
		jsfn2 = JsFunction(_fn_uses_shared_const_2)

		constants1 = jsfn1.get_constant_deps()
		constants2 = jsfn2.get_constant_deps()

		# Both should have the same JSExpr instance (cached)
		assert constants1["_SHARED_CONST"] is constants2["_SHARED_CONST"]


class TestJsFunctionDependencies:
	def test_detects_function_dependency(self) -> None:
		jsfn = JsFunction(_fn_uses_helper)
		functions = jsfn.get_function_deps()
		assert "_helper" in functions
		assert isinstance(functions["_helper"], JsFunction)
		assert functions["_helper"].fn is _helper

	def test_multiple_function_dependencies(self) -> None:
		jsfn = JsFunction(_fn_uses_add_mul)
		functions = jsfn.get_function_deps()
		assert "_add" in functions
		assert "_mul" in functions

	def test_function_dependency_cached(self) -> None:
		"""Same function referenced twice should use cache."""

		def fn1(x: int) -> int:
			return _helper(x)

		def fn2(x: int) -> int:
			return _helper(x) + 1

		jsfn1 = JsFunction(fn1)
		jsfn2 = JsFunction(fn2)

		functions1 = jsfn1.get_function_deps()
		functions2 = jsfn2.get_function_deps()

		# Both should reference the same JsFunction wrapper
		assert functions1["_helper"] is functions2["_helper"]

	def test_transitive_dependencies(self) -> None:
		"""Dependencies of dependencies are analyzed."""
		jsfn = JsFunction(_fn_uses_level1)
		functions = jsfn.get_function_deps()
		assert "_level1" in functions

		level1_fn = functions["_level1"]
		level1_functions = level1_fn.get_function_deps()
		assert "_level2" in level1_functions


class TestJsFunctionCycles:
	def test_mutual_recursion(self) -> None:
		"""Mutually recursive functions should not cause infinite loop."""
		jsfn_even = JsFunction(_is_even)
		functions_even = jsfn_even.get_function_deps()

		assert "_is_odd" in functions_even
		jsfn_odd = functions_even["_is_odd"]

		functions_odd = jsfn_odd.get_function_deps()
		assert "_is_even" in functions_odd

		# The _is_even reference in _is_odd should be the same as jsfn_even
		assert functions_odd["_is_even"] is jsfn_even

	def test_self_recursion(self) -> None:
		"""Self-recursive function should work."""
		jsfn = JsFunction(_factorial)
		functions = jsfn.get_function_deps()

		# factorial references itself
		assert "_factorial" in functions
		assert functions["_factorial"] is jsfn


class TestJsFunctionErrors:
	def test_rejects_closure(self) -> None:
		from collections.abc import Callable

		def make_closure() -> Callable[[], int]:
			captured = 42

			def inner() -> int:
				return captured

			return inner

		closure = make_closure()

		with pytest.raises(ValueError, match="captures nonlocal variables"):
			JsFunction(closure)


class TestJsFunctionNestedFunctions:
	def test_nested_function_deps_captured(self) -> None:
		"""Dependencies in nested functions should be captured."""
		jsfn = JsFunction(_fn_nested_deps)
		constants = jsfn.get_constant_deps()

		# Should capture _MY_CONST from nested function
		assert "_MY_CONST" in constants


class TestRawGlobalsAccess:
	def test_globals_contains_raw_values(self) -> None:
		"""JsFunction.globals should contain the raw Python objects."""
		jsfn = JsFunction(_fn_uses_helper)

		# Raw function is in globals
		assert "_helper" in jsfn.globals
		assert jsfn.globals["_helper"] is _helper

	def test_builtins_contains_raw_values(self) -> None:
		"""JsFunction.builtins should contain the raw builtin objects."""

		def fn(items: list[int]) -> int:
			return len(items)

		jsfn = JsFunction(fn)

		# len builtin is in builtins
		assert "len" in jsfn.builtins
		assert jsfn.builtins["len"] is len
