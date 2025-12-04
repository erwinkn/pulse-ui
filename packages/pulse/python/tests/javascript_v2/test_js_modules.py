"""Tests for pulse.js.* module integration in the transpiler."""

from __future__ import annotations

import pytest
from pulse.javascript_v2.constants import CONSTANTS_CACHE
from pulse.javascript_v2.function import FUNCTION_CACHE, javascript
from pulse.javascript_v2.imports import clear_import_registry
from pulse.javascript_v2.types import JsModuleRef
from pulse.js._core import JsValue


# Clear caches between tests
@pytest.fixture(autouse=True)
def clear_caches() -> None:
	FUNCTION_CACHE.clear()
	CONSTANTS_CACHE.clear()
	clear_import_registry()


class TestJsModuleDetection:
	"""Test dependency detection for pulse.js.* modules."""

	def test_detects_js_module_import(self) -> None:
		"""Test: import pulse.js.math as Math"""
		import pulse.js.math as Math

		@javascript
		def fn(x: float) -> float:
			return Math.floor(x)

		assert "Math" in fn.deps
		dep = fn.deps["Math"]
		assert isinstance(dep, JsModuleRef)
		assert dep.config.name == "Math"
		assert dep.config.is_builtin

	def test_detects_js_value_function_import(self) -> None:
		"""Test: from pulse.js.math import floor"""
		from pulse.js.math import floor

		@javascript
		def fn(x: float) -> float:
			return floor(x)

		assert "floor" in fn.deps
		dep = fn.deps["floor"]
		assert isinstance(dep, JsValue)

	def test_detects_js_value_constant_import(self) -> None:
		"""Test: from pulse.js.math import PI"""
		from pulse.js.math import PI

		@javascript
		def fn() -> float:
			return PI

		assert "PI" in fn.deps
		dep = fn.deps["PI"]
		assert isinstance(dep, JsValue)

	def test_detects_multiple_js_value_imports(self) -> None:
		"""Test: from pulse.js.math import floor, PI, sin"""
		from pulse.js.math import PI, floor, sin

		@javascript
		def fn(x: float) -> float:
			return floor(sin(x) * PI)

		assert "floor" in fn.deps
		assert "sin" in fn.deps
		assert "PI" in fn.deps
		for name in ["floor", "sin", "PI"]:
			assert isinstance(fn.deps[name], JsValue)


class TestJsModuleTranspilation:
	"""Test transpilation of pulse.js.* module usage."""

	def test_transpiles_module_method_call(self) -> None:
		"""Test: Math.floor(x) -> Math.floor(x)"""
		import pulse.js.math as Math

		@javascript
		def fn(x: float) -> float:
			return Math.floor(x)

		js = fn.transpile()
		assert "Math.floor(x)" in js

	def test_transpiles_module_property_access(self) -> None:
		"""Test: Math.PI -> Math.PI"""
		import pulse.js.math as Math

		@javascript
		def fn() -> float:
			return Math.PI

		js = fn.transpile()
		assert "Math.PI" in js

	def test_transpiles_imported_function(self) -> None:
		"""Test: floor(x) -> Math.floor(x)"""
		from pulse.js.math import floor

		@javascript
		def fn(x: float) -> float:
			return floor(x)

		js = fn.transpile()
		assert "Math.floor(x)" in js

	def test_transpiles_imported_constant(self) -> None:
		"""Test: PI -> Math.PI"""
		from pulse.js.math import PI

		@javascript
		def fn() -> float:
			return PI * 2

		js = fn.transpile()
		assert "Math.PI" in js

	def test_transpiles_complex_expression(self) -> None:
		"""Test: floor(sin(x) * PI) -> Math.floor(Math.sin(x) * Math.PI)"""
		from pulse.js.math import PI, floor, sin

		@javascript
		def fn(x: float) -> float:
			return floor(sin(x) * PI)

		js = fn.transpile()
		assert "Math.floor" in js
		assert "Math.sin" in js
		assert "Math.PI" in js

	def test_transpiles_multiple_calls(self) -> None:
		"""Test multiple function calls in sequence."""
		from pulse.js.math import abs, max, min

		@javascript
		def fn(a: float, b: float) -> float:
			return max(abs(a), min(b, 0))

		js = fn.transpile()
		assert "Math.max" in js
		assert "Math.abs" in js
		assert "Math.min" in js

	def test_mixed_module_and_value_imports(self) -> None:
		"""Test using both module import and value imports."""
		import pulse.js.math as Math
		from pulse.js.math import PI

		@javascript
		def fn(x: float) -> float:
			return Math.floor(x * PI)

		js = fn.transpile()
		assert "Math.floor" in js
		assert "Math.PI" in js


