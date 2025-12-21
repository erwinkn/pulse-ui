"""
Tests for registry functionality: function auto-id, Expr.as_.
"""

# pyright: reportPrivateUsage=false

import pytest
from pulse.transpiler_v2 import (
	clear_function_cache,
	clear_import_registry,
	javascript,
)
from pulse.transpiler_v2.function import JsFunction, JsxFunction
from pulse.transpiler_v2.imports import Import
from pulse.transpiler_v2.nodes import (
	Jsx,
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
# JsFunction Auto-ID
# =============================================================================


class TestFunctionAutoId:
	"""Test auto-created ID on JsFunction (including JSX-wrapped functions)."""

	def test_jsfunction_has_id(self):
		"""JsFunction has an .id attribute."""

		@javascript
		def helper(x: int) -> int:
			return x + 1

		assert isinstance(helper, JsFunction)
		assert hasattr(helper, "id")
		assert isinstance(helper.id, str)

	def test_jsx_wrapped_jsfunction_has_id(self):
		"""@javascript(jsx=True) returns JsxFunction where underlying JsFunction has id."""

		@javascript(jsx=True)
		def MyComponent() -> str:
			return "hi"

		assert isinstance(MyComponent, JsxFunction)
		assert isinstance(MyComponent.js_fn, JsFunction)
		assert isinstance(MyComponent.js_fn.id, str)

	def test_function_id_is_unique(self):
		"""Each function gets a unique id."""

		@javascript
		def fn_a() -> int:
			return 1

		@javascript
		def fn_b() -> int:
			return 2

		assert fn_a.id != fn_b.id


# =============================================================================
# Expr.as_() Type Casting
# =============================================================================


class TestExprAs:
	"""Test Expr.as_() type casting helper."""

	def test_as_returns_self(self):
		"""as_() returns self for type casting."""

		button = Import("Button", "@mantine/core")
		# Cast to a custom type - result is same object
		result = button.as_(type[str])
		assert result is button

	def test_as_with_identifier(self):
		"""as_() works on Identifier."""
		from pulse.transpiler_v2.nodes import Identifier

		ident = Identifier("foo")
		result = ident.as_(list[str])
		assert result is ident

	def test_as_with_jsx(self):
		"""as_() on Jsx returns the Jsx."""

		button = Import("Button", "@mantine/core")
		jsx = Jsx(button)
		result = jsx.as_(type[str])
		assert result is jsx
