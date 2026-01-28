"""
Tests for advanced expression transpilation: f-strings, lambdas, and comprehensions.
"""

# pyright: reportPrivateUsage=false

from collections.abc import Iterable
from typing import Any, Callable

import pytest
from pulse.transpiler import (
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

	def test_fstring_center_alignment_with_number(self):
		"""Center alignment must convert to string first to get .length.

		Bug: f"{num:^10}" fails because num.length is undefined for numbers.
		Fix: Convert to String first before using .length for center alignment.
		"""

		@javascript
		def center_num(x: int) -> str:
			return f"{x:^10}"

		fn = center_num.transpile()
		code = emit(fn)
		assert (
			code
			== 'function center_num_1(x) {\nreturn `${String(x).padStart((10 + String(x).length) / 2 | 0, " ").padEnd(10, " ")}`;\n}'
		)


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

	def test_lambda_in_subscript_target(self):
		@javascript
		def set_item(arr):
			arr[lambda x: x] = 1

		fn = set_item.transpile()
		code = emit(fn)
		assert code == "function set_item_1(arr) {\narr[x => x] = 1;\n}"


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
			== "function unique_doubled_1(items) {\nreturn new Set(items.map(x => x * 2));\n}"
		)

	def test_dict_comp(self):
		@javascript
		def double_values(pairs: Iterable[tuple[str, int]]) -> dict[str, int]:
			return {k: v * 2 for k, v in pairs}

		fn = double_values.transpile()
		code = emit(fn)
		assert (
			code
			== "function double_values_1(pairs) {\nreturn new Map(pairs.map(([k, v]) => [k, v * 2]));\n}"
		)

	def test_list_comp_in_subscript_target(self):
		@javascript
		def set_item(obj, items: Iterable[int]):
			obj[[x for x in items]] = 1

		fn = set_item.transpile()
		code = emit(fn)
		assert (
			code == "function set_item_1(obj, items) {\nobj[items.map(x => x)] = 1;\n}"
		)


# =============================================================================
# Format Specs
# =============================================================================


class TestFormatSpecs:
	"""Test format spec transpilation in f-strings."""

	def test_float_format(self):
		@javascript
		def format_pi() -> str:
			pi = 3.14159
			return f"{pi:.2f}"

		fn = format_pi.transpile()
		code = emit(fn)
		assert (
			code
			== "function format_pi_1() {\nlet pi;\npi = 3.14159;\nreturn `${pi.toFixed(2)}`;\n}"
		)

	def test_left_align(self):
		@javascript
		def left_pad(s: str) -> str:
			return f"{s:<10}"

		fn = left_pad.transpile()
		code = emit(fn)
		assert (
			code
			== 'function left_pad_1(s) {\nreturn `${String(s).padEnd(10, " ")}`;\n}'
		)

	def test_right_align(self):
		@javascript
		def right_pad(s: str) -> str:
			return f"{s:>10}"

		fn = right_pad.transpile()
		code = emit(fn)
		assert (
			code
			== 'function right_pad_1(s) {\nreturn `${String(s).padStart(10, " ")}`;\n}'
		)

	def test_center_align_with_number(self):
		"""Center alignment must convert expr to string before using .length.

		This tests the bug where expr.length was used on non-string values.
		The fix: convert to String first, then use .length for padding calculation.
		"""

		@javascript
		def center_number(n: int) -> str:
			return f"{n:^10}"

		fn = center_number.transpile()
		code = emit(fn)
		assert (
			code
			== 'function center_number_1(n) {\nreturn `${String(n).padStart((10 + String(n).length) / 2 | 0, " ").padEnd(10, " ")}`;\n}'
		)

	def test_center_align_with_float_format(self):
		"""Center alignment with float format spec.

		After toFixed(), we have a string, but center align should still
		explicitly convert to String to be safe.
		"""

		@javascript
		def center_float(x: float) -> str:
			return f"{x:^10.2f}"

		fn = center_float.transpile()
		code = emit(fn)
		assert (
			code
			== 'function center_float_1(x) {\nreturn `${x.toFixed(2).padStart((10 + x.toFixed(2).length) / 2 | 0, " ").padEnd(10, " ")}`;\n}'
		)

	def test_hex_format(self):
		@javascript
		def to_hex(n: int) -> str:
			return f"{n:x}"

		fn = to_hex.transpile()
		code = emit(fn)
		assert code == "function to_hex_1(n) {\nreturn `${n.toString(16)}`;\n}"

	def test_hex_format_alt(self):
		@javascript
		def to_hex_alt(n: int) -> str:
			return f"{n:#x}"

		fn = to_hex_alt.transpile()
		code = emit(fn)
		assert (
			code == 'function to_hex_alt_1(n) {\nreturn `${"0x" + n.toString(16)}`;\n}'
		)

	def test_percentage_format(self):
		"""% format spec multiplies by 100 and adds %."""

		@javascript
		def to_percent(x: float) -> str:
			return f"{x:.2%}"

		fn = to_percent.transpile()
		code = emit(fn)
		assert (
			code
			== 'function to_percent_1(x) {\nreturn `${(x * 100).toFixed(2) + "%"}`;\n}'
		)

	def test_general_format_g(self):
		"""g format uses general format (toPrecision)."""

		@javascript
		def general(x: float) -> str:
			return f"{x:.4g}"

		fn = general.transpile()
		code = emit(fn)
		assert code == "function general_1(x) {\nreturn `${x.toPrecision(4)}`;\n}"

	def test_general_format_G(self):
		"""G format uses general format with uppercase."""

		@javascript
		def general_upper(x: float) -> str:
			return f"{x:.4G}"

		fn = general_upper.transpile()
		code = emit(fn)
		assert (
			code
			== "function general_upper_1(x) {\nreturn `${x.toPrecision(4).toUpperCase()}`;\n}"
		)

	def test_char_format(self):
		"""c format converts int to character."""

		@javascript
		def to_char(n: int) -> str:
			return f"{n:c}"

		fn = to_char.transpile()
		code = emit(fn)
		assert code == "function to_char_1(n) {\nreturn `${String.fromCharCode(n)}`;\n}"

	def test_locale_number_format(self):
		"""n format uses locale-aware number formatting."""

		@javascript
		def locale_num(x: float) -> str:
			return f"{x:n}"

		fn = locale_num.transpile()
		code = emit(fn)
		assert code == "function locale_num_1(x) {\nreturn `${x.toLocaleString()}`;\n}"

	def test_thousand_separator_comma(self):
		"""Comma separator for thousands grouping."""

		@javascript
		def with_commas(n: int) -> str:
			return f"{n:,}"

		fn = with_commas.transpile()
		code = emit(fn)
		assert (
			code
			== 'function with_commas_1(n) {\nreturn `${n.toLocaleString("en-US")}`;\n}'
		)

	def test_thousand_separator_underscore(self):
		"""Underscore separator for thousands grouping."""

		@javascript
		def with_underscores(n: int) -> str:
			return f"{n:_}"

		fn = with_underscores.transpile()
		code = emit(fn)
		assert (
			code
			== 'function with_underscores_1(n) {\nreturn `${n.toLocaleString("en-US").replace(/,/g, "_")}`;\n}'
		)
