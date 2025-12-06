"""
Comprehensive example demonstrating Python -> JavaScript transpilation.

This example showcases ALL transpilation features:
1. Basic Python to JavaScript conversion
2. PyModule support (Python stdlib -> JS Math)
3. JsModule support (pulse.js.* modules)
4. import_js for typed JS imports
5. Cross-module function transpilation
6. Builtin functions (len, max, min, sum, etc.)
7. List/dict/set/string methods
8. Global constant transpilation
9. Function composition
"""

from __future__ import annotations

import math

import pulse as ps

# Import JS modules (the new pulse.js.* system)
import pulse.js.math as Math
import pulse.js.number as Number

# Import helper functions from another module - these will be auto-transpiled!
from pulse._examples import clamp, cube, factorial, is_even, square
from pulse.js.math import PI, floor, sin
from pulse.js.math import abs as js_abs
from pulse.js.number import MAX_SAFE_INTEGER, isFinite, isNaN, parseInt

# =============================================================================
# Using import_js for typed JS imports
# =============================================================================


# Import a JS function with proper typing using import_js as a decorator
@ps.import_js("clsx", "clsx", is_default=True)
def clsx(*classes: str) -> str:
	"""Typed import for the clsx library."""
	...


# =============================================================================
# Custom React Components for Testing
# =============================================================================

FunctionTester = ps.ReactComponent(
	"FunctionTester",
	"~/components/function-tester",
)
MultiArgFunctionTester = ps.ReactComponent(
	"MultiArgFunctionTester",
	"~/components/function-tester",
)
StringFunctionTester = ps.ReactComponent(
	"StringFunctionTester",
	"~/components/function-tester",
)
ArrayFunctionTester = ps.ReactComponent(
	"ArrayFunctionTester",
	"~/components/function-tester",
)

# =============================================================================
# Global Constants - automatically transpiled
# =============================================================================

TAU = 2 * 3.14159265358979
GOLDEN_RATIO = 1.618033988749895
MAX_ITEMS = 100


# =============================================================================
# Section 1: Basic Arithmetic & Control Flow
# =============================================================================


@ps.javascript
def double(x):
	"""Double a number - basic arithmetic."""
	return x * 2


@ps.javascript
def add(a, b):
	"""Add two numbers."""
	return a + b


@ps.javascript
def conditional_expression(x):
	"""Use conditional expressions (ternary)."""
	return "positive" if x > 0 else "negative" if x < 0 else "zero"


@ps.javascript
def fibonacci(n):
	"""Calculate the nth Fibonacci number using a loop."""
	if n <= 1:
		return n
	a = 0
	b = 1
	for _ in range(2, n + 1):
		temp = a + b
		a = b
		b = temp
	return b


@ps.javascript
def is_prime(n):
	"""Check if a number is prime."""
	if n < 2:
		return False
	for i in range(2, n):
		if n % i == 0:
			return False
	return True


# =============================================================================
# Section 2: PyModule Support (Python math -> JS Math)
# =============================================================================


@ps.javascript
def math_operations(x):
	"""Use Python math module - transpiles to JS Math."""
	return math.sqrt(x) + math.sin(x) + math.floor(x)


@ps.javascript
def trigonometry(angle):
	"""Full trigonometry support via Python math."""
	return math.sin(angle) ** 2 + math.cos(angle) ** 2


@ps.javascript
def use_math_constants():
	"""Python math constants -> JS Math constants."""
	return math.pi * 2 + math.e


# =============================================================================
# Section 3: JsModule Support (pulse.js.* modules)
# =============================================================================


@ps.javascript
def js_math_module(x):
	"""Using pulse.js.math as a module."""
	return Math.floor(x) + Math.ceil(x)


@ps.javascript
def js_math_imports(x):
	"""Using individual imports from pulse.js.math."""
	return floor(sin(x) * 100)


@ps.javascript
def js_math_constants():
	"""Using constants from pulse.js.math."""
	return PI * 2


@ps.javascript
def js_math_abs(x):
	"""Using abs from pulse.js.math."""
	return js_abs(x)


@ps.javascript
def js_number_module(x):
	"""Using pulse.js.number module functions."""
	return Number.isFinite(x) and not Number.isNaN(x)


