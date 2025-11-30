"""Tests for codegen: dependency graph traversal and output generation."""

from __future__ import annotations

import pytest
from pulse.javascript_v2.codegen import (
	CodegenOutput,
	collect_from_functions,
	collect_from_registries,
)
from pulse.javascript_v2.function import FUNCTION_CACHE, JsFunction
from pulse.javascript_v2.imports import IMPORT_REGISTRY, Import, clear_import_registry
from pulse.javascript_v2.nodes import JSNumber


@pytest.fixture(autouse=True)
def clear_registries() -> None:
	"""Clear all registries between tests."""
	FUNCTION_CACHE.clear()
	clear_import_registry()


# =============================================================================
# Module-level test fixtures
# =============================================================================

_MY_CONST = 42
_SHARED_LIST = [1, 2, 3]

# Create imports at module level to test registry
_import_react = Import.default("React", "react")
_import_useState = Import.named("useState", "react")


def _base_fn(x: int) -> int:
	return x * 2


def _mid_fn(x: int) -> int:
	return _base_fn(x) + 1


def _top_fn(x: int) -> int:
	return _mid_fn(x) + _MY_CONST


def _standalone(x: int) -> int:
	return x + _MY_CONST


def _fn_with_import() -> int:
	return _import_react  # pyright: ignore[reportReturnType]


def _fn_with_multiple_imports() -> tuple[int, int]:
	return _import_react, _import_useState  # pyright: ignore[reportReturnType]


def _fn_with_shared_const_1() -> int:
	return _SHARED_LIST[0]  # pyright: ignore[reportReturnType]


def _fn_with_shared_const_2() -> list[int]:
	return _SHARED_LIST


# Mutually recursive
def _ping(n: int) -> int:
	if n <= 0:
		return 0
	return _pong(n - 1)


def _pong(n: int) -> int:
	if n <= 0:
		return 1
	return _ping(n - 1)


# =============================================================================
# Tests
# =============================================================================


class TestImportRegistry:
	def test_imports_registered_via_js_import(self) -> None:
		"""Import objects created via js_import are registered in the global registry."""
		from pulse.javascript_v2.imports import js_import

		# Clear and create fresh
		IMPORT_REGISTRY.clear()

		@js_import("test", "./test.js")
		def test_fn() -> None: ...

		# The decorator returns an Import, not the function
		assert isinstance(test_fn, Import)
		assert test_fn in IMPORT_REGISTRY

	def test_module_level_imports_exist(self) -> None:
		"""Module-level imports should be accessible."""
		# Just verify the module-level imports exist and have correct properties
		assert _import_react.name == "React"
		assert _import_react.src == "react"
		assert _import_react.is_default
		assert _import_useState.name == "useState"
		assert not _import_useState.is_default


class TestTopologicalSort:
	def test_simple_dependency_chain(self) -> None:
		"""Functions are ordered so dependencies come first."""
		# top_fn -> mid_fn -> base_fn
		js_top = JsFunction(_top_fn)

		output = collect_from_functions([js_top])

		# Should have all 3 functions
		assert len(output.functions) == 3

		# Get order
		fn_names = [f.name for f in output.functions]

		# base_fn must come before mid_fn
		assert fn_names.index("_base_fn") < fn_names.index("_mid_fn")
		# mid_fn must come before top_fn
		assert fn_names.index("_mid_fn") < fn_names.index("_top_fn")

	def test_handles_cycles(self) -> None:
		"""Mutually recursive functions don't cause infinite loop."""
		js_ping = JsFunction(_ping)

		output = collect_from_functions([js_ping])

		# Should have both functions
		fn_names = [f.name for f in output.functions]
		assert "_ping" in fn_names
		assert "_pong" in fn_names


class TestImportMerging:
	def test_imports_from_same_source_merged(self) -> None:
		"""Multiple imports from same source are merged into one JSImport."""
		# Both imports are from "react"
		js_fn = JsFunction(_fn_with_multiple_imports)

		output = collect_from_functions([js_fn])

		# Should have one merged import
		assert len(output.imports) == 1
		assert output.imports[0].src == "react"
		assert output.imports[0].default == "React"
		assert "useState" in output.imports[0].named


class TestConstantDeduplication:
	def test_shared_constant_deduped(self) -> None:
		"""Same constant object is only emitted once."""
		js_fn1 = JsFunction(_fn_with_shared_const_1)
		js_fn2 = JsFunction(_fn_with_shared_const_2)

		output = collect_from_functions([js_fn1, js_fn2])

		# Should have only one constant definition for _SHARED_LIST
		list_consts = [c for c in output.constants if c.value_id == id(_SHARED_LIST)]
		assert len(list_consts) == 1


class TestFunctionRegistry:
	def test_registry_maps_qualified_name_to_function(self) -> None:
		"""Function registry maps qualified names to emitted names."""
		js_fn = JsFunction(_standalone)

		output = collect_from_functions([js_fn])

		# Should have entry in registry
		expected_key = f"{_standalone.__module__}.{_standalone.__qualname__}"
		assert expected_key in output.function_registry
		assert output.function_registry[expected_key] == "_standalone"


class TestCollectFromRegistries:
	def test_collects_all_registered(self) -> None:
		"""collect_from_registries gathers all registered functions."""
		# Create some functions (they auto-register)
		JsFunction(_base_fn)
		JsFunction(_standalone)

		output = collect_from_registries()

		# Should have both functions
		fn_names = {f.name for f in output.functions}
		assert "_base_fn" in fn_names
		assert "_standalone" in fn_names

	def test_includes_plain_imports(self) -> None:
		"""Plain imports not referenced by functions are included."""
		from pulse.javascript_v2.imports import js_import

		IMPORT_REGISTRY.clear()
		FUNCTION_CACHE.clear()

		# Create standalone import via js_import (registers in IMPORT_REGISTRY)
		@js_import("lodash", "lodash", is_default=True)
		def lodash_fn() -> None: ...

		# Create function that doesn't use it
		JsFunction(_base_fn)

		output = collect_from_registries()

		# Should include the standalone import
		import_srcs = {imp.src for imp in output.imports}
		assert "lodash" in import_srcs


class TestCodegenOutput:
	def test_output_structure(self) -> None:
		"""CodegenOutput has expected fields."""
		js_fn = JsFunction(_top_fn)
		output = collect_from_functions([js_fn])

		assert isinstance(output, CodegenOutput)
		assert isinstance(output.imports, list)
		assert isinstance(output.constants, list)
		assert isinstance(output.functions, list)
		assert isinstance(output.function_registry, dict)

	def test_constants_have_js_expr(self) -> None:
		"""Constants are converted to JSExpr with original names."""
		js_fn = JsFunction(_standalone)
		output = collect_from_functions([js_fn])

		# _MY_CONST should be in constants with its original name
		assert len(output.constants) == 1
		assert output.constants[0].name == "_MY_CONST"
		assert isinstance(output.constants[0].value, JSNumber)
