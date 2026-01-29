from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.component import component
from pulse.dom.tags import button, div, li, span, ul
from pulse.hooks.core import HookContext
from pulse.refs import RefHandle
from pulse.renderer import RenderTree
from pulse.transpiler.nodes import Element, PulseNode
from pulse.transpiler.vdom import VDOMElement, VDOMExpr


# Helpers for reconciliation-based updates
def _apply_reconciliation(prev: list[str], op: dict[str, Any]) -> list[str]:
	N = op["N"]
	new_indices, new_values = op["new"]
	reuse_indices, reuse_sources = op["reuse"]
	next_list: list[str | None] = [None] * N
	new_map = {dest: val for dest, val in zip(new_indices, new_values, strict=True)}
	reuse_map = {
		dest: src for dest, src in zip(reuse_indices, reuse_sources, strict=True)
	}
	for i in range(N):
		if i in new_map:
			v = new_map[i]
			if isinstance(v, dict) and "key" in v:
				next_list[i] = v["key"]
			elif isinstance(v, str):
				next_list[i] = v
			elif (
				isinstance(v, dict)
				and "children" in v
				and isinstance(v["children"], list)
			):
				# For components, try to extract the key from the structure
				if "key" in v:
					next_list[i] = v["key"]
				else:
					# For component VDOM, try to extract key from first child span content
					# This handles cases like CounterComponent where the key is in the span text
					first_child = v["children"][0] if v["children"] else None
					if (
						isinstance(first_child, dict)
						and first_child.get("tag") == "span"
						and isinstance(first_child.get("children"), list)
						and len(first_child["children"]) > 0  # pyright: ignore[reportUnknownArgumentType]
					):
						# Extract the label from "E:0" -> "e"
						span_text = first_child["children"][0]
						if isinstance(span_text, str) and ":" in span_text:
							label = span_text.split(":")[0].lower()
							next_list[i] = label
						else:
							next_list[i] = (
								span_text.lower()
								if isinstance(span_text, str)
								else v.get("tag", "?")
							)
					else:
						# Prefer first string child if present; otherwise fall back to tag
						s = next((c for c in v["children"] if isinstance(c, str)), None)
						next_list[i] = s if s is not None else v.get("tag", "?")
			else:
				next_list[i] = str(v)  # pyright: ignore[reportUnknownArgumentType]
		elif i in reuse_map:
			next_list[i] = prev[reuse_map[i]]
		else:
			next_list[i] = prev[i] if i < len(prev) else None
	return [x for x in next_list if x is not None]


def _get_reconciliation_ops(ops: Sequence[Any], path: str = "") -> list[dict[str, Any]]:
	return [
		op
		for op in ops
		if op.get("type") == "reconciliation" and op.get("path") == path
	]


class TrackingHookContext(HookContext):
	did_unmount: bool

	def __init__(self) -> None:
		super().__init__()
		self.did_unmount = False

	@override
	def unmount(self) -> None:
		self.did_unmount = True
		super().unmount()


def test_keyed_reorder_applies_operations_in_correct_order():
	def keyed_item(label: str) -> Element:
		return Element("li", key=label.lower(), children=[label])

	initial_children = [
		keyed_item("A"),
		keyed_item("B"),
		keyed_item("C"),
		keyed_item("D"),
	]
	tree = RenderTree(ul(*initial_children))
	tree.render()

	reordered_children = [
		keyed_item("D"),
		keyed_item("B"),
		keyed_item("E"),
		keyed_item("A"),
	]

	ops = tree.rerender(ul(*reordered_children))

	normalized_root = tree.element
	assert isinstance(normalized_root, Element)
	assert isinstance(normalized_root.children, list)
	current_order = [cast(Element, child).key for child in normalized_root.children]
	assert current_order == ["d", "b", "e", "a"], "sanity check normalized order"

	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	expected_final = [child.key for child in reordered_children]
	dom_order = ["a", "b", "c", "d"]
	final_order = _apply_reconciliation(dom_order, recon_ops[0])
	assert final_order == expected_final


