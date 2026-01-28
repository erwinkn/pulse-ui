from __future__ import annotations

from typing import Any

import pulse as ps
from pulse_mantine import (
	Badge,
	Button,
	Combobox,
	ComboboxChevron,
	ComboboxClearButton,
	ComboboxDropdown,
	ComboboxDropdownTarget,
	ComboboxEmpty,
	ComboboxEventsTarget,
	ComboboxFooter,
	ComboboxGroup,
	ComboboxHeader,
	ComboboxHiddenInput,
	ComboboxOption,
	ComboboxOptions,
	ComboboxSearch,
	ComboboxStore,
	ComboboxTarget,
	Divider,
	Group,
	Paper,
	ScrollArea,
	Stack,
	Text,
	TextInput,
	Title,
)

OPTIONS = [
	{"label": "React", "value": "react", "group": "Frontend"},
	{"label": "Vue", "value": "vue", "group": "Frontend"},
	{"label": "Svelte", "value": "svelte", "group": "Frontend"},
	{"label": "Solid", "value": "solid", "group": "Frontend"},
	{"label": "Lit", "value": "lit", "group": "Frontend"},
	{"label": "Angular", "value": "angular", "group": "Frontend", "disabled": True},
	{"label": "FastAPI", "value": "fastapi", "group": "Backend"},
	{"label": "Django", "value": "django", "group": "Backend"},
	{"label": "Flask", "value": "flask", "group": "Backend"},
	{"label": "Rails", "value": "rails", "group": "Backend"},
	{"label": "Phoenix", "value": "phoenix", "group": "Backend"},
	{"label": "Go", "value": "go", "group": "Backend"},
	{"label": "Postgres", "value": "postgres", "group": "Data"},
	{"label": "Redis", "value": "redis", "group": "Data"},
	{"label": "DuckDB", "value": "duckdb", "group": "Data"},
	{"label": "ClickHouse", "value": "clickhouse", "group": "Data"},
	{"label": "Kafka", "value": "kafka", "group": "Data"},
	{"label": "Supabase", "value": "supabase", "group": "Data"},
	{"label": "Vercel", "value": "vercel", "group": "Ops"},
	{"label": "Fly", "value": "fly", "group": "Ops"},
	{"label": "Docker", "value": "docker", "group": "Ops"},
	{"label": "Kubernetes", "value": "k8s", "group": "Ops"},
	{"label": "Terraform", "value": "terraform", "group": "Ops"},
	{"label": "Cloudflare", "value": "cloudflare", "group": "Ops"},
]

GROUPS = ["Frontend", "Backend", "Data", "Ops"]
LABELS = {opt["value"]: opt["label"] for opt in OPTIONS}


