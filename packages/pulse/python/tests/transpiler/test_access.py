"""
Tests for access patterns: attribute access, subscript access, and function calls.
"""

# pyright: reportPrivateUsage=false

from typing import Any

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
# Function Calls
# =============================================================================


class TestFunctionCalls:
	"""Test function call transpilation."""

	def test_method_call(self):
		@javascript
		def get_upper(s: str) -> str:
			return s.upper()

		fn = get_upper.transpile()
		code = emit(fn)
		assert (
			code
			== 'function get_upper_1(s) {\nreturn typeof s === "string" ? s.toUpperCase() : s.upper();\n}'
		)

	def test_chained_method_call(self):
		@javascript
		def process(s: str) -> str:
			return s.strip().lower()

		fn = process.transpile()
		code = emit(fn)
		assert (
			code
			== 'function process_1(s) {\nreturn typeof (typeof s === "string" ? s.trim() : s.strip()) === "string" ? (typeof s === "string" ? s.trim() : s.strip()).toLowerCase() : (typeof s === "string" ? s.trim() : s.strip()).lower();\n}'
		)


# =============================================================================
# Attribute Access
# =============================================================================


class TestAttributeAccess:
	"""Test attribute access transpilation."""

	def test_simple_attribute(self):
		@javascript
		def get_prop(obj: Any) -> Any:
			return obj.prop

		fn = get_prop.transpile()
		code = emit(fn)
		assert code == "function get_prop_1(obj) {\nreturn obj.prop;\n}"

	def test_chained_attributes(self):
		@javascript
		def get_nested(obj: Any) -> Any:
			return obj.a.b.c

		fn = get_nested.transpile()
		code = emit(fn)
		assert code == "function get_nested_1(obj) {\nreturn obj.a.b.c;\n}"


# =============================================================================
# Subscript Access
# =============================================================================


class TestSubscriptAccess:
	"""Test subscript access transpilation."""

	def test_index_access(self):
		@javascript
		def get_first(arr: list[Any]) -> Any:
			return arr[0]

		fn = get_first.transpile()
		code = emit(fn)
		assert code == "function get_first_1(arr) {\nreturn arr[0];\n}"

	def test_negative_index(self):
		@javascript
		def get_last(arr: list[Any]) -> Any:
			return arr[-1]

		fn = get_last.transpile()
		code = emit(fn)
		assert code == "function get_last_1(arr) {\nreturn arr[-1];\n}"

	def test_slice_start(self):
		@javascript
		def get_rest(arr: list[Any]) -> list[Any]:
			return arr[1:]

		fn = get_rest.transpile()
		code = emit(fn)
		assert code == "function get_rest_1(arr) {\nreturn arr.slice(1);\n}"

	def test_slice_end(self):
		@javascript
		def get_first_three(arr: list[Any]) -> list[Any]:
			return arr[:3]

		fn = get_first_three.transpile()
		code = emit(fn)
		assert code == "function get_first_three_1(arr) {\nreturn arr.slice(0, 3);\n}"

	def test_slice_both(self):
		@javascript
		def get_middle(arr: list[Any]) -> list[Any]:
			return arr[1:3]

		fn = get_middle.transpile()
		code = emit(fn)
		assert code == "function get_middle_1(arr) {\nreturn arr.slice(1, 3);\n}"

	def test_slice_empty(self):
		@javascript
		def copy(arr: list[Any]) -> list[Any]:
			return arr[:]

		fn = copy.transpile()
		code = emit(fn)
		assert code == "function copy_1(arr) {\nreturn arr.slice();\n}"