def test_nested_keyed_reorder_in_subtree():
	def inner_span(label: str) -> Element:
		return Element("span", key=label.lower(), children=[label])

	def outer_item(label: str, inner_labels: list[str]) -> Element:
		return Element(
			"li",
			key=f"outer-{label.lower()}",
			children=[
				Element(
					"ul",
					children=[inner_span(inner_label) for inner_label in inner_labels],
				)
			],
		)

	outer_a_initial = outer_item("A", ["A1", "A2", "A3", "A4"])
	outer_b = outer_item("B", ["B1", "B2"])

	tree = RenderTree(div(outer_a_initial, outer_b))
	tree.render()

	outer_a_reordered = outer_item("A", ["A4", "A2", "A5", "A1"])

	ops = tree.rerender(div(outer_a_reordered, outer_b))

	recon_ops = _get_reconciliation_ops(ops, path="0.0")
	assert len(recon_ops) == 1
	dom_order = ["a1", "a2", "a3", "a4"]
	expected_final = ["a4", "a2", "a5", "a1"]
	final_order = _apply_reconciliation(dom_order, recon_ops[0])
	assert final_order == expected_final

	normalized_root = tree.element
	assert isinstance(normalized_root, Element)
	outer = normalized_root.children
	assert isinstance(outer, list)
	first_outer = outer[0]
	assert isinstance(first_outer, Element)
	inner_list = first_outer.children
	assert isinstance(inner_list, list)
	assert len(inner_list) == 1
	inner_ul = inner_list[0]
	assert isinstance(inner_ul, Element)
	assert isinstance(inner_ul.children, list)
	inner_keys = [cast(Element, child).key for child in inner_ul.children]
	assert inner_keys == expected_final


def test_duplicate_key_detection_raises_error():
	first = Element("li", key="a")
	duplicate = Element("li", key="dup")

	tree = RenderTree(ul(first, duplicate))
	tree.render()

	with pytest.raises(ValueError, match="Duplicate key 'dup'"):
		tree.rerender(ul(first, duplicate, Element("li", key="dup")))


def test_component_replaced_with_text_unmounts_and_replaces():
	@component
	def Child() -> Element:
		return span("child")

	child = Child()
	child.key = "child"  # Ensure consistent key
	child.hooks = TrackingHookContext()

	sibling = Element("span", key="sibling", children=["sib"])

	tree = RenderTree(div(child, sibling))
	tree.render()

	assert isinstance(child.hooks, TrackingHookContext)
	assert child.hooks.did_unmount is False

	ops = tree.rerender(div("plain", Element("span", key="sibling", children=["sib"])))

	# With the new reconciliation algorithm, this generates a reconciliation operation
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	assert child.hooks.did_unmount is True


def test_diff_props_unmounts_render_prop_when_replaced_with_callback():
	@component
	def Child() -> Element:
		return span("child")

	child = Child()
	child.hooks = TrackingHookContext()

	tree = RenderTree(div(render=child))  # pyright: ignore[reportCallIssue, reportUnknownArgumentType]
	tree.render()

	assert isinstance(child.hooks, TrackingHookContext)
	assert child.hooks.did_unmount is False

	def handle_click() -> None:
		pass

	tree.rerender(div(render=handle_click))  # pyright: ignore[reportCallIssue, reportUnknownArgumentType]

	assert child.hooks.did_unmount is True


def test_diff_props_unmounts_render_prop_when_removed():
	@component
	def Child() -> Element:
		return span("child")

	child = Child()
	child.hooks = TrackingHookContext()

	tree = RenderTree(div(render=child))  # pyright: ignore[reportUnknownArgumentType, reportCallIssue]
	tree.render()

	assert isinstance(child.hooks, TrackingHookContext)
	assert child.hooks.did_unmount is False

	tree.rerender(div())

	assert child.hooks.did_unmount is True


def test_diff_props_unmounts_render_prop_when_replaced_with_jsexpr(tmp_path: Path):
	from pulse.transpiler.imports import Import, clear_import_registry
	from pulse.transpiler.nodes import Member

	clear_import_registry()

	@component
	def Child() -> Element:
		return span("child")

	child = Child()
	child.hooks = TrackingHookContext()

	tree = RenderTree(div(render=child))  # pyright: ignore[reportCallIssue, reportUnknownArgumentType]
	tree.render()

	assert isinstance(child.hooks, TrackingHookContext)
	assert child.hooks.did_unmount is False

	# Create a temporary CSS module file for testing
	test_css_file = tmp_path / "test.module.css"
	test_css_file.write_text(".foo { color: red; }")

	css_module = Import(str(test_css_file))
	css_ref = Member(css_module, "foo")

	tree.rerender(div(render=css_ref))  # pyright: ignore[reportCallIssue, reportUnknownArgumentType]

	assert child.hooks.did_unmount is True

	clear_import_registry()


