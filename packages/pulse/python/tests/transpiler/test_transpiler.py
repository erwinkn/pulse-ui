"""Tests for the JavaScript transpiler.

Adapted from the v1 transpiler tests, excluding tests that require:
- Builtin function transpilation (len, range, print, etc.)
- Builtin method transpilation with runtime type checks
"""

# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportReturnType=false, reportAttributeAccessIssue=false, reportIndexIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportUnusedVariable=false, reportMissingTypeArgument=false

import warnings

from pulse.transpiler.errors import JSCompilationError
from pulse.transpiler.function import javascript

# =============================================================================
# Basic Statements
# =============================================================================


class TestStatements:
	"""Test statement transpilation."""

	def test_if_else_statement(self):
		@javascript
		def f(x):
			if x > 0:
				return 1
			else:
				return 2

		code = f.transpile()
		assert "if (x > 0)" in code
		assert "return 1" in code
		assert "else" in code
		assert "return 2" in code

	def test_conditional_expression(self):
		@javascript
		def f(x):
			return 1 if x > 0 else 2

		code = f.transpile()
		assert "x > 0 ? 1 : 2" in code

	def test_boolean_precedence_or(self):
		@javascript
		def f(a, b, c):
			return (a and b) or c

		code = f.transpile()
		assert "a && b || c" in code

	def test_nested_ternary(self):
		@javascript
		def f(x):
			return 1 if x > 0 else 2 if x < -1 else 3

		code = f.transpile()
		assert "x > 0 ? 1 : x < -1 ? 2 : 3" in code

	def test_unpack_tuple_assignment(self):
		@javascript
		def f(t):
			a, b = t
			return a + b

		code = f.transpile()
		assert "$tmp" in code  # Uses temp variable
		assert "[0]" in code
		assert "[1]" in code
		assert "a + b" in code

	def test_unpack_list_assignment_literal_rhs(self):
		@javascript
		def f():
			a, b = [1, 2]
			return a * b

		code = f.transpile()
		assert "[1, 2]" in code
		assert "a * b" in code

	def test_unpack_tuple_reassignment_no_let(self):
		@javascript
		def f(t):
			a, b = t
			a, b = t
			return a - b

		code = f.transpile()
		# First assignment should have 'let'
		assert "let a" in code
		assert "let b" in code
		# Count occurrences - second assignment should not have 'let'
		assert code.count("let a") == 1
		assert code.count("let b") == 1

	def test_unpack_nested_unsupported(self):
		@javascript
		def f(t):
			(a, (b, c)) = t
			return a

		try:
			f.transpile()
			raise AssertionError("Expected JSCompilationError for nested unpacking")
		except JSCompilationError as e:
			assert "unpacking" in str(e).lower() or "simple" in str(e).lower()


# =============================================================================
# Operators
# =============================================================================


class TestOperators:
	"""Test operator transpilation."""

	def test_assign_and_return(self):
		@javascript
		def f(x):
			y = x + 1
			return y

		code = f.transpile()
		assert "let y = x + 1" in code
		assert "return y" in code

	def test_annassign_and_return(self):
		@javascript
		def f(x: int):
			y: int = x
			return y

		code = f.transpile()
		assert "let y = x" in code
		assert "return y" in code

	def test_reassignment_without_let(self):
		@javascript
		def f(x):
			y = x + 1
			y = y + 2
			return y

		code = f.transpile()
		assert "let y = x + 1" in code
		assert "y = y + 2" in code
		# Should not have 'let' on second assignment
		assert code.count("let y") == 1

	def test_param_reassignment(self):
		@javascript
		def f(x):
			x = x + 1
			return x

		code = f.transpile()
		assert "x = x + 1" in code
		# No 'let' for parameter reassignment
		assert "let x" not in code

	def test_augassign(self):
		@javascript
		def f(x):
			y = 1
			y += x
			return y

		code = f.transpile()
		assert "let y = 1" in code
		assert "y += x" in code

	def test_is_none(self):
		@javascript
		def f(x):
			return x is None

		code = f.transpile()
		assert "x == null" in code

	def test_is_not_none(self):
		@javascript
		def f(x):
			return x is not None

		code = f.transpile()
		assert "x != null" in code

	def test_simple_addition(self):
		@javascript
		def f(a, b):
			return a + b

		code = f.transpile()
		assert "return a + b" in code

	def test_is_with_value(self):
		@javascript
		def f(x):
			y = 5
			return x is y

		code = f.transpile()
		assert "x === y" in code

	def test_is_not_with_string(self):
		warnings.simplefilter("ignore", SyntaxWarning)

		@javascript
		def f(s):
			a = "a"
			return s is not a

		code = f.transpile()
		assert "s !== a" in code

	def test_constants_arithmetic_comparisons_boolean_ops(self):
		@javascript
		def f(x):
			return (x * 2 + 3) > 0 and not (x == 5)

		code = f.transpile()
		assert "x * 2 + 3 > 0" in code
		assert "&&" in code
		assert "!(x === 5)" in code

	def test_unary_minus(self):
		@javascript
		def f(x):
			return -x

		code = f.transpile()
		assert "-x" in code

	def test_compare_chaining(self):
		@javascript
		def f(x):
			return 0 < x < 10

		code = f.transpile()
		assert "0 < x" in code
		assert "x < 10" in code
		assert "&&" in code

	def test_pow_with_negative_base_parenthesized(self):
		@javascript
		def f():
			return (-2) ** 2

		code = f.transpile()
		assert "(-2) ** 2" in code


# =============================================================================
# Loops
# =============================================================================


class TestLoops:
	"""Test loop transpilation."""

	def test_simple_for_over_list(self):
		@javascript
		def f(xs):
			s = 0
			for x in xs:
				s = s + x
			return s

		code = f.transpile()
		assert "for (const x of xs)" in code
		assert "s = s + x" in code

	def test_for_with_break(self):
		@javascript
		def f(xs):
			s = 0
			for x in xs:
				if x > 10:
					break
				s = s + x
			return s

		code = f.transpile()
		assert "for (const x of xs)" in code
		assert "if (x > 10)" in code
		assert "break" in code

	def test_for_with_continue(self):
		@javascript
		def f(xs):
			s = 0
			for x in xs:
				if x % 2 == 0:
					continue
				s = s + x
			return s

		code = f.transpile()
		assert "for (const x of xs)" in code
		assert "x % 2 === 0" in code
		assert "continue" in code

	def test_while_loop(self):
		@javascript
		def f(n):
			i = 0
			s = 0
			while i < n:
				s = s + i
				i = i + 1
			return s

		code = f.transpile()
		assert "while (i < n)" in code
		assert "s = s + i" in code
		assert "i = i + 1" in code

	def test_while_with_break_continue(self):
		@javascript
		def f(n):
			i = 0
			s = 0
			while True:
				i = i + 1
				if i > n:
					break
				if i % 2 == 0:
					continue
				s = s + i
			return s

		code = f.transpile()
		assert "while (true)" in code
		assert "break" in code
		assert "continue" in code


# =============================================================================
# F-strings
# =============================================================================


