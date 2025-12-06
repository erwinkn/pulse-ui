"""
Registry Demo - Demonstrates the unified __registry system.

This example shows how the new registry system works conceptually:
1. CSS modules - Classes from .module.css files resolved via registry
2. JSExpr as props - Using Import() to call JS utilities (like class concatenation)
3. JsFunction - Transpiled Python functions for client-side execution
4. JSExpr children - Passing JSExpr that evaluates to strings as children

Note: This example demonstrates the patterns. Some features require the full
codegen pipeline to work end-to-end.
"""

from typing import Any, cast

import pulse as ps
from pulse.transpiler.function import javascript
from pulse.transpiler.imports import Import

# =============================================================================
# 1. CSS Module - classes resolve at runtime via __registry
# =============================================================================
# When codegen runs, this creates:
#   import styles_abc123 from "./registry-demo.module.css";
#   __registry["styles_abc123"] = styles_abc123;
#
# Then styles.card emits: get_object('styles_abc123').card
styles = ps.CssImport("./registry-demo.module.css", module=True, relative=True)

# =============================================================================
# 2. Import JS utilities for use in JSExpr
# =============================================================================
# cx() is a class concatenation utility (like clsx)
# When codegen runs, this creates:
#   import { cx as cx_xyz789 } from "~/components/utils";
#   __registry["cx_xyz789"] = cx_xyz789;
cx = Import("cx", "~/components/utils")

# formatGreeting() is a JS function we'll call to produce a greeting string
formatGreeting = Import("formatGreeting", "~/components/utils")


# =============================================================================
# 3. JsFunction - Transpiled Python function
# =============================================================================
# This decorator marks the function for transpilation to JavaScript.
# The function body is analyzed and transpiled to JS during codegen.
# The generated function is added to the registry.
#
# Example generated code:
#   function make_greeting_def456(name, count) {
#     return formatGreeting_xyz789(name, count);
#   }
#   __registry["make_greeting_def456"] = make_greeting_def456;
@javascript
def make_greeting(name: str, count: int) -> Any:
	"""Creates a greeting message. Transpiles to JS."""
	return formatGreeting(name, count)


# =============================================================================
# State
# =============================================================================
class DemoState(ps.State):
	name: str = "World"
	message_count: int = 3
	is_active: bool = False

	def toggle_active(self) -> None:
		self.is_active = not self.is_active

	def increment_count(self) -> None:
		self.message_count += 1

	def set_name(self, value: str) -> None:
		self.name = value


# =============================================================================
# Components
# =============================================================================
@ps.component
def RegistryDemo() -> ps.Element:
	with ps.init():
		state = DemoState()

	# -------------------------------------------------------------------------
	# CSS Module classes from the registry
	# -------------------------------------------------------------------------
	# styles.card, styles.title, etc. are JSMember expressions that resolve
	# to the actual CSS class names at runtime via the registry.
	# The renderer serializes these as "$js" placeholders and sends the
	# JavaScript code via jsexpr_paths for client-side evaluation.

	# -------------------------------------------------------------------------
	# JSExpr as prop: cx() for class concatenation
	# -------------------------------------------------------------------------
	# cx(styles.button, styles.buttonPrimary) creates a JSCall expression.
	# When serialized, this becomes something like:
	#   get_object('cx_xyz789')(get_object('styles_abc123').button, ...)
	#
	# Cast to Any to bypass static type checking (runtime handles JSExpr)
	button_primary_class = cast(
		Any, cx(styles.button, styles.buttonPrimary, "test-primary")
	)
	button_secondary_class = cast(
		Any, cx(styles.button, styles.buttonSecondary, "test-secondary")
	)

	# -------------------------------------------------------------------------
	# JsFunction call used as a prop value
	# -------------------------------------------------------------------------
	# The greeting is computed by calling the transpiled JS function.
	# make_greeting(name, count) creates a JsFunctionCall that evaluates
	# client-side to produce the greeting string.
	greeting_expr = make_greeting(state.name, state.message_count)

	# -------------------------------------------------------------------------
	# JSExpr as a child (non-JSX)
	# -------------------------------------------------------------------------
	# Create a JSExpr that evaluates to a string when rendered as a child.
	# This demonstrates passing JSExpr directly from Python to be evaluated
	# client-side and rendered as text content.
	jsexpr_child = cast(Any, formatGreeting(state.name, state.message_count))

	return ps.div(className=cast(Any, styles.card))[
		# Title using CSS module class
		ps.h1("Registry Demo", className=cast(Any, styles.title)),
		ps.p(
			"Demonstrating CSS modules, JSExpr props, JsFunction, and JSX children.",
			className=cast(Any, styles.subtitle),
		),
		# Input to change the name
		ps.div(className="flex gap-2 items-center mb-4")[
			ps.label("Name: ", htmlFor="name-input"),
			ps.input(
				id="name-input",
				type="text",
				value=state.name,
				onChange=lambda e: state.set_name(e["target"]["value"]),
				className="px-2 py-1 rounded border",
			),
		],
		# Greeting display - value comes from JsFunction call
		# For demonstration, we show both the Python-computed and the concept
		ps.div(className=cast(Any, styles.greeting))[
			ps.span(
				f"Python-computed: Hello, {state.name}! You have {state.message_count} new messages."
			),
		],
		ps.div(className="text-sm opacity-75 mt-2")[
			ps.span("JS greeting expression: "),
			ps.code(
				greeting_expr.fn.js_name + f"('{state.name}', {state.message_count})"
			),
		],
		# Buttons using cx() for dynamic class concatenation
		ps.div(className="flex gap-2 mt-4")[
			ps.button(
				"Increment Count",
				onClick=state.increment_count,
				className=button_primary_class,
			),
			ps.button(
				f"Toggle Active ({state.is_active})",
				onClick=state.toggle_active,
				className=button_secondary_class,
			),
		],
		# JSExpr child - evaluates to string content
		ps.div(className="mt-4 p-4 rounded")[
			"JSExpr child: ",
			jsexpr_child,
		],
	]


# =============================================================================
# App
# =============================================================================
app = ps.App([ps.Route("/", RegistryDemo)])
