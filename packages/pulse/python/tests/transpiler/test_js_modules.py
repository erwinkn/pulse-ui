"""Tests for pulse.js.* module integration in the transpiler."""

from __future__ import annotations

import pytest
from pulse.transpiler.constants import CONSTANTS_CACHE
from pulse.transpiler.function import FUNCTION_CACHE, javascript
from pulse.transpiler.imports import clear_import_registry
from pulse.transpiler.js_module import CONSTRUCTORS, JSConstructor
from pulse.transpiler.nodes import JSIdentifier, JSMember


# Clear caches between tests
@pytest.fixture(autouse=True)
def clear_caches() -> None:
	FUNCTION_CACHE.clear()
	CONSTANTS_CACHE.clear()
	CONSTRUCTORS.clear()
	clear_import_registry()


class TestJsModuleDetection:
	"""Test dependency detection for pulse.js.* modules."""

	def test_detects_js_module_import(self) -> None:
		"""Test: import pulse.js.math as Math -> JSIdentifier("Math")"""
		import pulse.js.math as Math

		@javascript
		def fn(x: float) -> float:
			return Math.floor(x)

		assert "Math" in fn.deps
		dep = fn.deps["Math"]
		# Builtin modules resolve to JSIdentifier with the module name
		assert isinstance(dep, JSIdentifier)
		assert dep.name == "Math"

	def test_detects_js_value_function_import(self) -> None:
		"""Test: from pulse.js.math import floor -> JSMember(JSIdentifier(Math), floor)"""
		from pulse.js.math import floor

		@javascript
		def fn(x: float) -> float:
			return floor(x)

		assert "floor" in fn.deps
		dep = fn.deps["floor"]
		# JSMember is now used directly
		assert isinstance(dep, JSMember)
		assert dep.prop == "floor"
		assert isinstance(dep.obj, JSIdentifier)
		assert dep.obj.name == "Math"

	def test_detects_js_value_constant_import(self) -> None:
		"""Test: from pulse.js.math import PI -> JSMember(JSIdentifier(Math), PI)"""
		from pulse.js.math import PI

		@javascript
		def fn() -> float:
			return PI

		assert "PI" in fn.deps
		dep = fn.deps["PI"]
		assert isinstance(dep, JSMember)
		assert dep.prop == "PI"
		assert isinstance(dep.obj, JSIdentifier)
		assert dep.obj.name == "Math"

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
			assert isinstance(fn.deps[name], JSMember)


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


class TestJsModuleConfig:
	"""Test JsModule functionality via JS_MODULES registry."""

	def test_builtin_module_config(self) -> None:
		"""Builtin modules have no src."""
		import pulse.js.math
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.math]
		assert config.name == "Math"
		assert config.is_builtin
		assert config.src is None

	def test_builtin_to_js_expr_returns_identifier(self) -> None:
		"""Builtin modules return JSIdentifier."""
		import pulse.js.math
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.math]
		js_expr = config.to_js_expr()
		assert isinstance(js_expr, JSIdentifier)
		assert js_expr.name == "Math"


