"""
Tests for error handling in transpilation.
"""

# pyright: reportPrivateUsage=false

from typing import Any

import pytest
from pulse.transpiler import (
	TranspileError,
	clear_function_cache,
	clear_import_registry,
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
# Error Cases
# =============================================================================


class TestErrors:
	"""Test error handling."""

	def test_unsupported_slice_step(self):
		@javascript
		def every_other(arr: list[Any]) -> list[Any]:
			return arr[::2]

		with pytest.raises(TranspileError, match="Slice steps"):
			every_other.transpile()

	def test_multiple_assignment_targets(self):
		@javascript
		def multi(x: Any) -> Any:
			a = b = x  # noqa: F841  # pyright: ignore[reportUnusedVariable]
			return a

		with pytest.raises(TranspileError, match="Multiple assignment"):
			multi.transpile()


# =============================================================================
# Dependencies
# =============================================================================


class TestDependencies:
	"""Test dependency substitution with manual dependency injection."""

	def test_unbound_name_raises(self):
		@javascript
		def use_unknown() -> Any:
			return unknown_var  # noqa: F821  # pyright: ignore[reportUndefinedVariable]

		with pytest.raises(TranspileError, match="Unbound name"):
			use_unknown.transpile()
