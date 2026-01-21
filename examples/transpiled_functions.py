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
from typing import Any

import pulse as ps

# Import helper functions from another module - these will be auto-transpiled!
from pulse._examples import clamp, cube, factorial, is_even, square

# Import JS modules (the new pulse.js.* system)
from pulse.js import Math, console, obj
from pulse.js.math import PI, floor, sin
from pulse.js.math import abs as js_abs
from pulse.js.number import Number
from pulse.js.react import useEffect, useState

# =============================================================================
# Using Import as a typed decorator
# =============================================================================


# Import a JS function with proper typing using Import as a decorator
@ps.Import("clsx").as_
def clsx(*classes: str):
	"""Typed import for the clsx library."""
	...


# =============================================================================
# Custom React Components for Testing
# =============================================================================


@ps.react_component(ps.Import("FunctionTester", "~/components/function-tester"))
def FunctionTester(
	fn: Any, label: str, initialValue: Any = None, showCode: bool = False
): ...


@ps.react_component(ps.Import("MultiArgFunctionTester", "~/components/function-tester"))
def MultiArgFunctionTester(
	fn: Any,
	label: str,
	argLabels: list[str] | None = None,
	initialValues: list[Any] | None = None,
	showCode: bool = False,
): ...


@ps.react_component(ps.Import("StringFunctionTester", "~/components/function-tester"))
def StringFunctionTester(
	fn: Any, label: str, initialValue: str = "", showCode: bool = False
): ...


@ps.react_component(ps.Import("ArrayFunctionTester", "~/components/function-tester"))
def ArrayFunctionTester(
	fn: Any, label: str, initialValue: str = "", showCode: bool = False
): ...


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
def double(x: float) -> float:
	"""Double a number - basic arithmetic."""
	return x * 2


@ps.javascript
def add(a: float, b: float) -> float:
	"""Add two numbers."""
	return a + b


@ps.javascript
def conditional_expression(x: float) -> str:
	"""Use conditional expressions (ternary)."""
	return "positive" if x > 0 else "negative" if x < 0 else "zero"


@ps.javascript
def fibonacci(n: int) -> int:
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
def is_prime(n: int) -> bool:
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
def math_operations(x: float) -> float:
	"""Use Python math module - transpiles to JS Math."""
	return math.sqrt(x) + math.sin(x) + math.floor(x)


@ps.javascript
def trigonometry(angle: float) -> float:
	"""Full trigonometry support via Python math."""
	return math.sin(angle) ** 2 + math.cos(angle) ** 2


@ps.javascript
def use_math_constants() -> float:
	"""Python math constants -> JS Math constants."""
	return math.pi * 2 + math.e


# =============================================================================
# Section 3: JsModule Support (pulse.js.* modules)
# =============================================================================


@ps.javascript
def js_math_module(x: float) -> float:
	"""Using pulse.js.math as a module."""
	return Math.floor(x) + Math.ceil(x)


@ps.javascript
def js_math_imports(x: float) -> float:
	"""Using individual imports from pulse.js.math."""
	return floor(sin(x) * 100)


@ps.javascript
def js_math_constants() -> float:
	"""Using constants from pulse.js.math."""
	return PI * 2


@ps.javascript
def js_math_abs(x: float) -> float:
	"""Using abs from pulse.js.math."""
	return js_abs(x)


@ps.javascript
def js_number_module(x: float) -> bool:
	"""Using pulse.js.number module functions."""
	return Number.isFinite(x) and not Number.isNaN(x)


@ps.javascript
def js_number_imports(s: str) -> bool:
	"""Using individual imports from pulse.js.number."""
	val = Number.parseInt(s, 10)
	return Number.isFinite(val) and not Number.isNaN(val)


@ps.javascript
def js_number_constants() -> float:
	"""Using constants from pulse.js.number."""
	return Number.MAX_SAFE_INTEGER


# =============================================================================
# Section 4: import_js for External Libraries
# =============================================================================


@ps.javascript
def use_clsx(is_active: bool, is_disabled: bool) -> str:
	"""Use the clsx library for class names."""
	return clsx("btn", "active" if is_active else "", "disabled" if is_disabled else "")


# =============================================================================
# Section 5: Cross-Module Function Transpilation
# =============================================================================


@ps.javascript
def use_imported_square(x: float) -> float:
	"""Use the square function imported from pulse._examples."""
	return square(x)