class TestFStrings:
	"""Test f-string transpilation."""

	def test_fstring_to_template_literal(self):
		@javascript
		def f(x):
			return f"value={x}"

		code = f.transpile()
		assert "`value=${x}`" in code

	def test_fstring_escapes_backtick_dollar_brace_and_backslash(self):
		@javascript
		def f(x):
			return f"$`${{{x}"

		code = f.transpile()
		assert r"\`" in code  # Escaped backtick
		assert r"\${" in code  # Escaped ${

	def test_fstring_escapes_line_separators(self):
		@javascript
		def f():
			return "\r\n\b\t\u2028\u2029"

		code = f.transpile()
		# These special chars should be escaped in the template literal
		assert r"\u2028" in code or "\\u2028" in code

	def test_simple_fstring(self):
		@javascript
		def greet(name: str) -> str:
			return f"Hello, {name}!"

		code = greet.transpile()
		assert "`Hello, ${name}!`" in code

	def test_fstring_with_expression(self):
		@javascript
		def show_sum(a: int, b: int) -> str:
			return f"{a} + {b} = {a + b}"

		code = show_sum.transpile()
		assert "${a}" in code
		assert "${b}" in code
		assert "${a + b}" in code

	def test_fstring_format_spec_float_precision(self):
		@javascript
		def f(x):
			return f"{x:.2f}"

		code = f.transpile()
		assert "toFixed(2)" in code

	def test_fstring_format_spec_float_precision_3(self):
		@javascript
		def f(x):
			return f"{x:.3f}"

		code = f.transpile()
		assert "toFixed(3)" in code

	def test_fstring_format_spec_zero_padded_int(self):
		@javascript
		def f(x):
			return f"{x:05d}"

		code = f.transpile()
		assert "padStart(5" in code
		assert '"0"' in code

	def test_fstring_format_spec_right_align(self):
		@javascript
		def f(s):
			return f"{s:>10}"

		code = f.transpile()
		assert "padStart(10" in code

	def test_fstring_format_spec_left_align(self):
		@javascript
		def f(s):
			return f"{s:<10}"

		code = f.transpile()
		assert "padEnd(10" in code

	def test_fstring_format_spec_center_align(self):
		@javascript
		def f(s):
			return f"{s:^10}"

		code = f.transpile()
		# Center needs both padStart and padEnd
		assert "padStart" in code
		assert "padEnd" in code

	def test_fstring_format_spec_hex_lowercase(self):
		@javascript
		def f(x):
			return f"{x:x}"

		code = f.transpile()
		assert "toString(16)" in code

	def test_fstring_format_spec_hex_uppercase(self):
		@javascript
		def f(x):
			return f"{x:X}"

		code = f.transpile()
		assert "toString(16)" in code
		assert "toUpperCase()" in code

	def test_fstring_format_spec_hex_with_prefix(self):
		@javascript
		def f(x):
			return f"{x:#x}"

		code = f.transpile()
		assert '"0x"' in code
		assert "toString(16)" in code

	def test_fstring_format_spec_binary_with_prefix(self):
		@javascript
		def f(x):
			return f"{x:#b}"

		code = f.transpile()
		assert '"0b"' in code
		assert "toString(2)" in code

	def test_fstring_format_spec_octal_with_prefix(self):
		@javascript
		def f(x):
			return f"{x:#o}"

		code = f.transpile()
		assert '"0o"' in code
		assert "toString(8)" in code

	def test_fstring_format_spec_exponential(self):
		@javascript
		def f(x):
			return f"{x:.2e}"

		code = f.transpile()
		assert "toExponential(2)" in code

	def test_fstring_conversion_str(self):
		@javascript
		def f(x):
			return f"{x!s}"

		code = f.transpile()
		assert "String(x)" in code

	def test_fstring_conversion_repr(self):
		@javascript
		def f(x):
			return f"{x!r}"

		code = f.transpile()
		assert "JSON.stringify(x)" in code

	def test_fstring_format_spec_custom_fill(self):
		@javascript
		def f(x):
			return f"{x:*>10}"

		code = f.transpile()
		assert "padStart(10" in code
		assert '"*"' in code


# =============================================================================
# Arrays (Lists/Tuples)
# =============================================================================


class TestArrays:
	"""Test array/list transpilation."""

	def test_subscript_access(self):
		@javascript
		def f(arr):
			return arr[0]

		code = f.transpile()
		assert "arr[0]" in code

	def test_list_comprehension_map(self):
		@javascript
		def f(xs):
			return [x + 1 for x in xs]

		code = f.transpile()
		assert "xs.map(x => x + 1)" in code

	def test_list_literal(self):
		@javascript
		def f():
			return [1, 2, 3]

		code = f.transpile()
		assert "[1, 2, 3]" in code

	def test_tuple_literal_emits_array(self):
		@javascript
		def f(x):
			return (1, x)

		code = f.transpile()
		assert "[1, x]" in code

	def test_singleton_tuple_emits_array(self):
		@javascript
		def f(x):
			return (x,)

		code = f.transpile()
		assert "[x]" in code

	def test_list_literal_with_spread(self):
		@javascript
		def f(a):
			return [1, *a, 3]

		code = f.transpile()
		assert "[1, ...a, 3]" in code

	def test_tuple_spread_mixed_sources(self):
		@javascript
		def f(a, b):
			return (*a, 2, *b)

		code = f.transpile()
		assert "[...a, 2, ...b]" in code

	def test_slice_range(self):
		@javascript
		def f(a):
			return a[1:3]

		code = f.transpile()
		assert "a.slice(1, 3)" in code

	def test_slice_prefix(self):
		@javascript
		def f(a):
			return a[:2]

		code = f.transpile()
		assert "a.slice(0, 2)" in code

	def test_slice_suffix(self):
		@javascript
		def f(a):
			return a[2:]

		code = f.transpile()
		assert "a.slice(2)" in code

	def test_slice_negative_suffix(self):
		@javascript
		def f(a):
			return a[-2:]

		code = f.transpile()
		assert "a.slice(-2)" in code

	def test_slice_negative_prefix(self):
		@javascript
		def f(a):
			return a[:-1]

		code = f.transpile()
		assert "a.slice(0, -1)" in code

	def test_index_negative_one(self):
		@javascript
		def f(a):
			return a[-1]

		code = f.transpile()
		assert "a.at(-1)" in code

	def test_index_negative_variable_uses_at(self):
		@javascript
		def f(a, i):
			return a[-i]

		code = f.transpile()
		assert "a.at(-i)" in code

	def test_in_membership(self):
		@javascript
		def f(a):
			return 2 in a

		code = f.transpile()
		# Should have membership test with runtime checks
		assert ".includes(" in code or ".has(" in code or " in " in code

	def test_not_in_membership(self):
		@javascript
		def f(a):
			return 2 not in a

		code = f.transpile()
		assert "!" in code


# =============================================================================
# Strings
# =============================================================================


class TestStrings:
	"""Test string transpilation."""

	def test_constant_string_escapes_quote_and_backslash(self):
		@javascript
		def f():
			return 'a"b\\c'

		code = f.transpile()
		# Should escape " and \ in the string
		assert '\\"' in code or '\\"' in code

	def test_membership_in_string(self):
		@javascript
		def f(s):
			return "x" in s

		code = f.transpile()
		# Should have string membership check
		assert ".includes(" in code or "typeof" in code


# =============================================================================
# Dicts
# =============================================================================


class TestDicts:
	"""Test dict transpilation."""

	def test_dict_literal(self):
		@javascript
		def f(x):
			return {"a": 1, "b": x}

		code = f.transpile()
		assert "new Map" in code
		assert '"a"' in code
		assert '"b"' in code

	def test_dynamic_dict_key(self):
		@javascript
		def f(k, v):
			return {k: v}

		code = f.transpile()
		assert "new Map" in code

	def test_dict_unpacking(self):
		@javascript
		def f(a, b):
			return {"x": 1, **a, **b, "y": 2}

		code = f.transpile()
		assert "new Map" in code
		assert "..." in code  # Spread operator

	def test_dict_comprehension_simple(self):
		@javascript
		def f(xs):
			return {x: x + 1 for x in xs}

		code = f.transpile()
		assert "new Map" in code
		assert ".map(" in code


# =============================================================================
# Sets
# =============================================================================


