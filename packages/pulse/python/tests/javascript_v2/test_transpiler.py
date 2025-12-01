"""Tests for the JavaScript transpiler.

Adapted from the v1 transpiler tests, excluding tests that require:
- Builtin function transpilation (len, range, print, etc.)
- Builtin method transpilation with runtime type checks
"""

import warnings

from pulse.javascript_v2.errors import JSCompilationError
from pulse.javascript_v2.function import javascript
from pulse.javascript_v2.transpiler import transpile_function

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

		code = transpile_function(f)
		assert "if (x > 0)" in code
		assert "return 1" in code
		assert "else" in code
		assert "return 2" in code

	def test_conditional_expression(self):
		@javascript
		def f(x):
			return 1 if x > 0 else 2

		code = transpile_function(f)
		assert "x > 0 ? 1 : 2" in code

	def test_boolean_precedence_or(self):
		@javascript
		def f(a, b, c):
			return (a and b) or c

		code = transpile_function(f)
		assert "a && b || c" in code

	def test_nested_ternary(self):
		@javascript
		def f(x):
			return 1 if x > 0 else 2 if x < -1 else 3

		code = transpile_function(f)
		assert "x > 0 ? 1 : x < -1 ? 2 : 3" in code

	def test_unpack_tuple_assignment(self):
		@javascript
		def f(t):
			a, b = t
			return a + b

		code = transpile_function(f)
		assert "$tmp" in code  # Uses temp variable
		assert "[0]" in code
		assert "[1]" in code
		assert "a + b" in code

	def test_unpack_list_assignment_literal_rhs(self):
		@javascript
		def f():
			a, b = [1, 2]
			return a * b

		code = transpile_function(f)
		assert "[1, 2]" in code
		assert "a * b" in code

	def test_unpack_tuple_reassignment_no_let(self):
		@javascript
		def f(t):
			a, b = t
			a, b = t
			return a - b

		code = transpile_function(f)
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
			transpile_function(f)
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

		code = transpile_function(f)
		assert "let y = x + 1" in code
		assert "return y" in code

	def test_annassign_and_return(self):
		@javascript
		def f(x: int):
			y: int = x
			return y

		code = transpile_function(f)
		assert "let y = x" in code
		assert "return y" in code

	def test_reassignment_without_let(self):
		@javascript
		def f(x):
			y = x + 1
			y = y + 2
			return y

		code = transpile_function(f)
		assert "let y = x + 1" in code
		assert "y = y + 2" in code
		# Should not have 'let' on second assignment
		assert code.count("let y") == 1

	def test_param_reassignment(self):
		@javascript
		def f(x):
			x = x + 1
			return x

		code = transpile_function(f)
		assert "x = x + 1" in code
		# No 'let' for parameter reassignment
		assert "let x" not in code

	def test_augassign(self):
		@javascript
		def f(x):
			y = 1
			y += x
			return y

		code = transpile_function(f)
		assert "let y = 1" in code
		assert "y += x" in code

	def test_is_none(self):
		@javascript
		def f(x):
			return x is None

		code = transpile_function(f)
		assert "x == null" in code

	def test_is_not_none(self):
		@javascript
		def f(x):
			return x is not None

		code = transpile_function(f)
		assert "x != null" in code

	def test_simple_addition(self):
		@javascript
		def f(a, b):
			return a + b

		code = transpile_function(f)
		assert "return a + b" in code

	def test_is_with_value(self):
		@javascript
		def f(x):
			y = 5
			return x is y

		code = transpile_function(f)
		assert "x === y" in code

	def test_is_not_with_string(self):
		warnings.simplefilter("ignore", SyntaxWarning)

		@javascript
		def f(s):
			a = "a"
			return s is not a

		code = transpile_function(f)
		assert "s !== a" in code

	def test_constants_arithmetic_comparisons_boolean_ops(self):
		@javascript
		def f(x):
			return (x * 2 + 3) > 0 and not (x == 5)

		code = transpile_function(f)
		assert "x * 2 + 3 > 0" in code
		assert "&&" in code
		assert "!(x === 5)" in code

	def test_unary_minus(self):
		@javascript
		def f(x):
			return -x

		code = transpile_function(f)
		assert "-x" in code

	def test_compare_chaining(self):
		@javascript
		def f(x):
			return 0 < x < 10

		code = transpile_function(f)
		assert "0 < x" in code
		assert "x < 10" in code
		assert "&&" in code

	def test_pow_with_negative_base_parenthesized(self):
		@javascript
		def f():
			return (-2) ** 2

		code = transpile_function(f)
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

		code = transpile_function(f)
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

		code = transpile_function(f)
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

		code = transpile_function(f)
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

		code = transpile_function(f)
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

		code = transpile_function(f)
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

		code = transpile_function(f)
		assert "`value=${x}`" in code

	def test_fstring_escapes_backtick_dollar_brace_and_backslash(self):
		@javascript
		def f(x):
			return f"$`${{{x}"

		code = transpile_function(f)
		assert r"\`" in code  # Escaped backtick
		assert r"\${" in code  # Escaped ${

	def test_fstring_escapes_line_separators(self):
		@javascript
		def f():
			return "\r\n\b\t\u2028\u2029"

		code = transpile_function(f)
		# These special chars should be escaped in the template literal
		assert r"\u2028" in code or "\\u2028" in code

	def test_simple_fstring(self):
		@javascript
		def greet(name: str) -> str:
			return f"Hello, {name}!"

		code = transpile_function(greet)
		assert "`Hello, ${name}!`" in code

	def test_fstring_with_expression(self):
		@javascript
		def show_sum(a: int, b: int) -> str:
			return f"{a} + {b} = {a + b}"

		code = transpile_function(show_sum)
		assert "${a}" in code
		assert "${b}" in code
		assert "${a + b}" in code

	def test_fstring_format_spec_float_precision(self):
		@javascript
		def f(x):
			return f"{x:.2f}"

		code = transpile_function(f)
		assert "toFixed(2)" in code

	def test_fstring_format_spec_float_precision_3(self):
		@javascript
		def f(x):
			return f"{x:.3f}"

		code = transpile_function(f)
		assert "toFixed(3)" in code

	def test_fstring_format_spec_zero_padded_int(self):
		@javascript
		def f(x):
			return f"{x:05d}"

		code = transpile_function(f)
		assert "padStart(5" in code
		assert '"0"' in code

	def test_fstring_format_spec_right_align(self):
		@javascript
		def f(s):
			return f"{s:>10}"

		code = transpile_function(f)
		assert "padStart(10" in code

	def test_fstring_format_spec_left_align(self):
		@javascript
		def f(s):
			return f"{s:<10}"

		code = transpile_function(f)
		assert "padEnd(10" in code

	def test_fstring_format_spec_center_align(self):
		@javascript
		def f(s):
			return f"{s:^10}"

		code = transpile_function(f)
		# Center needs both padStart and padEnd
		assert "padStart" in code
		assert "padEnd" in code

	def test_fstring_format_spec_hex_lowercase(self):
		@javascript
		def f(x):
			return f"{x:x}"

		code = transpile_function(f)
		assert "toString(16)" in code

	def test_fstring_format_spec_hex_uppercase(self):
		@javascript
		def f(x):
			return f"{x:X}"

		code = transpile_function(f)
		assert "toString(16)" in code
		assert "toUpperCase()" in code

	def test_fstring_format_spec_hex_with_prefix(self):
		@javascript
		def f(x):
			return f"{x:#x}"

		code = transpile_function(f)
		assert '"0x"' in code
		assert "toString(16)" in code

	def test_fstring_format_spec_binary_with_prefix(self):
		@javascript
		def f(x):
			return f"{x:#b}"

		code = transpile_function(f)
		assert '"0b"' in code
		assert "toString(2)" in code

	def test_fstring_format_spec_octal_with_prefix(self):
		@javascript
		def f(x):
			return f"{x:#o}"

		code = transpile_function(f)
		assert '"0o"' in code
		assert "toString(8)" in code

	def test_fstring_format_spec_exponential(self):
		@javascript
		def f(x):
			return f"{x:.2e}"

		code = transpile_function(f)
		assert "toExponential(2)" in code

	def test_fstring_conversion_str(self):
		@javascript
		def f(x):
			return f"{x!s}"

		code = transpile_function(f)
		assert "String(x)" in code

	def test_fstring_conversion_repr(self):
		@javascript
		def f(x):
			return f"{x!r}"

		code = transpile_function(f)
		assert "JSON.stringify(x)" in code

	def test_fstring_format_spec_custom_fill(self):
		@javascript
		def f(x):
			return f"{x:*>10}"

		code = transpile_function(f)
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

		code = transpile_function(f)
		assert "arr[0]" in code

	def test_list_comprehension_map(self):
		@javascript
		def f(xs):
			return [x + 1 for x in xs]

		code = transpile_function(f)
		assert "xs.map(x => x + 1)" in code

	def test_list_literal(self):
		@javascript
		def f():
			return [1, 2, 3]

		code = transpile_function(f)
		assert "[1, 2, 3]" in code

	def test_tuple_literal_emits_array(self):
		@javascript
		def f(x):
			return (1, x)

		code = transpile_function(f)
		assert "[1, x]" in code

	def test_singleton_tuple_emits_array(self):
		@javascript
		def f(x):
			return (x,)

		code = transpile_function(f)
		assert "[x]" in code

	def test_list_literal_with_spread(self):
		@javascript
		def f(a):
			return [1, *a, 3]

		code = transpile_function(f)
		assert "[1, ...a, 3]" in code

	def test_tuple_spread_mixed_sources(self):
		@javascript
		def f(a, b):
			return (*a, 2, *b)

		code = transpile_function(f)
		assert "[...a, 2, ...b]" in code

	def test_slice_range(self):
		@javascript
		def f(a):
			return a[1:3]

		code = transpile_function(f)
		assert "a.slice(1, 3)" in code

	def test_slice_prefix(self):
		@javascript
		def f(a):
			return a[:2]

		code = transpile_function(f)
		assert "a.slice(0, 2)" in code

	def test_slice_suffix(self):
		@javascript
		def f(a):
			return a[2:]

		code = transpile_function(f)
		assert "a.slice(2)" in code

	def test_slice_negative_suffix(self):
		@javascript
		def f(a):
			return a[-2:]

		code = transpile_function(f)
		assert "a.slice(-2)" in code

	def test_slice_negative_prefix(self):
		@javascript
		def f(a):
			return a[:-1]

		code = transpile_function(f)
		assert "a.slice(0, -1)" in code

	def test_index_negative_one(self):
		@javascript
		def f(a):
			return a[-1]

		code = transpile_function(f)
		assert "a.at(-1)" in code

	def test_index_negative_variable_uses_at(self):
		@javascript
		def f(a, i):
			return a[-i]

		code = transpile_function(f)
		assert "a.at(-i)" in code

	def test_in_membership(self):
		@javascript
		def f(a):
			return 2 in a

		code = transpile_function(f)
		# Should have membership test with runtime checks
		assert ".includes(" in code or ".has(" in code or " in " in code

	def test_not_in_membership(self):
		@javascript
		def f(a):
			return 2 not in a

		code = transpile_function(f)
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

		code = transpile_function(f)
		# Should escape " and \ in the string
		assert '\\"' in code or '\\"' in code

	def test_membership_in_string(self):
		@javascript
		def f(s):
			return "x" in s

		code = transpile_function(f)
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

		code = transpile_function(f)
		assert "new Map" in code
		assert '"a"' in code
		assert '"b"' in code

	def test_dynamic_dict_key(self):
		@javascript
		def f(k, v):
			return {k: v}

		code = transpile_function(f)
		assert "new Map" in code

	def test_dict_unpacking(self):
		@javascript
		def f(a, b):
			return {"x": 1, **a, **b, "y": 2}

		code = transpile_function(f)
		assert "new Map" in code
		assert "..." in code  # Spread operator

	def test_dict_comprehension_simple(self):
		@javascript
		def f(xs):
			return {x: x + 1 for x in xs}

		code = transpile_function(f)
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

		code = transpile_function(f)
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

		code = transpile_function(f)
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

		code = transpile_function(f)
		assert "y => y + 1" in code

	def test_multi_arg_lambda(self):
		@javascript
		def f():
			fn = lambda a, b: a + b  # noqa: E731
			return fn(1, 2)

		code = transpile_function(f)
		assert "(a, b) => a + b" in code

	def test_no_arg_lambda(self):
		@javascript
		def f():
			fn = lambda: 42  # noqa: E731
			return fn()

		code = transpile_function(f)
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

		code = transpile_function(f)
		assert ".map(" in code
		assert "x * 2" in code

	def test_list_comprehension_with_filter(self):
		@javascript
		def f(nums):
			return [x for x in nums if x % 2 == 0]

		code = transpile_function(f)
		assert ".filter(" in code
		assert ".map(" in code

	def test_nested_comprehension(self):
		@javascript
		def f(xss):
			return [x for xs in xss for x in xs]

		code = transpile_function(f)
		assert ".flatMap(" in code
		assert ".map(" in code

	def test_generator_expression(self):
		# Generator expressions are transpiled as arrays (map chains)
		@javascript
		def f(xs):
			# Use generator directly (without list() builtin)
			return [x + 1 for x in (y for y in xs)]

		code = transpile_function(f)
		assert ".map(" in code


