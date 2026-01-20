# pyright: reportUnusedFunction=false, reportMissingParameterType=false
"""
Inline Effect Caching Demo
==========================
Demonstrates @ps.effect usage inside components with:
1. Conditional effects - effects inside if/else blocks
2. Loop effects with keys - effects in for loops using the `key` parameter
"""

import pulse as ps
from pulse.js import console
from pulse.render_session import run_js


class DemoState(ps.State):
	show_effect: bool = True
	items: list[str]
	item_counts: dict[str, int]

	def __init__(self):
		self.items = ["apple", "banana", "cherry"]
		self.item_counts = {k: 0 for k in self.items}

	def toggle_effect(self):
		self.show_effect = not self.show_effect

	def add_item(self):
		self.items = [*self.items, f"item-{len(self.items)}"]

	def remove_item(self):
		if self.items:
			self.items = self.items[:-1]

	def shuffle_items(self):
		import random

		shuffled = self.items.copy()
		random.shuffle(shuffled)
		self.items = shuffled

	def increment_item(self, item: str):
		self.item_counts[item] = self.item_counts.get(item, 0) + 1


# Conditional Effects Demo
# ------------------------
# Effects inside conditionals are cached per code location.
# The effect is created once and reused across re-renders.


@ps.component
def ConditionalEffectDemo():
	with ps.init():
		counter = ps.Signal(0)
		state = DemoState()

	def increment():
		counter.write(counter.read() + 1)

	# This effect only exists when show_effect is True.
	# When toggled off, the effect is disposed; when toggled back on,
	# a new effect is created at the same location.
	if state.show_effect:

		@ps.effect(immediate=True)
		def conditional_effect():
			val = counter()
			print(f"[Conditional Effect] Counter changed to: {val}")
			run_js(console.log(f"[Conditional Effect] Counter changed to: {val}"))

			def cleanup():
				print(f"[Conditional Effect] Cleaning up for value: {val}")

			return cleanup

	return ps.div(
		ps.h2("Conditional Effects", className="text-xl font-bold mb-4"),
		ps.p(
			"The effect below only runs when enabled. Toggle it off to dispose, toggle back on to recreate.",
			className="text-gray-600 mb-4",
		),
		ps.div(
			ps.button(
				f"{'Disable' if state.show_effect else 'Enable'} Effect",
				onClick=state.toggle_effect,
				className="btn-secondary mr-2",
			),
			ps.button(
				"Increment Counter",
				onClick=increment,
				className="btn-primary mr-2",
			),
			ps.span(f"Counter: {counter()}", className="font-mono"),
			className="flex items-center",
		),
		ps.p(
			f"Effect is {'active' if state.show_effect else 'disabled'}",
			className=f"mt-2 text-sm {'text-green-600' if state.show_effect else 'text-red-600'}",
		),
		className="p-4 bg-white rounded shadow mb-6",
	)


# Loop Effects with Keys
# ----------------------
# When using @ps.effect inside a loop, you MUST provide a unique `key`
# to disambiguate each effect instance. Without a key, Pulse raises an error.


@ps.component
def LoopEffectDemo():
	with ps.init():
		state = DemoState()

	# Create an effect for each item using the `key` parameter.
	# Each effect tracks its own item's count via the reactive dict.
	for item in state.items:
		# The key parameter makes each effect unique, even though
		# they're defined at the same code location.
		@ps.effect(key=item, immediate=True)
		def item_effect(item=item):  # capture via default arg
			val = state.item_counts.get(item, 0)
			print(f"[Loop Effect:{item}] Count is {val}")
			run_js(console.log(f"[Loop Effect:{item}] Count is {val}"))

			def cleanup(name=item):
				print(f"[Loop Effect:{name}] Cleaning up")

			return cleanup

	return ps.div(
		ps.h2("Loop Effects with Keys", className="text-xl font-bold mb-4"),
		ps.p(
			"Each item has its own effect created in a loop. The `key` parameter ensures each effect is unique.",
			className="text-gray-600 mb-4",
		),
		ps.div(
			ps.button(
				"Add Item", onClick=state.add_item, className="btn-secondary mr-2"
			),
			ps.button(
				"Remove Item", onClick=state.remove_item, className="btn-secondary mr-2"
			),
			ps.button(
				"Shuffle Items", onClick=state.shuffle_items, className="btn-secondary"
			),
			className="mb-4",
		),
		ps.ul(
			*[
				ps.li(
					ps.span(f"{item}: ", className="font-semibold w-24 inline-block"),
					ps.button(
						"+",
						onClick=lambda _e, i=item: state.increment_item(i),
						className="btn-primary mr-2",
					),
					ps.span(
						f"{state.item_counts.get(item, 0)}",
						className="font-mono",
					),
					className="flex items-center mb-2",
					key=item,
				)
				for item in state.items
			],
			className="list-none",
		),
		className="p-4 bg-white rounded shadow mb-6",
	)