class TestSets:
	"""Test set transpilation."""

	def test_set_comprehension_simple(self):
		@javascript
		def f(xs):
			return {x + 1 for x in xs if x > 0}

		code = f.transpile()
		assert "new Set" in code
		assert ".filter(" in code
		assert ".map(" in code


# =============================================================================
# Objects
# =============================================================================


class TestObjects:
	"""Test object/attribute transpilation."""

	def test_attribute_access(self):
		@javascript
		def f(obj):
			return obj.value

		code = f.transpile()
		assert "obj.value" in code


# =============================================================================
# Lambdas
# =============================================================================


class TestLambdas:
	"""Test lambda transpilation."""

	def test_simple_lambda(self):
		@javascript
		def f(x):
			fn = lambda y: y + 1  # noqa: E731
			return fn(x)

		code = f.transpile()
		assert "y => y + 1" in code

	def test_multi_arg_lambda(self):
		@javascript
		def f():
			fn = lambda a, b: a + b  # noqa: E731
			return fn(1, 2)

		code = f.transpile()
		assert "(a, b) => a + b" in code

	def test_no_arg_lambda(self):
		@javascript
		def f():
			fn = lambda: 42  # noqa: E731
			return fn()

		code = f.transpile()
		assert "() => 42" in code


# =============================================================================
# Comprehensions
# =============================================================================


class TestComprehensions:
	"""Test comprehension transpilation."""

	def test_list_comprehension(self):
		@javascript
		def f(nums):
			return [x * 2 for x in nums]

		code = f.transpile()
		assert ".map(" in code
		assert "x * 2" in code

	def test_list_comprehension_with_filter(self):
		@javascript
		def f(nums):
			return [x for x in nums if x % 2 == 0]

		code = f.transpile()
		assert ".filter(" in code
		assert ".map(" in code

	def test_nested_comprehension(self):
		@javascript
		def f(xss):
			return [x for xs in xss for x in xs]

		code = f.transpile()
		assert ".flatMap(" in code
		assert ".map(" in code

	def test_generator_expression(self):
		# Generator expressions are transpiled as arrays (map chains)
		@javascript
		def f(xs):
			# Use generator directly (without list() builtin)
			return [x + 1 for x in (y for y in xs)]

		code = f.transpile()
		assert ".map(" in code


# =============================================================================
# Dependencies
# =============================================================================


class TestDependencies:
	"""Test dependency handling."""

	def test_import_dependency(self):
		from pulse.transpiler.imports import Import

		clsx = Import("clsx", "clsx")

		@javascript
		def make_class(base: str, extra: str) -> str:
			return clsx(base, extra)

		code = make_class.transpile()
		# The import should be renamed to its js_name
		assert clsx.js_name in code

	def test_function_dependency(self):
		@javascript
		def helper(x: int) -> int:
			return x * 2

		@javascript
		def main(x: int) -> int:
			return helper(x) + 1

		code = main.transpile()
		# The helper function should be renamed to its js_name
		assert helper.js_name in code

	def test_constant_dependency(self):
		MULTIPLIER = 10

		@javascript
		def f(x):
			return x * MULTIPLIER

		code = f.transpile()
		# The constant should be renamed to its js_name
		assert "MULTIPLIER_" in code


# =============================================================================
# Import Usage in Transpiled Code
# =============================================================================


class TestImportTranspilation:
	"""Test Import usage scenarios within transpiled functions."""

	def test_import_called_as_function_no_args(self):
		"""Import called as function with no arguments."""
		from pulse.transpiler.imports import Import

		init = Import("init", "./utils")

		@javascript
		def setup():
			return init()

		code = setup.transpile()
		assert f"{init.js_name}()" in code

	def test_import_called_as_function_with_args(self):
		"""Import called as function with various argument types."""
		from pulse.transpiler.imports import Import

		process = Import("process", "./utils")

		@javascript
		def run(x: int, name: str):
			return process(x, name, True, None)

		code = run.transpile()
		assert f"{process.js_name}(x, name, true, undefined)" in code

	def test_import_called_with_string_literals(self):
		"""Import called with string literal arguments."""
		from pulse.transpiler.imports import Import

		clsx = Import("clsx", "clsx")

		@javascript
		def make_class():
			return clsx("p-4", "bg-red")

		code = make_class.transpile()
		assert f'{clsx.js_name}("p-4", "bg-red")' in code

	def test_import_attribute_access(self):
		"""Import with attribute/property access."""
		from pulse.transpiler.imports import Import

		styles = Import("styles", "./app.module.css")

		@javascript
		def get_class():
			return styles.container

		code = get_class.transpile()
		assert f"{styles.js_name}.container" in code

	def test_import_nested_attribute_access(self):
		"""Import with nested attribute access."""
		from pulse.transpiler.imports import Import

		config = Import("config", "./config")

		@javascript
		def get_setting():
			return config.settings.theme

		code = get_setting.transpile()
		assert f"{config.js_name}.settings.theme" in code

	def test_import_subscript_access_with_variable(self):
		"""Import with subscript access using a variable."""
		from pulse.transpiler.imports import Import

		data = Import("data", "./data")

		@javascript
		def get_item(key: str):
			return data[key]

		code = get_item.transpile()
		assert f"{data.js_name}[key]" in code

	def test_import_subscript_access_with_literal(self):
		"""Import with subscript access using a string literal."""
		from pulse.transpiler.imports import Import

		translations = Import("translations", "./i18n")

		@javascript
		def get_greeting():
			return translations["hello"]

		code = get_greeting.transpile()
		assert f'{translations.js_name}["hello"]' in code

	def test_import_subscript_access_with_number(self):
		"""Import with subscript access using a number."""
		from pulse.transpiler.imports import Import

		items = Import("items", "./data")

		@javascript
		def get_first():
			return items[0]

		code = get_first.transpile()
		assert f"{items.js_name}[0]" in code

	def test_import_passed_as_argument(self):
		"""Import passed as argument to another function."""
		from pulse.transpiler.imports import Import

		Button = Import("Button", "@mantine/core")
		createElement = Import("createElement", "react")

		@javascript
		def render():
			return createElement(Button, None)

		code = render.transpile()
		assert f"{createElement.js_name}({Button.js_name}, undefined)" in code

	def test_import_passed_to_javascript_function(self):
		"""Import passed as argument to a @javascript function."""
		from pulse.transpiler.imports import Import

		config = Import("config", "./config")

		@javascript
		def process_config(cfg):
			return cfg.value

		@javascript
		def main():
			return process_config(config)

		code = main.transpile()
		assert f"{process_config.js_name}({config.js_name})" in code

	def test_import_method_call(self):
		"""Import with method call."""
		from pulse.transpiler.imports import Import

		api = Import("api", "./api")

		@javascript
		def fetch_data(id: int):
			return api.get(id)

		code = fetch_data.transpile()
		assert f"{api.js_name}.get(id)" in code

	def test_import_method_call_with_multiple_args(self):
		"""Import with method call with multiple arguments."""
		from pulse.transpiler.imports import Import

		client = Import("client", "./client")

		@javascript
		def send_request(url: str, data: dict):
			return client.post(url, data, True)

		code = send_request.transpile()
		assert f"{client.js_name}.post(url, data, true)" in code

	def test_import_chained_method_calls(self):
		"""Import with chained method calls."""
		from pulse.transpiler.imports import Import

		builder = Import("builder", "./builder")

		@javascript
		def build_query():
			return builder.select("*").from_table("users")

		code = build_query.transpile()
		assert f'{builder.js_name}.select("*").from_table("users")' in code

	def test_import_in_binary_operation(self):
		"""Import used in binary operations."""
		from pulse.transpiler.imports import Import

		BASE_VALUE = Import("BASE_VALUE", "./constants")

		@javascript
		def calculate(x: int):
			return x + BASE_VALUE

		code = calculate.transpile()
		assert f"x + {BASE_VALUE.js_name}" in code

	def test_import_in_comparison(self):
		"""Import used in comparison."""
		from pulse.transpiler.imports import Import

		MAX_VALUE = Import("MAX_VALUE", "./constants")

		@javascript
		def is_valid(x: int):
			return x < MAX_VALUE

		code = is_valid.transpile()
		assert f"x < {MAX_VALUE.js_name}" in code

	def test_import_in_ternary(self):
		"""Import used in conditional expression."""
		from pulse.transpiler.imports import Import

		DEFAULT = Import("DEFAULT", "./constants")

		@javascript
		def get_value(x: int):
			return x if x > 0 else DEFAULT

		code = get_value.transpile()
		assert DEFAULT.js_name in code
		# Python ternary becomes JS ternary
		assert "?" in code

	def test_import_in_list_literal(self):
		"""Import used within a list literal."""
		from pulse.transpiler.imports import Import

		item1 = Import("item1", "./items")
		item2 = Import("item2", "./items")

		@javascript
		def get_items():
			return [item1, item2]

		code = get_items.transpile()
		assert f"[{item1.js_name}, {item2.js_name}]" in code

	def test_import_in_dict_literal(self):
		"""Import used within a dict literal (transpiles to Map)."""
		from pulse.transpiler.imports import Import

		handler = Import("handler", "./handlers")

		@javascript
		def get_config():
			return {"onClick": handler}

		code = get_config.transpile()
		# Python dicts transpile to JS Map
		assert f'["onClick", {handler.js_name}]' in code

	def test_import_assigned_to_variable(self):
		"""Import assigned to a local variable."""
		from pulse.transpiler.imports import Import

		utils = Import("utils", "./utils")

		@javascript
		def process():
			helper = utils.helper
			return helper()

		code = process.transpile()
		assert f"helper = {utils.js_name}.helper" in code
		assert "helper()" in code

	def test_multiple_imports_same_function(self):
		"""Multiple different imports used in the same function."""
		from pulse.transpiler.imports import Import

		Button = Import("Button", "@mantine/core")
		Icon = Import("Icon", "@mantine/core")
		styles = Import("styles", "./styles.module.css")

		@javascript
		def render():
			return {"btn": Button, "icon": Icon, "class": styles.container}

		code = render.transpile()
		imports = render.imports()
		assert Button.js_name in code
		assert Icon.js_name in code
		assert f"{styles.js_name}.container" in code
		assert len(imports) == 3

	def test_default_import(self):
		"""Default import usage."""
		from pulse.transpiler.imports import Import

		React = Import.default("React", "react")

		@javascript
		def use_react():
			return React.createElement("div", None)

		code = use_react.transpile()
		imports = use_react.imports()
		assert f"{React.js_name}.createElement" in code
		assert imports["React"].is_default


