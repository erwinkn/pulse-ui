"""
Tests for advanced expression transpilation: f-strings, lambdas, and comprehensions.
"""

# pyright: reportPrivateUsage=false

from collections.abc import Iterable
from typing import Any, Callable

import pytest
from pulse.transpiler_v2 import (
	clear_function_cache,
	clear_import_registry,
	emit,
	javascript,
)


@pytest.fixture(autouse=True)
def reset_caches():
	"""Reset caches before each test."""
	clear_function_cache()
	clear_import_registry()
	yield
	clear_function_cache()
	clear_import_registry()


# =============================================================================
# F-strings / Template Literals
# =============================================================================


class TestFStrings:
	"""Test f-string transpilation."""

	def test_simple_fstring(self):
		@javascript
		def greet(name: str) -> str:
			return f"Hello, {name}!"

		fn = greet.transpile()
		code = emit(fn)
		assert code == "function greet_1(name) {\nreturn `Hello, ${name}!`;\n}"

	def test_fstring_with_expression(self):
		@javascript
		def show_sum(a: int, b: int) -> str:
			return f"Sum: {a + b}"

		fn = show_sum.transpile()
		code = emit(fn)
		assert code == "function show_sum_1(a, b) {\nreturn `Sum: ${a + b}`;\n}"

	def test_fstring_conversion_s(self):
		@javascript
		def stringify(x: Any) -> str:
			return f"{x!s}"

		fn = stringify.transpile()
		code = emit(fn)
		assert code == "function stringify_1(x) {\nreturn `${String(x)}`;\n}"

	def test_fstring_conversion_r(self):
		@javascript
		def repr_it(x: Any) -> str:
			return f"{x!r}"

		fn = repr_it.transpile()
		code = emit(fn)
		assert code == "function repr_it_1(x) {\nreturn `${JSON.stringify(x)}`;\n}"


# =============================================================================
# Lambda
# =============================================================================


class TestLambda:
	"""Test lambda transpilation."""

	def test_simple_lambda(self):
		@javascript
		def get_doubler() -> Callable[[float], float]:
			return lambda x: x * 2

		fn = get_doubler.transpile()
		code = emit(fn)
		assert code == "function get_doubler_1() {\nreturn x => x * 2;\n}"

	def test_multi_param_lambda(self):
		@javascript
		def get_adder() -> Callable[[int, int], int]:
			return lambda a, b: a + b

		fn = get_adder.transpile()
		code = emit(fn)
		assert code == "function get_adder_1() {\nreturn (a, b) => a + b;\n}"

	def test_zero_param_lambda(self):
		@javascript
		def get_const():
			return lambda: 42

		fn = get_const.transpile()
		code = emit(fn)
		assert code == "function get_const_1() {\nreturn () => 42;\n}"


# =============================================================================
# List Comprehensions
# =============================================================================


class TestComprehensions:
	"""Test comprehension transpilation."""

	def test_simple_list_comp(self):
		@javascript
		def double_all(items: Iterable[int]) -> list[int]:
			return [x * 2 for x in items]

		fn = double_all.transpile()
		code = emit(fn)
		assert (
			code == "function double_all_1(items) {\nreturn items.map(x => x * 2);\n}"
		)

	def test_list_comp_with_filter(self):
		@javascript
		def get_positives(items: Iterable[int]) -> list[int]:
			return [x for x in items if x > 0]

		fn = get_positives.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_positives_1(items) {\nreturn items.filter(x => x > 0).map(x => x);\n}"
		)

	def test_tuple_unpacking_in_comp(self):
		@javascript
		def sum_pairs(pairs: Iterable[tuple[int, int]]) -> list[int]:
			return [a + b for a, b in pairs]

		fn = sum_pairs.transpile()
		code = emit(fn)
		assert (
			code
			== "function sum_pairs_1(pairs) {\nreturn pairs.map(([a, b]) => a + b);\n}"
		)

	def test_set_comp(self):
		@javascript
		def unique_doubled(items: Iterable[int]) -> set[int]:
			return {x * 2 for x in items}

		fn = unique_doubled.transpile()
		code = emit(fn)
		assert (
			code
			== "function unique_doubled_1(items) {\nreturn Set(items.map(x => x * 2));\n}"
		)

	def test_dict_comp(self):
		@javascript
		def double_values(pairs: Iterable[tuple[str, int]]) -> dict[str, int]:
			return {k: v * 2 for k, v in pairs}

		fn = double_values.transpile()
		code = emit(fn)
		assert (
			code
			== "function double_values_1(pairs) {\nreturn Map(pairs.map(([k, v]) => [k, v * 2]));\n}"
		)