@ps.javascript
def use_imported_cube(x: float) -> float:
	"""Use the cube function imported from pulse._examples."""
	return cube(x)


@ps.javascript
def use_imported_clamp(value: float, min_val: float, max_val: float) -> float:
	"""Use the clamp function imported from pulse._examples."""
	return clamp(value, min_val, max_val)


@ps.javascript
def use_imported_is_even(n: int) -> bool:
	"""Use the is_even function imported from pulse._examples."""
	return is_even(n)


@ps.javascript
def use_imported_factorial(n: int) -> int:
	"""Use factorial from pulse._examples - auto-transpiled!"""
	return factorial(n)


@ps.javascript
def combine_imported_functions(x: float) -> float:
	"""Combine multiple imported functions."""
	squared = square(x)
	cubed = cube(x)
	return clamp(squared + cubed, 0, 1000)


# =============================================================================
# Section 6: Builtin Functions
# =============================================================================


@ps.javascript
def use_len(items: list[Any]) -> int:
	"""len() -> .length or .size"""
	return len(items)


@ps.javascript
def use_min_max(items: list[float]) -> float:
	"""min/max -> Math.min/Math.max"""
	return max(items) - min(items)


@ps.javascript
def use_abs(x: float) -> float:
	"""abs() -> Math.abs()"""
	return abs(x)


@ps.javascript
def use_round(x: float, digits: int) -> float:
	"""round() -> toFixed or Math.round"""
	return round(x, digits)


@ps.javascript
def use_str_int_float(x: float) -> str:
	"""Type conversion builtins."""
	return str(int(float(x)))


@ps.javascript
def use_sum(items: list[float]) -> float:
	"""sum() -> reduce()"""
	return sum(items)


@ps.javascript
def use_all_any(items: list[bool]) -> bool:
	"""all/any -> every/some"""
	return all(items) or any(items)


@ps.javascript
def use_range() -> list[int]:
	"""range() -> array generation"""
	return list(range(5))


@ps.javascript
def use_enumerate(items: list[str]) -> list[str]:
	"""enumerate() -> map with index"""
	return [f"{i}: {item}" for i, item in enumerate(items)]


@ps.javascript
def use_zip(a: list[int], b: list[int]) -> list[int]:
	"""zip() -> combine arrays"""
	return [x + y for x, y in zip(a, b)]  # noqa: B905


# =============================================================================
# Section 7: List/Dict/Set/String Methods
# =============================================================================


@ps.javascript
def list_methods(items: list[float]) -> list[float]:
	"""List comprehension and methods."""
	doubled = [x * 2 for x in items]
	filtered = [x for x in doubled if x > 5]
	return filtered


@ps.javascript
def list_comprehension_map(items: list[int]) -> list[int]:
	"""List comprehension -> .map()"""
	return [x + 1 for x in items]


@ps.javascript
def list_comprehension_filter(items: list[int]) -> list[int]:
	"""List comprehension with condition -> .filter()"""
	return [x for x in items if x % 2 == 0]


@ps.javascript
def list_comprehension_map_filter(items: list[int]) -> list[int]:
	"""Combined map and filter."""
	return [x * 2 for x in items if x > 0]


@ps.javascript
def generator_sum(items: list[int]) -> int:
	"""Generator expression in sum()."""
	return sum(x * x for x in items)


@ps.javascript
def string_methods(s: str) -> str:
	"""String method chaining."""
	return s.strip().upper().replace("HELLO", "HI")


@ps.javascript
def string_split_join(s: str) -> str:
	"""String split and join."""
	words = s.split(" ")
	return "-".join(words)


@ps.javascript
def string_startswith_endswith(s: str, prefix: str, suffix: str) -> bool:
	"""String prefix/suffix checks."""
	return s.startswith(prefix) and s.endswith(suffix)


@ps.javascript
def dict_operations(d: dict[str, Any]) -> int:
	"""Dict/Map operations."""
	return len(d)


@ps.javascript
def set_operations(items: list[Any]) -> int:
	"""Set operations."""
	unique = set(items)
	return len(unique)


@ps.javascript
def membership_test(item: Any, container: list[Any]) -> bool:
	"""Membership test (in operator)."""
	return item in container


# =============================================================================
# Section 8: Global Constants
# =============================================================================