@ps.javascript
def js_number_imports(s):
	"""Using individual imports from pulse.js.number."""
	val = parseInt(s, 10)
	return isFinite(val) and not isNaN(val)


@ps.javascript
def js_number_constants():
	"""Using constants from pulse.js.number."""
	return MAX_SAFE_INTEGER


# =============================================================================
# Section 4: import_js for External Libraries
# =============================================================================


@ps.javascript
def use_clsx(is_active, is_disabled):
	"""Use the clsx library for class names."""
	return clsx("btn", "active" if is_active else "", "disabled" if is_disabled else "")


# =============================================================================
# Section 5: Cross-Module Function Transpilation
# =============================================================================


@ps.javascript
def use_imported_square(x):
	"""Use the square function imported from pulse._examples."""
	return square(x)


@ps.javascript
def use_imported_cube(x):
	"""Use the cube function imported from pulse._examples."""
	return cube(x)


@ps.javascript
def use_imported_clamp(value, min_val, max_val):
	"""Use the clamp function imported from pulse._examples."""
	return clamp(value, min_val, max_val)


@ps.javascript
def use_imported_is_even(n):
	"""Use the is_even function imported from pulse._examples."""
	return is_even(n)


@ps.javascript
def use_imported_factorial(n):
	"""Use factorial from pulse._examples - auto-transpiled!"""
	return factorial(n)


@ps.javascript
def combine_imported_functions(x):
	"""Combine multiple imported functions."""
	squared = square(x)
	cubed = cube(x)
	return clamp(squared + cubed, 0, 1000)


# =============================================================================
# Section 6: Builtin Functions
# =============================================================================


@ps.javascript
def use_len(items):
	"""len() -> .length or .size"""
	return len(items)


@ps.javascript
def use_min_max(items):
	"""min/max -> Math.min/Math.max"""
	return max(items) - min(items)


@ps.javascript
def use_abs(x):
	"""abs() -> Math.abs()"""
	return abs(x)


@ps.javascript
def use_round(x, digits):
	"""round() -> toFixed or Math.round"""
	return round(x, digits)


@ps.javascript
def use_str_int_float(x):
	"""Type conversion builtins."""
	return str(int(float(x)))


@ps.javascript
def use_sum(items):
	"""sum() -> reduce()"""
	return sum(items)


@ps.javascript
def use_all_any(items):
	"""all/any -> every/some"""
	return all(items) or any(items)


@ps.javascript
def use_range():
	"""range() -> array generation"""
	return list(range(5))


@ps.javascript
def use_enumerate(items):
	"""enumerate() -> map with index"""
	return [f"{i}: {item}" for i, item in enumerate(items)]


@ps.javascript
def use_zip(a, b):
	"""zip() -> combine arrays"""
	return [x + y for x, y in zip(a, b)]  # noqa: B905


# =============================================================================
# Section 7: List/Dict/Set/String Methods
# =============================================================================


@ps.javascript
def list_methods(items):
	"""List comprehension and methods."""
	doubled = [x * 2 for x in items]
	filtered = [x for x in doubled if x > 5]
	return filtered


@ps.javascript
def list_comprehension_map(items):
	"""List comprehension -> .map()"""
	return [x + 1 for x in items]


@ps.javascript
def list_comprehension_filter(items):
	"""List comprehension with condition -> .filter()"""
	return [x for x in items if x % 2 == 0]


@ps.javascript
def list_comprehension_map_filter(items):
	"""Combined map and filter."""
	return [x * 2 for x in items if x > 0]


@ps.javascript
def generator_sum(items):
	"""Generator expression in sum()."""
	return sum(x * x for x in items)


@ps.javascript
def string_methods(s):
	"""String method chaining."""
	return s.strip().upper().replace("HELLO", "HI")


@ps.javascript
def string_split_join(s):
	"""String split and join."""
	words = s.split(" ")
	return "-".join(words)


@ps.javascript
def string_startswith_endswith(s, prefix, suffix):
	"""String prefix/suffix checks."""
	return s.startswith(prefix) and s.endswith(suffix)


@ps.javascript
def dict_operations(d):
	"""Dict/Map operations."""
	return len(d)


@ps.javascript
def set_operations(items):
	"""Set operations."""
	unique = set(items)
	return len(unique)


@ps.javascript
def membership_test(item, container):
	"""Membership test (in operator)."""
	return item in container