class TestJsValueRuntimeBehavior:
	"""Test that JsValue raises appropriately at runtime."""

	def test_jsvalue_raises_on_call(self) -> None:
		"""JsValue should raise when called at runtime."""
		from pulse.js.math import floor

		with pytest.raises(Exception, match="cannot be called at runtime"):
			floor(3.5)

	def test_jsvalue_raises_on_property_access(self) -> None:
		"""JsValue should raise on attribute access."""
		from pulse.js.math import PI

		with pytest.raises(Exception, match="cannot be accessed at runtime"):
			_ = PI.something  # pyright: ignore[reportAttributeAccessIssue]

	def test_jsvalue_raises_on_arithmetic(self) -> None:
		"""JsValue should raise on arithmetic operations."""
		from pulse.js.math import PI

		with pytest.raises(Exception, match="cannot be used in expression at runtime"):
			_ = PI + 1

	def test_jsvalue_raises_on_comparison(self) -> None:
		"""JsValue should raise on comparison operations."""
		from pulse.js.math import PI

		with pytest.raises(Exception, match="cannot be compared at runtime"):
			_ = PI == 3.14


class TestJsModuleConfig:
	"""Test JsModuleConfig functionality."""

	def test_builtin_module_config(self) -> None:
		"""Builtin modules have no src."""
		import pulse.js.math

		config = pulse.js.math.__js__
		assert config.name == "Math"
		assert config.is_builtin
		assert config.src is None

	def test_builtin_to_import_returns_none(self) -> None:
		"""Builtin modules don't need imports."""
		import pulse.js.math

		config = pulse.js.math.__js__
		assert config.to_import() is None


class TestJsNumberModule:
	"""Test the pulse.js.number module."""

	def test_number_module_config(self) -> None:
		"""Number module should be configured as builtin."""
		import pulse.js.number

		config = pulse.js.number.__js__
		assert config.name == "Number"
		assert config.is_builtin
		assert config.src is None

	def test_number_module_import(self) -> None:
		"""Test: import pulse.js.number as Number"""
		import pulse.js.number as Number

		@javascript
		def fn(x: float) -> bool:
			return Number.isFinite(x)

		assert "Number" in fn.deps
		dep = fn.deps["Number"]
		assert isinstance(dep, JsModuleRef)
		assert dep.config.name == "Number"

	def test_number_function_import(self) -> None:
		"""Test: from pulse.js.number import isFinite"""
		from pulse.js.number import isFinite

		@javascript
		def fn(x: float) -> bool:
			return isFinite(x)

		assert "isFinite" in fn.deps
		dep = fn.deps["isFinite"]
		assert isinstance(dep, JsValue)

	def test_number_constant_import(self) -> None:
		"""Test: from pulse.js.number import EPSILON"""
		from pulse.js.number import EPSILON

		@javascript
		def fn() -> float:
			return EPSILON

		assert "EPSILON" in fn.deps
		dep = fn.deps["EPSILON"]
		assert isinstance(dep, JsValue)

	def test_transpiles_number_method_call(self) -> None:
		"""Test: Number.isFinite(x) -> Number.isFinite(x)"""
		import pulse.js.number as Number

		@javascript
		def fn(x: float) -> bool:
			return Number.isFinite(x)

		js = fn.transpile()
		assert "Number.isFinite(x)" in js

	def test_transpiles_imported_number_function(self) -> None:
		"""Test: isNaN(x) -> Number.isNaN(x)"""
		from pulse.js.number import isNaN

		@javascript
		def fn(x: float) -> bool:
			return isNaN(x)

		js = fn.transpile()
		assert "Number.isNaN(x)" in js

	def test_transpiles_number_constant(self) -> None:
		"""Test: MAX_SAFE_INTEGER -> Number.MAX_SAFE_INTEGER"""
		from pulse.js.number import MAX_SAFE_INTEGER

		@javascript
		def fn() -> int:
			return MAX_SAFE_INTEGER

		js = fn.transpile()
		assert "Number.MAX_SAFE_INTEGER" in js

	def test_combined_math_and_number(self) -> None:
		"""Test using both Math and Number modules together."""
		from pulse.js.math import floor
		from pulse.js.number import isFinite

		@javascript
		def fn(x: float) -> bool:
			if isFinite(x):
				return floor(x) > 0
			return False

		js = fn.transpile()
		assert "Number.isFinite(x)" in js
		assert "Math.floor(x)" in js