def test_render_tree_initial_callbacks():
	def on_click() -> None:
		pass

	root = Element(
		"div",
		props={"id": "root"},
		children=[Element("button", props={"onClick": on_click}, children=["Click"])],
	)

	tree = RenderTree(root)
	vdom = tree.render()

	assert vdom == {
		"tag": "div",
		"props": {"id": "root"},
		"children": [
			{
				"tag": "button",
				"props": {"onClick": "$cb"},
				"children": ["Click"],
				"eval": ["onClick"],
			}
		],
	}
	assert set(tree.callbacks.keys()) == {"0.onClick"}


def test_callback_removal_clears_callbacks():
	def on_click() -> None:
		pass

	tree = RenderTree(div(button(onClick=on_click)["Click"]))
	tree.render()
	assert "0.onClick" in tree.callbacks

	tree.rerender(div())
	assert "0.onClick" not in tree.callbacks


def test_render_prop_removal_emits_update_props_delta():
	@component
	def Child() -> Element:
		return span("child")

	tree = RenderTree(div(render=Child()))  # pyright: ignore[reportCallIssue, reportUnknownArgumentType]
	tree.render()

	ops = tree.rerender(div())

	update_props = [op for op in ops if op["type"] == "update_props"]
	assert any(
		op["data"].get("remove") == ["render"] and op["data"].get("eval") == []
		for op in update_props
	)


def test_callback_render_prop_churn_updates_deltas():
	@component
	def Child() -> Element:
		return span("child")

	def handle_click() -> None:
		pass

	tree = RenderTree(div(button(onClick=handle_click)["Click"]))
	tree.render()

	ops = tree.rerender(div(render=Child()))  # pyright: ignore[reportCallIssue, reportUnknownArgumentType]
	assert "0.onClick" not in tree.callbacks
	assert any(
		op["type"] == "update_props" and "render" in op["data"].get("set", {})
		for op in ops
	)

	ops = tree.rerender(div(button(onClick=handle_click)["Click"]))
	assert "0.onClick" in tree.callbacks
	assert any(
		op["type"] == "update_props" and "render" in op["data"].get("remove", [])
		for op in ops
	)


def test_render_prop_nested_components_unmount_on_type_change():
	@component
	def Leaf() -> Element:
		return span("leaf")

	inner = Leaf()
	inner.hooks = TrackingHookContext()

	@component
	def Wrapper() -> Element:
		return div(inner)

	outer = Wrapper()
	outer.hooks = TrackingHookContext()

	tree = RenderTree(div(render=outer))  # pyright: ignore[reportCallIssue, reportUnknownArgumentType]
	tree.render()

	assert isinstance(inner.hooks, TrackingHookContext)
	assert isinstance(outer.hooks, TrackingHookContext)
	assert inner.hooks.did_unmount is False
	assert outer.hooks.did_unmount is False

	def handle_click() -> None:
		pass

	tree.rerender(div(onClick=handle_click))

	assert inner.hooks.did_unmount is True
	assert outer.hooks.did_unmount is True


def test_render_tree_unmount_clears_state_and_unmounts_children():
	@component
	def Child() -> Element:
		return span("child")

	child = Child()
	child.hooks = TrackingHookContext()

	tree = RenderTree(div(child))
	tree.render()

	assert isinstance(child.hooks, TrackingHookContext)
	assert child.hooks.did_unmount is False

	tree.unmount()

	assert child.hooks.did_unmount is True
	assert tree.callbacks == {}
	assert tree.rendered is False


def test_diff_updates_props():
	tree = RenderTree(Element("div", props={"class": "one"}))
	tree.render()

	ops = tree.rerender(Element("div", props={"class": "two"}))
	assert ops == [
		{
			"type": "update_props",
			"path": "",
			"data": {"set": {"class": "two"}},
		}
	]


