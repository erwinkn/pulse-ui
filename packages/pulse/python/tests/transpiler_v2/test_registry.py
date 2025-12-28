"""
Tests for registry functionality: function auto-id, Expr.as_.
"""

# pyright: reportPrivateUsage=false

from inspect import Signature

import pytest
from pulse.transpiler_v2 import (
	clear_function_cache,
	clear_import_registry,
	javascript,
)
from pulse.transpiler_v2.function import JsFunction, JsxFunction
from pulse.transpiler_v2.imports import Import
from pulse.transpiler_v2.nodes import (
	Identifier,
	Jsx,
)
from pulse.transpiler_v2.nodes import (
	Signature as SignatureNode,
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

		ident = Identifier("foo")
		result = ident.as_(list[str])
		assert result is ident

	def test_as_with_jsx(self):
		"""as_() on Jsx returns a Jsx."""

		button = Import("Button", "@mantine/core")
		jsx = Jsx(button)
		result = jsx.as_(type[str])
		assert result is jsx

	def test_as_returns_signature_node_for_callable(self):
		"""as_() returns Signature node when passed a user-defined callable."""

		def my_callable(x: int, y: str) -> str:
			return f"{x}:{y}"

		ident = Identifier("foo")
		result = ident.as_(my_callable)

		assert isinstance(result, SignatureNode)
		assert result.expr is ident
		assert isinstance(result.sig, Signature)
		assert list(result.sig.parameters.keys()) == ["x", "y"]
		assert result.sig.return_annotation is str

	def test_as_emits_wrapped_expression(self):
		"""Signature node emits wrapped expression."""

		def my_callable(x: int) -> str:
			return str(x)

		ident = Identifier("bar")
		result = ident.as_(my_callable)

		assert isinstance(result, SignatureNode)
		from pulse.transpiler_v2 import emit

		code = emit(result)
		assert code == "bar"

	def test_as_handles_builtin_without_signature(self):
		"""as_() gracefully handles built-ins that aren't functions."""

		# Built-in callables like len are not functions - should not wrap
		ident = Identifier("baz")
		result = ident.as_(len)

		assert result is ident

	def test_as_with_non_callable_type(self):
		"""as_() works fine with non-callable types (returns self)."""

		ident = Identifier("noncallable")
		result = ident.as_(str)

		assert result is ident
		assert not isinstance(result, SignatureNode)

	def test_as_signature_delegates_transpile_call(self):
		"""Signature node delegates transpile_call to wrapped expression."""

		def my_callable(x: int, y: str) -> str:
			return f"{x}:{y}"

		ident = Identifier("test")
		result = ident.as_(my_callable)

		assert isinstance(result, SignatureNode)