# =============================================================================
# Comparisons
# =============================================================================


class TestComparisons:
	"""Test comparison transpilation."""

	def test_equality(self):
		@javascript
		def f(a, b):
			return a == b

		code = f.transpile()
		assert "a === b" in code

	def test_not_equal(self):
		@javascript
		def f(a, b):
			return a != b

		code = f.transpile()
		assert "a !== b" in code

	def test_less_than(self):
		@javascript
		def f(a, b):
			return a < b

		code = f.transpile()
		assert "a < b" in code

	def test_greater_than(self):
		@javascript
		def f(a, b):
			return a > b

		code = f.transpile()
		assert "a > b" in code

	def test_less_equal(self):
		@javascript
		def f(a, b):
			return a <= b

		code = f.transpile()
		assert "a <= b" in code

	def test_greater_equal(self):
		@javascript
		def f(a, b):
			return a >= b

		code = f.transpile()
		assert "a >= b" in code

	def test_chained_comparison(self):
		@javascript
		def f(x, lo, hi):
			return lo <= x <= hi

		code = f.transpile()
		assert "lo <= x" in code
		assert "x <= hi" in code
		assert "&&" in code


# =============================================================================
# Literals
# =============================================================================


class TestLiterals:
	"""Test literal value transpilation."""

	def test_string_literal(self):
		@javascript
		def f():
			return "hello"

		code = f.transpile()
		assert '"hello"' in code

	def test_number_literal(self):
		@javascript
		def f():
			return 42

		code = f.transpile()
		assert "42" in code

	def test_float_literal(self):
		@javascript
		def f():
			return 3.14

		code = f.transpile()
		assert "3.14" in code

	def test_boolean_true(self):
		@javascript
		def f():
			return True

		code = f.transpile()
		assert "true" in code

	def test_boolean_false(self):
		@javascript
		def f():
			return False

		code = f.transpile()
		assert "false" in code

	def test_none_to_undefined(self):
		@javascript
		def f():
			return None

		code = f.transpile()
		assert "undefined" in code

	def test_list_literal(self):
		@javascript
		def f():
			return [1, 2, 3]

		code = f.transpile()
		assert "[1, 2, 3]" in code

	def test_empty_list(self):
		@javascript
		def f():
			return []

		code = f.transpile()
		assert "[]" in code

	def test_set_literal(self):
		@javascript
		def f():
			return {1, 2, 3}

		code = f.transpile()
		assert "new Set" in code


# =============================================================================
# Builtin Functions
# =============================================================================