def test_keyed_move_preserves_component_nodes():
	@component
	def Item(label: str, key: str | None = None) -> Element:
		return li(label)

	first = Item(label="A", key="a")
	second = Item(label="B", key="b")

	tree = RenderTree(ul(first, second))
	tree.render()

	# Verify initial order
	normalized_root = tree.element
	assert isinstance(normalized_root, Element)
	assert isinstance(normalized_root.children, list)
	assert len(normalized_root.children) == 2

	# Check that the initial labels are correct
	first_child = normalized_root.children[0]
	second_child = normalized_root.children[1]
	assert isinstance(first_child, PulseNode)
	assert isinstance(second_child, PulseNode)
	assert first_child.kwargs["label"] == "A"
	assert second_child.kwargs["label"] == "B"

	ops = tree.rerender(ul(Item(label="B", key="b"), Item(label="A", key="a")))

	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1

	# Verify labels moved correctly after reordering
	updated_root = tree.element
	assert isinstance(updated_root, Element)
	assert isinstance(updated_root.children, list)
	assert len(updated_root.children) == 2

	# After move: B should be first, A should be second
	updated_first_child = updated_root.children[0]
	updated_second_child = updated_root.children[1]
	assert isinstance(updated_first_child, PulseNode)
	assert isinstance(updated_second_child, PulseNode)
	assert updated_first_child.kwargs["label"] == "B"
	assert updated_second_child.kwargs["label"] == "A"

	# Verify the rendered DOM content matches the labels
	vdom_raw = tree.render()
	assert isinstance(vdom_raw, dict)
	vdom = cast(VDOMElement, vdom_raw)
	assert vdom["tag"] == "ul"
	children = vdom.get("children")
	assert isinstance(children, list)
	assert len(children) == 2

	# Check rendered content: B should be first, A should be second
	first_rendered = children[0]
	second_rendered = children[1]
	assert first_rendered == {"tag": "li", "children": ["B"]}
	assert second_rendered == {"tag": "li", "children": ["A"]}


def test_unmount_invokes_component_hooks():
	@component
	def Item(label: str, key: str | None = None) -> Element:
		return li(label)

	first = Item(label="A", key="a")
	second = Item(label="B", key="b")
	first.hooks = TrackingHookContext()
	second.hooks = TrackingHookContext()

	tree = RenderTree(ul(first, second))
	tree.render()

	tree.rerender(ul(Item(label="A", key="a")))

	assert isinstance(second.hooks, TrackingHookContext)
	assert second.hooks.did_unmount is True


def test_keyed_component_state_preservation():
	"""Test that component state is preserved when components are moved via keys."""

	class Counter(ps.State):
		count: int = 0
		label: str = ""

		def __init__(self, label: str):
			self.label = label

		def inc(self):
			self.count += 1

	@component
	def CounterComponent(label: str, key: str | None = None) -> Element:
		with ps.init():
			counter = Counter(label)

		def handle_click():
			counter.inc()

		return div(
			span(f"{counter.label}:{counter.count}"), button(onClick=handle_click)["+"]
		)

	# Initial render
	first = CounterComponent("A", key="a")
	second = CounterComponent("B", key="b")

	tree = RenderTree(div(first, second))
	tree.render()

	# Increment first counter
	tree.callbacks["0.1.onClick"].fn()
	ops = tree.rerender(div(first, second))
	# With the new reconciliation algorithm, this generates a reconciliation operation
	recon_ops = _get_reconciliation_ops(ops, path="0.0")
	assert len(recon_ops) == 1

	# Reorder components - move A to end
	ops = tree.rerender(div(second, first))
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1

	# Verify state is preserved - A should still have count 1
	normalized_root = tree.element
	assert isinstance(normalized_root, Element)
	assert isinstance(normalized_root.children, list)
	# A is now at index 1
	a_component = normalized_root.children[1]
	assert isinstance(a_component, PulseNode)
	# The component should still have its state preserved
	assert a_component.hooks is not None


