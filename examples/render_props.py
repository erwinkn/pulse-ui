import pulse as ps


@ps.react_component("RenderPropComponent", "~/components/render-prop")
def RenderPropComponent(
	*children: ps.Child,
	key: str | None = None,
	left: ps.Element = None,
	right: ps.Element = None,
): ...


class CounterState(ps.State):
	label: str
	count: int = 0

	def __init__(self, label: str):
		self.label = label

	def increment(self):
		self.count += 1

	def decrement(self):
		self.count -= 1

	def reset(self):
		self.count = 0


@ps.component
def RenderPropCounter(label: str):
	state = ps.states(CounterState(label))
	return ps.div(className="flex items-center gap-2")[
		ps.button("−", onClick=state.decrement, className="btn-secondary"),
		ps.span(
			f"rendered: {label} | state: {state.label} | count: {state.count}",
			className="font-mono text-sm",
		),
		ps.button("+", onClick=state.increment, className="btn-secondary"),
	]


class SwapDemoState(ps.State):
	unkeyed_swapped: bool = False
	keyed_swapped: bool = False

	def toggle_unkeyed(self):
		self.unkeyed_swapped = not self.unkeyed_swapped

	def toggle_keyed(self):
		self.keyed_swapped = not self.keyed_swapped


@ps.component
def UnkeyedVsKeyedSwapSection():
	state = ps.states(SwapDemoState)
	labels = ["Alpha", "Beta"]

	def render_item(label: str, *, use_key: bool) -> ps.Element:
		return ps.div(
			className="rounded border p-3 space-y-2", key=label if use_key else None
		)[
			RenderPropComponent(
				left=RenderPropCounter(label=f"{label} left"),
			)[
				ps.div(
					ps.h4(label, className="font-semibold"),
					ps.p(
						"Click the counter buttons on the left, then swap the order to observe how state behaves.",
						className="text-sm text-slate-600",
					),
				)
			]
		]

	def ordered(seq, swapped: bool) -> list[str]:
		return list(reversed(seq)) if swapped else list(seq)

	return ps.div(className="space-y-4")[
		ps.h2("Unkeyed vs keyed render prop swap", className="text-xl font-semibold"),
		ps.p(
			"Swapping unkeyed components reuses the underlying render prop instances, while keyed instances carry their state along with the key.",
			className="text-sm text-slate-600",
		),
		ps.div(className="grid gap-4 md:grid-cols-2")[
			ps.div(className="space-y-2")[
				ps.div(className="flex justify-between items-center")[
					ps.h3("Unkeyed", className="font-semibold"),
					ps.button(
						"Swap",
						onClick=state.toggle_unkeyed,
						className="btn-primary btn-sm",
					),
				],
				*[
					render_item(label, use_key=False)
					for label in ordered(labels, state.unkeyed_swapped)
				],
			],
			ps.div(className="space-y-2")[
				ps.div(className="flex justify-between items-center")[
					ps.h3("Keyed", className="font-semibold"),
					ps.button(
						"Swap",
						onClick=state.toggle_keyed,
						className="btn-primary btn-sm",
					),
				],
				*[
					render_item(label, use_key=True)
					for label in ordered(labels, state.keyed_swapped)
				],
			],
		],
	]


@ps.component
def CounterWithControlRenderProps():
	state = ps.states(CounterState("control"))
	return ps.div(className="space-y-3")[
		ps.h2(
			"Buttons supplied through render props", className="text-xl font-semibold"
		),
		RenderPropComponent(
			left=ps.button("−", onClick=state.decrement, className="btn-secondary"),
			right=ps.button("+", onClick=state.increment, className="btn-secondary"),
		)[
			ps.div(
				ps.span(f"Count: {state.count}", className="font-mono text-lg"),
				ps.p(
					"Both increment and decrement buttons are Pulse components passed as render props.",
					className="text-sm text-slate-600",
				),
			)
		],
		ps.button("Reset", onClick=state.reset, className="btn-light btn-sm"),
	]


class DynamicRenderPropState(ps.State):
	active: bool = False
	index: int = 0

	labels = ["Primary", "Secondary", "Acid"]

	def toggle(self):
		self.active = not self.active

	def cycle(self):
		self.index = (self.index + 1) % len(self.labels)


@ps.component
def DynamicRenderPropUpdates():
	state = ps.states(DynamicRenderPropState)
	label = state.labels[state.index]
	button_class = "btn-primary" if state.active else "btn-secondary"
	return ps.div(className="space-y-3")[
		ps.h2(
			"Updating props and callbacks inside render props",
			className="text-xl font-semibold",
		),
		RenderPropComponent(
			left=ps.button(
				f"Toggle ({label})",
				className=f"{button_class} btn-sm",
				onClick=state.toggle,
				disabled=state.active and state.index == 0,
			),
			right=ps.button(
				"Next label", className="btn-light btn-sm", onClick=state.cycle
			),
		)[
			ps.p(
				"The button on the left lives inside a render prop and updates both its class and disabled state as local state changes.",
				className="text-sm text-slate-600",
			)
		],
	]


class NestedRenderPropState(ps.State):
	swap: bool = False

	def toggle(self):
		self.swap = not self.swap


@ps.component
def NestedRenderPropsSection():
	state = ps.states(NestedRenderPropState)

	def inner(label: str) -> ps.Element:
		return RenderPropComponent(
			left=RenderPropCounter(label=f"{label} inner"),
			right=ps.span(f"Nested child: {label}", className="text-xs text-slate-600"),
		)[ps.span(f"Inner payload {label}")]

	left_label, right_label = (
		("Blue", "Orange") if not state.swap else ("Orange", "Blue")
	)

	return ps.div(className="space-y-3")[
		ps.h2("Nested render props", className="text-xl font-semibold"),
		ps.button(
			"Swap inner order", onClick=state.toggle, className="btn-primary btn-sm"
		),
		RenderPropComponent(
			left=inner(left_label),
			right=RenderPropCounter(label=f"{right_label} outer"),
		)[
			ps.p(
				"The left slot is another RenderPropComponent whose content swaps as you toggle the button.",
				className="text-sm text-slate-600",
			)
		],
	]


@ps.component
def RenderPropsPage():
	return ps.div(className="space-y-8 max-w-5xl mx-auto py-10")[
		ps.h1("Render prop experiments", className="text-3xl font-bold"),
		ps.p(
			"These examples demonstrate Pulse components supplied as render props to a React component, including keyed swaps, nested render props, and callback wiring.",
			className="text-slate-600",
		),
		UnkeyedVsKeyedSwapSection(),
		CounterWithControlRenderProps(),
		DynamicRenderPropUpdates(),
		NestedRenderPropsSection(),
	]


app = ps.App(
	[ps.Route("/", RenderPropsPage)],
)