class TestBuiltins:
	"""Test Python builtin function transpilation."""

	def test_print(self):
		@javascript
		def f(x):
			print(x)
			return x

		code = f.transpile()
		assert "console.log(x)" in code

	def test_print_multiple_args(self):
		@javascript
		def f(a, b):
			print(a, b)

		code = f.transpile()
		assert "console.log(a, b)" in code

	def test_len_array(self):
		@javascript
		def f(x):
			return len(x)

		code = f.transpile()
		assert "x.length ?? x.size" in code

	def test_min(self):
		@javascript
		def f(a, b):
			return min(a, b)

		code = f.transpile()
		assert "Math.min(a, b)" in code

	def test_max(self):
		@javascript
		def f(a, b, c):
			return max(a, b, c)

		code = f.transpile()
		assert "Math.max(a, b, c)" in code

	def test_abs(self):
		@javascript
		def f(x):
			return abs(x)

		code = f.transpile()
		assert "Math.abs(x)" in code

	def test_round_one_arg(self):
		@javascript
		def f(x):
			return round(x)

		code = f.transpile()
		assert "Math.round(x)" in code

	def test_str(self):
		@javascript
		def f(x):
			return str(x)

		code = f.transpile()
		assert "String(x)" in code

	def test_int_one_arg(self):
		@javascript
		def f(x):
			return int(x)

		code = f.transpile()
		assert "parseInt(x)" in code

	def test_int_two_args(self):
		@javascript
		def f(x):
			return int(x, 16)

		code = f.transpile()
		assert "parseInt(x, 16)" in code

	def test_float(self):
		@javascript
		def f(x):
			return float(x)

		code = f.transpile()
		assert "parseFloat(x)" in code

	def test_bool(self):
		@javascript
		def f(x):
			return bool(x)

		code = f.transpile()
		assert "Boolean(x)" in code

	def test_set_empty(self):
		@javascript
		def f():
			return set()

		code = f.transpile()
		assert "new Set()" in code

	def test_set_from_iterable(self):
		@javascript
		def f(x):
			return set(x)

		code = f.transpile()
		assert "new Set(x)" in code

	def test_tuple_empty(self):
		@javascript
		def f():
			return tuple()

		code = f.transpile()
		assert "[]" in code

	def test_tuple_from_iterable(self):
		@javascript
		def f(x):
			return tuple(x)

		code = f.transpile()
		assert "Array.from(x)" in code

	def test_dict_empty(self):
		@javascript
		def f():
			return dict()

		code = f.transpile()
		assert "new Map()" in code

	def test_dict_from_iterable(self):
		@javascript
		def f(x):
			return dict(x)

		code = f.transpile()
		assert "new Map(x)" in code

	def test_list_from_iterable(self):
		@javascript
		def f(x):
			return list(x)

		code = f.transpile()
		assert "Array.from(x)" in code

	def test_filter(self):
		@javascript
		def f(items):
			return filter(lambda x: x > 0, items)

		code = f.transpile()
		assert "items.filter" in code

	def test_map(self):
		@javascript
		def f(items):
			return map(lambda x: x * 2, items)

		code = f.transpile()
		assert "items.map" in code

	def test_reversed(self):
		@javascript
		def f(items):
			return reversed(items)

		code = f.transpile()
		assert "items.slice().reverse()" in code

	def test_enumerate(self):
		@javascript
		def f(items):
			return enumerate(items)

		code = f.transpile()
		assert "items.map" in code
		assert "[i + 0, v]" in code

	def test_enumerate_with_start(self):
		@javascript
		def f(items):
			return enumerate(items, 1)

		code = f.transpile()
		assert "[i + 1, v]" in code

	def test_range_one_arg(self):
		@javascript
		def f(n):
			return range(n)

		code = f.transpile()
		assert "Array.from" in code
		assert "Math.max(0, n)" in code

	def test_range_two_args(self):
		@javascript
		def f(start, stop):
			return range(start, stop)

		code = f.transpile()
		assert "Array.from" in code
		assert "Math.ceil" in code

	def test_range_three_args(self):
		@javascript
		def f(start, stop, step):
			return range(start, stop, step)

		code = f.transpile()
		assert "Array.from" in code
		assert "step" in code

	def test_sorted(self):
		@javascript
		def f(items):
			return sorted(items)

		code = f.transpile()
		assert "items.slice().sort" in code

	def test_zip(self):
		@javascript
		def f(a, b):
			return zip(a, b)  # noqa: B905

		code = f.transpile()
		assert "Array.from" in code
		assert "a[i]" in code
		assert "b[i]" in code

	def test_pow(self):
		@javascript
		def f(x, y):
			return pow(x, y)

		code = f.transpile()
		assert "Math.pow(x, y)" in code

	def test_chr(self):
		@javascript
		def f(x):
			return chr(x)

		code = f.transpile()
		assert "String.fromCharCode(x)" in code

	def test_ord(self):
		@javascript
		def f(x):
			return ord(x)

		code = f.transpile()
		assert "x.charCodeAt(0)" in code

	def test_any(self):
		@javascript
		def f(items):
			return any(items)

		code = f.transpile()
		assert "items.some" in code

	def test_all(self):
		@javascript
		def f(items):
			return all(items)

		code = f.transpile()
		assert "items.every" in code

	def test_sum(self):
		@javascript
		def f(items):
			return sum(items)

		code = f.transpile()
		assert "items.reduce" in code
		assert "a + b" in code

	def test_sum_with_start(self):
		@javascript
		def f(items):
			return sum(items, 10)

		code = f.transpile()
		assert "items.reduce" in code
		assert "10" in code

	def test_divmod(self):
		@javascript
		def f(x, y):
			return divmod(x, y)

		code = f.transpile()
		assert "Math.floor" in code

	def test_builtin_in_expression(self):
		"""Test that builtins can be used within expressions."""

		@javascript
		def f(items):
			return len(items) + 1

		code = f.transpile()
		assert "(items.length ?? items.size) + 1" in code

	def test_nested_builtin_calls(self):
		"""Test that builtins can be nested."""

		@javascript
		def f(x):
			return abs(min(x, 0))

		code = f.transpile()
		assert "Math.abs(Math.min(x, 0))" in code


# =============================================================================
# Builtin Methods
# =============================================================================


class TestBuiltinMethods:
	"""Test Python builtin method transpilation."""

	# String methods

	def test_str_lower(self):
		@javascript
		def f(s):
			return s.lower()

		code = f.transpile()
		assert "s.toLowerCase()" in code

	def test_str_upper(self):
		@javascript
		def f(s):
			return s.upper()

		code = f.transpile()
		assert "s.toUpperCase()" in code

	def test_str_strip(self):
		@javascript
		def f(s):
			return s.strip()

		code = f.transpile()
		assert "s.trim()" in code

	def test_str_lstrip(self):
		@javascript
		def f(s):
			return s.lstrip()

		code = f.transpile()
		assert "s.trimStart()" in code

	def test_str_rstrip(self):
		@javascript
		def f(s):
			return s.rstrip()

		code = f.transpile()
		assert "s.trimEnd()" in code

	def test_str_zfill(self):
		@javascript
		def f(s):
			return s.zfill(5)

		code = f.transpile()
		assert 's.padStart(5, "0")' in code

	def test_str_startswith(self):
		@javascript
		def f(s, prefix):
			return s.startswith(prefix)

		code = f.transpile()
		assert "s.startsWith(prefix)" in code

	def test_str_endswith(self):
		@javascript
		def f(s, suffix):
			return s.endswith(suffix)

		code = f.transpile()
		assert "s.endsWith(suffix)" in code

	def test_str_replace(self):
		@javascript
		def f(s, old, new):
			return s.replace(old, new)

		code = f.transpile()
		assert "s.replaceAll(old, new)" in code

	def test_str_capitalize(self):
		@javascript
		def f(s):
			return s.capitalize()

		code = f.transpile()
		assert "s.charAt(0).toUpperCase()" in code
		assert "s.slice(1).toLowerCase()" in code

	def test_str_join(self):
		@javascript
		def f(sep, items):
			return sep.join(items)

		code = f.transpile()
		assert "items.join(sep)" in code

	def test_str_split(self):
		"""str.split doesn't need transformation - uses default method call."""

		@javascript
		def f(s, sep):
			return s.split(sep)

		code = f.transpile()
		assert "s.split(sep)" in code

	# List methods

	def test_list_append(self):
		@javascript
		def f(items, x):
			items.append(x)
			return items

		code = f.transpile()
		assert "items.push(x)" in code

	def test_list_extend(self):
		@javascript
		def f(items, more):
			items.extend(more)
			return items

		code = f.transpile()
		assert "items.push(...more)" in code

	def test_list_copy(self):
		@javascript
		def f(items):
			return items.copy()

		code = f.transpile()
		assert "items.slice()" in code

	def test_list_count(self):
		@javascript
		def f(items, value):
			return items.count(value)

		code = f.transpile()
		assert "items.filter" in code
		assert "v === value" in code
		assert ".length" in code

	def test_list_index(self):
		@javascript
		def f(items, value):
			return items.index(value)

		code = f.transpile()
		assert "items.indexOf(value)" in code

	def test_list_reverse_method(self):
		@javascript
		def f(items):
			items.reverse()
			return items

		code = f.transpile()
		assert "items.reverse()" in code

	def test_list_sort_method(self):
		@javascript
		def f(items):
			items.sort()
			return items

		code = f.transpile()
		assert "items.sort()" in code

	# Dict methods (for Map)

	def test_dict_keys(self):
		@javascript
		def f(d):
			return d.keys()

		code = f.transpile()
		assert "[...d.keys()]" in code

	def test_dict_values(self):
		@javascript
		def f(d):
			return d.values()

		code = f.transpile()
		assert "[...d.values()]" in code

	def test_dict_items(self):
		@javascript
		def f(d):
			return d.items()

		code = f.transpile()
		assert "[...d.entries()]" in code

	def test_dict_get_with_default(self):
		@javascript
		def f(d, key):
			return d.get(key, 0)

		code = f.transpile()
		assert "d.get(key) ?? 0" in code

	def test_dict_get_without_default(self):
		"""dict.get without default uses regular .get() call."""

		@javascript
		def f(d, key):
			return d.get(key)

		code = f.transpile()
		assert "d.get(key)" in code

	# Set methods

	def test_set_remove(self):
		@javascript
		def f(s, value):
			return s.remove(value)

		code = f.transpile()
		assert "s.delete(value)" in code

	def test_set_add(self):
		"""set.add doesn't need transformation."""

		@javascript
		def f(s, value):
			return s.add(value)

		code = f.transpile()
		assert "s.add(value)" in code

	def test_set_clear(self):
		"""set.clear doesn't need transformation."""

		@javascript
		def f(s):
			return s.clear()

		code = f.transpile()
		assert "s.clear()" in code