def test_keyed_parent_node_move_preserves_child_state():
	"""Test that component state is preserved when a parent Element is moved due to its key."""

	class Counter(ps.State):
		count: int = 0
		label: str = ""

		def __init__(self, label: str):
			self.label = label

		def inc(self):
			self.count += 1

	@component
	def CounterComponent(label: str) -> Element:
		with ps.init():
			counter = Counter(label)

		def handle_click():
			counter.inc()

		return div(
			span(f"{counter.label}:{counter.count}"), button(onClick=handle_click)["+"]
		)

	# Create parent nodes with keys containing components
	parent_a = Element("div", children=[CounterComponent("A")], key="parent-a")
	parent_b = Element("div", children=[CounterComponent("B")], key="parent-b")

	tree = RenderTree(div(parent_a, parent_b))
	tree.render()

	# Increment counter in first parent
	tree.callbacks["0.0.1.onClick"].fn()
	ops = tree.rerender(div(parent_a, parent_b))
	# With the new reconciliation algorithm, this generates a reconciliation operation
	recon_ops = _get_reconciliation_ops(ops, path="0.0.0")
	assert len(recon_ops) == 1

	# Move parent A to end (swap positions)
	ops = tree.rerender(div(parent_b, parent_a))
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1

	# Verify the component state is preserved - A should still have count 1
	normalized_root = tree.element
	assert isinstance(normalized_root, Element)
	assert isinstance(normalized_root.children, list)
	# Parent A is now at index 1
	parent_a_node = normalized_root.children[1]
	assert isinstance(parent_a_node, Element)
	assert isinstance(parent_a_node.children, list)
	# The component should still have its state preserved
	a_component = parent_a_node.children[0]
	assert isinstance(a_component, PulseNode)
	assert a_component.hooks is not None

	# Inspect stored Counter state inside the component after the move using init hook
	init_ns = a_component.hooks.namespaces.get("init_storage")
	assert init_ns is not None
	stored_hook_state = next(iter(init_ns.states.values()))
	# InitState stores captured variables keyed by callsite
	assert hasattr(stored_hook_state, "storage")
	# Find the captured counter in the storage
	for entry in stored_hook_state.storage.values():
		if "counter" in entry["vars"]:
			stored_counter = entry["vars"]["counter"]
			assert isinstance(stored_counter, Counter)
			assert stored_counter.label == "A"
			assert stored_counter.count == 1
			break
	else:
		raise AssertionError("Counter not found in init storage")

	# Click A's button again at the new location; state should increment to 2
	tree.callbacks["1.0.1.onClick"].fn()
	ops = tree.rerender(div(parent_b, parent_a))
	# With the new reconciliation algorithm, this generates a reconciliation operation
	recon_ops = _get_reconciliation_ops(ops, path="1.0.0")
	assert len(recon_ops) == 1


def test_unkeyed_reconciliation_insert_remove():
	"""Test unkeyed reconciliation with proper operation ordering."""
	tree = RenderTree(div(span("A"), span("B")))
	tree.render()

	# Remove first child - with the new reconciliation algorithm, this generates reconciliation operations
	ops = tree.rerender(div(span("B")))
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1

	# Add child at end
	ops = tree.rerender(div(span("B"), span("C")))
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	new_indices, new_values = recon_ops[0]["new"]
	assert new_indices == [1]
	assert isinstance(new_values[0], dict) and new_values[0].get("tag") == "span"

	# Add child at beginning - with the new reconciliation algorithm, this generates reconciliation operations
	ops = tree.rerender(div(span("A"), span("B"), span("C")))
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	new_indices, _ = recon_ops[0]["new"]
	assert 2 in new_indices


def test_unkeyed_multiple_removes_descending_order():
	"""Test that multiple removes are emitted in descending order."""
	tree = RenderTree(div(span("A"), span("B"), span("C"), span("D"), span("E")))
	tree.render()

	# Remove last two items -> expect a reconciliation op reflecting final length
	ops = tree.rerender(div(span("A"), span("B"), span("C")))
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom = ["A", "B", "C", "D", "E"]
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["A", "B", "C"]


