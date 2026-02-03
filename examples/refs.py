"""Pulse refs demo: DOM focus, measure, scroll, and value ops."""

from __future__ import annotations

import inspect
from typing import Any

import pulse as ps


class RefDemoState(ps.State):
	log: list[str]
	click_count: int
	last_value: Any
	last_text: str | None
	measured: dict[str, Any] | None
	show_target: bool
	list_ids: list[int]
	next_item_id: int
	item_refs: dict[int, ps.Ref[Any]]
	list_ref: ps.Ref[Any] | None

	def __init__(self) -> None:
		self.log = []
		self.click_count = 0
		self.last_value = None
		self.last_text = None
		self.measured = None
		self.show_target = True
		self.list_ids = []
		self.next_item_id = 1
		self.item_refs = {}
		self.list_ref = None

	def add_log(self, message: str) -> None:
		self.log = [*self.log, message][-40:]

	def inc_click(self) -> None:
		self.click_count += 1

	def toggle_target(self) -> None:
		self.show_target = not self.show_target
		state = "shown" if self.show_target else "hidden"
		self.add_log(f"target {state}")

	def set_list_ref(self, value: ps.Ref[Any] | None) -> None:
		if value is None:
			self.add_log("list unmounted (callback)")
			return
		self.list_ref = value
		self.add_log("list mounted (callback)")

	def add_item(self) -> None:
		item_id = self.next_item_id
		self.next_item_id += 1
		self.item_refs[item_id] = ps.ref(
			on_mount=lambda: self.on_mount(item_id),
			on_unmount=lambda: self.on_unmount(item_id),
		)
		self.list_ids = [*self.list_ids, item_id]
		self.add_log(f"item {item_id} added")

	def on_mount(self, item_id) -> None:
		self.add_log(f"item {item_id} mounted")

	def on_unmount(self, item_id) -> None:
		self.add_log(f"item {item_id} unmounted")

	def remove_item(self, item_id: int) -> None:
		self.list_ids = [item for item in self.list_ids if item != item_id]
		self.add_log(f"item {item_id} removed")

	async def scroll_to_item(self, item_id: int) -> None:
		ref = self.item_refs.get(item_id)
		if ref is None:
			self.add_log(f"item {item_id} missing ref")
			return
		if not ref.mounted:
			self.add_log(f"item {item_id} not mounted yet, waiting")
			try:
				await ref.wait_mounted(timeout=1.0)
			except Exception as exc:
				self.add_log(f"item {item_id} wait error: {exc}")
				return
		ref.scroll_into_view(behavior="smooth", block="center")
		self.add_log(f"scrolled to item {item_id}")

	async def scroll_list_top(self) -> None:
		if self.list_ref is None:
			self.add_log("list ref missing")
			return
		if not self.list_ref.mounted:
			self.add_log("list not mounted yet, waiting")
			try:
				await self.list_ref.wait_mounted(timeout=1.0)
			except Exception as exc:
				self.add_log(f"list wait error: {exc}")
				return
		self.list_ref.scroll_to(top=0, behavior="smooth")
		self.add_log("list scrolled to top")


