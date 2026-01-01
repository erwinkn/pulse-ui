"""
Tests for comparison operators: identity comparisons and membership tests.
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
# Identity Comparisons
# =============================================================================


class TestIdentityComparisons:
	"""Test is/is not transpilation."""

	def test_is_none(self):
		@javascript
		def is_null(x: Any) -> bool:
			return x is None

		fn = is_null.transpile()
		code = emit(fn)
		assert code == "function is_null_1(x) {\nreturn x == null;\n}"

	def test_is_not_none(self):
		@javascript
		def is_not_null(x: Any) -> bool:
			return x is not None

		fn = is_not_null.transpile()
		code = emit(fn)
		assert code == "function is_not_null_1(x) {\nreturn x != null;\n}"

	def test_is_comparison(self):
		@javascript
		def same(a: Any, b: Any) -> bool:
			return a is b

		fn = same.transpile()
		code = emit(fn)
		assert code == "function same_1(a, b) {\nreturn a === b;\n}"


# =============================================================================
# Membership Tests
# =============================================================================


class TestMembershipTests:
	"""Test in/not in transpilation."""

	def test_in_operator(self):
		@javascript
		def contains(items: list[Any] | set[Any] | dict[Any, Any], x: Any) -> bool:
			return x in items

		fn = contains.transpile()
		code = emit(fn)
		assert (
			code
			== 'function contains_1(items, x) {\nreturn Array.isArray(items) || typeof items === "string" ? items.includes(x) : items instanceof Set || items instanceof Map ? items.has(x) : x in items;\n}'
		)

	def test_not_in_operator(self):
		@javascript
		def not_contains(items: list[Any] | set[Any] | dict[Any, Any], x: Any) -> bool:
			return x not in items

		fn = not_contains.transpile()
		code = emit(fn)
		assert (
			code
			== 'function not_contains_1(items, x) {\nreturn !(Array.isArray(items) || typeof items === "string" ? items.includes(x) : items instanceof Set || items instanceof Map ? items.has(x) : x in items);\n}'
		)