# =============================================================================
# Python Module Transpilation
# =============================================================================


class TestPyModules:
	"""Test Python module transpilation (e.g., math module)."""

	def test_math_sqrt(self):
		"""Test math.sqrt() transpilation."""
		import math

		@javascript
		def f(x):
			return math.sqrt(x)

		code = f.transpile()
		assert "Math.sqrt(x)" in code

	def test_math_sin(self):
		"""Test math.sin() transpilation."""
		import math

		@javascript
		def f(x):
			return math.sin(x)

		code = f.transpile()
		assert "Math.sin(x)" in code

	def test_math_cos(self):
		"""Test math.cos() transpilation."""
		import math

		@javascript
		def f(x):
			return math.cos(x)

		code = f.transpile()
		assert "Math.cos(x)" in code

	def test_math_log(self):
		"""Test math.log() transpilation."""
		import math

		@javascript
		def f(x):
			return math.log(x)

		code = f.transpile()
		assert "Math.log(x)" in code

	def test_math_log_with_base(self):
		"""Test math.log(x, base) transpilation."""
		import math

		@javascript
		def f(x):
			return math.log(x, 10)

		code = f.transpile()
		assert "Math.log(x)" in code
		assert "Math.log(10)" in code

	def test_math_floor(self):
		"""Test math.floor() transpilation."""
		import math

		@javascript
		def f(x):
			return math.floor(x)

		code = f.transpile()
		assert "Math.floor(x)" in code

	def test_math_ceil(self):
		"""Test math.ceil() transpilation."""
		import math

		@javascript
		def f(x):
			return math.ceil(x)

		code = f.transpile()
		assert "Math.ceil(x)" in code

	def test_math_pi_constant(self):
		"""Test math.pi constant transpilation."""
		import math

		@javascript
		def f(r):
			return math.pi * r * r

		code = f.transpile()
		assert "Math.PI" in code

	def test_math_e_constant(self):
		"""Test math.e constant transpilation."""
		import math

		@javascript
		def f(x):
			return math.e**x

		code = f.transpile()
		assert "Math.E" in code

	def test_math_pow(self):
		"""Test math.pow() transpilation."""
		import math

		@javascript
		def f(x, y):
			return math.pow(x, y)

		code = f.transpile()
		assert "Math.pow(x, y)" in code

	def test_math_hypot(self):
		"""Test math.hypot() transpilation."""
		import math

		@javascript
		def f(x, y):
			return math.hypot(x, y)

		code = f.transpile()
		assert "Math.hypot(x, y)" in code

	def test_math_radians(self):
		"""Test math.radians() transpilation."""
		import math

		@javascript
		def f(degrees):
			return math.radians(degrees)

		code = f.transpile()
		assert "Math.PI" in code
		assert "180" in code

	def test_math_degrees(self):
		"""Test math.degrees() transpilation."""
		import math

		@javascript
		def f(radians):
			return math.degrees(radians)

		code = f.transpile()
		assert "Math.PI" in code
		assert "180" in code

	def test_math_isnan(self):
		"""Test math.isnan() transpilation."""
		import math

		@javascript
		def f(x):
			return math.isnan(x)

		code = f.transpile()
		assert "Number.isNaN(x)" in code

	def test_math_isfinite(self):
		"""Test math.isfinite() transpilation."""
		import math

		@javascript
		def f(x):
			return math.isfinite(x)

		code = f.transpile()
		assert "Number.isFinite(x)" in code

	def test_math_trunc(self):
		"""Test math.trunc() transpilation."""
		import math

		@javascript
		def f(x):
			return math.trunc(x)

		code = f.transpile()
		assert "Math.trunc(x)" in code

	def test_math_combined_expression(self):
		"""Test combined math expressions."""
		import math

		@javascript
		def f(x, y):
			return math.sqrt(x * x + y * y)

		code = f.transpile()
		assert "Math.sqrt(x * x + y * y)" in code


