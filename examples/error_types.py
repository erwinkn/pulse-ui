import asyncio

import pulse as ps

_seen_render_failures: set[int] = set()
_seen_setup_failures: set[int] = set()
_seen_init_failures: set[int] = set()


def fail(message: str) -> None:
	raise RuntimeError(message)


def consume_failure_once(seen: set[int], token: int | None) -> bool:
	if token is None or token in seen:
		return False
	seen.add(token)
	return True


def raise_deep_stack(message: str) -> None:
	chain_lines: list[str] = []
	depth = 24
	for idx in range(depth):
		next_name = f"frame_{idx + 1}" if idx + 1 < depth else "raise_internal"
		chain_lines.append(f"def frame_{idx}():\n    return {next_name}()")
	chain_lines.append(
		"def raise_internal():\n"
		"    namespace = {}\n"
		"    exec(\n"
		"        compile(\n"
		f'            "def __overlay_raise__():\\n    raise RuntimeError({message!r})\\n__overlay_raise__()\\n",\n'
		'            "node_modules/pulse_overlay_internal.py",\n'
		'            "exec",\n'
		"        ),\n"
		"        namespace,\n"
		"        namespace,\n"
		"    )"
	)
	chain_lines.append("frame_0()")
	namespace: dict[str, object] = {}
	exec(
		compile("\n\n".join(chain_lines), "examples/error_types.py", "exec"),
		namespace,
		namespace,
	)


def init_probe_value(token: int, should_fail: bool) -> str:
	if should_fail:
		raise RuntimeError("init failure in error_types example")
	return f"init:{token}"


class ActivityState(ps.State):
	recent: list[str] = []

	def record(self, label: str) -> None:
		self.recent = [label, *self.recent[:11]]


class RefFailureState(ps.State):
	show_mount_target: bool = False
	show_unmount_target: bool = True

	def toggle_mount_target(self) -> None:
		self.show_mount_target = not self.show_mount_target

	def show_unmount_target_again(self) -> None:
		self.show_unmount_target = True

	def hide_unmount_target(self) -> None:
		self.show_unmount_target = False


class QueryFailureState(ps.State):
	reload_token: int = 0
	fail_handler: bool = False

	@ps.query(retries=0)
	async def value(self) -> int:
		await asyncio.sleep(0.05)
		return self.reload_token

	@value.key
	def _value_key(self):
		return ("error-types", self.reload_token)

	@value.on_success
	def _on_success(self, _value: int) -> None:
		if self.fail_handler:
			self.fail_handler = False
			raise RuntimeError("query.on_success failure in error_types example")

	def trigger(self) -> None:
		self.fail_handler = True
		self.reload_token += 1


class MutationFailureState(ps.State):
	fail_handler: bool = False
	runs: int = 0

	@ps.mutation
	async def run(self) -> int:
		await asyncio.sleep(0.05)
		self.runs += 1
		return self.runs

	@run.on_success
	def _on_success(self, _value: int) -> None:
		if self.fail_handler:
			self.fail_handler = False
			raise RuntimeError("mutation.on_success failure in error_types example")

	async def trigger(self) -> None:
		self.fail_handler = True
		await self.run()


class DestructiveFailureState(ps.State):
	next_token: int = 0
	render_enabled: bool = False
	setup_enabled: bool = False
	init_enabled: bool = False
	render_token: int | None = None
	setup_token: int | None = None
	init_token: int | None = None

	def claim_token(self) -> int:
		self.next_token += 1
		return self.next_token

	def trigger_render(self) -> None:
		self.render_enabled = True
		self.render_token = self.claim_token()

	def trigger_setup(self) -> None:
		self.setup_enabled = True
		self.setup_token = self.claim_token()

	def trigger_init(self) -> None:
		self.init_enabled = True
		self.init_token = self.claim_token()

	def reset(self) -> None:
		self.render_enabled = False
		self.setup_enabled = False
		self.init_enabled = False
		self.render_token = None
		self.setup_token = None
		self.init_token = None


def button(label: str, on_click, *, tone: str = "slate"):
	tones = {
		"slate": "border-slate-700 bg-slate-900 hover:border-slate-400",
		"amber": "border-amber-700 bg-amber-950 hover:border-amber-400",
		"rose": "border-rose-700 bg-rose-950 hover:border-rose-400",
	}
	return ps.button(
		label,
		onClick=on_click,
		className=f"rounded border px-3 py-2 text-sm text-left {tones[tone]}",
	)