@ps.javascript
def use_tau() -> float:
	"""Use the TAU global constant."""
	return TAU


@ps.javascript
def use_golden_ratio() -> float:
	"""Use the GOLDEN_RATIO global constant."""
	return GOLDEN_RATIO


@ps.javascript
def use_max_items() -> int:
	"""Use the MAX_ITEMS global constant."""
	return MAX_ITEMS


@ps.javascript
def combine_constants() -> float:
	"""Combine multiple global constants."""
	return TAU * GOLDEN_RATIO


# =============================================================================
# Section 9: Function Composition
# =============================================================================


# Local helper that will be auto-transpiled when used
def triple(x: float) -> float:
	return x * 3


@ps.javascript
def compose_double_triple(x: float) -> float:
	"""Compose double and triple (auto-transpiled locals)."""
	return triple(double(x))


@ps.javascript
def compose_imported_functions(x: float) -> float:
	"""Compose imported functions."""
	return cube(square(x))


@ps.javascript
def full_pipeline(x: float) -> float:
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
# Section 10: React Components with Hooks
# =============================================================================


@ps.javascript(jsx=True)
def ToggleComponent(*children: ps.Node, initial_visible: bool = True):
	"""React component with show/hide toggle using useState and useEffect.

	This component demonstrates:
	- Using React hooks (useState, useEffect) via pulse.js.react
	- JSX transpilation with jsx=True
	- State management and side effects
	- Accepting children as regular Pulse server-side components
	"""
	# Initialize state with useState hook
	is_visible, set_is_visible = useState(initial_visible)

	# Log state changes with useEffect hook
	useEffect(
		lambda: console.log(f"Toggle state changed: {is_visible}"),  # type: ignore
		[is_visible],  # Dependency array
	)

	# Return JSX element
	return ps.div()[
		ps.button(
			onClick=lambda e: set_is_visible(not is_visible),  # type: ignore
			className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600",
		)["Hide" if is_visible else "Show"],
		ps.div(
			style=obj(display="block" if is_visible else "none"),
			className="mt-4 p-4 border rounded",
		)[*children],
	]


class CounterState(ps.State):
	count: int = 0

	def increment(self):
		self.count += 1

	def decrement(self):
		self.count -= 1

	def reset(self):
		self.count = 0


@ps.component
def CounterComponent():
	"""Pulse server-side component with its own state (counter)."""
	with ps.init():
		state = CounterState()

	return ps.div(className="p-4 bg-slate-800 rounded-lg")[
		ps.h3(
			"Pulse Counter Component", className="text-lg font-semibold mb-3 text-white"
		),
		ps.p(
			"This is a regular Pulse server-side component with its own state. "
			+ "The counter persists independently of the React toggle state.",
			className="text-slate-300 mb-4 text-sm",
		),
		ps.div(className="flex items-center space-x-4")[
			ps.button(
				onClick=lambda: state.decrement(),
				className="px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600",
			)["−"],
			ps.span(f"Count: {state.count}", className="text-xl font-bold text-white"),
			ps.button(
				onClick=lambda: state.increment(),
				className="px-3 py-1 bg-green-500 text-white rounded hover:bg-green-600",
			)["+"],
		],
		ps.button(
			onClick=lambda: state.reset(),
			className="mt-3 px-3 py-1 bg-slate-600 text-white rounded hover:bg-slate-700 text-sm",
		)["Reset"],
	]


