"""Demo of run_js() for imperative JavaScript execution from Python callbacks.

Run with:
    uv run pulse dev examples/js_exec_demo.py

This example demonstrates:
1. Fire-and-forget with transpiled @javascript function
2. Awaiting a result from the client
3. Error handling when JS throws
"""

from typing import Any, cast

import pulse as ps
from pulse import App, Route, component, javascript, run_js
from pulse.js import Error, console, document, navigator, window
from pulse.render_session import JsExecError


class DemoState(ps.State):
	log: list[str] = []
	result: dict[str, Any] | None = None
	error: str | None = None

	def add_log(self, msg: str):
		self.log = [*self.log[-9:], msg]  # Keep last 10 entries

	def clear_log(self):
		self.log = []


# ============================================================================
# Transpiled JavaScript functions
# ============================================================================


@javascript
def show_alert(message: str):
	window.alert(message)


@javascript
def focus_element(selector: str):
	cast(Any, document.querySelector(selector)).focus()


@javascript
def get_window_info():
	return {
		"innerWidth": window.innerWidth,
		"innerHeight": window.innerHeight,
		"scrollX": window.scrollX,
		"scrollY": window.scrollY,
		"userAgent": navigator.userAgent,
	}


@javascript
def get_selected_text() -> str:
	selection: Any = window.getSelection()
	return selection.toString()


@javascript
def console_log(message: str):
	console.log(message)


@javascript
def cause_error():
	# Use Python raise with JS Error - transpiles to: throw Error(...)
	raise Error("Intentional error from transpiled function")


# ============================================================================
# Component
# ============================================================================


@component
def JsExecDemo():
	with ps.init():
		state = DemoState()

	# 1. Fire-and-forget with transpiled function
	def on_console_log():
		run_js(console_log("Hello from Python! Check your browser console."))
		state.add_log("Sent: console.log (check browser console)")

	# 2. Fire-and-forget with transpiled function
	def on_alert():
		run_js(show_alert("This alert was triggered from Python!"))
		state.add_log("Sent: show_alert()")

	def on_focus():
		run_js(focus_element("#focus-target"))
		state.add_log("Sent: focus_element('#focus-target')")

	# 3. Await result from client
	async def on_get_window_info():
		state.add_log("Requesting window info...")
		result = await run_js(get_window_info(), result=True)
		state.result = result
		state.add_log(f"Received: {result['innerWidth']}x{result['innerHeight']}")

	async def on_get_selection():
		state.add_log("Requesting selected text...")
		result = await run_js(get_selected_text(), result=True)
		state.result = {"selectedText": result or "(nothing selected)"}
		state.add_log(f"Received: '{result or '(empty)'}'")

	# 4. Error handling
	async def on_cause_error():
		state.add_log("Triggering JS error...")
		try:
			await run_js(cause_error(), result=True)  # pyright: ignore[reportArgumentType]
		except JsExecError as e:
			state.error = str(e)
			state.add_log(f"Caught error: {e}")

	def clear_state():
		state.clear_log()
		state.result = None
		state.error = None

	btn = "px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 cursor-pointer"
	btn_gray = (
		"px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 cursor-pointer"
	)

	return ps.div(className="p-8 max-w-3xl mx-auto font-sans")[
		ps.h1(className="text-3xl font-bold mb-2")["run_js() Demo"],
		ps.p(className="text-gray-600 mb-6")[
			"Test imperative JavaScript execution from Python callbacks."
		],
		# Fire and forget section
		ps.h2(className="text-xl font-semibold mb-2")["🔥 Fire and Forget"],
		ps.div(className="flex gap-2 flex-wrap mb-4")[
			ps.button(onClick=on_console_log, className=btn, style={"width": "500px"})[
				"Console Log"
			],
			ps.button(onClick=on_alert, className=btn)["Show Alert"],
			ps.button(onClick=on_focus, className=btn)["Focus Input"],
		],
		# Focus target input
		ps.div(className="mb-6")[
			ps.p(className="mb-2")["Focus target:"],
			ps.input(
				id="focus-target",
				type="text",
				placeholder="Click 'Focus Input' to focus me!",
				className="border-2 border-gray-300 rounded px-3 py-2 w-64",
			),
		],
		# Await result section
		ps.h2(className="text-xl font-semibold mb-2")["⏳ Await Result"],
		ps.p(className="text-gray-600 text-sm mb-2")[
			"Select some text on the page, then click 'Get Selection'"
		],
		ps.div(className="flex gap-2 flex-wrap mb-4")[
			ps.button(onClick=on_get_window_info, className=btn)["Get Window Info"],
			ps.button(onClick=on_get_selection, className=btn)["Get Selection"],
		],
		# Error handling section
		ps.h2(className="text-xl font-semibold mb-2")["💥 Error Handling"],
		ps.p(className="text-gray-600 text-sm mb-2")[
			"Test catching JS errors in Python callbacks"
		],
		ps.div(className="flex gap-2 flex-wrap mb-4")[
			ps.button(onClick=on_cause_error, className=btn)["Trigger Error"],
		],
		# Results display
		ps.h2(className="text-xl font-semibold mb-2")["📊 Results"],
		ps.div(className="grid grid-cols-2 gap-4 mb-6")[
			ps.div()[
				ps.h2(className="text-sm font-medium mb-1")["Last Result"],
				ps.pre(
					className="bg-gray-100 p-4 rounded text-sm min-h-16 overflow-auto"
				)[str(state.result) if state.result else "(none)"],
			],
			ps.div()[
				ps.h2(className="text-sm font-medium mb-1")["Last Error"],
				ps.pre(
					className="bg-gray-100 p-4 rounded text-sm min-h-16 overflow-auto text-red-600"
				)[state.error if state.error else "(none)"],
			],
		],
		# Log section
		ps.h2(className="text-xl font-semibold mb-2")["📝 Event Log"],
		ps.button(onClick=clear_state, className=f"{btn_gray} mb-2")["Clear"],
		ps.pre(className="bg-gray-100 p-4 rounded text-sm min-h-24 overflow-auto")[
			"\n".join(state.log) if state.log else "(empty)"
		],
	]


# ============================================================================
# App
# ============================================================================

app = App(
	routes=[
		Route("/", JsExecDemo),
	]
)

if __name__ == "__main__":
	app.run()
