"""
Tests for the @javascript decorator and dependency analysis.
"""

# pyright: reportPrivateUsage=false

from typing import Any

import pytest
from pulse.transpiler import (
	JsFunction,
	clear_function_cache,
	clear_import_registry,
	collect_function_graph,
	emit,
	javascript,
	registered_functions,
)
from pulse.transpiler.function import Constant, analyze_deps


@pytest.fixture(autouse=True)
def reset_caches():
	"""Reset caches before each test."""
	clear_function_cache()
	clear_import_registry()
	yield
	clear_function_cache()
	clear_import_registry()


# =============================================================================
# @javascript Decorator (End-to-End)
# =============================================================================


class TestJavascriptDecorator:
	"""Test the @javascript decorator end-to-end."""

	def test_basic_decorator(self):
		"""Test basic @javascript decorator creates JsFunction."""

		@javascript
		def add(a: int, b: int) -> int:
			return a + b

		assert isinstance(add, JsFunction)
		assert add.js_name == "add_1"

	def test_caching(self):
		"""Test that the same function returns the same JsFunction."""

		def helper(x: int) -> int:
			return x * 2

		js1 = javascript(helper)
		js2 = javascript(helper)
		assert js1 is js2

	def test_function_dependencies(self):
		"""Test that functions can reference other @javascript functions."""

		@javascript
		def helper(n: int) -> int:
			return n + 1

		@javascript
		def caller(n: int) -> Any:
			return helper(n) * 2

		assert "helper" in caller.deps
		assert isinstance(caller.deps["helper"], JsFunction)
		assert caller.deps["helper"] is helper

	def test_transpile_with_function_deps(self):
		"""Test transpiling a function that uses another function."""

		@javascript
		def double(x: int) -> int:
			return x * 2

		@javascript
		def quadruple(x: int) -> Any:
			return double(double(x))

		assert "double" in quadruple.deps

		fn = quadruple.transpile()
		code = emit(fn)
		assert code == "function quadruple_2(x) {\nreturn double_1(double_1(x));\n}"

	def test_closure_variables(self):
		"""Test that closure variables are captured as deps."""

		def make_adder(n: int):
			@javascript
			def adder(x: int) -> int:
				return x + n

			return adder

		add5 = make_adder(5)
		assert isinstance(add5, JsFunction)
		assert "n" in add5.deps

	def test_constant_deps(self):
		"""Test that constant values are captured as deps."""
		MULTIPLIER = 10

		@javascript
		def multiply(x: int) -> int:
			return x * MULTIPLIER

		assert "MULTIPLIER" in multiply.deps
		fn = multiply.transpile()
		code = emit(fn)
		assert code == "function multiply_1(x) {\nreturn x * 10;\n}"

	def test_registered_functions(self):
		"""Test that registered_functions returns all JsFunctions."""

		@javascript
		def fn1() -> int:
			return 1

		@javascript
		def fn2() -> int:
			return 2

		fns = registered_functions()
		assert len(fns) == 2
		assert fn1 in fns
		assert fn2 in fns


class TestAnalyzeDeps:
	"""Test dependency analysis."""

	def test_empty_deps(self):
		"""Test analyzing a function with no deps."""

		def simple(x: int) -> int:
			return x + 1

		deps = analyze_deps(simple)
		assert deps == {}

	def test_constant_deps(self):
		"""Test analyzing a function with constant deps."""
		VALUE = 42

		def use_const() -> int:
			return VALUE

		deps = analyze_deps(use_const)
		assert "VALUE" in deps

	def test_nonprimitive_constant_hoisting(self):
		"""Test that non-primitive constants are wrapped in Constant for hoisting."""

		ITEMS = [1, 2, 3]
		OPTIONS = {"a": 1, "b": 2}

		def use_list() -> int:
			return ITEMS[0]

		def use_dict() -> int:
			return OPTIONS["a"]

		list_deps = analyze_deps(use_list)
		dict_deps = analyze_deps(use_dict)

		# Non-primitives should be wrapped in Constant
		assert isinstance(list_deps["ITEMS"], Constant)
		assert isinstance(dict_deps["OPTIONS"], Constant)

		# Constants should have unique js_name
		assert list_deps["ITEMS"].js_name.startswith("ITEMS_")
		assert dict_deps["OPTIONS"].js_name.startswith("OPTIONS_")

		# Check the underlying expr emits correctly
		assert emit(list_deps["ITEMS"].expr) == "[1, 2, 3]"
		assert emit(dict_deps["OPTIONS"].expr) == '{"a": 1, "b": 2}'


class TestCollectFunctionGraph:
	"""Test the collect_function_graph helper for codegen."""

	def test_collects_constants_and_functions(self):
		"""Test that constants and functions are collected in dependency order."""

		SHARED = [1, 2, 3]

		@javascript
		def use_shared() -> int:
			return SHARED[0]

		consts, funcs = collect_function_graph([use_shared])

		# Should have one constant
		assert len(consts) == 1
		assert isinstance(consts[0], Constant)
		assert consts[0].js_name.startswith("SHARED_")

		# Should have one function
		assert len(funcs) == 1
		assert funcs[0] is use_shared

	def test_deduplicates_shared_constants(self):
		"""Test that shared constants are only emitted once."""

		SHARED = {"key": "value"}

		@javascript
		def fn1() -> str:
			return SHARED["key"]

		@javascript
		def fn2() -> str:
			return SHARED["key"]

		consts, funcs = collect_function_graph([fn1, fn2])

		# Shared constant should only appear once
		assert len(consts) == 1
		assert isinstance(consts[0], Constant)

		# Both functions should be collected
		assert len(funcs) == 2
