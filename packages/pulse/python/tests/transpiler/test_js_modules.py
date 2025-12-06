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


class TestJsModuleImportPattern:
	"""Test the pattern: from pulse.js import Module -> JSIdentifier."""

	def test_module_import_resolves_to_identifier(self) -> None:
		"""Module imports resolve to JSIdentifier."""
		from pulse.js import Math

		@javascript
		def fn(x: float) -> float:
			return Math.floor(x)

		assert "Math" in fn.deps
		dep = fn.deps["Math"]
		assert isinstance(dep, JSIdentifier)
		assert dep.name == "Math"


class TestJsModuleUsagePatterns:
	"""Test transpilation patterns for module usage."""

	def test_method_call_pattern(self) -> None:
		"""Module.method() transpiles correctly."""
		from pulse.js import Math

		@javascript
		def fn(x: float) -> float:
			return Math.floor(x)

		js = fn.transpile()
		assert "Math.floor(x)" in js

	def test_property_access_pattern(self) -> None:
		"""Module.property transpiles correctly."""
		from pulse.js import Math

		@javascript
		def fn() -> float:
			return Math.PI

		js = fn.transpile()
		assert "Math.PI" in js

	def test_multiple_modules_pattern(self) -> None:
		"""Multiple modules can be used together."""
		from pulse.js import Math, Number

		@javascript
		def fn(x: float) -> bool:
			if Number.isFinite(x):
				return Math.floor(x) > 0
			return False

		js = fn.transpile()
		assert "Number.isFinite(x)" in js
		assert "Math.floor(x)" in js


class TestJsModuleConfig:
	"""Test module configuration patterns."""

	def test_builtin_module_config(self) -> None:
		"""Builtin modules have correct configuration."""
		import pulse.js.math
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.math]
		assert config.name == "Math"
		assert config.is_builtin
		assert config.src is None
		js_expr = config.to_js_expr()
		assert isinstance(js_expr, JSIdentifier)
		assert js_expr.name == "Math"


class TestJsConstructorPattern:
	"""Test constructor pattern: from pulse.js import Constructor -> JSConstructor."""

	def test_constructor_detection(self) -> None:
		"""Constructors are detected in module config."""
		import pulse.js.set
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.set]
		assert "Set" in config.constructors

	def test_constructor_import_pattern(self) -> None:
		"""Constructor imports resolve to JSConstructor."""
		from pulse.js import Set

		@javascript
		def fn() -> object:
			return Set([1, 2, 3])  # type: ignore[misc]

		assert "Set" in fn.deps
		dep = fn.deps["Set"]
		assert isinstance(dep, JSConstructor)
		assert isinstance(dep.ctor, JSIdentifier)
		assert dep.ctor.name == "Set"

	def test_constructor_transpilation_pattern(self) -> None:
		"""Constructors transpile to 'new Constructor()' pattern."""
		from pulse.js import Set

		@javascript
		def fn() -> object:
			return Set([1, 2, 3])

		js = fn.transpile()
		assert "new Set([1, 2, 3])" in js
		assert "Set.Set" not in js


class TestJsModuleImportFiltering:
	"""Test that imported names are filtered from module exports."""

	def test_imported_names_filtered(self) -> None:
		"""Imported names (Protocol, Generic, etc.) are not in constructors."""
		import pulse.js.set
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.set]
		# Imported names should not be in constructors
		assert "Protocol" not in config.constructors
		assert "Generic" not in config.constructors
		assert "TypeVar" not in config.constructors
		assert "_T" not in config.constructors
		# Only defined names should be in constructors
		assert "Set" in config.constructors

	def test_imported_names_not_accessible(self) -> None:
		"""Imported names raise AttributeError when accessed."""
		import pulse.js.set

		with pytest.raises(AttributeError):
			_ = pulse.js.set._Generic  # pyright: ignore[reportPrivateLocalImportUsage, reportPrivateUsage]

		# Defined names should be accessible
		set_class = pulse.js.set.Set
		assert isinstance(set_class, JSConstructor)

	def test_namespace_module_functions_not_constructors(self) -> None:
		"""Namespace modules (like console) have functions but no constructors."""
		import pulse.js.console
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.console]
		assert len(config.constructors) == 0

		# Functions should be accessible
		log = pulse.js.console.log
		assert isinstance(log, JSMember)
		assert log.prop == "log"


class TestGlobalScopeModulePattern:
	"""Test global scope module pattern (Set, Map, Date)."""

	def test_global_scope_module_disallows_module_import(self) -> None:
		"""Global scope modules disallow module imports."""
		import pulse.js.set
		from pulse.transpiler.errors import JSCompilationError
		from pulse.transpiler.js_module import JS_MODULES

		config = JS_MODULES[pulse.js.set]
		assert config.global_scope

		with pytest.raises(JSCompilationError, match="Cannot import module"):
			config.to_js_expr()

	def test_global_scope_constructor_pattern(self) -> None:
		"""Global scope constructors transpile as direct identifiers."""
		from pulse.js import Map, Set

		@javascript
		def fn() -> object:
			return Set([1, 2, 3])  # type: ignore[misc]

		js = fn.transpile()
		# Should be "new Set([1, 2, 3])" not "new Set.Set([1, 2, 3])"
		assert "new Set([1, 2, 3])" in js
		assert "Set.Set" not in js

		@javascript
		def fn2() -> object:
			return Map([("a", 1)])  # type: ignore[misc]

		js2 = fn2.transpile()
		assert 'new Map([["a", 1]])' in js2
		assert "Map.Map" not in js2