# =============================================================================
# Section 8: Global Constants
# =============================================================================


@ps.javascript
def use_tau():
	"""Use the TAU global constant."""
	return TAU


@ps.javascript
def use_golden_ratio():
	"""Use the GOLDEN_RATIO global constant."""
	return GOLDEN_RATIO


@ps.javascript
def use_max_items():
	"""Use the MAX_ITEMS global constant."""
	return MAX_ITEMS


@ps.javascript
def combine_constants():
	"""Combine multiple global constants."""
	return TAU * GOLDEN_RATIO


# =============================================================================
# Section 9: Function Composition
# =============================================================================


# Local helper that will be auto-transpiled when used
def triple(x):
	return x * 3


@ps.javascript
def compose_double_triple(x):
	"""Compose double and triple (auto-transpiled locals)."""
	return triple(double(x))


@ps.javascript
def compose_imported_functions(x):
	"""Compose imported functions."""
	return cube(square(x))


@ps.javascript
def full_pipeline(x):
	"""Full pipeline using multiple transpiled functions."""
	# Double the input
	doubled = double(x)
	# Square it using imported function
	squared = square(doubled)
	# Use math operations
	result = math.sqrt(squared)
	# Clamp to valid range
	return clamp(result, 0, 100)


# =============================================================================
# Section 10: F-String Formatting
# =============================================================================


@ps.javascript
def fstring_basic(name, age):
	"""Basic f-string interpolation."""
	return f"Hello, {name}! You are {age} years old."


@ps.javascript
def fstring_expressions(x, y):
	"""F-string with expressions."""
	return f"Sum: {x + y}, Product: {x * y}"


@ps.javascript
def fstring_format_specs(x):
	"""F-string format specifications."""
	return f"Fixed: {x:.2f}, Hex: {x:#x}, Padded: {x:05d}"


@ps.javascript
def fstring_alignment(s):
	"""F-string alignment."""
	return f"Left: |{s:<10}|, Right: |{s:>10}|, Center: |{s:^10}|"


# =============================================================================
# UI Components
# =============================================================================


@ps.component
def Section(title: str, description: str, children: list):
	"""A section with a title and description."""
	return ps.div(className="mb-8")[
		ps.h2(title, className="text-2xl font-bold text-white mb-2"),
		ps.p(description, className="text-slate-400 mb-4"),
		ps.div(className="grid gap-4 md:grid-cols-2")[*children],
	]


