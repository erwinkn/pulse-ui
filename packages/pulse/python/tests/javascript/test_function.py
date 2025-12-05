"""Tests for JsFunction dependency analysis."""

from __future__ import annotations

import pytest
from pulse.javascript.builtins import PyBuiltin
from pulse.javascript.constants import CONSTANTS_CACHE, JsConstant
from pulse.javascript.errors import JSCompilationError
from pulse.javascript.function import (
	FUNCTION_CACHE,
	JsFunction,
	javascript,
)
from pulse.javascript.imports import Import, clear_import_registry
from pulse.javascript.nodes import JSArray, JSNumber, JSString


# Clear caches between tests
@pytest.fixture(autouse=True)
def clear_caches() -> None:
	FUNCTION_CACHE.clear()
	CONSTANTS_CACHE.clear()
	clear_import_registry()


def test_detects_js_import() -> None:
	test_import = Import("foo", "./foo.js")

	@javascript
	def fn() -> int:
		return test_import  # pyright: ignore[reportReturnType]

	assert "test_import" in fn.deps
	assert fn.deps["test_import"] is test_import


def test_multiple_imports() -> None:
	import_a = Import("a", "./a.js")
	import_b = Import.default("b", "./b.js")

	@javascript
	def fn() -> tuple[int, str]:
		return import_a, import_b  # pyright: ignore[reportReturnType]

	imports = fn.imports()
	assert len(imports) == 2
	assert imports["import_a"] is import_a
	assert imports["import_b"] is import_b


def test_namespace_import() -> None:
	ns_import = Import.namespace("Foo", "foo-package")

	@javascript
	def fn() -> int:
		return ns_import  # pyright: ignore[reportReturnType]

	imports = fn.imports()
	assert len(imports) == 1
	assert imports["ns_import"] is ns_import
	assert ns_import.is_namespace is True
	assert ns_import.is_default is False
	assert ns_import.name == "Foo"


def test_detects_numeric_constant() -> None:
	MY_CONST = 42

	@javascript
	def fn() -> int:
		return MY_CONST

	assert "MY_CONST" in fn.deps
	const = fn.deps["MY_CONST"]
	assert isinstance(const, JsConstant)
	assert isinstance(const.expr, JSNumber)


def test_detects_string_constant() -> None:
	GREETING = "hello"

	@javascript
	def fn() -> str:
		return GREETING

	assert "GREETING" in fn.deps
	const = fn.deps["GREETING"]
	assert isinstance(const, JsConstant)
	assert isinstance(const.expr, JSString)


def test_detects_list_constant() -> None:
	ITEMS = [1, 2, 3]

	@javascript
	def fn() -> list[int]:
		return ITEMS

	assert "ITEMS" in fn.deps
	const = fn.deps["ITEMS"]
	assert isinstance(const, JsConstant)
	assert isinstance(const.expr, JSArray)


def test_constants_are_cached_globally() -> None:
	"""Same constant value should reuse cached JsConstant."""
	SHARED_CONST = 999

	@javascript
	def fn1() -> int:
		return SHARED_CONST

	@javascript
	def fn2() -> int:
		return SHARED_CONST + 1

	assert fn1.deps["SHARED_CONST"] is fn2.deps["SHARED_CONST"]


def test_detects_function_dependency() -> None:
	def helper(x: int) -> int:
		return x + 1

	@javascript
	def fn(x: int) -> int:
		return helper(x)

	assert "helper" in fn.deps
	helper_dep = fn.deps["helper"]
	assert isinstance(helper_dep, JsFunction)
	assert helper_dep.fn is helper


def test_multiple_function_dependencies() -> None:
	def add(a: int, b: int) -> int:
		return a + b

	def mul(a: int, b: int) -> int:
		return a * b

	@javascript
	def fn(x: int) -> int:
		return add(mul(x, 2), 1)

	fn_deps = fn.functions()
	assert "add" in fn_deps
	assert "mul" in fn_deps


def test_function_dependency_cached() -> None:
	"""Same function referenced twice should use cache."""

	def helper(x: int) -> int:
		return x + 1

	@javascript
	def fn1(x: int) -> int:
		return helper(x)

	@javascript
	def fn2(x: int) -> int:
		return helper(x) + 1

	assert fn1.deps["helper"] is fn2.deps["helper"]


def test_transitive_dependencies() -> None:
	"""Dependencies of dependencies are analyzed."""

	def level2(x: int) -> int:
		return x * 2

	def level1(x: int) -> int:
		return level2(x) + 1

	@javascript
	def fn(x: int) -> int:
		return level1(x)

	assert "level1" in fn.deps
	level1_fn = fn.deps["level1"]
	assert isinstance(level1_fn, JsFunction)
	assert "level2" in level1_fn.deps


def test_mutual_recursion() -> None:
	"""Mutually recursive functions should not cause infinite loop."""

	def is_even_fn(n: int) -> bool:
		if n == 0:
			return True
		return is_odd_fn(n - 1)

	def is_odd_fn(n: int) -> bool:
		if n == 0:
			return False
		return is_even_fn(n - 1)

	is_even = javascript(is_even_fn)
	_ = javascript(is_odd_fn)  # Create to handle mutual recursion

	assert "is_odd_fn" in is_even.deps
	jsfn_odd = is_even.deps["is_odd_fn"]
	assert isinstance(jsfn_odd, JsFunction)

	assert "is_even_fn" in jsfn_odd.deps
	assert jsfn_odd.deps["is_even_fn"] is is_even


def test_self_recursion() -> None:
	"""Self-recursive function should work."""

	def factorial_fn(n: int) -> int:
		if n <= 1:
			return 1
		return n * factorial_fn(n - 1)

	factorial = javascript(factorial_fn)

	assert "factorial_fn" in factorial.deps
	assert factorial.deps["factorial_fn"] is factorial


def test_rejects_callable_objects() -> None:
	"""Callable objects (not functions) should raise JSCompilationError."""

	class CallableClass:
		def __call__(self, x: int) -> int:
			return x + 1

	callable_obj = CallableClass()

	def fn(x: int) -> int:
		return callable_obj(x)

	with pytest.raises(JSCompilationError, match="Callable object.*is not supported"):
		JsFunction(fn)


def test_nested_function_deps_captured() -> None:
	"""Dependencies in nested functions should be captured."""
	MY_CONST = 42

	@javascript
	def fn(items: list[int]) -> list[int]:
		def transform(x: int) -> int:
			return x * MY_CONST

		return [transform(x) for x in items]

	assert "MY_CONST" in fn.deps
	assert isinstance(fn.deps["MY_CONST"], JsConstant)


def test_builtins_become_pybuiltin() -> None:
	"""Builtins are wrapped as PyBuiltin."""

	@javascript
	def fn(items: list[int]) -> int:
		return len(items)

	assert "len" in fn.deps
	builtin = fn.deps["len"]
	assert isinstance(builtin, PyBuiltin)
	assert builtin.name == "len"