# Dynamic Key Effects
# -------------------
# Keys can change during the component lifecycle. When a key changes,
# the old effect is disposed and a new one is created.


@ps.component
def DynamicKeyDemo():
	with ps.init():
		current_key = ps.Signal("v1", "key")
		run_count = ps.Signal(0, "count")
		trigger_count = ps.Signal(0, "trigger")

	def change_key():
		key = current_key.read()
		new_key = f"v{int(key[1:]) + 1}"
		current_key.write(new_key)

	def trigger_effect():
		trigger_count.write(trigger_count.read() + 1)

	# When the key changes, the old effect is disposed (cleanup runs)
	# and a new effect is created.
	current = current_key.read()
	trigger = trigger_count.read()

	@ps.effect(key=current, immediate=True)
	def key_dependent_effect():
		trigger = trigger_count.read()
		# Use Untrack to avoid tracking run_count as a dependency.
		# Otherwise, writing to run_count would trigger this effect to re-run infinitely.
		# Same for key, otherwise this effect would run instantly on key change before being disposed by the rerender.
		with ps.Untrack():
			count = run_count.read() + 1
			key = current_key.read()
		run_count.write(count)
		print(f"[Dynamic Key Effect] Run #{count} for key={key} (trigger={trigger})")
		run_js(
			console.log(
				f"[Dynamic Key Effect] Run #{count} for key={key} (trigger={trigger})"
			)
		)

		def cleanup(k=key):
			print(f"[Dynamic Key Effect] Disposing effect with key={key}")

		return cleanup

	return ps.div(
		ps.h2("Dynamic Key Effects", className="text-xl font-bold mb-4"),
		ps.p(
			"Change the key to dispose/recreate the effect, or trigger it to re-run with the same key.",
			className="text-gray-600 mb-4",
		),
		ps.div(
			ps.button("Change Key", onClick=change_key, className="btn-primary mr-4"),
			ps.button(
				"Trigger Effect",
				onClick=trigger_effect,
				className="btn-secondary mr-4",
			),
			ps.span(f"Current key: {current_key()}", className="font-mono mr-4"),
			ps.span(f"Trigger count: {trigger}", className="font-mono mr-4"),
			ps.span(f"Effect fired {run_count()} time(s)", className="text-gray-600"),
			className="flex flex-wrap items-center",
		),
		className="p-4 bg-white rounded shadow mb-6",
	)


@ps.component
def main_layout():
	return ps.div(
		ps.header(
			ps.h1("Inline Effect Caching Demo", className="text-2xl font-bold"),
			className="p-4 bg-gray-800 text-white mb-6",
		),
		ps.main(
			ps.p(
				"This example demonstrates @ps.effect usage inside components with inline caching.",
				className="mb-6 text-gray-700",
			),
			ConditionalEffectDemo(),
			LoopEffectDemo(),
			DynamicKeyDemo(),
			ps.div(
				ps.h3("How it works", className="text-lg font-semibold mb-2"),
				ps.ul(
					ps.li(
						"Effects are cached by code location (file + line number)",
						className="mb-1",
					),
					ps.li(
						"In loops, use key= to make each effect unique",
						className="mb-1",
					),
					ps.li(
						"Key changes dispose old effect and create new one",
						className="mb-1",
					),
					ps.li(
						"Conditional effects are disposed when condition becomes false",
						className="mb-1",
					),
					className="list-disc list-inside text-gray-600",
				),
				className="p-4 bg-gray-50 rounded border",
			),
			className="container mx-auto px-4",
		),
		className="min-h-screen bg-gray-100 text-gray-800",
	)


app = ps.App(
	routes=[
		ps.Route("/", main_layout),
	],
)