class TestReModule:
	"""Test Python re module transpilation."""

	def test_re_match(self):
		"""Test re.match() transpilation - anchors at start."""
		import re

		@javascript
		def f(s):
			return re.match(r"\d+", s)

		code = f.transpile()
		# Should anchor at start with ^
		assert 's.match(new RegExp("^\\\\d+"))' in code

	def test_re_search(self):
		"""Test re.search() transpilation."""
		import re

		@javascript
		def f(s):
			return re.search(r"\d+", s)

		code = f.transpile()
		assert 'new RegExp("\\\\d+").exec(s)' in code

	def test_re_fullmatch(self):
		"""Test re.fullmatch() transpilation - anchors at both ends."""
		import re

		@javascript
		def f(s):
			return re.fullmatch(r"\d+", s)

		code = f.transpile()
		# Should anchor at both ends with ^ and $
		assert 's.match(new RegExp("^\\\\d+$"))' in code

	def test_re_sub_replace_all(self):
		"""Test re.sub() transpilation - default replaces all."""
		import re

		@javascript
		def f(s):
			return re.sub(r"\s+", " ", s)

		code = f.transpile()
		# Should use global flag for replace all
		assert 's.replace(new RegExp("\\\\s+", "g"), " ")' in code

	def test_re_sub_replace_first(self):
		"""Test re.sub() with count=1 transpilation."""
		import re

		@javascript
		def f(s):
			return re.sub(r"\s+", " ", s, count=1)

		code = f.transpile()
		# Should NOT use global flag for replace first
		assert 's.replace(new RegExp("\\\\s+"), " ")' in code

	def test_re_split(self):
		"""Test re.split() transpilation."""
		import re

		@javascript
		def f(s):
			return re.split(r"\s+", s)

		code = f.transpile()
		assert 's.split(new RegExp("\\\\s+"))' in code

	def test_re_split_with_maxsplit(self):
		"""Test re.split() with maxsplit transpilation."""
		import re

		@javascript
		def f(s):
			return re.split(r"\s+", s, maxsplit=2)

		code = f.transpile()
		# Python maxsplit=2 means 3 parts, so JS limit=3
		assert 's.split(new RegExp("\\\\s+"), 3)' in code

	def test_re_findall(self):
		"""Test re.findall() transpilation."""
		import re

		@javascript
		def f(s):
			return re.findall(r"\d+", s)

		code = f.transpile()
		# Should use matchAll with spread and map
		assert 'matchAll(new RegExp("\\\\d+", "g"))' in code
		assert ".map(m => m[0])" in code

	def test_re_compile(self):
		"""Test re.compile() transpilation."""
		import re

		@javascript
		def f():
			return re.compile(r"\d+")

		code = f.transpile()
		assert 'new RegExp("\\\\d+")' in code

	def test_re_flag_ignorecase(self):
		"""Test re.I / re.IGNORECASE flag."""
		import re

		@javascript
		def f(s):
			return re.search(r"hello", s, re.I)

		code = f.transpile()
		assert 'new RegExp("hello", "i")' in code

	def test_re_flag_multiline(self):
		"""Test re.M / re.MULTILINE flag."""
		import re

		@javascript
		def f(s):
			return re.search(r"^hello", s, re.M)

		code = f.transpile()
		assert 'new RegExp("^hello", "m")' in code

	def test_re_flag_dotall(self):
		"""Test re.S / re.DOTALL flag."""
		import re

		@javascript
		def f(s):
			return re.search(r"a.b", s, re.S)

		code = f.transpile()
		assert 'new RegExp("a.b", "s")' in code

	def test_re_named_group_conversion(self):
		"""Test Python named group (?P<name>...) converts to JS (?<name>...)."""
		import re

		@javascript
		def f(s):
			return re.match(r"(?P<word>\w+)", s)

		code = f.transpile()
		# Python's (?P<word>...) should become JS's (?<word>...)
		assert "(?<word>" in code
		assert "(?P<" not in code

	def test_re_named_backref_conversion(self):
		"""Test Python named backref (?P=name) converts to JS \\k<name>."""
		import re

		@javascript
		def f(s):
			return re.match(r"(?P<word>\w+)\s+(?P=word)", s)

		code = f.transpile()
		# Python's (?P=word) should become JS's \k<word>
		assert "\\\\k<word>" in code
		assert "(?P=" not in code

	def test_re_replacement_backref_conversion(self):
		"""Test Python replacement \\g<name> converts to JS $<name>."""
		import re

		@javascript
		def f(s):
			return re.sub(r"(\w+)", r"\g<1>!", s)

		code = f.transpile()
		# Python's \g<1> should become JS's $<1>
		assert "$<1>!" in code
		assert "\\\\g<" not in code

	def test_re_escape(self):
		"""Test re.escape() transpilation."""
		import re

		@javascript
		def f(s):
			return re.escape(s)

		code = f.transpile()
		assert "s.replace(" in code
		assert "\\\\$&" in code

	def test_re_test_convenience(self):
		"""Test re.test() convenience method (returns boolean)."""
		import re

		@javascript
		def f(s):
			return re.test(r"\d+", s)

		code = f.transpile()
		# Should use RegExp.test() for boolean result
		assert ".test(s)" in code

	def test_function_name_in_output(self):
		"""Test that transpiled functions include their JS name."""

		@javascript
		def my_function(x):
			return x + 1

		code = my_function.transpile()
		# Function should be named with its js_name
		assert f"function {my_function.js_name}" in code
		assert "return x + 1" in code
		# Should not be anonymous
		assert "function(" not in code or code.index(
			f"function {my_function.js_name}"
		) < code.index("function(")

	def test_js_function_def_with_name(self):
		"""Test JSFunctionDef emits name when provided."""
		from pulse.transpiler.nodes import JSFunctionDef, JSNumber, JSReturn

		# Named function
		named_fn = JSFunctionDef(
			params=["x"], body=[JSReturn(JSNumber(42))], name="myFunction"
		)
		code = named_fn.emit()
		assert code == "function myFunction(x){\nreturn 42;\n}"
		assert "function myFunction" in code

	def test_js_function_def_without_name(self):
		"""Test JSFunctionDef emits anonymous function when name is None."""
		from pulse.transpiler.nodes import JSFunctionDef, JSNumber, JSReturn

		# Anonymous function
		anon_fn = JSFunctionDef(params=["x"], body=[JSReturn(JSNumber(42))], name=None)
		code = anon_fn.emit()
		assert code == "function(x){\nreturn 42;\n}"
		# Should be anonymous (no space between "function" and "(")
		assert code.startswith("function(")
		# Should not have a name after "function"
		assert "function " not in code


# =============================================================================
# Builtin Method Runtime Checks
# =============================================================================


class TestBuiltinMethodRuntimeChecks:
	"""Test runtime type checking for builtin methods with type-dependent behavior."""

	# -------------------------------------------------------------------------
	# Fast Path Tests: Known Literal Types (no runtime checks needed)
	# -------------------------------------------------------------------------

	def test_string_literal_method_no_runtime_check(self):
		"""String literals dispatch directly without runtime checks."""

		@javascript
		def f():
			return "hello".upper()

		code = f.transpile()
		# Should be direct call, no typeof check
		assert '"hello".toUpperCase()' in code
		assert "typeof" not in code

	def test_array_literal_method_no_runtime_check(self):
		"""Array literals dispatch directly without runtime checks."""

		@javascript
		def f():
			return [1, 2, 3].index(2)

		code = f.transpile()
		# Should be direct call, no Array.isArray check
		assert "[1, 2, 3].indexOf(2)" in code
		assert "Array.isArray" not in code

	def test_set_literal_method_no_runtime_check(self):
		"""Set constructor dispatch directly without runtime checks."""

		@javascript
		def f():
			s = set()
			return s.remove(1)

		code = f.transpile()
		# new Set() is a known type
		assert ".delete(1)" in code

	def test_map_literal_method_no_runtime_check(self):
		"""Map constructor (dict literal) dispatch directly without runtime checks."""

		@javascript
		def f():
			return {"a": 1, "b": 2}.keys()

		code = f.transpile()
		# Dict literal becomes new Map(), a known type
		assert "[...new Map" in code
		assert ".keys()]" in code
		# Should not have instanceof check wrapping it
		assert "instanceof Map ?" not in code

	# -------------------------------------------------------------------------
	# Slow Path Tests: Unknown Types (runtime checks needed)
	# -------------------------------------------------------------------------

	def test_unknown_type_string_method_has_runtime_check(self):
		"""Unknown types need runtime typeof check for string methods."""

		@javascript
		def f(s):
			return s.lower()

		code = f.transpile()
		# Should have typeof check
		assert 'typeof s === "string"' in code
		assert "s.toLowerCase()" in code

	def test_unknown_type_list_method_has_runtime_check(self):
		"""Unknown types need Array.isArray check for list methods."""

		@javascript
		def f(items):
			return items.copy()

		code = f.transpile()
		# Should have Array.isArray check
		assert "Array.isArray(items)" in code
		assert "items.slice()" in code

	def test_unknown_type_dict_method_has_runtime_check(self):
		"""Unknown types need instanceof Map check for dict methods."""

		@javascript
		def f(d):
			return d.keys()

		code = f.transpile()
		# Should have instanceof Map check
		assert "d instanceof Map" in code
		assert "[...d.keys()]" in code

	def test_unknown_type_set_method_has_runtime_check(self):
		"""Unknown types need instanceof Set check for set methods."""

		@javascript
		def f(s):
			return s.remove(1)

		code = f.transpile()
		# Should have instanceof Set check
		assert "s instanceof Set" in code
		assert "s.delete(1)" in code

	# -------------------------------------------------------------------------
	# Method Overlap Tests: Methods that exist on multiple types
	# -------------------------------------------------------------------------

	def test_copy_method_overlap_list_and_dict(self):
		"""copy() exists on both list and dict - needs ternary chain."""

		@javascript
		def f(x):
			return x.copy()

		code = f.transpile()
		# Should have checks for both Array and Map
		assert "Array.isArray(x)" in code
		assert "x instanceof Map" in code
		# List copy: .slice()
		assert "x.slice()" in code
		# Dict copy: new Map(x.entries())
		assert "new Map(x.entries())" in code

	def test_clear_method_overlap_dict_and_set(self):
		"""clear() exists on both dict and set - but both pass through."""

		@javascript
		def f(x):
			return x.clear()

		code = f.transpile()
		# Both Set and Map clear() don't need transformation,
		# so it should just be x.clear() with no ternaries
		assert "x.clear()" in code

	def test_pop_method_list_with_index(self):
		"""list.pop(index) has special handling."""

		@javascript
		def f(items, idx):
			return items.pop(idx)

		code = f.transpile()
		# Should have Array.isArray check
		assert "Array.isArray(items)" in code
		# List pop with index: splice
		assert "items.splice(idx, 1)[0]" in code

	def test_pop_method_list_without_index(self):
		"""list.pop() without index falls through to default."""

		@javascript
		def f(items):
			return items.pop()

		code = f.transpile()
		# No index means fall through to regular pop()
		assert "items.pop()" in code

	# -------------------------------------------------------------------------
	# Ternary Chain Structure Tests
	# -------------------------------------------------------------------------

	def test_ternary_chain_order(self):
		"""Methods with multiple implementations build proper ternary chain."""

		@javascript
		def f(x):
			return x.copy()

		code = f.transpile()
		# The ternary should check types in priority order
		# Array.isArray should be checked before instanceof Map
		array_pos = code.find("Array.isArray(x)")
		map_pos = code.find("x instanceof Map")
		assert array_pos != -1
		assert map_pos != -1
		# Array check comes before (is outer) Map check
		assert array_pos < map_pos

	def test_method_not_in_any_class_passes_through(self):
		"""Methods not in any builtin class pass through unchanged."""

		@javascript
		def f(x):
			return x.someCustomMethod()

		code = f.transpile()
		# Should just be a regular method call
		assert "x.someCustomMethod()" in code
		# No runtime checks
		assert "typeof" not in code
		assert "Array.isArray" not in code
		assert "instanceof" not in code

	# -------------------------------------------------------------------------
	# Edge Cases
	# -------------------------------------------------------------------------

	def test_method_on_expression_result(self):
		"""Method called on expression result (not a simple identifier)."""

		@javascript
		def f(items):
			return items[0].lower()

		code = f.transpile()
		# Should have typeof check on the subscript expression
		assert "typeof items[0]" in code or 'typeof (items[0]) === "string"' in code

	def test_chained_method_calls_with_known_type(self):
		"""Chained method calls on known types."""

		@javascript
		def f():
			return "hello".upper().lower()

		code = f.transpile()
		# First call is on known string, second is also on string
		assert '"hello".toUpperCase()' in code
		assert ".toLowerCase()" in code

	def test_string_join_reverses_receiver_and_arg(self):
		"""str.join(iterable) -> iterable.join(str)."""

		@javascript
		def f(sep, items):
			return sep.join(items)

		code = f.transpile()
		# Should reverse to items.join(sep)
		assert "items.join(sep)" in code

	def test_string_literal_join(self):
		"""String literal join should work without runtime checks."""

		@javascript
		def f(items):
			return ", ".join(items)

		code = f.transpile()
		assert 'items.join(", ")' in code
		assert "typeof" not in code