class TestJsNumberModule:
	"""Test the pulse.js.number module."""

	def test_number_module_config(self) -> None:
		"""Number module should be configured as builtin."""
		import pulse.js.number
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.number]
		assert config.name == "Number"
		assert config.is_builtin
		assert config.src is None

	def test_number_module_import(self) -> None:
		"""Test: import pulse.js.number as Number -> JSIdentifier("Number")"""
		import pulse.js.number as Number

		@javascript
		def fn(x: float) -> bool:
			return Number.isFinite(x)

		assert "Number" in fn.deps
		dep = fn.deps["Number"]
		assert isinstance(dep, JSIdentifier)
		assert dep.name == "Number"

	def test_number_function_import(self) -> None:
		"""Test: from pulse.js.number import isFinite -> JSMember(JSIdentifier(Number), isFinite)"""
		from pulse.js.number import isFinite

		@javascript
		def fn(x: float) -> bool:
			return isFinite(x)

		assert "isFinite" in fn.deps
		dep = fn.deps["isFinite"]
		assert isinstance(dep, JSMember)
		assert dep.prop == "isFinite"
		assert isinstance(dep.obj, JSIdentifier)
		assert dep.obj.name == "Number"

	def test_number_constant_import(self) -> None:
		"""Test: from pulse.js.number import EPSILON -> JSMember(JSIdentifier(Number), EPSILON)"""
		from pulse.js.number import EPSILON

		@javascript
		def fn() -> float:
			return EPSILON

		assert "EPSILON" in fn.deps
		dep = fn.deps["EPSILON"]
		assert isinstance(dep, JSMember)
		assert dep.prop == "EPSILON"
		assert isinstance(dep.obj, JSIdentifier)
		assert dep.obj.name == "Number"

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


class TestJsModuleConstructorDetection:
	"""Test constructor detection for classes and @constructor-decorated functions."""

	def test_set_class_is_detected_as_constructor(self) -> None:
		"""Test that Set class is detected as a constructor."""
		import pulse.js.set
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.set]
		assert "Set" in config.constructors

	def test_set_class_returns_jsconstructor(self) -> None:
		"""Test that accessing Set returns JSConstructor wrapper."""
		from pulse.js.set import Set

		@javascript
		def fn() -> object:
			return Set()  # type: ignore[misc]

		assert "Set" in fn.deps
		dep = fn.deps["Set"]
		assert isinstance(dep, JSConstructor)
		assert isinstance(dep.ctor, JSIdentifier)
		assert dep.ctor.name == "Set"

	def test_set_class_transpiles_to_new(self) -> None:
		"""Test that Set() transpiles to new Set()."""
		from pulse.js.set import Set

		@javascript
		def fn() -> object:
			return Set()  # type: ignore[misc]

		js = fn.transpile()
		assert "new Set()" in js

	def test_set_class_with_args_transpiles_to_new(self) -> None:
		"""Test that Set([1, 2, 3]) transpiles to new Set([1, 2, 3])."""
		from pulse.js.set import Set

		@javascript
		def fn() -> object:
			return Set([1, 2, 3])

		js = fn.transpile()
		assert "new Set([1, 2, 3])" in js

	def test_map_function_with_constructor_decorator(self) -> None:
		"""Test that @constructor-decorated functions still work."""
		import pulse.js.map
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.map]
		assert "Map" in config.constructors

	def test_map_function_returns_jsconstructor(self) -> None:
		"""Test that accessing Map returns JSConstructor wrapper."""
		from pulse.js.map import Map

		@javascript
		def fn() -> object:
			return Map()

		assert "Map" in fn.deps
		dep = fn.deps["Map"]
		assert isinstance(dep, JSConstructor)
		assert isinstance(dep.ctor, JSIdentifier)
		assert dep.ctor.name == "Map"

	def test_map_function_transpiles_to_new(self) -> None:
		"""Test that Map() transpiles to new Map()."""
		from pulse.js.map import Map

		@javascript
		def fn() -> object:
			return Map([("a", 1)])

		js = fn.transpile()
		assert 'new Map([["a", 1]])' in js


