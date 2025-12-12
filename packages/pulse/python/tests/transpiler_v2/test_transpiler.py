"""
Tests for the v2 Python -> JavaScript transpiler.

Tests expression and statement transpilation using the @javascript decorator
with real Python functions, proper type annotations, and full output comparisons.
"""

import ast
from collections.abc import Iterable
from typing import Any

import pytest
from pulse.transpiler_v2 import (
	JsFunction,
	TranspileError,
	clear_function_cache,
	clear_import_registry,
	emit,
	javascript,
	registered_functions,
	transpile,
)
from pulse.transpiler_v2.function import analyze_deps
from pulse.transpiler_v2.imports import (
	Import,
	get_registered_imports,
)


def parse_fn(code: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
	"""Parse a function definition from code string. Used for low-level API tests."""
	tree = ast.parse(code)
	fn = tree.body[0]
	assert isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
	return fn


@pytest.fixture(autouse=True)
def reset_caches():
	"""Reset caches before each test."""
	clear_function_cache()
	clear_import_registry()
	yield
	clear_function_cache()
	clear_import_registry()


# =============================================================================
# Basic Expressions
# =============================================================================


class TestBasicExpressions:
	"""Test basic expression transpilation."""

	def test_simple_return(self):
		@javascript
		def add(x: int, y: int) -> int:
			return x + y

		fn = add.transpile()
		code = emit(fn)
		assert code == "function add_1(x, y) {\nreturn x + y;\n}"

	def test_constant_return(self):
		@javascript
		def get_answer() -> int:
			return 42

		fn = get_answer.transpile()
		code = emit(fn)
		assert code == "function get_answer_1() {\nreturn 42;\n}"

	def test_string_return(self):
		@javascript
		def greet() -> str:
			return "hello"

		fn = greet.transpile()
		code = emit(fn)
		assert code == 'function greet_1() {\nreturn "hello";\n}'

	def test_boolean_return(self):
		@javascript
		def get_true() -> bool:
			return True

		fn = get_true.transpile()
		code = emit(fn)
		assert code == "function get_true_1() {\nreturn true;\n}"

	def test_none_return(self):
		@javascript
		def get_none() -> None:
			return None

		fn = get_none.transpile()
		code = emit(fn)
		assert code == "function get_none_1() {\nreturn null;\n}"

	def test_empty_body_returns_null(self):
		@javascript
		def empty() -> None:
			"""Docstring only."""
			pass

		fn = empty.transpile()
		code = emit(fn)
		assert code == "function empty_1() {\n{\n}\n}"


# =============================================================================
# Operators
# =============================================================================


class TestOperators:
	"""Test operator transpilation."""

	def test_binary_operators(self):
		@javascript
		def math(a: int | float, b: int | float) -> int | float:
			return a + b - a * b / a % b**a

		fn = math.transpile()
		code = emit(fn)
		assert code == "function math_1(a, b) {\nreturn a + b - a * b / a % b ** a;\n}"

	def test_comparison_operators(self):
		@javascript
		def cmp(a: Any, b: Any) -> bool:
			return a == b

		fn = cmp.transpile()
		code = emit(fn)
		assert code == "function cmp_1(a, b) {\nreturn a === b;\n}"

	def test_not_equal(self):
		@javascript
		def ne(a: Any, b: Any) -> bool:
			return a != b

		fn = ne.transpile()
		code = emit(fn)
		assert code == "function ne_1(a, b) {\nreturn a !== b;\n}"

	def test_less_than(self):
		@javascript
		def lt(a: int | float, b: int | float) -> bool:
			return a < b

		fn = lt.transpile()
		code = emit(fn)
		assert code == "function lt_1(a, b) {\nreturn a < b;\n}"

	def test_unary_not(self):
		@javascript
		def negate(x: Any) -> bool:
			return not x

		fn = negate.transpile()
		code = emit(fn)
		assert code == "function negate_1(x) {\nreturn !x;\n}"

	def test_unary_minus(self):
		@javascript
		def neg(x: int | float) -> int | float:
			return -x

		fn = neg.transpile()
		code = emit(fn)
		assert code == "function neg_1(x) {\nreturn -x;\n}"

	def test_boolean_and(self):
		@javascript
		def both(a: Any, b: Any) -> Any:
			return a and b

		fn = both.transpile()
		code = emit(fn)
		assert code == "function both_1(a, b) {\nreturn a && b;\n}"

	def test_boolean_or(self):
		@javascript
		def either(a: Any, b: Any) -> Any:
			return a or b

		fn = either.transpile()
		code = emit(fn)
		assert code == "function either_1(a, b) {\nreturn a || b;\n}"


# =============================================================================
# Ternary / Conditional
# =============================================================================


class TestTernary:
	"""Test ternary expression transpilation."""

	def test_simple_ternary(self):
		@javascript
		def check(x: Any) -> int:
			return 1 if x else 0

		fn = check.transpile()
		code = emit(fn)
		assert code == "function check_1(x) {\nreturn x ? 1 : 0;\n}"

	def test_ternary_with_comparison(self):
		@javascript
		def sign(x: int | float) -> str:
			return "positive" if x > 0 else "non-positive"

		fn = sign.transpile()
		code = emit(fn)
		assert (
			code
			== 'function sign_1(x) {\nreturn x > 0 ? "positive" : "non-positive";\n}'
		)

	def test_nested_ternary(self):
		@javascript
		def classify(x: int | float) -> int:
			return 1 if x > 0 else -1 if x < 0 else 0

		fn = classify.transpile()
		code = emit(fn)
		assert code == "function classify_1(x) {\nreturn x > 0 ? 1 : x < 0 ? -1 : 0;\n}"


# =============================================================================
# Data Structures
# =============================================================================


class TestDataStructures:
	"""Test list/dict/set transpilation."""

	def test_list_literal(self):
		@javascript
		def get_list() -> list[int]:
			return [1, 2, 3]

		fn = get_list.transpile()
		code = emit(fn)
		assert code == "function get_list_1() {\nreturn [1, 2, 3];\n}"

	def test_tuple_as_array(self):
		@javascript
		def get_tuple() -> tuple[int, int, int]:
			return (1, 2, 3)

		fn = get_tuple.transpile()
		code = emit(fn)
		assert code == "function get_tuple_1() {\nreturn [1, 2, 3];\n}"

	def test_dict_as_map(self):
		@javascript
		def get_dict() -> dict[str, int]:
			return {"a": 1, "b": 2}

		fn = get_dict.transpile()
		code = emit(fn)
		assert code == 'function get_dict_1() {\nreturn Map([["a", 1], ["b", 2]]);\n}'

	def test_set_literal(self):
		@javascript
		def get_set() -> set[int]:
			return {1, 2, 3}

		fn = get_set.transpile()
		code = emit(fn)
		assert code == "function get_set_1() {\nreturn Set([1, 2, 3]);\n}"


# =============================================================================
# Function Calls
# =============================================================================


class TestFunctionCalls:
	"""Test function call transpilation."""

	def test_method_call(self):
		@javascript
		def get_upper(s: str) -> str:
			return s.upper()

		fn = get_upper.transpile()
		code = emit(fn)
		assert (
			code
			== 'function get_upper_1(s) {\nreturn typeof s === "string" ? s.toUpperCase() : s.upper();\n}'
		)

	def test_chained_method_call(self):
		@javascript
		def process(s: str) -> str:
			return s.strip().lower()

		fn = process.transpile()
		code = emit(fn)
		# With runtime type checks: strip becomes trim for strings, lower becomes toLowerCase
		assert 'typeof s === "string"' in code
		assert "s.trim()" in code
		assert "toLowerCase()" in code


# =============================================================================
# Attribute Access
# =============================================================================


class TestAttributeAccess:
	"""Test attribute access transpilation."""

	def test_simple_attribute(self):
		@javascript
		def get_prop(obj: Any) -> Any:
			return obj.prop

		fn = get_prop.transpile()
		code = emit(fn)
		assert code == "function get_prop_1(obj) {\nreturn obj.prop;\n}"

	def test_chained_attributes(self):
		@javascript
		def get_nested(obj: Any) -> Any:
			return obj.a.b.c

		fn = get_nested.transpile()
		code = emit(fn)
		assert code == "function get_nested_1(obj) {\nreturn obj.a.b.c;\n}"


# =============================================================================
# Subscript Access
# =============================================================================


class TestSubscriptAccess:
	"""Test subscript access transpilation."""

	def test_index_access(self):
		@javascript
		def get_first(arr: list[Any]) -> Any:
			return arr[0]

		fn = get_first.transpile()
		code = emit(fn)
		assert code == "function get_first_1(arr) {\nreturn arr[0];\n}"

	def test_negative_index(self):
		@javascript
		def get_last(arr: list[Any]) -> Any:
			return arr[-1]

		fn = get_last.transpile()
		code = emit(fn)
		assert code == "function get_last_1(arr) {\nreturn arr.at(-1);\n}"

	def test_slice_start(self):
		@javascript
		def get_rest(arr: list[Any]) -> list[Any]:
			return arr[1:]

		fn = get_rest.transpile()
		code = emit(fn)
		assert code == "function get_rest_1(arr) {\nreturn arr.slice(1);\n}"

	def test_slice_end(self):
		@javascript
		def get_first_three(arr: list[Any]) -> list[Any]:
			return arr[:3]

		fn = get_first_three.transpile()
		code = emit(fn)
		assert code == "function get_first_three_1(arr) {\nreturn arr.slice(0, 3);\n}"

	def test_slice_both(self):
		@javascript
		def get_middle(arr: list[Any]) -> list[Any]:
			return arr[1:3]

		fn = get_middle.transpile()
		code = emit(fn)
		assert code == "function get_middle_1(arr) {\nreturn arr.slice(1, 3);\n}"

	def test_slice_empty(self):
		@javascript
		def copy(arr: list[Any]) -> list[Any]:
			return arr[:]

		fn = copy.transpile()
		code = emit(fn)
		assert code == "function copy_1(arr) {\nreturn arr.slice();\n}"


# =============================================================================
# F-strings / Template Literals
# =============================================================================


class TestFStrings:
	"""Test f-string transpilation."""

	def test_simple_fstring(self):
		@javascript
		def greet(name: str) -> str:
			return f"Hello, {name}!"

		fn = greet.transpile()
		code = emit(fn)
		assert code == "function greet_1(name) {\nreturn `Hello, ${name}!`;\n}"

	def test_fstring_with_expression(self):
		@javascript
		def show_sum(a: int, b: int) -> str:
			return f"Sum: {a + b}"

		fn = show_sum.transpile()
		code = emit(fn)
		assert code == "function show_sum_1(a, b) {\nreturn `Sum: ${a + b}`;\n}"

	def test_fstring_conversion_s(self):
		@javascript
		def stringify(x: Any) -> str:
			return f"{x!s}"

		fn = stringify.transpile()
		code = emit(fn)
		assert code == "function stringify_1(x) {\nreturn `${String(x)}`;\n}"

	def test_fstring_conversion_r(self):
		@javascript
		def repr_it(x: Any) -> str:
			return f"{x!r}"

		fn = repr_it.transpile()
		code = emit(fn)
		assert code == "function repr_it_1(x) {\nreturn `${JSON.stringify(x)}`;\n}"


# =============================================================================
# Lambda
# =============================================================================


class TestLambda:
	"""Test lambda transpilation."""

	def test_simple_lambda(self):
		@javascript
		def get_doubler():
			return lambda x: x * 2

		fn = get_doubler.transpile()
		code = emit(fn)
		assert code == "function get_doubler_1() {\nreturn x => x * 2;\n}"

	def test_multi_param_lambda(self):
		@javascript
		def get_adder():
			return lambda a, b: a + b

		fn = get_adder.transpile()
		code = emit(fn)
		assert code == "function get_adder_1() {\nreturn (a, b) => a + b;\n}"

	def test_zero_param_lambda(self):
		@javascript
		def get_const() -> int:
			return lambda: 42

		fn = get_const.transpile()
		code = emit(fn)
		assert code == "function get_const_1() {\nreturn () => 42;\n}"


# =============================================================================
# List Comprehensions
# =============================================================================


class TestComprehensions:
	"""Test comprehension transpilation."""

	def test_simple_list_comp(self):
		@javascript
		def double_all(items: Iterable[int]) -> list[int]:
			return [x * 2 for x in items]

		fn = double_all.transpile()
		code = emit(fn)
		assert (
			code == "function double_all_1(items) {\nreturn items.map(x => x * 2);\n}"
		)

	def test_list_comp_with_filter(self):
		@javascript
		def get_positives(items: Iterable[int]) -> list[int]:
			return [x for x in items if x > 0]

		fn = get_positives.transpile()
		code = emit(fn)
		assert (
			code
			== "function get_positives_1(items) {\nreturn items.filter(x => x > 0).map(x => x);\n}"
		)

	def test_tuple_unpacking_in_comp(self):
		@javascript
		def sum_pairs(pairs: Iterable[tuple[int, int]]) -> list[int]:
			return [a + b for a, b in pairs]

		fn = sum_pairs.transpile()
		code = emit(fn)
		assert (
			code
			== "function sum_pairs_1(pairs) {\nreturn pairs.map([a, b] => a + b);\n}"
		)

	def test_set_comp(self):
		@javascript
		def unique_doubled(items: Iterable[int]) -> set[int]:
			return {x * 2 for x in items}

		fn = unique_doubled.transpile()
		code = emit(fn)
		assert (
			code
			== "function unique_doubled_1(items) {\nreturn Set(items.map(x => x * 2));\n}"
		)

	def test_dict_comp(self):
		@javascript
		def double_values(pairs: Iterable[tuple[str, int]]) -> dict[str, int]:
			return {k: v * 2 for k, v in pairs}

		fn = double_values.transpile()
		code = emit(fn)
		assert (
			code
			== "function double_values_1(pairs) {\nreturn Map(pairs.map([k, v] => [k, v * 2]));\n}"
		)


# =============================================================================
# Dependencies
# =============================================================================


class TestDependencies:
	"""Test dependency substitution with manual dependency injection."""

	def test_unbound_name_raises(self):
		@javascript
		def use_unknown() -> Any:
			return unknown_var  # noqa: F821  # pyright: ignore[reportUndefinedVariable]

		with pytest.raises(TranspileError, match="Unbound name"):
			use_unknown.transpile()


# =============================================================================
# Multi-Statement Functions
# =============================================================================


class TestMultiStatement:
	"""Test multi-statement function transpilation."""

	def test_if_else_statement(self):
		@javascript
		def abs_val(x: int | float) -> int | float:
			if x < 0:
				return -x
			else:
				return x

		fn = abs_val.transpile()
		code = emit(fn)
		assert (
			code
			== "function abs_val_1(x) {\nif (x < 0) {\nreturn -x;\n} else {\nreturn x;\n}\n}"
		)

	def test_variable_assignment(self):
		@javascript
		def swap(x: Any, y: Any) -> list[Any]:
			temp = x
			x = y
			y = temp
			return [x, y]

		fn = swap.transpile()
		code = emit(fn)
		assert (
			code
			== "function swap_1(x, y) {\nlet temp = x;\nx = y;\ny = temp;\nreturn [x, y];\n}"
		)

	def test_while_loop(self):
		@javascript
		def countdown(n: int) -> int:
			while n > 0:
				n = n - 1
			return n

		fn = countdown.transpile()
		code = emit(fn)
		assert (
			code
			== "function countdown_1(n) {\nwhile (n > 0) {\nn = n - 1;\n}\nreturn n;\n}"
		)

	def test_for_of_loop(self):
		@javascript
		def sum_items(items: Iterable[int]) -> int:
			total = 0
			for x in items:
				total = total + x
			return total

		fn = sum_items.transpile()
		code = emit(fn)
		assert (
			code
			== "function sum_items_1(items) {\nlet total = 0;\nfor (const x of items) {\ntotal = total + x;\n}\nreturn total;\n}"
		)

	def test_for_of_with_tuple_unpacking(self):
		@javascript
		def sum_pairs(pairs: Iterable[tuple[int, int]]) -> int:
			total = 0
			for a, b in pairs:
				total = total + a + b
			return total

		fn = sum_pairs.transpile()
		code = emit(fn)
		assert (
			code
			== "function sum_pairs_1(pairs) {\nlet total = 0;\nfor (const [a, b] of pairs) {\ntotal = total + a + b;\n}\nreturn total;\n}"
		)

	def test_break_statement(self):
		@javascript
		def find_first(items: Iterable[Any], target: Any) -> Any:
			result = None
			for x in items:
				if x == target:
					result = x
					break
			return result

		fn = find_first.transpile()
		code = emit(fn)
		assert "break;" in code

	def test_continue_statement(self):
		@javascript
		def count_positive(items: Iterable[int]) -> int:
			count = 0
			for x in items:
				if x <= 0:
					continue
				count = count + 1
			return count

		fn = count_positive.transpile()
		code = emit(fn)
		assert "continue;" in code

	def test_augmented_assignment(self):
		@javascript
		def add_to(x: int, y: int) -> int:
			x += y
			return x

		fn = add_to.transpile()
		code = emit(fn)
		assert code == "function add_to_1(x, y) {\nx += y;\nreturn x;\n}"

	def test_nested_function(self):
		@javascript
		def outer(x: int) -> int:
			def inner(y: int) -> int:
				return x + y

			return inner(10)

		fn = outer.transpile()
		code = emit(fn)
		assert "const inner = function(y)" in code
		assert "return x + y" in code
		assert "return inner(10)" in code

	def test_tuple_unpacking_assignment(self):
		@javascript
		def unpack(t: tuple[int, int]) -> int:
			a, b = t
			return a + b

		fn = unpack.transpile()
		code = emit(fn)
		assert "$tmp" in code  # Uses temp variable
		assert "[0]" in code
		assert "[1]" in code


# =============================================================================
# Identity Comparisons
# =============================================================================


class TestIdentityComparisons:
	"""Test is/is not transpilation."""

	def test_is_none(self):
		@javascript
		def is_null(x: Any) -> bool:
			return x is None

		fn = is_null.transpile()
		code = emit(fn)
		assert code == "function is_null_1(x) {\nreturn x == null;\n}"

	def test_is_not_none(self):
		@javascript
		def is_not_null(x: Any) -> bool:
			return x is not None

		fn = is_not_null.transpile()
		code = emit(fn)
		assert code == "function is_not_null_1(x) {\nreturn x != null;\n}"

	def test_is_comparison(self):
		@javascript
		def same(a: Any, b: Any) -> bool:
			return a is b

		fn = same.transpile()
		code = emit(fn)
		assert code == "function same_1(a, b) {\nreturn a === b;\n}"


# =============================================================================
# Membership Tests
# =============================================================================


class TestMembershipTests:
	"""Test in/not in transpilation."""

	def test_in_operator(self):
		@javascript
		def contains(items: list[Any] | set[Any] | dict[Any, Any], x: Any) -> bool:
			return x in items

		fn = contains.transpile()
		code = emit(fn)
		# Should have runtime check for container type
		assert "includes" in code or "has" in code or "in" in code

	def test_not_in_operator(self):
		@javascript
		def not_contains(items: list[Any] | set[Any] | dict[Any, Any], x: Any) -> bool:
			return x not in items

		fn = not_contains.transpile()
		code = emit(fn)
		assert "!" in code


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


# =============================================================================
# Import as Dependency
# =============================================================================


class TestImportDependency:
	"""Test Import as a transpiler dependency (ToExpr, EmitsCall, EmitsGetattr)."""

	def setup_method(self):
		"""Clear import registry before each test."""
		clear_import_registry()

	def test_import_as_value(self):
		"""Import used as a value resolves to Identifier with unique js_name."""
		fn = parse_fn("""
def use_hook():
    return useState
""")
		useState = Import("useState", "react")
		result = transpile(fn, {"useState": useState})
		assert emit(result) == "() => useState_1"

	def test_import_in_call(self):
		"""Import called as function (non-jsx) produces Call node."""
		fn = parse_fn("""
def use_hook():
    return useState(0)
""")
		useState = Import("useState", "react")
		result = transpile(fn, {"useState": useState})
		assert emit(result) == "() => useState_1(0)"

	def test_import_jsx_call(self):
		"""Import with jsx=True called produces ElementNode."""
		fn = parse_fn("""
def render():
    return Button("Click me", disabled=True)
""")
		Button = Import("Button", "@mantine/core", jsx=True)
		result = transpile(fn, {"Button": Button})
		code = emit(result)
		# $$ prefix is stripped during emit, js_name used as tag
		assert "<Button_1" in code
		assert "disabled={true}" in code
		assert "</Button_1>" in code

	def test_import_jsx_call_with_key(self):
		"""Import jsx call with key prop extracts key."""
		fn = parse_fn("""
def render():
    return Item("text", key="item-1")
""")
		Item = Import("Item", "./components", jsx=True)
		result = transpile(fn, {"Item": Item})
		code = emit(result)
		assert 'key="item-1"' in code

	def test_import_jsx_call_no_children(self):
		"""Import jsx call with only props, no children."""
		fn = parse_fn("""
def render():
    return Icon(name="check")
""")
		Icon = Import("Icon", "./icons", jsx=True)
		result = transpile(fn, {"Icon": Icon})
		code = emit(result)
		# $$ prefix is stripped during emit
		assert "<Icon_1" in code
		assert 'name="check"' in code
		assert "/>" in code  # Self-closing

	def test_import_attribute_access(self):
		"""Import with attribute access produces Member."""
		fn = parse_fn("""
def get_version():
    return React.version
""")
		React = Import("React", "react", is_default=True)
		result = transpile(fn, {"React": React})
		assert emit(result) == "() => React_1.version"

	def test_import_method_call(self):
		"""Import method call chains correctly."""
		fn = parse_fn("""
def navigate():
    return router.push("/home")
""")
		router = Import("router", "next/router", is_default=True)
		result = transpile(fn, {"router": router})
		assert emit(result) == '() => router_1.push("/home")'

	def test_import_deduplication(self):
		"""Same import used twice gets same ID."""
		fn = parse_fn("""
def both(x):
    return useState(x) + useEffect(x)
""")
		useState = Import("useState", "react")
		useEffect = Import("useEffect", "react")
		result = transpile(fn, {"useState": useState, "useEffect": useEffect})
		code = emit(result)
		assert "useState_1" in code
		assert "useEffect_2" in code

	def test_import_same_name_different_src(self):
		"""Same name from different sources get different IDs."""
		foo1 = Import("foo", "package-a")
		foo2 = Import("foo", "package-b")
		# They should have different IDs
		assert foo1.id != foo2.id

	def test_import_registry(self):
		"""get_registered_imports returns all created imports."""
		_ = Import("useState", "react")
		_ = Import("Button", "@mantine/core", jsx=True)
		_ = Import("MyType", "./types", is_type=True)

		imports = get_registered_imports()
		assert len(imports) == 3
		names = {imp.name for imp in imports}
		assert names == {"useState", "Button", "MyType"}

	def test_import_type_only_merged(self):
		"""Type-only import merged with regular becomes regular."""
		type_only = Import("Foo", "./types", is_type=True)
		assert type_only.is_type is True

		regular = Import("Foo", "./types")
		# Both now point to regular
		assert type_only.is_type is False
		assert regular.is_type is False

	def test_import_before_constraints_merged(self):
		"""Before constraints are merged across duplicate imports."""
		a = Import("A", "pkg", before=("x",))
		assert a.before == ("x",)

		b = Import("A", "pkg", before=("y", "z"))
		# Both have merged before
		assert set(a.before) == {"x", "y", "z"}
		assert set(b.before) == {"x", "y", "z"}


# =============================================================================
# Error Cases
# =============================================================================


class TestErrors:
	"""Test error handling."""

	def test_unsupported_slice_step(self):
		@javascript
		def every_other(arr: list[Any]) -> list[Any]:
			return arr[::2]

		with pytest.raises(TranspileError, match="Slice steps"):
			every_other.transpile()

	def test_multiple_assignment_targets(self):
		@javascript
		def multi(x: Any) -> Any:
			a = b = x  # noqa: F841  # pyright: ignore[reportUnusedVariable]
			return a

		with pytest.raises(TranspileError, match="Multiple assignment"):
			multi.transpile()


# =============================================================================
# @javascript Decorator (End-to-End)
# =============================================================================


class TestJavascriptDecorator:
	"""Test the @javascript decorator end-to-end."""

	def test_basic_decorator(self):
		"""Test basic @javascript decorator creates JsFunction."""

		@javascript
		def add(a: int, b: int) -> int:
			return a + b

		assert isinstance(add, JsFunction)
		assert add.js_name == "add_1"

	def test_caching(self):
		"""Test that the same function returns the same JsFunction."""

		def helper(x: int) -> int:
			return x * 2

		js1 = javascript(helper)
		js2 = javascript(helper)
		assert js1 is js2

	def test_function_dependencies(self):
		"""Test that functions can reference other @javascript functions."""

		@javascript
		def helper(n: int) -> int:
			return n + 1

		@javascript
		def caller(n: int) -> int:
			return helper(n) * 2

		assert "helper" in caller.deps
		assert isinstance(caller.deps["helper"], JsFunction)
		assert caller.deps["helper"] is helper

	def test_transpile_with_function_deps(self):
		"""Test transpiling a function that uses another function."""

		@javascript
		def double(x: int) -> int:
			return x * 2

		@javascript
		def quadruple(x: int) -> int:
			return double(double(x))

		assert "double" in quadruple.deps

		fn = quadruple.transpile()
		code = emit(fn)
		assert "function quadruple_2" in code
		assert "double_1" in code  # Reference uses js_name

	def test_closure_variables(self):
		"""Test that closure variables are captured as deps."""

		def make_adder(n: int):
			@javascript
			def adder(x: int) -> int:
				return x + n

			return adder

		add5 = make_adder(5)
		assert isinstance(add5, JsFunction)
		assert "n" in add5.deps

	def test_constant_deps(self):
		"""Test that constant values are captured as deps."""
		MULTIPLIER = 10

		@javascript
		def multiply(x: int) -> int:
			return x * MULTIPLIER

		assert "MULTIPLIER" in multiply.deps
		fn = multiply.transpile()
		code = emit(fn)
		assert code == "function multiply_1(x) {\nreturn x * 10;\n}"

	def test_registered_functions(self):
		"""Test that registered_functions returns all JsFunctions."""

		@javascript
		def fn1() -> int:
			return 1

		@javascript
		def fn2() -> int:
			return 2

		fns = registered_functions()
		assert len(fns) == 2
		assert fn1 in fns
		assert fn2 in fns


class TestAnalyzeDeps:
	"""Test dependency analysis."""

	def test_empty_deps(self, reset_caches):
		"""Test analyzing a function with no deps."""

		def simple(x: int) -> int:
			return x + 1

		deps = analyze_deps(simple)
		assert deps == {}

	def test_constant_deps(self, reset_caches):
		"""Test analyzing a function with constant deps."""
		VALUE = 42

		def use_const() -> int:
			return VALUE

		deps = analyze_deps(use_const)
		assert "VALUE" in deps
