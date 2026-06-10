"""Fine-grained rendering: per-component render effects.

State changes re-render only the component that read the state, not the whole
tree. These tests exercise the RenderTree dispatch machinery directly (no
View/RenderSession), accumulating ops via tree.take_ops().
"""

from typing import cast

import pulse as ps
from pulse.reactive import Signal, flush_effects
from pulse.renderer import RenderTree
from pulse.transpiler.vdom import VDOMElement


def test_leaf_state_change_rerenders_only_leaf():
	leaf_signal = Signal(0)
	renders = {"parent": 0, "leaf": 0, "sibling": 0}

	@ps.component
	def Leaf():
		renders["leaf"] += 1
		return ps.span(f"count: {leaf_signal()}")

	@ps.component
	def Sibling():
		renders["sibling"] += 1
		return ps.span("static")

	@ps.component
	def Parent():
		renders["parent"] += 1
		return ps.div(Leaf(), Sibling())

	tree = RenderTree(Parent())
	vdom = cast(VDOMElement, tree.render())
	assert renders == {"parent": 1, "leaf": 1, "sibling": 1}
	assert vdom == {
		"tag": "div",
		"children": [
			{"tag": "span", "children": ["count: 0"]},
			{"tag": "span", "children": ["static"]},
		],
	}

	leaf_signal.write(1)
	flush_effects()

	assert renders == {"parent": 1, "leaf": 2, "sibling": 1}
	ops = tree.take_ops()
	assert ops == [
		{
			"type": "reconciliation",
			"path": "0",
			"N": 1,
			"new": ([0], ["count: 1"]),
			"reuse": ([], []),
		}
	]


def test_parent_state_change_rerenders_subtree_once():
	parent_signal = Signal("a")
	child_signal = Signal(0)
	renders = {"parent": 0, "child": 0}

	@ps.component
	def Child():
		renders["child"] += 1
		return ps.span(f"child: {child_signal()}")

	@ps.component
	def Parent():
		renders["parent"] += 1
		return ps.div(parent_signal(), Child())

	tree = RenderTree(Parent())
	tree.render()
	assert renders == {"parent": 1, "child": 1}

	# Parent and child deps change in the same batch: the parent re-renders
	# first and refreshes the child, whose queued run then becomes a no-op.
	parent_signal.write("b")
	child_signal.write(1)
	flush_effects()

	assert renders == {"parent": 2, "child": 2}


def test_child_state_change_does_not_rerun_parent():
	child_signal = Signal(0)
	renders = {"parent": 0, "child": 0}

	@ps.component
	def Child():
		renders["child"] += 1
		return ps.span(child_signal())

	@ps.component
	def Parent():
		renders["parent"] += 1
		return ps.div(Child())

	tree = RenderTree(Parent())
	tree.render()

	for i in range(1, 4):
		child_signal.write(i)
		flush_effects()
		assert renders["child"] == 1 + i
		assert renders["parent"] == 1


def test_unmounted_component_effect_is_disposed():
	show = Signal(True)
	leaf_signal = Signal(0)
	renders = {"leaf": 0}

	@ps.component
	def Leaf():
		renders["leaf"] += 1
		return ps.span(leaf_signal())

	@ps.component
	def Parent():
		if show():
			return ps.div(Leaf())
		return ps.div(ps.span("empty"))

	tree = RenderTree(Parent())
	tree.render()
	assert renders["leaf"] == 1
	runtimes = list(tree.iter_runtimes())
	assert len(runtimes) == 2  # Parent + Leaf

	show.write(False)
	flush_effects()
	tree.take_ops()

	# The leaf is unmounted: its effect must no longer react to its state.
	leaf_signal.write(1)
	flush_effects()
	assert renders["leaf"] == 1
	assert tree.take_ops() == []
	assert len(list(tree.iter_runtimes())) == 1


def test_nested_component_ops_use_absolute_paths():
	inner_signal = Signal("x")

	@ps.component
	def Inner():
		return ps.span(inner_signal())

	@ps.component
	def Middle():
		return ps.section(ps.p("intro"), Inner())

	@ps.component
	def Outer():
		return ps.div(ps.h1("title"), Middle())

	tree = RenderTree(Outer())
	vdom = cast(VDOMElement, tree.render())
	middle = cast(VDOMElement, vdom.get("children", [])[1])
	assert middle.get("children", [])[1] == {"tag": "span", "children": ["x"]}

	inner_signal.write("y")
	flush_effects()
	ops = tree.take_ops()
	assert ops == [
		{
			"type": "reconciliation",
			"path": "1.1",
			"N": 1,
			"new": ([0], ["y"]),
			"reuse": ([], []),
		}
	]