def section(title: str, description: str, *children):
	return ps.section(className="rounded-xl border border-slate-800 bg-slate-900 p-4")[
		ps.h2(title, className="text-lg font-semibold"),
		ps.p(description, className="mt-1 text-sm text-slate-300"),
		ps.div(className="mt-3 flex flex-wrap gap-2")[*children],
	]


@ps.component
def RenderFailureProbe(token: int):
	if consume_failure_once(_seen_render_failures, token):
		raise RuntimeError("render failure in error_types example")
	return ps.div(
		f"Render probe consumed ({token})",
		className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-400",
	)


@ps.component
def SetupFailureProbe(token: int):
	def _boom(current_token: int) -> str:
		if consume_failure_once(_seen_setup_failures, current_token):
			raise RuntimeError("setup failure in error_types example")
		return f"setup:{current_token}"

	label = ps.setup(_boom, token)
	return ps.div(
		f"Setup probe consumed ({label})",
		className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-400",
	)


@ps.component
def InitFailureProbe(token: int):
	should_fail = consume_failure_once(_seen_init_failures, token)
	with ps.init():
		label = init_probe_value(token, should_fail)

	return ps.div(
		f"Init probe consumed ({label})",
		className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-400",
	)


@ps.component
def ErrorTypesPage():
	with ps.init():
		activity = ActivityState()
		refs = RefFailureState()
		query = QueryFailureState()
		mutation = MutationFailureState()
		destructive = DestructiveFailureState()

	def callback_failure() -> None:
		activity.record("callback")
		fail("callback failure in error_types example")

	def deep_callback_failure() -> None:
		activity.record("callback.deep")
		raise_deep_stack("Deep callback failure in error_types example. " * 8)

	def schedule_later_failure() -> None:
		def _later() -> None:
			activity.record("timer.later")
			fail("timer.later failure in error_types example")

		ps.later(0.05, _later)

	def schedule_repeat_failure() -> None:
		handle_box: list[object] = []

		def _repeat() -> None:
			activity.record("timer.repeat")
			handle = handle_box[0]
			handle.cancel()  # pyright: ignore[reportAttributeAccessIssue]
			fail("timer.repeat failure in error_types example")

		handle_box.append(ps.repeat(0.05, _repeat))

	def schedule_overlay_queue() -> None:
		def _first() -> None:
			activity.record("queue:1")
			fail("overlay queue item one")

		def _second() -> None:
			activity.record("queue:2")
			fail("overlay queue item two")

		ps.later(0.05, _first)
		ps.later(0.12, _second)

	async def submit_failure(_data: ps.FormData) -> None:
		activity.record("form")
		raise RuntimeError("form submission failure in error_types example")

	def ref_mount_failure() -> None:
		activity.record("ref.mount")
		fail("ref.mount failure in error_types example")

	def ref_unmount_failure() -> None:
		activity.record("ref.unmount")
		fail("ref.unmount failure in error_types example")

	def trigger_render_failure() -> None:
		activity.record("render")
		destructive.trigger_render()

	def trigger_setup_failure() -> None:
		activity.record("setup")
		destructive.trigger_setup()

	def trigger_init_failure() -> None:
		activity.record("init")
		destructive.trigger_init()

	mount_ref = ps.ref(on_mount=ref_mount_failure)
	unmount_ref = ps.ref(on_unmount=ref_unmount_failure)

	return ps.div(className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100")[
		ps.div(className="mx-auto max-w-6xl space-y-6")[
			ps.header(className="space-y-3")[
				ps.h1("Pulse Error Modes", className="text-3xl font-bold"),
				ps.p(
					"Every button below triggers a real failure path inside the mounted app so the dev overlay can be verified end-to-end.",
					className="max-w-3xl text-sm text-slate-300",
				),
			],
			ps.div(className="grid gap-4 lg:grid-cols-2")[
				section(
					"Render / Setup / Init",
					"These failures are mounted into the current route so they exercise the overlay instead of falling back to the router prerender error page.",
					button(
						"Trigger render failure", trigger_render_failure, tone="rose"
					),
					button(
						"Trigger setup failure", trigger_setup_failure, tone="amber"
					),
					button("Trigger init failure", trigger_init_failure, tone="amber"),
					button("Reset destructive probes", destructive.reset, tone="slate"),
				),
				section(
					"Callback",
					"Direct callback exceptions plus a deep stack variant for overlay controls.",
					button("Trigger callback failure", callback_failure, tone="rose"),
					button(
						"Trigger deep callback failure",
						deep_callback_failure,
						tone="amber",
					),
				),
				section(
					"Timers",
					"Exceptions raised from later() and repeat(), plus a two-error sequence for queue navigation.",
					button("Trigger later() failure", schedule_later_failure),
					button("Trigger repeat() failure", schedule_repeat_failure),
					button("Trigger queued timer failures", schedule_overlay_queue),
				),
				section(
					"Refs",
					"Mount and unmount handlers raise from the real ref lifecycle hooks.",
					button(
						"Toggle mount target",
						refs.toggle_mount_target,
						tone="amber",
					),
					button(
						"Hide unmount target",
						refs.hide_unmount_target,
						tone="rose",
					),
					button(
						"Show unmount target",
						refs.show_unmount_target_again,
						tone="slate",
					),
				),
				section(
					"Query / Mutation",
					"Handlers fail from on_success after a real query refetch or mutation completion.",
					button(
						"Trigger query handler failure", query.trigger, tone="amber"
					),
					button(
						"Trigger mutation handler failure",
						mutation.trigger,
						tone="rose",
					),
				),
			],
			ps.section(className="rounded-xl border border-slate-800 bg-slate-900 p-4")[
				ps.h2("Form", className="text-lg font-semibold"),
				ps.p(
					"Submit this real Pulse form to raise from the server-side submit handler.",
					className="mt-1 text-sm text-slate-300",
				),
				ps.Form(key="error-types-form", onSubmit=submit_failure)[
					ps.div(className="mt-3 flex flex-wrap items-end gap-3")[
						ps.label(className="flex min-w-64 flex-col gap-1 text-sm")[
							ps.span("Any value", className="text-slate-300"),
							ps.input(
								name="value",
								defaultValue="overlay-check",
								className="rounded border border-slate-700 bg-slate-950 px-3 py-2",
							),
						],
						ps.button(
							"Submit failing form",
							type="submit",
							className="rounded border border-rose-700 bg-rose-950 px-3 py-2 text-sm hover:border-rose-400",
						),
					]
				],
			],
			ps.section(className="rounded-xl border border-slate-800 bg-slate-900 p-4")[
				ps.h2("Live State", className="text-lg font-semibold"),
				ps.div(className="mt-3 grid gap-4 md:grid-cols-2")[
					ps.div(className="space-y-2 text-sm text-slate-300")[
						ps.p(f"Query reload token: {query.reload_token}"),
						ps.p(f"Mutation runs: {mutation.runs}"),
						ps.p(f"Render probe active: {destructive.render_enabled}"),
						ps.p(f"Setup probe active: {destructive.setup_enabled}"),
						ps.p(f"Init probe active: {destructive.init_enabled}"),
						ps.p(f"Render probe token: {destructive.render_token}"),
						ps.p(f"Setup probe token: {destructive.setup_token}"),
						ps.p(f"Init probe token: {destructive.init_token}"),
						ps.p(f"Mount target visible: {refs.show_mount_target}"),
						ps.p(f"Unmount target visible: {refs.show_unmount_target}"),
					],
					ps.div(className="space-y-2")[
						RenderFailureProbe(destructive.render_token)
						if destructive.render_enabled
						and destructive.render_token is not None
						else None,
						SetupFailureProbe(destructive.setup_token)
						if destructive.setup_enabled
						and destructive.setup_token is not None
						else None,
						InitFailureProbe(destructive.init_token)
						if destructive.init_enabled
						and destructive.init_token is not None
						else None,
						ps.div(
							"Mount target",
							ref=mount_ref,
							className="rounded border border-amber-700 bg-amber-950 px-3 py-2 text-sm text-amber-100",
						)
						if refs.show_mount_target
						else ps.div(
							"Mount target hidden",
							className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-400",
						),
						ps.div(
							"Unmount target",
							ref=unmount_ref,
							className="rounded border border-rose-700 bg-rose-950 px-3 py-2 text-sm text-rose-100",
						)
						if refs.show_unmount_target
						else ps.div(
							"Unmount target hidden",
							className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-400",
						),
					],
				],
			],
			ps.section(className="rounded-xl border border-slate-800 bg-slate-900 p-4")[
				ps.h2("Recent Triggers", className="text-lg font-semibold"),
				ps.ul(className="mt-3 space-y-1 font-mono text-sm text-slate-300")[
					ps.For(
						activity.recent,
						lambda item, idx: ps.li(
							f"{idx + 1}. {item}", key=f"{item}:{idx}"
						),
					)
					if activity.recent
					else ps.li("No failures triggered yet."),
				],
			],
		]
	]


app = ps.App([ps.Route("/", ErrorTypesPage)])