# =============================================================================
# ReactComponent JSX Transpilation
# =============================================================================


class TestReactComponentJSX:
	"""Test ReactComponent transpilation to JSX."""

	def test_component_call_with_props(self):
		"""Component(prop=value) -> <Component prop={value} />."""
		from pulse.react_component import ReactComponent

		Button = ReactComponent("Button", "@mantine/core")

		@javascript
		def f():
			return Button(variant="filled")

		code = f.transpile()
		assert "<Button" in code
		assert 'variant="filled"' in code
		assert "/>" in code

	def test_component_call_with_children(self):
		"""Component(prop=value)['child'] -> <Component prop={value}>child</Component>."""
		from pulse.react_component import ReactComponent

		Button = ReactComponent("Button", "@mantine/core")

		@javascript
		def f():
			return Button(variant="filled")["Click me"]

		code = f.transpile()
		assert "<Button" in code
		assert 'variant="filled"' in code
		assert "Click me" in code
		assert "</Button" in code

	def test_component_call_no_props_with_children(self):
		"""Component()['child'] -> <Component>child</Component>."""
		from pulse.react_component import ReactComponent

		Button = ReactComponent("Button", "@mantine/core")

		@javascript
		def f():
			return Button()["Click me"]

		code = f.transpile()
		assert "<Button" in code
		assert ">Click me</Button" in code

	def test_component_as_prop_polymorphic(self):
		"""Component(component=OtherComponent) for polymorphic 'as' patterns."""
		from pulse.react_component import ReactComponent

		Button = ReactComponent("Button", "@mantine/core")
		Link = ReactComponent("Link", "react-router-dom")

		@javascript
		def f():
			return Button(component=Link, to="/home")["Go Home"]

		code = f.transpile()
		assert "<Button" in code
		assert "component={Link" in code
		assert 'to="/home"' in code
		assert "Go Home" in code

	def test_component_as_renderRoot_prop(self):
		"""Component(renderRoot=lambda props: OtherComponent(**props))."""
		from pulse.react_component import ReactComponent

		Button = ReactComponent("Button", "@mantine/core")
		Link = ReactComponent("Link", "react-router-dom")

		@javascript
		def f():
			return Button(renderRoot=lambda props: Link(**props, to="/home"))[
				"Navigate"
			]

		code = f.transpile()
		assert "<Button" in code
		assert "renderRoot={props =>" in code
		assert "<Link" in code
		assert "{...props}" in code
		assert 'to="/home"' in code

	def test_nested_components(self):
		"""Nested component calls produce nested JSX."""
		from pulse.react_component import ReactComponent

		Stack = ReactComponent("Stack", "@mantine/core")
		Button = ReactComponent("Button", "@mantine/core")

		@javascript
		def f():
			return Stack(gap="md")[
				Button(variant="filled")["Submit"],
				Button(variant="outline")["Cancel"],
			]

		code = f.transpile()
		assert "<Stack" in code
		assert 'gap="md"' in code
		assert "<Button" in code
		assert "Submit" in code
		assert "Cancel" in code
		assert "</Stack" in code

	def test_component_with_spread_props(self):
		"""Component(**props) -> <Component {...props} />."""
		from pulse.react_component import ReactComponent

		Button = ReactComponent("Button", "@mantine/core")

		@javascript
		def f(props):
			return Button(**props)["Click"]

		code = f.transpile()
		assert "<Button" in code
		assert "{...props}" in code
		assert "Click" in code

	def test_component_with_dynamic_children(self):
		"""Component with list comprehension children."""
		from pulse.react_component import ReactComponent

		Stack = ReactComponent("Stack", "@mantine/core")
		Button = ReactComponent("Button", "@mantine/core")

		@javascript
		def f(items):
			return Stack()[*[Button()[item] for item in items]]

		code = f.transpile()
		assert "<Stack" in code
		assert "items.map(item =>" in code
		assert "<Button" in code

	def test_component_with_prop_access(self):
		"""Component with prop access like AppShell.Header."""
		from pulse.react_component import ReactComponent

		AppShellHeader = ReactComponent("AppShell", "@mantine/core", prop="Header")

		@javascript
		def f():
			return AppShellHeader()["Header Content"]

		code = f.transpile()
		assert "<AppShell" in code or "AppShell.Header" in code
		assert "Header Content" in code

	def test_component_direct_subscript_error(self):
		"""Direct subscript on ReactComponent should raise an error."""
		from pulse.react_component import ReactComponent

		Button = ReactComponent("Button", "@mantine/core")

		@javascript
		def f():
			return Button["Click me"]

		try:
			f.transpile()
			raise AssertionError("Expected JSCompilationError for direct subscript")
		except JSCompilationError as e:
			assert "Cannot subscript ReactComponent" in str(e)