def test_keyed_remove_then_readd_resets_state():
	"""Test that removing and re-adding a component with the same key resets its state."""

	class Counter(ps.State):
		count: int = 0

		def inc(self):
			self.count += 1

	@component
	def CounterComponent(label: str, key: str | None = None) -> Element:
		with ps.init():
			counter = Counter()

		def handle_click():
			counter.inc()

		return div(span(f"{label}:{counter.count}"), button(onClick=handle_click)["+"])

	# Initial render
	first = CounterComponent("A", key="a")
	second = CounterComponent("B", key="b")

	tree = RenderTree(div(first, second))
	tree.render()

	# Increment first counter
	tree.callbacks["0.1.onClick"].fn()
	ops = tree.rerender(div(first, second))
	# With the new reconciliation algorithm, this generates a reconciliation operation
	recon_ops = _get_reconciliation_ops(ops, path="0.0")
	assert len(recon_ops) == 1

	# Remove first component -> expect callback removal delta and a reconciliation op
	ops = tree.rerender(div(second))
	assert len(ops) >= 1
	assert set(tree.callbacks.keys()) == {"0.1.onClick"}
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom = ["a", "b"]
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["b"]

	# Re-add first component - should reset state
	new_first = CounterComponent("A", key="a")
	ops = tree.rerender(div(second, new_first))
	assert len(ops) >= 1
	assert set(tree.callbacks.keys()) == {"0.1.onClick", "1.1.onClick"}
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	new_indices, _ = recon_ops[0]["new"]
	assert 1 in new_indices


def test_keyed_complex_reorder():
	"""Test complex keyed reordering with multiple components."""

	class Counter(ps.State):
		count: int = 0
		label: str = ""

		def __init__(self, label: str):
			self.label = label

		def inc(self):
			self.count += 1

	@component
	def CounterComponent(label: str, key: str | None = None) -> Element:
		with ps.init():
			counter = Counter(label)

		def handle_click():
			counter.inc()

		return div(
			span(f"{counter.label}:{counter.count}"), button(onClick=handle_click)["+"]
		)

	# Initial render: A, B, C, D
	components = [
		CounterComponent("A", key="a"),
		CounterComponent("B", key="b"),
		CounterComponent("C", key="c"),
		CounterComponent("D", key="d"),
	]

	tree = RenderTree(div(*components))
	tree.render()

	# Increment B and D
	tree.callbacks["1.1.onClick"].fn()  # B -> 1
	tree.callbacks["3.1.onClick"].fn()  # D -> 1
	ops = tree.rerender(div(*components))
	# With the new reconciliation algorithm, this generates reconciliation operations
	recon_ops = _get_reconciliation_ops(ops, path="1.0")
	assert len(recon_ops) == 1
	recon_ops = _get_reconciliation_ops(ops, path="3.0")
	assert len(recon_ops) == 1

	# Complex reorder: D, B, E, A (remove C, add E, reorder others)
	new_components = [
		CounterComponent("D", key="d"),
		CounterComponent("B", key="b"),
		CounterComponent("E", key="e"),  # New component
		CounterComponent("A", key="a"),
	]

	ops = tree.rerender(div(*new_components))
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom = ["a", "b", "c", "d"]
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["d", "b", "e", "a"]


def test_render_props():
	"""Test render props functionality."""

	@component
	def ChildComponent() -> Element:
		return span("child")

	# Create a div with render prop
	tree = RenderTree(div(render=ChildComponent()))  # pyright: ignore[reportCallIssue, reportUnknownArgumentType]
	vdom = cast(VDOMElement, tree.render())
	props = cast(dict[str, Any], vdom.get("props", {}))
	render_elem = cast(VDOMElement, props.get("render"))
	assert render_elem["tag"] == "span"
	assert vdom.get("eval") == ["render"]

	# Change render prop
	@component
	def NewChildComponent() -> Element:
		return span("new child")

	ops = tree.rerender(div(render=NewChildComponent()))  # pyright: ignore[reportCallIssue, reportUnknownArgumentType]
	assert any(
		op["type"] == "replace"
		and op["path"] == "render"
		and cast(dict[str, Any], cast(object, op.get("data", {}))).get("tag") == "span"
		for op in ops
	)