class TestJsModuleImportFiltering:
	"""Test that imported names are filtered out from module exports."""

	def test_imported_classes_not_in_constructors(self) -> None:
		"""Test that imported classes (like Protocol, Generic) are not in constructors."""
		import pulse.js.set
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.set]
		# Protocol, Generic, TypeVar, Iterable are imported, should not be in constructors
		assert "Protocol" not in config.constructors
		assert "Generic" not in config.constructors
		assert "TypeVar" not in config.constructors
		assert "Iterable" not in config.constructors
		# Only Set (defined in module) should be in constructors
		assert "Set" in config.constructors

	def test_imported_functions_not_in_constructors(self) -> None:
		"""Test that imported functions are not in constructors."""
		import pulse.js.map
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.map]
		# Protocol is imported, should not be in constructors
		assert "Protocol" not in config.constructors
		# MapProtocol is defined in module, so it's in constructors
		# Map is defined in module with @constructor, so it's in constructors
		assert "Map" in config.constructors

	def test_imported_names_not_accessible_via_getattr(self) -> None:
		"""Test that imported names raise AttributeError when accessed."""
		import pulse.js.set

		# Imported names should not be accessible
		with pytest.raises(AttributeError):
			_ = pulse.js.set.Protocol  # type: ignore[attr-defined, unused-assignment]
		with pytest.raises(AttributeError):
			_ = pulse.js.set.Generic  # type: ignore[attr-defined, unused-assignment]
		with pytest.raises(AttributeError):
			_ = pulse.js.set.TypeVar  # type: ignore[attr-defined, unused-assignment]

		# Defined names should be accessible
		set_class = pulse.js.set.Set
		assert isinstance(set_class, JSConstructor)

	def test_underscore_prefixed_names_filtered(self) -> None:
		"""Test that names starting with underscore are filtered out."""
		import pulse.js.set
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.set]
		# _T (TypeVar) should not be in constructors
		assert "_T" not in config.constructors

	def test_console_module_functions_not_constructors(self) -> None:
		"""Test that regular functions in console module are not constructors."""
		import pulse.js.console
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.console]
		# Console module has no constructors
		assert len(config.constructors) == 0

	def test_console_module_functions_accessible(self) -> None:
		"""Test that console module functions are accessible but not constructors."""
		import pulse.js.console

		# Functions should be accessible
		log = pulse.js.console.log
		assert isinstance(log, JSMember)
		assert log.prop == "log"

		# But not as constructors
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.console]
		assert "log" not in config.constructors


class TestGlobalScopeModules:
	"""Test global scope module behavior (e.g., Set, Map, Date)."""

	def test_global_scope_module_disallows_module_import(self) -> None:
		"""Test that global scope modules disallow module imports."""
		import pulse.js.set
		from pulse.transpiler.errors import JSCompilationError
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.set]
		assert config.global_scope

		# Module import should raise error
		with pytest.raises(JSCompilationError, match="Cannot import module"):
			config.to_js_expr()

	def test_global_scope_module_allows_value_import(self) -> None:
		"""Test that global scope modules allow value imports."""
		from pulse.js.set import Set

		@javascript
		def fn() -> object:
			return Set()  # type: ignore[misc]

		assert "Set" in fn.deps
		dep = fn.deps["Set"]
		# Should be JSConstructor wrapping JSIdentifier (not JSMember)
		assert isinstance(dep, JSConstructor)
		assert isinstance(dep.ctor, JSIdentifier)
		assert dep.ctor.name == "Set"

	def test_global_scope_module_transpiles_as_identifier(self) -> None:
		"""Test that global scope module values transpile as direct identifiers."""
		from pulse.js.set import Set

		@javascript
		def fn() -> object:
			return Set([1, 2, 3])

		js = fn.transpile()
		# Should be "new Set([1, 2, 3])" not "new Set.Set([1, 2, 3])"
		assert "new Set([1, 2, 3])" in js
		assert "Set.Set" not in js

	def test_global_scope_map_module(self) -> None:
		"""Test Map module with global scope."""
		from pulse.js.map import Map

		@javascript
		def fn() -> object:
			return Map([("a", 1)])

		js = fn.transpile()
		assert 'new Map([["a", 1]])' in js
		assert "Map.Map" not in js

	def test_global_scope_date_module(self) -> None:
		"""Test Date module with global scope."""
		from pulse.js.date import Date

		@javascript
		def fn() -> object:
			return Date()

		js = fn.transpile()
		assert "new Date()" in js
		assert "Date.Date" not in js
