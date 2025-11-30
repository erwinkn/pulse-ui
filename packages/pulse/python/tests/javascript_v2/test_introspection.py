"""Tests for the introspection utilities."""

from __future__ import annotations

import math
from math import log

import pytest
from pulse.javascript_v2.introspection import (
	get_code_names,
	get_function_refs,
	validate_no_nonlocals,
)


class TestGetCodeNames:
	def test_simple_function_no_refs(self) -> None:
		def fn(x: int) -> int:
			return x + 1

		names = get_code_names(fn)
		# Type annotations are evaluated lazily in Python 3.12+, so no names
		assert names == set()

	def test_global_reference(self) -> None:
		# math is a module-level global, so it shows up
		def fn() -> float:
			return math.pi

		names = get_code_names(fn)
		assert "math" in names

	def test_builtin_reference(self) -> None:
		def fn(items: list[int]) -> int:
			return len(items)

		names = get_code_names(fn)
		assert "len" in names

	def test_module_attribute_access(self) -> None:
		def fn() -> float:
			return math.pi * 2

		names = get_code_names(fn)
		assert "math" in names
		assert "pi" in names  # attribute access shows up in co_names

	def test_nested_function_globals_captured(self) -> None:
		"""The key test: globals in nested functions must be captured."""

		def fn() -> list[float]:
			data = [1, 2, 3]

			def transform(x: int) -> float:
				return math.pi * x  # math is referenced in nested fn

			return list(map(transform, data))

		names = get_code_names(fn)
		assert "math" in names  # from nested function
		assert "map" in names  # builtin in outer function
		assert "list" in names

	def test_deeply_nested_functions(self) -> None:
		def fn() -> float:
			def level1() -> float:
				def level2() -> float:
					return math.e

				return level2()

			return level1()

		names = get_code_names(fn)
		assert "math" in names
		assert "e" in names


class TestGetFunctionRefs:
	def test_categorizes_globals(self) -> None:
		# Use an actual module-level global (math module)
		def fn() -> float:
			return math.pi + log(10)

		refs = get_function_refs(fn)
		assert "math" in refs.globals
		assert refs.globals["math"] is math
		assert "log" in refs.globals
		assert refs.globals["log"] is log

	def test_categorizes_builtins(self) -> None:
		def fn(items: list[int]) -> int:
			return len(items) + sum(items)

		refs = get_function_refs(fn)
		assert "len" in refs.builtins
		assert "sum" in refs.builtins
		assert refs.builtins["len"] is len
		assert refs.builtins["sum"] is sum

	def test_categorizes_unresolved_as_attributes(self) -> None:
		def fn() -> float:
			return math.pi

		refs = get_function_refs(fn)
		assert "math" in refs.globals
		assert "pi" in refs.unresolved  # attribute, not a global

	def test_imported_function(self) -> None:
		def fn() -> float:
			return log(10)

		refs = get_function_refs(fn)
		assert "log" in refs.globals
		assert refs.globals["log"] is log

	def test_module_in_globals(self) -> None:
		def fn() -> float:
			return math.sqrt(4)

		refs = get_function_refs(fn)
		assert "math" in refs.globals
		assert refs.globals["math"] is math

	def test_nested_function_refs(self) -> None:
		"""Verify nested function references are properly categorized."""

		def fn() -> list[float]:
			items = [1, 2, 3]

			def scale(x: int) -> float:
				return math.pi * x

			return list(map(scale, items))

		refs = get_function_refs(fn)

		# Globals
		assert "math" in refs.globals

		# Builtins
		assert "map" in refs.builtins
		assert "list" in refs.builtins

		# Unresolved (attributes)
		assert "pi" in refs.unresolved


class TestValidateNoNonlocals:
	def test_simple_function_passes(self) -> None:
		def fn(x: int) -> int:
			return x + 1

		validate_no_nonlocals(fn)  # Should not raise

	def test_closure_raises(self) -> None:
		from collections.abc import Callable

		def make_closure() -> Callable[[], int]:
			captured = 42

			def inner() -> int:
				return captured

			return inner

		closure_fn = make_closure()

		with pytest.raises(ValueError, match="captures nonlocal variables"):
			validate_no_nonlocals(closure_fn)

	def test_function_with_nested_def_but_no_capture_passes(self) -> None:
		def fn() -> int:
			def inner(x: int) -> int:
				return x + 1

			return inner(5)

		# The outer function is fine
		validate_no_nonlocals(fn)