@ps.component
def RefsPage():
	with ps.init():
		state = RefDemoState()

	input_ref = ps.ref(
		on_mount=lambda: state.add_log("input mounted"),
		on_unmount=lambda: state.add_log("input unmounted"),
	)
	click_ref = ps.ref()
	target_ref = ps.ref(
		on_mount=lambda: state.add_log("target mounted"),
		on_unmount=lambda: state.add_log("target unmounted"),
	)
	text_ref = ps.ref()

	async def test():
		x = await input_ref.set_prop("checked", 1)  # noqa: F841

	async def run(label: str, fn):
		try:
			result = fn()
			if inspect.isawaitable(result):
				result = await result
			state.add_log(f"{label} ok")
			return result
		except Exception as exc:
			state.add_log(f"{label} error: {exc}")
			return None

	async def focus_input():
		await run("wait+focus", lambda: input_ref.wait_mounted(timeout=2.0))
		await run("focus", input_ref.focus)

	async def blur_input():
		await run("blur", input_ref.blur)

	async def select_input():
		await run("select", input_ref.select)

	async def set_input_value():
		value = await run(
			"set_value", lambda: input_ref.set_prop("value", "Pulse refs")
		)
		state.last_value = value

	async def get_input_value():
		value = await run("get_value", lambda: input_ref.get_prop("value"))
		state.last_value = value

	async def set_text_value():
		text = await run("set_text", lambda: text_ref.set_text("Updated by ref"))
		if isinstance(text, str):
			state.last_text = text

	async def get_text_value():
		text = await run("get_text", text_ref.get_text)
		if isinstance(text, str):
			state.last_text = text

	async def measure_target():
		result = await run("measure", target_ref.measure)
		if isinstance(result, dict):
			state.measured = result

	async def scroll_target():
		await run(
			"scroll_into_view",
			lambda: target_ref.scroll_into_view(behavior="smooth", block="center"),
		)

	def click_button():
		click_ref.click()
		state.add_log("click ok")

	return ps.div(
		ps.h1("Pulse Refs Demo", className="text-2xl font-bold mb-4"),
		ps.p(
			"Imperative DOM refs backed by channels.",
			className="text-sm text-gray-600 mb-6",
		),
		ps.section(
			ps.h2("Input ref", className="text-xl font-semibold mb-2"),
			ps.input(
				ref=input_ref,
				defaultValue="Type here…",
				className="input input-bordered w-full max-w-md",
			),
			ps.div(className="flex flex-wrap gap-2 mt-3")[
				ps.button("Focus", onClick=focus_input, className="btn-primary btn-sm"),
				ps.button("Blur", onClick=blur_input, className="btn-secondary btn-sm"),
				ps.button("Select", onClick=select_input, className="btn-light btn-sm"),
				ps.button(
					"Set value",
					onClick=set_input_value,
					className="btn-light btn-sm",
				),
				ps.button(
					"Get value",
					onClick=get_input_value,
					className="btn-light btn-sm",
				),
			],
			ps.p(
				f"Last value: {state.last_value!r}",
				className="text-xs text-gray-600 mt-2",
			),
			className="p-4 border rounded mb-6",
		),
		ps.section(
			ps.h2("Click + text refs", className="text-xl font-semibold mb-2"),
			ps.div(className="flex flex-wrap items-center gap-3")[
				ps.button(
					f"Clicked {state.click_count}",
					ref=click_ref,
					onClick=state.inc_click,
					className="btn-primary btn-sm",
				),
				ps.button(
					"Trigger click", onClick=click_button, className="btn-light btn-sm"
				),
			],
			ps.div(
				ps.div(
					state.last_text or "Edit via refs",
					ref=text_ref,
					className="border rounded p-2 min-w-[12rem]",
				),
				ps.div(className="flex flex-wrap gap-2 mt-2")[
					ps.button(
						"Set text",
						onClick=set_text_value,
						className="btn-secondary btn-sm",
					),
					ps.button(
						"Get text",
						onClick=get_text_value,
						className="btn-light btn-sm",
					),
				],
				className="mt-3",
			),
			className="p-4 border rounded mb-6",
		),
		ps.section(
			ps.h2("Scroll + measure", className="text-xl font-semibold mb-2"),
			ps.button(
				"Toggle target",
				onClick=state.toggle_target,
				className="btn-light btn-sm mb-3",
			),
			ps.div(
				ps.button(
					"Scroll to target",
					onClick=scroll_target,
					className="btn-primary btn-sm mr-2",
				),
				ps.button(
					"Measure target",
					onClick=measure_target,
					className="btn-secondary btn-sm",
				),
				className="flex flex-wrap gap-2",
			),
			ps.div(
				ps.div(className="h-28"),
				ps.If(
					state.show_target,
					then=ps.div(
						"Target box",
						ref=target_ref,
						className="rounded bg-blue-100 border border-blue-300 p-4",
					),
					else_=ps.div(
						"Target hidden",
						className="rounded bg-gray-100 border border-gray-200 p-4",
					),
				),
				ps.div(className="h-28"),
				className="space-y-4",
			),
			ps.p(
				f"Measured: {state.measured}",
				className="text-xs text-gray-600 mt-2",
			),
			className="p-4 border rounded mb-6",
		),
		ps.section(
			ps.h2("Dynamic list refs", className="text-xl font-semibold mb-2"),
			ps.p(
				"Refs are created outside render when items are added.",
				className="text-sm text-gray-600 mb-4",
			),
			ps.div(className="flex flex-wrap gap-2 mb-3")[
				ps.button(
					"Add item",
					onClick=state.add_item,
					className="btn-primary btn-sm",
				),
				ps.button(
					"Scroll list top",
					onClick=state.scroll_list_top,
					className="btn-light btn-sm",
				),
			],
			ps.div(
				ps.div(className="flex flex-wrap gap-2 mb-3")[
					ps.For(
						state.list_ids,
						lambda item_id, _idx: ps.button(
							f"Item {item_id}",
							onClick=lambda _evt=None,
							item_id=item_id: state.scroll_to_item(item_id),
							className="btn-secondary btn-xs",
							key=f"jump-{item_id}",
						),
					)
					if state.list_ids
					else ps.span("No items yet", className="text-xs text-gray-500"),
				],
				ps.div(
					ps.For(
						state.list_ids,
						lambda item_id: ps.div(
							ps.div(f"Item {item_id}", className="font-medium"),
							ps.button(
								"Remove",
								onClick=lambda: state.remove_item(item_id),
								className="btn-light btn-xs",
							),
							ref=state.item_refs.get(item_id),
							key=f"item-{item_id}",
							className="flex items-center justify-between gap-3 border rounded p-2",
						),
					)
					if state.list_ids
					else ps.div(
						"Add items to create refs and scroll targets.",
						className="text-xs text-gray-500",
					),
					ref=state.set_list_ref,
					className="max-h-52 overflow-auto border rounded p-3 space-y-2 bg-gray-50",
				),
			),
			className="p-4 border rounded mb-6",
		),
		ps.section(
			ps.h2("Event log", className="text-xl font-semibold mb-2"),
			ps.div(
				ps.ul(
					ps.For(
						state.log,
						lambda item, idx: ps.li(
							f"{len(state.log) - idx}. {item}",
							key=f"log-{idx}",
						),
					)
					if state.log
					else ps.li("No events yet"),
					className="text-xs text-gray-700 space-y-1",
				),
				className="max-h-48 overflow-auto border rounded p-2 bg-gray-50",
			),
			className="p-4 border rounded",
		),
		className="max-w-3xl mx-auto p-6 space-y-4",
	)


app = ps.App(routes=[ps.Route("/", RefsPage)])
