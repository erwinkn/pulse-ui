"""
Tests for registry functionality: function auto-ref, clear_ref_registry, Expr.as_.
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
	Ref,
	clear_ref_registry,
	registered_refs,
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
# JsFunction Auto-Ref
# =============================================================================


class TestFunctionAutoRef:
	"""Test auto-created Ref on JsFunction (including JSX-wrapped functions)."""

	def test_jsfunction_has_ref(self):
		"""JsFunction has a .registry_ref attribute."""

		@javascript
		def helper(x: int) -> int:
			return x + 1

		assert isinstance(helper, JsFunction)
		assert hasattr(helper, "registry_ref")
		assert isinstance(helper.registry_ref, Ref)
		assert helper.registry_ref.expr is helper

	def test_jsx_wrapped_jsfunction_has_ref(self):
		"""@javascript(jsx=True) returns JsxFunction where underlying JsFunction has ref."""

		@javascript(jsx=True)
		def MyComponent() -> str:
			return "hi"

		assert isinstance(MyComponent, JsxFunction)
		assert isinstance(MyComponent.js_fn, JsFunction)
		assert isinstance(MyComponent.js_fn.registry_ref, Ref)
		assert MyComponent.js_fn.registry_ref.expr is MyComponent.js_fn

	def test_function_ref_in_registry(self):
		"""Function refs are registered in the ref registry."""

		@javascript
		def fn1() -> int:
			return 1

		@javascript(jsx=True)
		def Comp1() -> str:
			return "c"

		refs = registered_refs()
		assert fn1.registry_ref in refs
		assert Comp1.js_fn.registry_ref in refs

	def test_function_ref_key_is_unique(self):
		"""Each function gets a unique ref key."""

		@javascript
		def fn_a() -> int:
			return 1

		@javascript
		def fn_b() -> int:
			return 2

		assert fn_a.registry_ref.key != fn_b.registry_ref.key


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

	def test_as_with_ref(self):
		"""as_() on Ref returns the Ref."""

		button = Import("Button", "@mantine/core")
		ref = Ref(Jsx(button))
		result = ref.as_(type[str])
		assert result is ref


# =============================================================================
# clear_ref_registry Behavior
# =============================================================================


class TestClearRefRegistry:
	"""Test clear_ref_registry behavior."""

	def test_clear_ref_registry_empties_registry(self):
		"""clear_ref_registry() clears all refs."""

		# Create some refs
		Ref(Jsx(Import("A", "@a")))
		Ref(Jsx(Import("B", "@b")))

		assert len(registered_refs()) >= 2

		clear_ref_registry()

		assert len(registered_refs()) == 0

	def test_clear_ref_registry_resets_counter(self):
		"""clear_ref_registry() resets the key counter."""

		# Create refs to increment counter
		ref1 = Ref(Jsx(Import("A", "@a")))
		_ref2 = Ref(Jsx(Import("B", "@b")))

		# Keys should be incrementing
		first_key = ref1.key

		clear_ref_registry()

		# New ref should start from beginning again
		ref3 = Ref(Jsx(Import("C", "@c")))
		assert ref3.key == first_key  # Counter reset
