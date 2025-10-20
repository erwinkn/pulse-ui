import pulse as ps

# This example exercises all keyed reconciliation code paths in packages/pulse/src/pulse/renderer.py
# The scenarios are driven by a stateful stepper that transforms a keyed child list through
# sequences that force each branch:
#   - Step 0 → 1: empty → keyed inserts (n_old=0)
#   - Step 1 → 2: head-only inserts
#   - Step 2 → 3: tail-only inserts
#   - Step 3 → 4: middle early deletes (delete keys not present in new mid-slice)
#   - Step 4 → 5: move-only via LIS (reorder survivors without insert/delete)
#   - Step 5 → 6: insert + move mix in middle window
#   - Step 6 → 7: tail-only removals (n_new < n_old, trailing deletes)
#   - Step 7 → 8: head-only removals (leading deletes)
#   - Step 8 → 9: replace same key with different tag to trigger replace op
# Also covers phase-2 deep pass by changing props on head/tail survivors.


def Item(label: str, *, key: str, variant: str = "div") -> ps.Element:
	if variant == "div":
		return ps.div(
			ps.span(label, className="font-mono"),
			key=key,
			className="px-2 py-1 rounded border",
		)
	if variant == "p":
		return ps.p(label, key=key, className="px-2 py-1 rounded border")
	# Fallback to div
	return ps.div(ps.span(label), key=key)


class Steps(ps.State):
	step: int = 0
	# toggle to alter a head survivor's props to force a phase-2 deep patch
	flip: bool = False

	def next(self):
		self.step = min(self.step + 1, 9)

	def prev(self):
		self.step = max(self.step - 1, 0)

	def toggle(self):
		self.flip = not self.flip


def scenario(step: int, flip: bool) -> list[ps.Element]:
	# Keys universe we reuse to get stable identities: A..G
	# We attach a small style/label mutation to A to ensure deep patch runs on survivors.
	a_label = f"A{'*' if flip else ''}"

	if step == 0:
		# []
		return []

	if step == 1:
		# Inserts only (n_old=0) → [A, B]
		return [
			Item(a_label, key="A"),
			Item("B", key="B"),
		]

	if step == 2:
		# Head-only insert → [X, A, B] (X is new at head)
		return [
			Item("X", key="X"),
			Item(a_label, key="A"),
			Item("B", key="B"),
		]

	if step == 3:
		# Tail-only insert → [X, A, B, C]
		return [
			Item("X", key="X"),
			Item(a_label, key="A"),
			Item("B", key="B"),
			Item("C", key="C"),
		]

	if step == 4:
		# Early deletes in middle window: drop X and C → [A, B]
		# (old mid had X,A,B,C; new mid keeps only A,B)
		return [
			Item(a_label, key="A"),
			Item("B", key="B"),
		]

	if step == 5:
		# Move-only (no insert/delete): [B, A] (LIS path will detect reorder)
		return [
			Item("B", key="B"),
			Item(a_label, key="A"),
		]

	if step == 6:
		# Insert + move mix in middle: [B, A, D] (D new at tail; order change retained)
		return [
			Item("B", key="B"),
			Item(a_label, key="A"),
			Item("D", key="D"),
		]

	if step == 7:
		# Tail-only removals: remove D → [B, A]
		return [
			Item("B", key="B"),
			Item(a_label, key="A"),
		]

	if step == 8:
		# Head-only removals: remove B → [A]
		return [
			Item(a_label, key="A"),
		]

	if step == 9:
		# Same key different tag → ReplaceOperation at that index
		# A remains but tag switches from div→p to hit replace branch despite same key
		return [
			Item(a_label, key="A", variant="p"),
		]

	# Fallback: mirror step 1
	return [Item(a_label, key="A"), Item("B", key="B")]


@ps.component
def KeyedList(step: int, flip: bool):
	items = scenario(step, flip)
	return ps.ul(className="space-y-2 list-none p-0 m-0")[
		[
			ps.li(child, key=child.key) if isinstance(child, ps.Node) else child
			for child in items
		]
	]


@ps.component
def Controls(state: Steps):
	return ps.div(className="flex items-center gap-2")[
		ps.button("Prev", onClick=state.prev, className="btn-secondary"),
		ps.span(f"step={state.step}", className="font-mono text-sm"),
		ps.button("Next", onClick=state.next, className="btn-secondary"),
		ps.button("Flip A label", onClick=state.toggle, className="btn-light"),
	]


@ps.component
def KeyedReconciliationPage():
	state = ps.states(Steps)
	return ps.div(className="max-w-3xl mx-auto py-8 space-y-4")[
		ps.h1("Keyed reconciliation scenarios", className="text-2xl font-bold"),
		ps.p(
			"Step through to exercise inserts, deletes, moves (LIS), and replace at same key.",
			className="text-slate-600",
		),
		Controls(state),
		ps.div(className="rounded border p-3 bg-white shadow")[
			KeyedList(step=state.step, flip=state.flip)
		],
		ps.ul(className="text-xs text-slate-600 space-y-1 list-disc pl-5")[
			ps.li("0: []"),
			ps.li("1: [A, B] (insert only)"),
			ps.li("2: [X, A, B] (head insert)"),
			ps.li("3: [X, A, B, C] (tail insert)"),
			ps.li("4: [A, B] (early deletes in middle)"),
			ps.li("5: [B, A] (move-only)"),
			ps.li("6: [B, A, D] (insert + move mix)"),
			ps.li("7: [B, A] (tail removals)"),
			ps.li("8: [A] (head removals)"),
			ps.li("9: [A<p>] (same key, different tag → replace)"),
		],
	]


app = ps.App(
	[ps.Route("/", KeyedReconciliationPage)],
)