class ComboboxShowcase(ps.State):
	input_value: str | None
	input_search: str
	input_opened: bool
	action_value: str | None
	action_search: str
	action_keep_open: bool
	_action_reopening: bool
	split_value: str | None
	split_search: str
	inline_value: str
	inline_store: ComboboxStore
	events: list[str]
	selected_index: int
	dropdown_opened: bool
	list_id: str | None
	input_store: ComboboxStore
	action_store: ComboboxStore
	split_store: ComboboxStore

	def __init__(self) -> None:
		self.input_value = "react"
		self.input_search = LABELS[self.input_value]
		self.input_opened = False
		self.action_value = "postgres"
		self.action_search = ""
		self.action_keep_open = False
		self._action_reopening = False
		self.split_value = None
		self.split_search = ""
		self.inline_value = "First"
		self.inline_store = ComboboxStore()
		self.events = []
		self.selected_index = -1
		self.dropdown_opened = False
		self.list_id = None
		self.input_store = ComboboxStore(
			loop=True,
			scrollBehavior="smooth",
			onOpenedChange=self._on_input_opened_change,
			onDropdownOpen=self._on_input_open,
			onDropdownClose=self._on_input_close,
		)
		self.action_store = ComboboxStore(
			loop=True,
			scrollBehavior="instant",
			onDropdownOpen=self._on_action_open,
			onDropdownClose=self._on_action_close,
		)
		self.split_store = ComboboxStore(
			loop=True,
			onDropdownOpen=self._on_split_open,
			onDropdownClose=self._on_split_close,
		)

	def _log(self, message: str) -> None:
		self.events = (self.events + [message])[-8:]

	def _on_input_opened_change(self, opened: bool) -> None:
		self.input_opened = opened
		self._log(f"input onOpenedChange -> {opened}")

	def _on_input_open(self, source: str) -> None:
		self._log(f"input onDropdownOpen ({source})")
		self.input_store.update_selected_option_index("active")

	def _on_input_close(self, source: str) -> None:
		self._log(f"input onDropdownClose ({source})")
		self.input_store.reset_selected_option()
		if self.input_value:
			self.input_search = LABELS[self.input_value]
		else:
			self.input_search = ""

	def set_input_search(self, event: dict[str, Any]) -> None:
		value = str(event.get("target", {}).get("value", ""))
		self.input_search = value
		self.input_store.open_dropdown()
		self.input_store.update_selected_option_index("active")

	def clear_input(self) -> None:
		self.input_value = None
		self.input_search = ""
		self.input_store.reset_selected_option()
		self.input_store.open_dropdown()

	def choose_input(self, value: str) -> None:
		self.input_value = value
		self.input_search = LABELS.get(value, value)
		self.input_store.close_dropdown()
		self._log(f"input selected -> {value}")

	def _on_action_open(self, source: str) -> None:
		self._log(f"actions onDropdownOpen ({source})")
		reopening = self._action_reopening
		self._action_reopening = False
		if not reopening:
			self.action_store.update_selected_option_index("active")
			self.action_store.focus_search_input()

	def _on_action_close(self, source: str) -> None:
		self._log(f"actions onDropdownClose ({source})")
		if self.action_keep_open:
			self._action_reopening = True
			self.action_store.open_dropdown()
		else:
			self.action_store.reset_selected_option()
			self.action_store.focus_target()

	def set_action_search(self, event: dict[str, Any]) -> None:
		value = str(event.get("target", {}).get("value", ""))
		self.action_search = value
		self.action_store.update_selected_option_index("active")

	def clear_action_search(self) -> None:
		self.action_search = ""
		self.action_store.update_selected_option_index("active")

	def choose_action(self, value: str) -> None:
		self.action_value = value
		self.action_store.close_dropdown()
		self._log(f"actions selected -> {value}")

	def _on_split_open(self, source: str) -> None:
		self._log(f"split onDropdownOpen ({source})")

	def _on_split_close(self, source: str) -> None:
		self._log(f"split onDropdownClose ({source})")
		self.split_store.reset_selected_option()

	def set_split_search(self, event: dict[str, Any]) -> None:
		value = str(event.get("target", {}).get("value", ""))
		self.split_search = value
		self.split_store.update_selected_option_index("active")

	def choose_split(self, value: str) -> None:
		self.split_value = value
		self.split_search = LABELS.get(value, value)
		self.split_store.close_dropdown()

	def set_inline_value(self, event: dict[str, Any]) -> None:
		self.inline_value = str(event.get("target", {}).get("value", ""))

	def choose_inline(self, value: str) -> None:
		self.inline_value = value

	def toggle_keep_open(self) -> None:
		self.action_keep_open = not self.action_keep_open

	def action_open(self) -> None:
		self.action_store.open_dropdown()

	def action_close(self) -> None:
		self.action_store.close_dropdown()

	def action_toggle(self) -> None:
		self.action_store.toggle_dropdown()

	def action_select_first(self) -> None:
		self.action_store.select_first_option()

	def action_select_next(self) -> None:
		self.action_store.select_next_option()

	def action_select_previous(self) -> None:
		self.action_store.select_previous_option()

	def action_select_active(self) -> None:
		self.action_store.select_active_option()

	def action_select_index(self, index: int) -> None:
		self.action_store.select_option(index)

	def action_reset_selected(self) -> None:
		self.action_store.reset_selected_option()

	def action_click_selected(self) -> None:
		self.action_store.click_selected_option()

	def action_update_active(self) -> None:
		self.action_store.update_selected_option_index("active")

	def action_update_selected(self) -> None:
		self.action_store.update_selected_option_index("selected")

	def action_focus_search(self) -> None:
		self.action_store.focus_search_input()

	def action_focus_target(self) -> None:
		self.action_store.focus_target()

	def action_set_list_id(self) -> None:
		self.action_store.set_list_id("combobox-actions-list")

	async def refresh_state(self) -> None:
		self.dropdown_opened = await self.action_store.get_dropdown_opened()
		self.selected_index = await self.action_store.get_selected_option_index()
		self.list_id = await self.action_store.get_list_id()

	def clear_events(self) -> None:
		self.events = []