@ps.component
def ReactHooksDemo():
	"""Demo page showing the React component with hooks."""
	return ps.div(className="min-h-screen bg-slate-950 text-slate-100 p-8")[
		ps.div(className="max-w-4xl mx-auto")[
			ps.Link(
				to="/",
				className="text-blue-400 hover:text-blue-300 mb-4 inline-block",
			)["← Back to Transpiler Demo"],
			ps.h1("React Components with Hooks", className="text-3xl font-bold mb-4"),
			ps.p(
				"This example shows a React component created in Python using the transpiler system. "
				+ "The component uses useState and useEffect hooks imported from React.",
				className="text-slate-400 mb-8",
			),
			# Use the transpiled React component with Pulse component children
			ToggleComponent(initial_visible=True)[
				# Pass regular Pulse server-side components as children
				ps.h3(
					"Hidden Content with State", className="text-xl font-semibold mb-2"
				),
				ps.p(
					"This content can be toggled on and off using the button above. "
					+ "The component logs state changes to the console via useEffect. "
					+ "Below is a Pulse component with its own independent state.",
					className="text-slate-300 mb-4",
				),
				# Pulse component with its own state
				CounterComponent(),
				ps.div(className="mt-4 p-3 bg-slate-700 rounded")[
					ps.p(
						"Interaction Demo:",
						className="text-sm font-semibold text-slate-300 mb-2",
					),
					ps.ul(className="text-sm text-slate-400 space-y-1")[
						ps.li("• Toggle visibility with the React component above"),
						ps.li("• Increment/decrement the counter independently"),
						ps.li("• Both states are managed separately"),
					],
				],
			],
			ps.div(className="mt-8")[
				ps.h2("How it works", className="text-2xl font-semibold mb-4"),
				ps.div(className="space-y-4 text-slate-300")[
					ps.p("1. React hooks are imported from pulse.js.react"),
					ps.p(
						"2. The @ps.javascript(jsx=True) decorator enables JSX transpilation"
					),
					ps.p("3. useState manages the visibility state in React"),
					ps.p("4. useEffect logs state changes to the console"),
					ps.p(
						"5. CounterComponent is a regular Pulse component with ps.state()"
					),
					ps.p("6. Both components maintain independent state"),
				],
			],
		]
	]


# =============================================================================
# Section 11: F-String Formatting
# =============================================================================


@ps.javascript
def fstring_basic(name: str, age: int) -> str:
	"""Basic f-string interpolation."""
	return f"Hello, {name}! You are {age} years old."


@ps.javascript
def fstring_expressions(x: float, y: float) -> str:
	"""F-string with expressions."""
	return f"Sum: {x + y}, Product: {x * y}"


@ps.javascript
def fstring_format_specs(x: float) -> str:
	"""F-string format specifications."""
	return f"Fixed: {x:.2f}, Hex: {x:#x}, Padded: {x:05d}"


@ps.javascript
def fstring_alignment(s: str) -> str:
	"""F-string alignment."""
	return f"Left: |{s:<10}|, Right: |{s:>10}|, Center: |{s:^10}|"


# =============================================================================
# UI Components
# =============================================================================


@ps.component
def Section(*children: ps.Node, title: str, description: str):
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
			)[
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
			# PyModule Support
			Section(
				title="2. PyModule Support (Python math -> JS Math)",
				description="Python's math module is automatically transpiled to JavaScript's Math object.",
			)[
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
			# JsModule Support
			Section(
				title="3. JsModule Support (pulse.js.* modules)",
				description="Direct access to JavaScript globals like Math and Number via pulse.js.*.",
			)[
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
			# Cross-Module Transpilation
			Section(
				title="5. Cross-Module Function Transpilation",
				description="Functions imported from other Python modules are automatically transpiled.",
			)[
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
			# Builtin Functions
			Section(
				title="6. Builtin Functions",
				description="Python builtins are transpiled to their JavaScript equivalents.",
			)[
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
			# List/String Methods
			Section(
				title="7. List/Dict/Set/String Methods",
				description="Python methods are transpiled to their JavaScript equivalents.",
			)[
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
			# Global Constants
			Section(
				title="8. Global Constants",
				description="Python global constants are automatically inlined in transpiled code.",
			)[
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
			# Function Composition
			Section(
				title="9. Function Composition",
				description="Transpiled functions can call other transpiled functions.",
			)[
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
			# F-String Formatting
			Section(
				title="10. F-String Formatting",
				description="Python f-strings are transpiled to JavaScript template literals.",
			)[
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
		],
		# React Hooks Demo Link
		ps.div(className="max-w-6xl mx-auto py-8 px-4")[
			Section(
				title="11. React Components with Hooks",
				description="Create React components with useState and useEffect hooks.",
			)[
				ps.div(className="col-span-2 p-6 bg-slate-800 rounded-lg")[
					ps.p(
						"The transpiler can create full React components with hooks that run entirely in the browser.",
						className="text-slate-300 mb-4",
					),
					ps.Link(
						to="/react-hooks",
						className="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors",
					)["View React Hooks Demo →"],
				],
			],
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


app = ps.App(
	[
		ps.Route("/", TranspilerDemo),
		ps.Route("/react-hooks", ReactHooksDemo),
	]
)