def test_callbacks_swept_per_component_pass():
	toggle = Signal(True)
	other_clicked: list[str] = []

	@ps.component
	def WithButton():
		if toggle():
			return ps.button("on", onClick=lambda: None)
		return ps.span("off")

	@ps.component
	def OtherButton():
		return ps.button("other", onClick=lambda: other_clicked.append("hit"))

	@ps.component
	def Root():
		return ps.div(WithButton(), OtherButton())

	tree = RenderTree(Root())
	tree.render()
	assert set(tree.callbacks) == {"0.onClick", "1.onClick"}

	toggle.write(False)
	flush_effects()
	tree.take_ops()

	# WithButton's callback is gone; OtherButton's untouched (it never re-ran).
	assert set(tree.callbacks) == {"1.onClick"}
	tree.callbacks["1.onClick"].fn()
	assert other_clicked == ["hit"]


def test_keyed_reorder_rebinds_component_paths():
	order = Signal(["a", "b"])
	signals = {"a": Signal(0), "b": Signal(0)}

	@ps.component
	def Item(name: str, key: str | None = None):
		return ps.li(f"{name}:{signals[name]()}")

	@ps.component
	def Root():
		return ps.ul(*[Item(name, key=name) for name in order()])

	tree = RenderTree(Root())
	vdom = cast(VDOMElement, tree.render())
	items = [cast(VDOMElement, c) for c in vdom.get("children", [])]
	assert [c.get("children", [])[0] for c in items] == ["a:0", "b:0"]

	order.write(["b", "a"])
	flush_effects()
	tree.take_ops()

	# After the reorder, item "a" lives at index 1; its update must target it.
	signals["a"].write(7)
	flush_effects()
	ops = tree.take_ops()
	assert ops == [
		{
			"type": "reconciliation",
			"path": "1",
			"N": 1,
			"new": ([0], ["a:7"]),
			"reuse": ([], []),
		}
	]


def test_pause_and_resume_effects():
	leaf_signal = Signal(0)
	renders = {"leaf": 0}

	@ps.component
	def Leaf():
		renders["leaf"] += 1
		return ps.span(leaf_signal())

	tree = RenderTree(Leaf())
	tree.render()

	tree.pause_effects()
	leaf_signal.write(1)
	flush_effects()
	assert renders["leaf"] == 1

	tree.resume_effects()
	flush_effects()
	assert renders["leaf"] == 2
	ops = tree.take_ops()
	assert ops == [
		{
			"type": "reconciliation",
			"path": "",
			"N": 1,
			"new": ([0], [1]),
			"reuse": ([], []),
		}
	]


def test_sibling_updates_in_one_batch_emit_separate_precise_ops():
	left = Signal(0)
	right = Signal(0)

	@ps.component
	def Left():
		return ps.span(f"L{left()}")

	@ps.component
	def Right():
		return ps.span(f"R{right()}")

	@ps.component
	def Root():
		return ps.div(Left(), Right())

	tree = RenderTree(Root())
	tree.render()

	left.write(1)
	right.write(2)
	flush_effects()
	ops = tree.take_ops()
	assert sorted(op["path"] for op in ops) == ["0", "1"]
	assert all(op["type"] == "reconciliation" for op in ops)


def test_parent_unmounting_child_in_same_batch_skips_child_effect():
	"""Parent and child both read the same signal; the parent's re-render
	unmounts the child, whose queued effect must not run afterwards."""
	show = Signal(True)
	renders = {"parent": 0, "child": 0}

	@ps.component
	def Child():
		renders["child"] += 1
		return ps.span(f"child sees {show()}")

	@ps.component
	def Parent():
		renders["parent"] += 1
		if show():
			return ps.div(Child())
		return ps.div(ps.span("empty"))

	tree = RenderTree(Parent())
	tree.render()
	assert renders == {"parent": 1, "child": 1}

	show.write(False)
	flush_effects()

	# The child was unmounted by the parent's pass; its queued run is skipped.
	assert renders == {"parent": 2, "child": 1}
	ops = tree.take_ops()
	assert ops and all(op["path"].startswith("") for op in ops)
	assert len(list(tree.iter_runtimes())) == 1