@ps.component
def TranspilerDemo():
	return ps.div(className="min-h-screen bg-slate-950 text-slate-100")[
		# Header
		ps.div(className="bg-gradient-to-r from-purple-900 to-indigo-900 py-12 px-8")[
			ps.div(className="max-w-6xl mx-auto text-center")[
				ps.h1(
					"Python to JavaScript Transpilation",
					className="text-4xl font-bold mb-4",
				),
				ps.p(
					"Comprehensive demo of ALL transpilation features.",
					className="text-xl text-slate-300 mb-2",
				),
				ps.p(
					"Functions are transpiled at build time and execute entirely in the browser.",
					className="text-lg text-slate-400",
				),
			],
		],
		# Content
		ps.div(className="max-w-6xl mx-auto py-8 px-4")[
			# Basic Arithmetic
			Section(
				title="1. Basic Arithmetic & Control Flow",
				description="Simple operations, conditionals, and loops.",
				children=[
					FunctionTester(
						fn=double, label="double(x)", initialValue=5, showCode=True
					),
					MultiArgFunctionTester(
						fn=add,
						label="add(a, b)",
						argLabels=["a", "b"],
						initialValues=[5, 3],
						showCode=True,
					),
					FunctionTester(
						fn=conditional_expression,
						label="conditional_expression(x)",
						initialValue=0,
						showCode=True,
					),
					FunctionTester(
						fn=fibonacci,
						label="fibonacci(n)",
						initialValue=10,
						showCode=True,
					),
					FunctionTester(
						fn=is_prime, label="is_prime(n)", initialValue=17, showCode=True
					),
				],
			),
			# PyModule Support
			Section(
				title="2. PyModule Support (Python math -> JS Math)",
				description="Python's math module is automatically transpiled to JavaScript's Math object.",
				children=[
					FunctionTester(
						fn=math_operations,
						label="math_operations(x)",
						initialValue=4,
						showCode=True,
					),
					FunctionTester(
						fn=trigonometry,
						label="trigonometry(angle)",
						initialValue=0,
						showCode=True,
					),
					FunctionTester(
						fn=use_math_constants,
						label="use_math_constants()",
						initialValue=0,
						showCode=True,
					),
				],
			),
			# JsModule Support
			Section(
				title="3. JsModule Support (pulse.js.* modules)",
				description="Direct access to JavaScript globals like Math and Number via pulse.js.*.",
				children=[
					FunctionTester(
						fn=js_math_module,
						label="js_math_module(x) - Math module",
						initialValue=3.7,
						showCode=True,
					),
					FunctionTester(
						fn=js_math_imports,
						label="js_math_imports(x) - imported functions",
						initialValue=1,
						showCode=True,
					),
					FunctionTester(
						fn=js_math_constants,
						label="js_math_constants() - PI",
						initialValue=0,
						showCode=True,
					),
					FunctionTester(
						fn=js_number_module,
						label="js_number_module(x) - Number module",
						initialValue=42,
						showCode=True,
					),
					StringFunctionTester(
						fn=js_number_imports,
						label="js_number_imports(s)",
						initialValue="42",
						showCode=True,
					),
					FunctionTester(
						fn=js_number_constants,
						label="js_number_constants() - MAX_SAFE_INTEGER",
						initialValue=0,
						showCode=True,
					),
				],
			),
			# Cross-Module Transpilation
			Section(
				title="5. Cross-Module Function Transpilation",
				description="Functions imported from other Python modules are automatically transpiled.",
				children=[
					FunctionTester(
						fn=use_imported_square,
						label="use_imported_square(x)",
						initialValue=5,
						showCode=True,
					),
					FunctionTester(
						fn=use_imported_cube,
						label="use_imported_cube(x)",
						initialValue=3,
						showCode=True,
					),
					MultiArgFunctionTester(
						fn=use_imported_clamp,
						label="use_imported_clamp(value, min, max)",
						argLabels=["value", "min", "max"],
						initialValues=[150, 0, 100],
						showCode=True,
					),
					FunctionTester(
						fn=use_imported_is_even,
						label="use_imported_is_even(n)",
						initialValue=4,
						showCode=True,
					),
					FunctionTester(
						fn=use_imported_factorial,
						label="use_imported_factorial(n)",
						initialValue=5,
						showCode=True,
					),
				],
			),
			# Builtin Functions
			Section(
				title="6. Builtin Functions",
				description="Python builtins are transpiled to their JavaScript equivalents.",
				children=[
					ArrayFunctionTester(
						fn=use_len,
						label="use_len(items)",
						initialValue="1, 2, 3, 4, 5",
						showCode=True,
					),
					ArrayFunctionTester(
						fn=use_min_max,
						label="use_min_max(items)",
						initialValue="1, 5, 3, 9, 2",
						showCode=True,
					),
					FunctionTester(
						fn=use_abs, label="use_abs(x)", initialValue=-42, showCode=True
					),
					ArrayFunctionTester(
						fn=use_sum,
						label="use_sum(items)",
						initialValue="1, 2, 3, 4, 5",
						showCode=True,
					),
					ArrayFunctionTester(
						fn=use_range,
						label="use_range() - generates [0..4]",
						initialValue="",
						showCode=True,
					),
				],
			),
			# List/String Methods
			Section(
				title="7. List/Dict/Set/String Methods",
				description="Python methods are transpiled to their JavaScript equivalents.",
				children=[
					ArrayFunctionTester(
						fn=list_comprehension_map,
						label="list_comprehension_map(items)",
						initialValue="1, 2, 3",
						showCode=True,
					),
					ArrayFunctionTester(
						fn=list_comprehension_filter,
						label="list_comprehension_filter(items)",
						initialValue="1, 2, 3, 4, 5, 6",
						showCode=True,
					),
					ArrayFunctionTester(
						fn=generator_sum,
						label="generator_sum(items) - sum of squares",
						initialValue="1, 2, 3",
						showCode=True,
					),
					StringFunctionTester(
						fn=string_methods,
						label="string_methods(s)",
						initialValue="  hello world  ",
						showCode=True,
					),
					StringFunctionTester(
						fn=string_split_join,
						label="string_split_join(s)",
						initialValue="hello world example",
						showCode=True,
					),
				],
			),
			# Global Constants
			Section(
				title="8. Global Constants",
				description="Python global constants are automatically inlined in transpiled code.",
				children=[
					FunctionTester(
						fn=use_tau,
						label="use_tau() - TAU constant",
						initialValue=0,
						showCode=True,
					),
					FunctionTester(
						fn=use_golden_ratio,
						label="use_golden_ratio() - GOLDEN_RATIO",
						initialValue=0,
						showCode=True,
					),
					FunctionTester(
						fn=combine_constants,
						label="combine_constants() - TAU * GOLDEN_RATIO",
						initialValue=0,
						showCode=True,
					),
				],
			),
			# Function Composition
			Section(
				title="9. Function Composition",
				description="Transpiled functions can call other transpiled functions.",
				children=[
					FunctionTester(
						fn=compose_double_triple,
						label="compose_double_triple(x)",
						initialValue=5,
						showCode=True,
					),
					FunctionTester(
						fn=compose_imported_functions,
						label="compose_imported_functions(x)",
						initialValue=2,
						showCode=True,
					),
					FunctionTester(
						fn=full_pipeline,
						label="full_pipeline(x) - complete pipeline",
						initialValue=3,
						showCode=True,
					),
				],
			),
			# F-String Formatting
			Section(
				title="10. F-String Formatting",
				description="Python f-strings are transpiled to JavaScript template literals.",
				children=[
					MultiArgFunctionTester(
						fn=fstring_basic,
						label="fstring_basic(name, age)",
						argLabels=["name", "age"],
						initialValues=["Alice", 30],
						showCode=True,
					),
					FunctionTester(
						fn=fstring_format_specs,
						label="fstring_format_specs(x)",
						initialValue=42,
						showCode=True,
					),
					StringFunctionTester(
						fn=fstring_alignment,
						label="fstring_alignment(s)",
						initialValue="hi",
						showCode=True,
					),
				],
			),
		],
		# Footer
		ps.div(className="bg-slate-900 py-8 px-4 mt-8 border-t border-slate-800")[
			ps.div(className="max-w-6xl mx-auto text-center text-slate-500")[
				ps.p(
					"All functions above are Python code transpiled to JavaScript at build time."
				),
				ps.p(
					"They execute entirely in the browser with no server communication.",
					className="mt-2",
				),
			],
		],
	]