# =============================================================================
# Dependencies
# =============================================================================


class TestDependencies:
	"""Test dependency handling."""

	def test_import_dependency(self):
		from pulse.javascript_v2.imports import Import

		clsx = Import("clsx", "clsx")

		@javascript
		def make_class(base: str, extra: str) -> str:
			return clsx(base, extra)

		code = transpile_function(make_class)
		# The import should be renamed to its js_name
		assert clsx.js_name in code

	def test_function_dependency(self):
		@javascript
		def helper(x: int) -> int:
			return x * 2

		@javascript
		def main(x: int) -> int:
			return helper(x) + 1

		code = transpile_function(main)
		# The helper function should be renamed to its js_name
		assert helper.js_name in code

	def test_constant_dependency(self):
		MULTIPLIER = 10

		@javascript
		def f(x):
			return x * MULTIPLIER

		code = transpile_function(f)
		# The constant should be renamed to its js_name
		assert "MULTIPLIER_" in code


# =============================================================================
# Comparisons
# =============================================================================


class TestComparisons:
	"""Test comparison transpilation."""

	def test_equality(self):
		@javascript
		def f(a, b):
			return a == b

		code = transpile_function(f)
		assert "a === b" in code

	def test_not_equal(self):
		@javascript
		def f(a, b):
			return a != b

		code = transpile_function(f)
		assert "a !== b" in code

	def test_less_than(self):
		@javascript
		def f(a, b):
			return a < b

		code = transpile_function(f)
		assert "a < b" in code

	def test_greater_than(self):
		@javascript
		def f(a, b):
			return a > b

		code = transpile_function(f)
		assert "a > b" in code

	def test_less_equal(self):
		@javascript
		def f(a, b):
			return a <= b

		code = transpile_function(f)
		assert "a <= b" in code

	def test_greater_equal(self):
		@javascript
		def f(a, b):
			return a >= b

		code = transpile_function(f)
		assert "a >= b" in code

	def test_chained_comparison(self):
		@javascript
		def f(x, lo, hi):
			return lo <= x <= hi

		code = transpile_function(f)
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

		code = transpile_function(f)
		assert '"hello"' in code

	def test_number_literal(self):
		@javascript
		def f():
			return 42

		code = transpile_function(f)
		assert "42" in code

	def test_float_literal(self):
		@javascript
		def f():
			return 3.14

		code = transpile_function(f)
		assert "3.14" in code

	def test_boolean_true(self):
		@javascript
		def f():
			return True

		code = transpile_function(f)
		assert "true" in code

	def test_boolean_false(self):
		@javascript
		def f():
			return False

		code = transpile_function(f)
		assert "false" in code

	def test_none_to_undefined(self):
		@javascript
		def f():
			return None

		code = transpile_function(f)
		assert "undefined" in code

	def test_list_literal(self):
		@javascript
		def f():
			return [1, 2, 3]

		code = transpile_function(f)
		assert "[1, 2, 3]" in code

	def test_empty_list(self):
		@javascript
		def f():
			return []

		code = transpile_function(f)
		assert "[]" in code

	def test_set_literal(self):
		@javascript
		def f():
			return {1, 2, 3}

		code = transpile_function(f)
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

		code = transpile_function(f)
		assert "console.log(x)" in code

	def test_print_multiple_args(self):
		@javascript
		def f(a, b):
			print(a, b)

		code = transpile_function(f)
		assert "console.log(a, b)" in code

	def test_len_array(self):
		@javascript
		def f(x):
			return len(x)

		code = transpile_function(f)
		assert "x.length ?? x.size" in code

	def test_min(self):
		@javascript
		def f(a, b):
			return min(a, b)

		code = transpile_function(f)
		assert "Math.min(a, b)" in code

	def test_max(self):
		@javascript
		def f(a, b, c):
			return max(a, b, c)

		code = transpile_function(f)
		assert "Math.max(a, b, c)" in code

	def test_abs(self):
		@javascript
		def f(x):
			return abs(x)

		code = transpile_function(f)
		assert "Math.abs(x)" in code

	def test_round_one_arg(self):
		@javascript
		def f(x):
			return round(x)

		code = transpile_function(f)
		assert "Math.round(x)" in code

	def test_str(self):
		@javascript
		def f(x):
			return str(x)

		code = transpile_function(f)
		assert "String(x)" in code

	def test_int_one_arg(self):
		@javascript
		def f(x):
			return int(x)

		code = transpile_function(f)
		assert "parseInt(x)" in code

	def test_int_two_args(self):
		@javascript
		def f(x):
			return int(x, 16)

		code = transpile_function(f)
		assert "parseInt(x, 16)" in code

	def test_float(self):
		@javascript
		def f(x):
			return float(x)

		code = transpile_function(f)
		assert "parseFloat(x)" in code

	def test_bool(self):
		@javascript
		def f(x):
			return bool(x)

		code = transpile_function(f)
		assert "Boolean(x)" in code

	def test_set_empty(self):
		@javascript
		def f():
			return set()

		code = transpile_function(f)
		assert "new Set()" in code

	def test_set_from_iterable(self):
		@javascript
		def f(x):
			return set(x)

		code = transpile_function(f)
		assert "new Set(x)" in code

	def test_tuple_empty(self):
		@javascript
		def f():
			return tuple()

		code = transpile_function(f)
		assert "[]" in code

	def test_tuple_from_iterable(self):
		@javascript
		def f(x):
			return tuple(x)

		code = transpile_function(f)
		assert "Array.from(x)" in code

	def test_dict_empty(self):
		@javascript
		def f():
			return dict()

		code = transpile_function(f)
		assert "new Map()" in code

	def test_dict_from_iterable(self):
		@javascript
		def f(x):
			return dict(x)

		code = transpile_function(f)
		assert "new Map(x)" in code

	def test_list_from_iterable(self):
		@javascript
		def f(x):
			return list(x)

		code = transpile_function(f)
		assert "Array.from(x)" in code

	def test_filter(self):
		@javascript
		def f(items):
			return filter(lambda x: x > 0, items)

		code = transpile_function(f)
		assert "items.filter" in code

	def test_map(self):
		@javascript
		def f(items):
			return map(lambda x: x * 2, items)

		code = transpile_function(f)
		assert "items.map" in code

	def test_reversed(self):
		@javascript
		def f(items):
			return reversed(items)

		code = transpile_function(f)
		assert "items.slice().reverse()" in code

	def test_enumerate(self):
		@javascript
		def f(items):
			return enumerate(items)

		code = transpile_function(f)
		assert "items.map" in code
		assert "[i + 0, v]" in code

	def test_enumerate_with_start(self):
		@javascript
		def f(items):
			return enumerate(items, 1)

		code = transpile_function(f)
		assert "[i + 1, v]" in code

	def test_range_one_arg(self):
		@javascript
		def f(n):
			return range(n)

		code = transpile_function(f)
		assert "Array.from" in code
		assert "Math.max(0, n)" in code

	def test_range_two_args(self):
		@javascript
		def f(start, stop):
			return range(start, stop)

		code = transpile_function(f)
		assert "Array.from" in code
		assert "Math.ceil" in code

	def test_range_three_args(self):
		@javascript
		def f(start, stop, step):
			return range(start, stop, step)

		code = transpile_function(f)
		assert "Array.from" in code
		assert "step" in code

	def test_sorted(self):
		@javascript
		def f(items):
			return sorted(items)

		code = transpile_function(f)
		assert "items.slice().sort" in code

	def test_zip(self):
		@javascript
		def f(a, b):
			return zip(a, b)  # noqa: B905

		code = transpile_function(f)
		assert "Array.from" in code
		assert "a[i]" in code
		assert "b[i]" in code

	def test_pow(self):
		@javascript
		def f(x, y):
			return pow(x, y)

		code = transpile_function(f)
		assert "Math.pow(x, y)" in code

	def test_chr(self):
		@javascript
		def f(x):
			return chr(x)

		code = transpile_function(f)
		assert "String.fromCharCode(x)" in code

	def test_ord(self):
		@javascript
		def f(x):
			return ord(x)

		code = transpile_function(f)
		assert "x.charCodeAt(0)" in code

	def test_any(self):
		@javascript
		def f(items):
			return any(items)

		code = transpile_function(f)
		assert "items.some" in code

	def test_all(self):
		@javascript
		def f(items):
			return all(items)

		code = transpile_function(f)
		assert "items.every" in code

	def test_sum(self):
		@javascript
		def f(items):
			return sum(items)

		code = transpile_function(f)
		assert "items.reduce" in code
		assert "a + b" in code

	def test_sum_with_start(self):
		@javascript
		def f(items):
			return sum(items, 10)

		code = transpile_function(f)
		assert "items.reduce" in code
		assert "10" in code

	def test_divmod(self):
		@javascript
		def f(x, y):
			return divmod(x, y)

		code = transpile_function(f)
		assert "Math.floor" in code

	def test_builtin_in_expression(self):
		"""Test that builtins can be used within expressions."""

		@javascript
		def f(items):
			return len(items) + 1

		code = transpile_function(f)
		assert "(items.length ?? items.size) + 1" in code

	def test_nested_builtin_calls(self):
		"""Test that builtins can be nested."""

		@javascript
		def f(x):
			return abs(min(x, 0))

		code = transpile_function(f)
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

		code = transpile_function(f)
		assert "s.toLowerCase()" in code

	def test_str_upper(self):
		@javascript
		def f(s):
			return s.upper()

		code = transpile_function(f)
		assert "s.toUpperCase()" in code

	def test_str_strip(self):
		@javascript
		def f(s):
			return s.strip()

		code = transpile_function(f)
		assert "s.trim()" in code

	def test_str_lstrip(self):
		@javascript
		def f(s):
			return s.lstrip()

		code = transpile_function(f)
		assert "s.trimStart()" in code

	def test_str_rstrip(self):
		@javascript
		def f(s):
			return s.rstrip()

		code = transpile_function(f)
		assert "s.trimEnd()" in code

	def test_str_zfill(self):
		@javascript
		def f(s):
			return s.zfill(5)

		code = transpile_function(f)
		assert 's.padStart(5, "0")' in code

	def test_str_startswith(self):
		@javascript
		def f(s, prefix):
			return s.startswith(prefix)

		code = transpile_function(f)
		assert "s.startsWith(prefix)" in code

	def test_str_endswith(self):
		@javascript
		def f(s, suffix):
			return s.endswith(suffix)

		code = transpile_function(f)
		assert "s.endsWith(suffix)" in code

	def test_str_replace(self):
		@javascript
		def f(s, old, new):
			return s.replace(old, new)

		code = transpile_function(f)
		assert "s.replaceAll(old, new)" in code

	def test_str_capitalize(self):
		@javascript
		def f(s):
			return s.capitalize()

		code = transpile_function(f)
		assert "s.charAt(0).toUpperCase()" in code
		assert "s.slice(1).toLowerCase()" in code

	def test_str_join(self):
		@javascript
		def f(sep, items):
			return sep.join(items)

		code = transpile_function(f)
		assert "items.join(sep)" in code

	def test_str_split(self):
		"""str.split doesn't need transformation - uses default method call."""

		@javascript
		def f(s, sep):
			return s.split(sep)

		code = transpile_function(f)
		assert "s.split(sep)" in code

	# List methods

	def test_list_append(self):
		@javascript
		def f(items, x):
			items.append(x)
			return items

		code = transpile_function(f)
		assert "items.push(x)" in code

	def test_list_extend(self):
		@javascript
		def f(items, more):
			items.extend(more)
			return items

		code = transpile_function(f)
		assert "items.push(...more)" in code

	def test_list_copy(self):
		@javascript
		def f(items):
			return items.copy()

		code = transpile_function(f)
		assert "items.slice()" in code

	def test_list_count(self):
		@javascript
		def f(items, value):
			return items.count(value)

		code = transpile_function(f)
		assert "items.filter" in code
		assert "v === value" in code
		assert ".length" in code

	def test_list_index(self):
		@javascript
		def f(items, value):
			return items.index(value)

		code = transpile_function(f)
		assert "items.indexOf(value)" in code

	def test_list_reverse_method(self):
		@javascript
		def f(items):
			items.reverse()
			return items

		code = transpile_function(f)
		assert "items.reverse()" in code

	def test_list_sort_method(self):
		@javascript
		def f(items):
			items.sort()
			return items

		code = transpile_function(f)
		assert "items.sort()" in code

	# Dict methods (for Map)

	def test_dict_keys(self):
		@javascript
		def f(d):
			return d.keys()

		code = transpile_function(f)
		assert "[...d.keys()]" in code

	def test_dict_values(self):
		@javascript
		def f(d):
			return d.values()

		code = transpile_function(f)
		assert "[...d.values()]" in code

	def test_dict_items(self):
		@javascript
		def f(d):
			return d.items()

		code = transpile_function(f)
		assert "[...d.entries()]" in code

	def test_dict_get_with_default(self):
		@javascript
		def f(d, key):
			return d.get(key, 0)

		code = transpile_function(f)
		assert "d.get(key) ?? 0" in code

	def test_dict_get_without_default(self):
		"""dict.get without default uses regular .get() call."""

		@javascript
		def f(d, key):
			return d.get(key)

		code = transpile_function(f)
		assert "d.get(key)" in code

	# Set methods

	def test_set_remove(self):
		@javascript
		def f(s, value):
			return s.remove(value)

		code = transpile_function(f)
		assert "s.delete(value)" in code

	def test_set_add(self):
		"""set.add doesn't need transformation."""

		@javascript
		def f(s, value):
			return s.add(value)

		code = transpile_function(f)
		assert "s.add(value)" in code

	def test_set_clear(self):
		"""set.clear doesn't need transformation."""

		@javascript
		def f(s):
			return s.clear()

		code = transpile_function(f)
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

		code = transpile_function(f)
		assert "Math.sqrt(x)" in code

	def test_math_sin(self):
		"""Test math.sin() transpilation."""
		import math

		@javascript
		def f(x):
			return math.sin(x)

		code = transpile_function(f)
		assert "Math.sin(x)" in code

	def test_math_cos(self):
		"""Test math.cos() transpilation."""
		import math

		@javascript
		def f(x):
			return math.cos(x)

		code = transpile_function(f)
		assert "Math.cos(x)" in code

	def test_math_log(self):
		"""Test math.log() transpilation."""
		import math

		@javascript
		def f(x):
			return math.log(x)

		code = transpile_function(f)
		assert "Math.log(x)" in code

	def test_math_log_with_base(self):
		"""Test math.log(x, base) transpilation."""
		import math

		@javascript
		def f(x):
			return math.log(x, 10)

		code = transpile_function(f)
		assert "Math.log(x)" in code
		assert "Math.log(10)" in code

	def test_math_floor(self):
		"""Test math.floor() transpilation."""
		import math

		@javascript
		def f(x):
			return math.floor(x)

		code = transpile_function(f)
		assert "Math.floor(x)" in code

	def test_math_ceil(self):
		"""Test math.ceil() transpilation."""
		import math

		@javascript
		def f(x):
			return math.ceil(x)

		code = transpile_function(f)
		assert "Math.ceil(x)" in code

	def test_math_pi_constant(self):
		"""Test math.pi constant transpilation."""
		import math

		@javascript
		def f(r):
			return math.pi * r * r

		code = transpile_function(f)
		assert "Math.PI" in code

	def test_math_e_constant(self):
		"""Test math.e constant transpilation."""
		import math

		@javascript
		def f(x):
			return math.e**x

		code = transpile_function(f)
		assert "Math.E" in code

	def test_math_pow(self):
		"""Test math.pow() transpilation."""
		import math

		@javascript
		def f(x, y):
			return math.pow(x, y)

		code = transpile_function(f)
		assert "Math.pow(x, y)" in code

	def test_math_hypot(self):
		"""Test math.hypot() transpilation."""
		import math

		@javascript
		def f(x, y):
			return math.hypot(x, y)

		code = transpile_function(f)
		assert "Math.hypot(x, y)" in code

	def test_math_radians(self):
		"""Test math.radians() transpilation."""
		import math

		@javascript
		def f(degrees):
			return math.radians(degrees)

		code = transpile_function(f)
		assert "Math.PI" in code
		assert "180" in code

	def test_math_degrees(self):
		"""Test math.degrees() transpilation."""
		import math

		@javascript
		def f(radians):
			return math.degrees(radians)

		code = transpile_function(f)
		assert "Math.PI" in code
		assert "180" in code

	def test_math_isnan(self):
		"""Test math.isnan() transpilation."""
		import math

		@javascript
		def f(x):
			return math.isnan(x)

		code = transpile_function(f)
		assert "Number.isNaN(x)" in code

	def test_math_isfinite(self):
		"""Test math.isfinite() transpilation."""
		import math

		@javascript
		def f(x):
			return math.isfinite(x)

		code = transpile_function(f)
		assert "Number.isFinite(x)" in code

	def test_math_trunc(self):
		"""Test math.trunc() transpilation."""
		import math

		@javascript
		def f(x):
			return math.trunc(x)

		code = transpile_function(f)
		assert "Math.trunc(x)" in code

	def test_math_combined_expression(self):
		"""Test combined math expressions."""
		import math

		@javascript
		def f(x, y):
			return math.sqrt(x * x + y * y)

		code = transpile_function(f)
		assert "Math.sqrt(x * x + y * y)" in code