def test_css_module_with_jsexpr(tmp_path: Path):
	"""Test CSS module Import/Member integrates with renderer expressions."""
	from pulse.transpiler.imports import Import, clear_import_registry
	from pulse.transpiler.nodes import Member

	clear_import_registry()

	# Create a temporary CSS file for testing
	test_css_file = tmp_path / "test.module.css"
	test_css_file.write_text(".test { color: red; }")

	css_module = Import(str(test_css_file))
	css_ref = Member(css_module, "test")

	tree = RenderTree(div(className=css_ref))
	vdom = cast(VDOMElement, tree.render())

	assert vdom.get("eval") == ["className"]
	props = cast(dict[str, Any], vdom.get("props", {}))
	class_value = cast(dict[str, Any], props.get("className"))
	assert class_value["t"] == "member"
	assert class_value["prop"] == "test"
	clear_import_registry()


def test_expr_tag_renders_as_expr():
	"""Tag expressions should be serialized as VDOMExpr for client evaluation."""
	from pulse.transpiler.imports import Import, clear_import_registry
	from pulse.transpiler.nodes import Member

	clear_import_registry()
	app_shell = Import("AppShell", "@mantine/core")
	header = Member(app_shell, "Header")

	tree = RenderTree(Element(tag=header))
	vdom = cast(VDOMElement, tree.render())

	tag = cast(VDOMExpr, vdom.get("tag"))
	assert tag["t"] == "member"
	assert tag["prop"] == "Header"
	obj = cast(VDOMExpr, tag["obj"])
	assert obj["t"] == "ref"
	clear_import_registry()


# -----------------------------------------------------------------------------
# Additional keyed reconciliation scenarios to exhaust code paths
# -----------------------------------------------------------------------------


def test_keyed_inserts_from_empty():
	tree = RenderTree(ul())
	tree.render()

	ops = tree.rerender(ul(li("A", key="a"), li("B", key="b")))

	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom: list[str] = []
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["a", "b"]


def test_keyed_head_insert_single_insert():
	tree = RenderTree(ul(li("A", key="a"), li("B", key="b")))
	tree.render()

	ops = tree.rerender(ul(li("X", key="x"), li("A", key="a"), li("B", key="b")))

	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom = ["a", "b"]
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["x", "a", "b"]


def test_keyed_tail_insert_single_insert():
	tree = RenderTree(ul(li("X", key="x"), li("A", key="a"), li("B", key="b")))
	tree.render()

	ops = tree.rerender(
		ul(li("X", key="x"), li("A", key="a"), li("B", key="b"), li("C", key="c"))
	)

	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom = ["x", "a", "b"]
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["x", "a", "b", "c"]


def test_keyed_middle_early_deletes_remove_nonpresent():
	tree = RenderTree(
		ul(li("X", key="x"), li("A", key="a"), li("B", key="b"), li("C", key="c"))
	)
	tree.render()

	ops = tree.rerender(ul(li("A", key="a"), li("B", key="b")))

	# Expect reconciliation leading to the final list
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom = ["x", "a", "b", "c"]
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["a", "b"]


def test_keyed_insert_and_move_mix():
	# Old: A, C, D, B  -> New: B, A, E, D
	tree = RenderTree(
		ul(li("A", key="a"), li("C", key="c"), li("D", key="d"), li("B", key="b"))
	)
	tree.render()

	ops = tree.rerender(
		ul(li("B", key="b"), li("A", key="a"), li("E", key="e"), li("D", key="d"))
	)

	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom = ["a", "c", "d", "b"]
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["b", "a", "e", "d"]


def test_keyed_only_removals_when_new_window_exhausted():
	# Old: A, B, C, D  -> New: A, D (head/tail match leaves only removals in middle)
	tree = RenderTree(
		ul(li("A", key="a"), li("B", key="b"), li("C", key="c"), li("D", key="d"))
	)
	tree.render()

	ops = tree.rerender(ul(li("A", key="a"), li("D", key="d")))

	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom = ["a", "b", "c", "d"]
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["a", "d"]


def test_keyed_head_only_removal():
	# Old: X, A  -> New: A (tail sync + new exhausted -> remove head)
	tree = RenderTree(ul(li("X", key="x"), li("A", key="a")))
	tree.render()

	ops = tree.rerender(ul(li("A", key="a")))

	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	dom = ["x", "a"]
	final_dom = _apply_reconciliation(dom, recon_ops[0])
	assert final_dom == ["a"]