@ps.component
def Demo():
	with ps.init():
		state = ComboboxShowcase()

	input_selected_label = LABELS.get(state.input_value or "", "Pick a stack")
	action_selected_label = LABELS.get(state.action_value or "", "Select resource")
	split_selected_label = LABELS.get(state.split_value or "", "Split target")

	def filter_options(search: str, selected: str | None) -> list[dict[str, Any]]:
		needle = search.strip().lower()
		selected_label = LABELS.get(selected or "", "").lower()
		if not needle or needle == selected_label:
			return OPTIONS
		return [
			opt
			for opt in OPTIONS
			if needle in opt["label"].lower() or needle in opt["value"].lower()
		]

	def grouped_nodes(options: list[dict[str, Any]]) -> list[ps.Node]:
		nodes: list[ps.Node] = []
		for group in GROUPS:
			group_items = [opt for opt in options if opt["group"] == group]
			if not group_items:
				continue
			nodes.append(
				ComboboxGroup(label=group)[
					*[
						ComboboxOption(
							opt["label"],
							value=opt["value"],
							disabled=bool(opt.get("disabled")),
						)
						for opt in group_items
					]
				]
			)
		return nodes

	input_filtered = filter_options(state.input_search, state.input_value)
	action_filtered = filter_options(state.action_search, state.action_value)
	split_filtered = filter_options(state.split_search, state.split_value)

	return Stack(gap="xl", p="lg")[
		Stack(gap="xs")[
			Title("Combobox showcase", order=2),
			Text(
				"Search, group, open/close, split targets, store actions, focus, and state getters.",
			),
		],
		Paper(withBorder=True, p="lg", radius="md")[
			Stack(gap="md")[
				Group(align="center", justify="space-between")[
					Text("Searchable input target", fw=600),
					Group(gap="xs")[
						Badge("loop", variant="light"),
						Badge("smooth scroll", variant="light"),
						Badge(
							"opened" if state.input_opened else "closed",
							variant="outline",
						),
					],
				],
				Combobox(
					store=state.input_store,
					onOptionSubmit=state.choose_input,
					position="bottom",
				)[
					ComboboxTarget()[
						TextInput(
							label="Pick a framework",
							placeholder="Type to filter",
							value=state.input_search,
							onChange=state.set_input_search,
							onFocus=lambda _event: state.input_store.open_dropdown(),
							onClick=lambda _event: state.input_store.open_dropdown(),
							onBlur=lambda _event: state.input_store.close_dropdown(),
							rightSection=Group(gap="xs")[
								ComboboxChevron(),
								ComboboxClearButton(onClick=state.clear_input),
							],
							rightSectionWidth=72,
						),
					],
					ComboboxDropdown()[
						ComboboxHeader()[
							Text(
								f"Selected: {input_selected_label}",
								size="sm",
							),
						],
						ComboboxOptions()[
							*(
								grouped_nodes(input_filtered)
								if input_filtered
								else [ComboboxEmpty("No matches")]
							)
						],
						ComboboxFooter()[
							Group(gap="xs", justify="space-between")[
								Text("Uses Combobox.HiddenInput", size="xs"),
								Button(
									"Reset",
									variant="subtle",
									onClick=state.clear_input,
								),
							],
						],
					],
					ComboboxHiddenInput(
						name="framework",
						value=state.input_value or "",
					),
				],
			],
		],
		Paper(withBorder=True, p="lg", radius="md")[
			Stack(gap="md")[
				Text("Combobox.Search + full store API", fw=600),
				Divider(label="Store actions", labelPosition="center"),
				Group(gap="xs")[
					Button(
						"Keep open" if not state.action_keep_open else "Keep open (ON)",
						variant="filled" if state.action_keep_open else "default",
						onClick=state.toggle_keep_open,
					),
					Button("Open", variant="light", onClick=state.action_open),
					Button("Close", variant="light", onClick=state.action_close),
					Button("Toggle", variant="light", onClick=state.action_toggle),
				],
				Group(gap="xs")[
					Button("First", variant="light", onClick=state.action_select_first),
					Button("Next", variant="light", onClick=state.action_select_next),
					Button(
						"Prev", variant="light", onClick=state.action_select_previous
					),
					Button(
						"Active", variant="light", onClick=state.action_select_active
					),
					Button(
						"Select #3",
						variant="light",
						onClick=lambda: state.action_select_index(2),
					),
				],
				Group(gap="xs")[
					Button(
						"Reset", variant="light", onClick=state.action_reset_selected
					),
					Button(
						"Click", variant="light", onClick=state.action_click_selected
					),
					Button(
						"Update(active)",
						variant="light",
						onClick=state.action_update_active,
					),
					Button(
						"Update(selected)",
						variant="light",
						onClick=state.action_update_selected,
					),
				],
				Group(gap="xs")[
					Button(
						"Focus search",
						variant="light",
						onClick=state.action_focus_search,
					),
					Button(
						"Focus target",
						variant="light",
						onClick=state.action_focus_target,
					),
					Button(
						"Set list id",
						variant="default",
						onClick=state.action_set_list_id,
					),
					Button(
						"Refresh state",
						variant="default",
						onClick=state.refresh_state,
					),
				],
				Group(gap="xs")[
					Badge(
						f"opened: {state.dropdown_opened}",
						variant="outline",
					),
					Badge(
						f"index: {state.selected_index}",
						variant="outline",
					),
					Badge(
						f"listId: {state.list_id or 'unset'}",
						variant="outline",
					),
				],
				Combobox(
					store=state.action_store,
					onOptionSubmit=state.choose_action,
					withinPortal=False,
				)[
					ComboboxTarget()[
						Button(action_selected_label, onClick=state.action_toggle),
					],
					ComboboxDropdown()[
						ComboboxSearch(
							value=state.action_search,
							placeholder="Search inside dropdown",
							onChange=state.set_action_search,
							rightSection=ComboboxClearButton(
								onClick=state.clear_action_search
							),
						),
						ComboboxOptions()[
							*(
								grouped_nodes(action_filtered)
								if action_filtered
								else [ComboboxEmpty("Nothing found")]
							)
						],
					],
				],
			],
		],
		Paper(withBorder=True, p="lg", radius="md")[
			Stack(gap="md")[
				Text("Split events and dropdown targets", fw=600),
				Combobox(
					store=state.split_store,
					onOptionSubmit=state.choose_split,
				)[
					ComboboxDropdownTarget()[
						Group(gap="xs", align="end")[
							ComboboxEventsTarget()[
								TextInput(
									label="Events target",
									placeholder="Type to filter",
									value=state.split_search,
									onChange=state.set_split_search,
									onFocus=lambda _event: state.split_store.open_dropdown(),
								),
							],
							Button(
								"Toggle dropdown",
								onClick=state.split_store.toggle_dropdown,
							),
						],
					],
					ComboboxDropdown()[
						ComboboxHeader()[
							Text(f"Selected: {split_selected_label}", size="sm"),
						],
						ComboboxOptions()[
							*(
								grouped_nodes(split_filtered)
								if split_filtered
								else [ComboboxEmpty("No matches")]
							)
						],
						ComboboxFooter()[
							Text("EventsTarget + DropdownTarget", size="xs"),
						],
					],
				],
			],
		],
		Paper(withBorder=True, p="lg", radius="md")[
			Stack(gap="md")[
				Text("Inline options (no dropdown)", fw=600),
				Combobox(store=state.inline_store, onOptionSubmit=state.choose_inline)[
					ComboboxEventsTarget()[
						TextInput(
							label="Inline combobox",
							placeholder="Type or pick",
							value=state.inline_value,
							onChange=state.set_inline_value,
						),
					],
					ComboboxOptions()[
						ComboboxOption("First", value="First"),
						ComboboxOption("Second", value="Second"),
						ComboboxOption("Third", value="Third"),
					],
				],
			],
		],
		Paper(withBorder=True, p="lg", radius="md")[
			Stack(gap="md")[
				Group(justify="space-between")[
					Text("Event log", fw=600),
					Button("Clear", variant="subtle", onClick=state.clear_events),
				],
				ScrollArea(h=160)[
					Stack(gap="xs")[*[Text(item, size="sm") for item in state.events]]
				],
			],
		],
	]


app = ps.App([ps.Route("/", Demo)])
