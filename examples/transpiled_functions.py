"""
Example demonstrating Python -> JavaScript transpilation.

This example shows various Python functions decorated with @ps.javascript,
and demonstrates their actual execution on the client side using custom
React components that accept synchronous function props.

The transpiled functions are:
1. Registered during route initialization via the `functions` parameter
2. Transpiled to JavaScript and embedded in the generated route file
3. Added to the registry so they can be looked up at runtime
4. Passed as props to React components that execute them client-side
"""

import math

import pulse as ps

# =============================================================================
# Custom React Components for Testing Transpiled Functions
# =============================================================================

# These components accept synchronous function props and execute them client-side
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
# Transpiled Functions - These run on the CLIENT via JavaScript
# =============================================================================


@ps.javascript
def double(x):
	"""Double a number."""
	return x * 2


@ps.javascript
def add(a, b):
	"""Add two numbers."""
	return a + b


@ps.javascript
def multiply_and_add(x, y, z):
	"""Multiply x and y, then add z."""
	return x * y + z


@ps.javascript
def factorial(n):
	"""Calculate factorial using a loop."""
	result = 1
	for i in range(1, n + 1):
		result = result * i
	return result


@ps.javascript
def fibonacci(n):
	"""Calculate the nth Fibonacci number."""
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


def square(x):
	return x**2


@ps.javascript
def sum_of_squares(items):
	"""Calculate the sum of squares of a list."""
	return sum(square(x) for x in items)


@ps.javascript
def filter_evens(items):
	"""Filter even numbers from a list."""
	return [x for x in items if x % 2 == 0]


@ps.javascript
def format_greeting(name, age):
	"""Format a greeting string."""
	return f"Hello, {name}! You are {age} years old."


@ps.javascript
def string_operations(s):
	"""Apply string transformations."""
	return s.strip().upper().replace("HELLO", "HI")


@ps.javascript
def math_operations(x):
	"""Use Python math module functions."""
	return math.sqrt(x) + math.sin(x) + math.floor(x)


@ps.javascript
def conditional_expression(x):
	"""Use conditional expressions."""
	return "positive" if x > 0 else "negative" if x < 0 else "zero"


@ps.javascript
def nested_data(items):
	"""Transform data with conditional logic."""
	result = []
	for item in items:
		if item > 0:
			result.append(item * 2)
	return result


@ps.javascript
def use_builtins(items):
	"""Use Python built-in functions."""
	return len(items) + max(items) - min(items)


@ps.javascript
def format_number(x):
	"""Demonstrate f-string format specs."""
	return f"Fixed: {x:.2f}, Hex: {x:#x}, Padded: {x:05d}"


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
					"These Python functions are transpiled to JavaScript and executed entirely on the client side.",
					className="text-xl text-slate-300 mb-2",
				),
				ps.p(
					"The functions are passed as props to React components - no server round-trips!",
					className="text-lg text-slate-400",
				),
			],
		],
		# Content
		ps.div(className="max-w-6xl mx-auto py-8 px-4")[
			# Basic Arithmetic
			Section(
				title="Basic Arithmetic",
				description="Simple mathematical operations transpiled to JS.",
				children=[
					FunctionTester(
						fn=double,
						label="double(x) - Multiply by 2",
						initialValue=5,
						showCode=True,
					),
					MultiArgFunctionTester(
						fn=add,
						label="add(a, b) - Addition",
						argLabels=["a", "b"],
						initialValues=[5, 3],
						showCode=True,
					),
				],
			),
			# Algorithms
			Section(
				title="Algorithms",
				description="Classic algorithms implemented in Python, running in JavaScript.",
				children=[
					FunctionTester(
						fn=factorial,
						label="factorial(n) - Iterative factorial",
						initialValue=5,
						showCode=True,
					),
					FunctionTester(
						fn=fibonacci,
						label="fibonacci(n) - Fibonacci sequence",
						initialValue=10,
						showCode=True,
					),
					FunctionTester(
						fn=is_prime,
						label="is_prime(n) - Prime check",
						initialValue=17,
						showCode=True,
					),
				],
			),
			# String Operations
			Section(
				title="String Operations",
				description="String methods and f-string formatting.",
				children=[
					StringFunctionTester(
						fn=string_operations,
						label="string_operations(s) - String methods",
						initialValue="  hello world  ",
						showCode=True,
					),
					FunctionTester(
						fn=format_number,
						label="format_number(x) - F-string format specs",
						initialValue=42,
						showCode=True,
					),
				],
			),
			# Conditional Logic
			Section(
				title="Conditional Logic",
				description="Conditional expressions and control flow.",
				children=[
					FunctionTester(
						fn=conditional_expression,
						label="conditional_expression(x) - Ternary",
						initialValue=0,
						showCode=True,
					),
				],
			),
			# Math Module
			Section(
				title="Math Module",
				description="Python's math module transpiled to JavaScript Math object.",
				children=[
					FunctionTester(
						fn=math_operations,
						label="math_operations(x) - sqrt + sin + floor",
						initialValue=4,
						showCode=True,
					),
				],
			),
			# Array Operations
			Section(
				title="Array Operations",
				description="List comprehensions and built-in functions on arrays.",
				children=[
					ArrayFunctionTester(
						fn=filter_evens,
						label="filter_evens(items) - List comprehension filter",
						initialValue="1, 2, 3, 4, 5, 6, 7, 8, 9, 10",
						showCode=True,
					),
					ArrayFunctionTester(
						fn=sum_of_squares,
						label="sum_of_squares(items) - Generator expression",
						initialValue="1, 2, 3, 4, 5",
						showCode=True,
					),
					ArrayFunctionTester(
						fn=nested_data,
						label="nested_data(items) - Loop with conditionals",
						initialValue="-2, -1, 0, 1, 2, 3",
						showCode=True,
					),
					ArrayFunctionTester(
						fn=use_builtins,
						label="use_builtins(items) - len, max, min",
						initialValue="1, 5, 3, 9, 2",
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


# Collect all transpiled functions to register with the route
ALL_FUNCTIONS = [
	double,
	add,
	multiply_and_add,
	factorial,
	fibonacci,
	is_prime,
	sum_of_squares,
	filter_evens,
	format_greeting,
	string_operations,
	math_operations,
	conditional_expression,
	nested_data,
	use_builtins,
	format_number,
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
