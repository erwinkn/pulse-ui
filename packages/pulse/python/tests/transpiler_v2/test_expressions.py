"""
Tests for basic expression transpilation.

Tests basic expressions, operators, ternary expressions, and data structures.
"""

# pyright: reportPrivateUsage=false

from typing import Any

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
# Basic Expressions
# =============================================================================


class TestBasicExpressions:
	"""Test basic expression transpilation."""

	def test_simple_return(self):
		@javascript
		def add(x: int, y: int) -> int:
			return x + y

		fn = add.transpile()
		code = emit(fn)
		assert code == "function add_1(x, y) {\nreturn x + y;\n}"

	def test_constant_return(self):
		@javascript
		def get_answer() -> int:
			return 42

		fn = get_answer.transpile()
		code = emit(fn)
		assert code == "function get_answer_1() {\nreturn 42;\n}"

	def test_string_return(self):
		@javascript
		def greet() -> str:
			return "hello"

		fn = greet.transpile()
		code = emit(fn)
		assert code == 'function greet_1() {\nreturn "hello";\n}'

	def test_boolean_return(self):
		@javascript
		def get_true() -> bool:
			return True

		fn = get_true.transpile()
		code = emit(fn)
		assert code == "function get_true_1() {\nreturn true;\n}"

	def test_none_return(self):
		@javascript
		def get_none() -> None:
			return None

		fn = get_none.transpile()
		code = emit(fn)
		assert code == "function get_none_1() {\nreturn null;\n}"

	def test_empty_body_returns_null(self):
		@javascript
		def empty() -> None:
			"""Docstring only."""
			pass

		fn = empty.transpile()
		code = emit(fn)
		assert code == "function empty_1() {\n{\n}\n}"


# =============================================================================
# Operators
# =============================================================================


class TestOperators:
	"""Test operator transpilation."""

	def test_binary_operators(self):
		@javascript
		def math(a: int | float, b: int | float) -> int | float:
			return a + b - a * b / a % b**a

		fn = math.transpile()
		code = emit(fn)
		assert code == "function math_1(a, b) {\nreturn a + b - a * b / a % b ** a;\n}"

	def test_comparison_operators(self):
		@javascript
		def cmp(a: Any, b: Any) -> bool:
			return a == b

		fn = cmp.transpile()
		code = emit(fn)
		assert code == "function cmp_1(a, b) {\nreturn a === b;\n}"

	def test_not_equal(self):
		@javascript
		def ne(a: Any, b: Any) -> bool:
			return a != b

		fn = ne.transpile()
		code = emit(fn)
		assert code == "function ne_1(a, b) {\nreturn a !== b;\n}"

	def test_less_than(self):
		@javascript
		def lt(a: int | float, b: int | float) -> bool:
			return a < b

		fn = lt.transpile()
		code = emit(fn)
		assert code == "function lt_1(a, b) {\nreturn a < b;\n}"

	def test_unary_not(self):
		@javascript
		def negate(x: Any) -> bool:
			return not x

		fn = negate.transpile()
		code = emit(fn)
		assert code == "function negate_1(x) {\nreturn !x;\n}"

	def test_unary_minus(self):
		@javascript
		def neg(x: int | float) -> int | float:
			return -x

		fn = neg.transpile()
		code = emit(fn)
		assert code == "function neg_1(x) {\nreturn -x;\n}"

	def test_boolean_and(self):
		@javascript
		def both(a: Any, b: Any) -> Any:
			return a and b

		fn = both.transpile()
		code = emit(fn)
		assert code == "function both_1(a, b) {\nreturn a && b;\n}"

	def test_boolean_or(self):
		@javascript
		def either(a: Any, b: Any) -> Any:
			return a or b

		fn = either.transpile()
		code = emit(fn)
		assert code == "function either_1(a, b) {\nreturn a || b;\n}"


# =============================================================================
# Ternary / Conditional
# =============================================================================


class TestTernary:
	"""Test ternary expression transpilation."""

	def test_simple_ternary(self):
		@javascript
		def check(x: Any) -> int:
			return 1 if x else 0

		fn = check.transpile()
		code = emit(fn)
		assert code == "function check_1(x) {\nreturn x ? 1 : 0;\n}"

	def test_ternary_with_comparison(self):
		@javascript
		def sign(x: int | float) -> str:
			return "positive" if x > 0 else "non-positive"

		fn = sign.transpile()
		code = emit(fn)
		assert (
			code
			== 'function sign_1(x) {\nreturn x > 0 ? "positive" : "non-positive";\n}'
		)

	def test_nested_ternary(self):
		@javascript
		def classify(x: int | float) -> int:
			return 1 if x > 0 else -1 if x < 0 else 0

		fn = classify.transpile()
		code = emit(fn)
		assert code == "function classify_1(x) {\nreturn x > 0 ? 1 : x < 0 ? -1 : 0;\n}"


# =============================================================================
# Data Structures
# =============================================================================


class TestDataStructures:
	"""Test list/dict/set transpilation."""

	def test_list_literal(self):
		@javascript
		def get_list() -> list[int]:
			return [1, 2, 3]

		fn = get_list.transpile()
		code = emit(fn)
		assert code == "function get_list_1() {\nreturn [1, 2, 3];\n}"

	def test_tuple_as_array(self):
		@javascript
		def get_tuple() -> tuple[int, int, int]:
			return (1, 2, 3)

		fn = get_tuple.transpile()
		code = emit(fn)
		assert code == "function get_tuple_1() {\nreturn [1, 2, 3];\n}"

	def test_dict_as_map(self):
		@javascript
		def get_dict() -> dict[str, int]:
			return {"a": 1, "b": 2}

		fn = get_dict.transpile()
		code = emit(fn)
		assert code == 'function get_dict_1() {\nreturn Map([["a", 1], ["b", 2]]);\n}'

	def test_set_literal(self):
		@javascript
		def get_set() -> set[int]:
			return {1, 2, 3}

		fn = get_set.transpile()
		code = emit(fn)
		assert code == "function get_set_1() {\nreturn Set([1, 2, 3]);\n}"