def test_keyed_same_key_different_tag_triggers_replace():
	tree = RenderTree(div(li("A", key="a")))
	tree.render()

	ops = tree.rerender(div(span("A", key="a")))

	# With the new reconciliation algorithm, this generates a reconciliation operation
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1


def test_keyed_head_tail_placeholders_deep_reconcile_props_change():
	# Old: A(class=one), C, B  -> New: A(class=two), X, B
	tree = RenderTree(
		ul(li("A", key="a", className="one"), li("C", key="c"), li("B", key="b"))
	)
	tree.render()

	ops = tree.rerender(
		ul(li("A", key="a", className="two"), li("X", key="x"), li("B", key="b"))
	)

	# Expect: reconciliation with a new at idx=1, and update_props for A at path 0
	recon_ops = _get_reconciliation_ops(ops, path="")
	assert len(recon_ops) == 1
	new_indices, _new_values = recon_ops[0]["new"]
	assert 1 in new_indices
	assert any(
		op["type"] == "update_props"
		and op["path"] == "0"
		and op["data"].get("set", {}).get("className") == "two"
		for op in ops
	)


def test_ref_prop_serializes_with_eval():
	handle: RefHandle[Any] | None = None

	@component
	def WithRef() -> ps.Element:
		nonlocal handle
		handle = ps.ref()
		return div(ref=handle)

	app = ps.App()
	render = ps.RenderSession("render-ref", app.routes)
	session: Any = SimpleNamespace(sid="session-ref")
	with ps.PulseContext(app=app, session=session, render=render):
		tree = RenderTree(WithRef())
		vdom = tree.render()
	assert handle is not None
	assert isinstance(vdom, dict)
	props = vdom.get("props", {})
	ref_spec = props.get("ref")
	assert isinstance(ref_spec, dict)
	assert ref_spec.get("__pulse_ref__") == {
		"channelId": handle.channel_id,
		"refId": handle.id,
	}
	assert "ref" in vdom.get("eval", [])


def test_ref_handles_share_session_channel():
	handle_a: RefHandle[Any] | None = None
	handle_b: RefHandle[Any] | None = None

	@component
	def WithRefA() -> ps.Element:
		nonlocal handle_a
		handle_a = ps.ref()
		return div(ref=handle_a)

	@component
	def WithRefB() -> ps.Element:
		nonlocal handle_b
		handle_b = ps.ref()
		return span(ref=handle_b)

	app = ps.App()
	render = ps.RenderSession("render-ref-shared-channel", app.routes)
	session: Any = SimpleNamespace(sid="session-ref-shared-channel")
	with ps.PulseContext(app=app, session=session, render=render):
		tree = RenderTree(div(WithRefA(), WithRefB()))
		tree.render()

	assert handle_a is not None
	assert handle_b is not None
	assert handle_a.channel_id == handle_b.channel_id


def test_ref_hook_handlers_register():
	events: list[str] = []
	handle: RefHandle[Any] | None = None

	def on_mount() -> None:
		events.append("mount")

	def on_unmount() -> None:
		events.append("unmount")

	@component
	def WithRef() -> ps.Element:
		nonlocal handle
		handle = ps.ref(on_mount=on_mount, on_unmount=on_unmount)
		return div(ref=handle)

	app = ps.App()
	render = ps.RenderSession("render-ref-handlers", app.routes)
	session: Any = SimpleNamespace(sid="session-ref-handlers")
	with ps.PulseContext(app=app, session=session, render=render):
		tree = RenderTree(WithRef())
		tree.render()
	assert handle is not None
	handle._on_mounted({"refId": handle.id})
	handle._on_unmounted({"refId": handle.id})
	assert events == ["mount", "unmount"]


def test_ref_prop_rejects_non_ref_key():
	@component
	def BadRef() -> ps.Element:
		handle = ps.ref()
		return div(dataRef=handle)  # pyright: ignore[reportCallIssue]

	app = ps.App()
	render = ps.RenderSession("render-ref-2", app.routes)
	session: Any = SimpleNamespace(sid="session-ref-2")
	with ps.PulseContext(app=app, session=session, render=render):
		tree = RenderTree(BadRef())
		with pytest.raises(
			TypeError, match="RefHandle can only be used as the 'ref' prop"
		):
			tree.render()
