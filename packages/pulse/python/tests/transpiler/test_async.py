"""
Tests for async function transpilation.
"""

# pyright: reportPrivateUsage=false

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
# Async Functions
# =============================================================================


class TestAsyncFunctions:
	"""Test async function transpilation."""

	def test_async_arrow(self):
		@javascript
		async def fetch_data(url: str) -> str:
			# Async functions without await are transpiled as regular functions
			return url

		fn = fetch_data.transpile()
		code = emit(fn)
		assert code == "function fetch_data_1(url) {\nreturn url;\n}"

	def test_async_multi_statement(self):
		@javascript
		async def process(x: int) -> int:
			result = x * 2
			return result

		fn = process.transpile()
		code = emit(fn)
		assert (
			code
			== "async function process_1(x) {\nlet result = x * 2;\nreturn result;\n}"
		)