# Collect all transpiled functions
ALL_FUNCTIONS = [
	# Section 1: Basic
	double,
	add,
	conditional_expression,
	fibonacci,
	is_prime,
	# Section 2: PyModule
	math_operations,
	trigonometry,
	use_math_constants,
	# Section 3: JsModule
	js_math_module,
	js_math_imports,
	js_math_constants,
	js_math_abs,
	js_number_module,
	js_number_imports,
	js_number_constants,
	# Section 4: import_js
	use_clsx,
	# Section 5: Cross-module
	use_imported_square,
	use_imported_cube,
	use_imported_clamp,
	use_imported_is_even,
	use_imported_factorial,
	combine_imported_functions,
	# Section 6: Builtins
	use_len,
	use_min_max,
	use_abs,
	use_round,
	use_str_int_float,
	use_sum,
	use_all_any,
	use_range,
	use_enumerate,
	use_zip,
	# Section 7: Methods
	list_methods,
	list_comprehension_map,
	list_comprehension_filter,
	list_comprehension_map_filter,
	generator_sum,
	string_methods,
	string_split_join,
	string_startswith_endswith,
	dict_operations,
	set_operations,
	membership_test,
	# Section 8: Constants
	use_tau,
	use_golden_ratio,
	use_max_items,
	combine_constants,
	# Section 9: Composition
	compose_double_triple,
	compose_imported_functions,
	full_pipeline,
	# Section 10: F-strings
	fstring_basic,
	fstring_expressions,
	fstring_format_specs,
	fstring_alignment,
]

app = ps.App(
	[
		ps.Route(
			"/",
			TranspilerDemo,
			components=[
				FunctionTester,
				MultiArgFunctionTester,
				StringFunctionTester,
				ArrayFunctionTester,
			],
			functions=ALL_FUNCTIONS,
		)
	]
)
