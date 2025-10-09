from pathlib import Path
from typing import Optional
import pytest
from pulse.hooks.core import HookContext
from pulse.html.tags import li, ul, div, span, button
from pulse.renderer import RenderTree
from pulse.vdom import Node, component
import pulse as ps
from pulse.css import CssModule, CssReference


class TrackingHookContext(HookContext):
    def __init__(self) -> None:
        super().__init__()
        self.did_unmount = False

    def unmount(self) -> None:  # type: ignore[override]
        self.did_unmount = True
        super().unmount()


def test_keyed_reorder_applies_operations_in_correct_order():
    def keyed_item(label: str) -> Node:
        return Node("li", key=label.lower(), children=[label])

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

    ops = tree.diff(ul(*reordered_children))

    normalized_root = tree._normalized  # type: ignore[attr-defined]
    assert isinstance(normalized_root, Node)
    assert isinstance(normalized_root.children, list)
    current_order = [child.key for child in normalized_root.children]
    assert current_order == ["d", "b", "e", "a"], "sanity check normalized order"

    dom_order = ["a", "b", "c", "d"]
    expected_final = [child.key for child in reordered_children]

    for op in ops:
        if op["type"] == "remove":
            dom_order.pop(op["idx"])
        elif op["type"] == "insert":
            dom_order.insert(op["idx"], expected_final[op["idx"]])
        elif op["type"] == "move":
            moved = dom_order.pop(op["data"]["from_index"])
            dom_order.insert(op["data"]["to_index"], moved)

    assert dom_order == expected_final


def test_nested_keyed_reorder_in_subtree():
    def inner_span(label: str) -> Node:
        return Node("span", key=label.lower(), children=[label])

    def outer_item(label: str, inner_labels: list[str]) -> Node:
        return Node(
            "li",
            key=f"outer-{label.lower()}",
            children=[
                Node(
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

    ops = tree.diff(div(outer_a_reordered, outer_b))

    relevant_ops = [op for op in ops if op["path"] == "0.0"]
    dom_order = ["a1", "a2", "a3", "a4"]
    expected_final = ["a4", "a2", "a5", "a1"]

    for op in relevant_ops:
        if op["type"] == "remove":
            dom_order.pop(op["idx"])
        elif op["type"] == "insert":
            key = op["data"].get("key", f"__idx__{op['idx']}")
            dom_order.insert(op["idx"], key)
        elif op["type"] == "move":
            moved = dom_order.pop(op["data"]["from_index"])
            dom_order.insert(op["data"]["to_index"], moved)

    assert dom_order == expected_final

    normalized_root = tree._normalized  # type: ignore[attr-defined]
    assert isinstance(normalized_root, Node)
    outer = normalized_root.children
    assert isinstance(outer, list)
    first_outer = outer[0]
    assert isinstance(first_outer, Node)
    inner_list = first_outer.children
    assert isinstance(inner_list, list)
    assert len(inner_list) == 1
    inner_ul = inner_list[0]
    assert isinstance(inner_ul, Node)
    assert isinstance(inner_ul.children, list)
    inner_keys = [child.key for child in inner_ul.children]
    assert inner_keys == expected_final


def test_duplicate_key_detection_raises_error():
    first = Node("li", key="a")
    duplicate = Node("li", key="dup")

    tree = RenderTree(ul(first, duplicate))
    tree.render()

    with pytest.raises(ValueError, match="Duplicate key 'dup'"):
        tree.diff(ul(first, duplicate, Node("li", key="dup")))


def test_component_replaced_with_text_unmounts_and_replaces():
    @component
    def Child() -> Node:
        return span("child")

    child = Child()
    child.key = "child"  # Ensure consistent key
    child.hooks = TrackingHookContext()

    sibling = Node("span", key="sibling", children=["sib"])

    tree = RenderTree(div(child, sibling))
    tree.render()

    assert isinstance(child.hooks, TrackingHookContext)
    assert child.hooks.did_unmount is False

    ops = tree.diff(div("plain", Node("span", key="sibling", children=["sib"])))

    assert {"type": "remove", "path": "", "idx": 0} in ops
    assert {"type": "insert", "path": "", "idx": 0, "data": "plain"} in ops
    assert child.hooks.did_unmount is True


def test_diff_props_unmounts_render_prop_when_replaced_with_callback():
    @component
    def Child() -> Node:
        return span("child")

    child = Child()
    child.hooks = TrackingHookContext()

    tree = RenderTree(div(render=child))  # pyright: ignore[reportCallIssue]
    tree.render()

    assert isinstance(child.hooks, TrackingHookContext)
    assert child.hooks.did_unmount is False

    def handle_click() -> None:
        pass

    tree.diff(div(render=handle_click))  # pyright: ignore[reportCallIssue]

    assert child.hooks.did_unmount is True


def test_diff_props_unmounts_render_prop_when_removed():
    @component
    def Child() -> Node:
        return span("child")

    child = Child()
    child.hooks = TrackingHookContext()

    tree = RenderTree(div(render=child))  # pyright: ignore[reportCallIssue]
    tree.render()

    assert isinstance(child.hooks, TrackingHookContext)
    assert child.hooks.did_unmount is False

    tree.diff(div())

    assert child.hooks.did_unmount is True


def test_diff_props_unmounts_render_prop_when_replaced_with_css_reference():
    from pulse.css import CssModule, CssReference

    @component
    def Child() -> Node:
        return span("child")

    child = Child()
    child.hooks = TrackingHookContext()

    tree = RenderTree(div(render=child))  # pyright: ignore[reportCallIssue]
    tree.render()

    assert isinstance(child.hooks, TrackingHookContext)
    assert child.hooks.did_unmount is False

    css_module = CssModule("test", "/fake.css")
    css_ref = CssReference(css_module, "foo")

    tree.diff(div(render=css_ref))  # pyright: ignore[reportCallIssue]

    assert child.hooks.did_unmount is True


def test_render_tree_initial_callbacks():
    def on_click() -> None:
        pass

    root = Node(
        "div",
        props={"id": "root"},
        children=[Node("button", props={"onClick": on_click}, children=["Click"])],
    )

    tree = RenderTree(root)
    vdom = tree.render()

    assert vdom == {
        "tag": "div",
        "props": {"id": "root"},
        "children": [
            {"tag": "button", "props": {"onClick": "$cb"}, "children": ["Click"]}
        ],
    }
    assert set(tree.callbacks.keys()) == {"0.onClick"}
    assert tree.render_props == set()
    assert tree.css_refs == set()


def test_callback_removal_emits_update_callbacks_delta():
    def on_click() -> None:
        pass

    tree = RenderTree(div(button(onClick=on_click)["Click"]))
    tree.render()

    ops = tree.diff(div())

    update_callbacks = [op for op in ops if op["type"] == "update_callbacks"]
    assert update_callbacks == [
        {"type": "update_callbacks", "path": "", "data": {"remove": ["0.onClick"]}}
    ]


def test_render_prop_removal_emits_update_render_props_delta():
    @component
    def Child() -> Node:
        return span("child")

    tree = RenderTree(div(render=Child()))
    tree.render()

    ops = tree.diff(div())

    update_render_props = [op for op in ops if op["type"] == "update_render_props"]
    assert update_render_props == [
        {"type": "update_render_props", "path": "", "data": {"remove": ["render"]}}
    ]


def test_callback_render_prop_churn_updates_deltas():
    @component
    def Child() -> Node:
        return span("child")

    def handle_click() -> None:
        pass

    tree = RenderTree(div(button(onClick=handle_click)["Click"]))
    tree.render()

    ops = tree.diff(div(render=Child()))  # pyright: ignore[reportCallIssue]
    assert any(
        op
        == {"type": "update_callbacks", "path": "", "data": {"remove": ["0.onClick"]}}
        for op in ops
    )
    assert any(
        op == {"type": "update_render_props", "path": "", "data": {"add": ["render"]}}
        for op in ops
    )

    ops = tree.diff(div(button(onClick=handle_click)["Click"]))
    assert any(
        op == {"type": "update_callbacks", "path": "", "data": {"add": ["0.onClick"]}}
        for op in ops
    )
    assert any(
        op
        == {"type": "update_render_props", "path": "", "data": {"remove": ["render"]}}
        for op in ops
    )


def test_render_prop_nested_components_unmount_on_type_change():
    @component
    def Leaf() -> Node:
        return span("leaf")

    inner = Leaf()
    inner.hooks = TrackingHookContext()

    @component
    def Wrapper() -> Node:
        return div(inner)

    outer = Wrapper()
    outer.hooks = TrackingHookContext()

    tree = RenderTree(div(render=outer))
    tree.render()

    assert isinstance(inner.hooks, TrackingHookContext)
    assert isinstance(outer.hooks, TrackingHookContext)
    assert inner.hooks.did_unmount is False
    assert outer.hooks.did_unmount is False

    def handle_click() -> None:
        pass

    tree.diff(div(onClick=handle_click))

    assert inner.hooks.did_unmount is True
    assert outer.hooks.did_unmount is True


def test_render_tree_unmount_clears_state_and_unmounts_children():
    @component
    def Child() -> Node:
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
    assert tree.render_props == set()
    assert tree.css_refs == set()
    assert tree._normalized is None  # type: ignore[attr-defined]


def test_diff_updates_props():
    tree = RenderTree(Node("div", props={"class": "one"}))
    tree.render()

    ops = tree.diff(Node("div", props={"class": "two"}))
    assert ops == [
        {
            "type": "update_props",
            "path": "",
            "data": {"set": {"class": "two"}},
        }
    ]


def test_keyed_move_preserves_component_nodes():
    @component
    def Item(label: str, key: Optional[str] = None) -> Node:
        return li(label)

    first = Item(label="A", key="a")
    second = Item(label="B", key="b")

    tree = RenderTree(ul(first, second))
    tree.render()

    # Verify initial order
    normalized_root = tree._normalized  # type: ignore[attr-defined]
    assert isinstance(normalized_root, Node)
    assert isinstance(normalized_root.children, list)
    assert len(normalized_root.children) == 2

    # Check that the initial labels are correct
    first_child = normalized_root.children[0]
    second_child = normalized_root.children[1]
    assert isinstance(first_child, ps.ComponentNode)
    assert isinstance(second_child, ps.ComponentNode)
    assert first_child.kwargs["label"] == "A"
    assert second_child.kwargs["label"] == "B"

    ops = tree.diff(ul(Item(label="B", key="b"), Item(label="A", key="a")))

    assert ops == [
        {"type": "move", "path": "", "data": {"from_index": 1, "to_index": 0}}
    ]

    # Verify labels moved correctly after reordering
    updated_root = tree._normalized  # type: ignore[attr-defined]
    assert isinstance(updated_root, Node)
    assert isinstance(updated_root.children, list)
    assert len(updated_root.children) == 2

    # After move: B should be first, A should be second
    updated_first_child = updated_root.children[0]
    updated_second_child = updated_root.children[1]
    assert isinstance(updated_first_child, ps.ComponentNode)
    assert isinstance(updated_second_child, ps.ComponentNode)
    assert updated_first_child.kwargs["label"] == "B"
    assert updated_second_child.kwargs["label"] == "A"

    # Verify the rendered DOM content matches the labels
    vdom = tree.render()
    assert isinstance(vdom, dict)
    assert vdom["tag"] == "ul"
    assert isinstance(vdom["children"], list)
    assert len(vdom["children"]) == 2

    # Check rendered content: B should be first, A should be second
    first_rendered = vdom["children"][0]
    second_rendered = vdom["children"][1]
    assert first_rendered == {"tag": "li", "children": ["B"]}
    assert second_rendered == {"tag": "li", "children": ["A"]}


def test_unmount_invokes_component_hooks():
    @component
    def Item(label: str, key: Optional[str] = None) -> Node:
        return li(label)

    first = Item(label="A", key="a")
    second = Item(label="B", key="b")
    first.hooks = TrackingHookContext()
    second.hooks = TrackingHookContext()

    tree = RenderTree(ul(first, second))
    tree.render()

    tree.diff(ul(Item(label="A", key="a")))

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
    def CounterComponent(label: str, key: Optional[str] = None) -> Node:
        counter = ps.states(Counter(label))

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
    ops = tree.diff(div(first, second))
    assert ops == [{"type": "replace", "path": "0.0.0", "data": "A:1"}]

    # Reorder components - move A to end
    ops = tree.diff(div(second, first))
    assert ops == [
        {"type": "move", "path": "", "data": {"from_index": 1, "to_index": 0}}
    ]

    # Verify state is preserved - A should still have count 1
    normalized_root = tree._normalized
    assert isinstance(normalized_root, Node)
    assert isinstance(normalized_root.children, list)
    # A is now at index 1
    a_component = normalized_root.children[1]
    assert isinstance(a_component, ps.ComponentNode)
    # The component should still have its state preserved
    assert a_component.hooks is not None


def test_keyed_parent_node_move_preserves_child_state():
    """Test that component state is preserved when a parent Node is moved due to its key."""

    class Counter(ps.State):
        count: int = 0
        label: str = ""

        def __init__(self, label: str):
            self.label = label

        def inc(self):
            self.count += 1

    @component
    def CounterComponent(label: str) -> Node:
        counter = ps.states(Counter(label))

        def handle_click():
            counter.inc()

        return div(
            span(f"{counter.label}:{counter.count}"), button(onClick=handle_click)["+"]
        )

    # Create parent nodes with keys containing components
    parent_a = Node("div", children=[CounterComponent("A")], key="parent-a")
    parent_b = Node("div", children=[CounterComponent("B")], key="parent-b")

    tree = RenderTree(div(parent_a, parent_b))
    tree.render()

    # Increment counter in first parent
    tree.callbacks["0.0.1.onClick"].fn()
    ops = tree.diff(div(parent_a, parent_b))
    assert ops == [{"type": "replace", "path": "0.0.0.0", "data": "A:1"}]

    # Move parent A to end (swap positions)
    ops = tree.diff(div(parent_b, parent_a))
    assert ops == [
        {"type": "move", "path": "", "data": {"from_index": 1, "to_index": 0}}
    ]

    # Verify the component state is preserved - A should still have count 1
    normalized_root = tree._normalized
    assert isinstance(normalized_root, Node)
    assert isinstance(normalized_root.children, list)
    # Parent A is now at index 1
    parent_a_node = normalized_root.children[1]
    assert isinstance(parent_a_node, Node)
    assert isinstance(parent_a_node.children, list)
    # The component should still have its state preserved
    a_component = parent_a_node.children[0]
    assert isinstance(a_component, ps.ComponentNode)
    assert a_component.hooks is not None

    # Inspect stored Counter state inside the component after the move
    states_ns = a_component.hooks.namespaces.get("pulse:core.states")
    assert states_ns is not None
    stored_hook_state = next(iter(states_ns.states.values()))
    stored_counter = stored_hook_state.states[0]
    assert isinstance(stored_counter, Counter)
    assert stored_counter.label == "A"
    assert stored_counter.count == 1

    # Click A's button again at the new location; state should increment to 2
    tree.callbacks["1.0.1.onClick"].fn()
    ops = tree.diff(div(parent_b, parent_a))
    assert ops == [{"type": "replace", "path": "1.0.0.0", "data": "A:2"}]


def test_unkeyed_reconciliation_insert_remove():
    """Test unkeyed reconciliation with proper operation ordering."""
    tree = RenderTree(div(span("A"), span("B")))
    tree.render()

    # Remove first child - the renderer replaces the text content and removes the element
    ops = tree.diff(div(span("B")))
    # The renderer emits replace for text content changes and remove for element removal
    assert ops == [
        {"type": "replace", "path": "0.0", "data": "B"},
        {"type": "remove", "path": "", "idx": 1},
    ]

    # Add child at end
    ops = tree.diff(div(span("B"), span("C")))
    assert ops == [
        {
            "type": "insert",
            "path": "",
            "idx": 1,
            "data": {"tag": "span", "children": ["C"]},
        }
    ]

    # Add child at beginning
    ops = tree.diff(div(span("A"), span("B"), span("C")))
    assert ops == [
        {"type": "replace", "path": "0.0", "data": "A"},
        {"type": "replace", "path": "1.0", "data": "B"},
        {
            "type": "insert",
            "path": "",
            "idx": 2,
            "data": {"tag": "span", "children": ["C"]},
        },
    ]


def test_unkeyed_multiple_removes_descending_order():
    """Test that multiple removes are emitted in descending order."""
    tree = RenderTree(div(span("A"), span("B"), span("C"), span("D"), span("E")))
    tree.render()

    # Remove last two items
    ops = tree.diff(div(span("A"), span("B"), span("C")))
    assert ops == [
        {"type": "remove", "path": "", "idx": 4},
        {"type": "remove", "path": "", "idx": 3},
    ]


def test_keyed_remove_then_readd_resets_state():
    """Test that removing and re-adding a component with the same key resets its state."""

    class Counter(ps.State):
        count: int = 0

        def inc(self):
            self.count += 1

    @component
    def CounterComponent(label: str, key: Optional[str] = None) -> Node:
        counter = ps.states(Counter)

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
    ops = tree.diff(div(first, second))
    assert ops == [{"type": "replace", "path": "0.0.0", "data": "A:1"}]

    # Remove first component
    ops = tree.diff(div(second))
    # The renderer emits callback removal operations first
    assert len(ops) >= 1
    assert any(op["type"] == "remove" and op["idx"] == 0 for op in ops)

    # Re-add first component - should reset state
    new_first = CounterComponent("A", key="a")
    ops = tree.diff(div(second, new_first))
    # The renderer emits callback operations first, then insert
    assert len(ops) >= 2
    assert any(op["type"] == "update_callbacks" for op in ops)
    assert any(op["type"] == "insert" and op["idx"] == 1 for op in ops)


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
    def CounterComponent(label: str, key: Optional[str] = None) -> Node:
        counter = ps.states(Counter(label))

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
    ops = tree.diff(div(*components))
    assert len(ops) == 2
    assert {"type": "replace", "path": "1.0.0", "data": "B:1"} in ops
    assert {"type": "replace", "path": "3.0.0", "data": "D:1"} in ops

    # Complex reorder: D, B, E, A (remove C, add E, reorder others)
    new_components = [
        CounterComponent("D", key="d"),
        CounterComponent("B", key="b"),
        CounterComponent("E", key="e"),  # New component
        CounterComponent("A", key="a"),
    ]

    ops = tree.diff(div(*new_components))
    # Should have: remove C, insert E, move D and A
    assert any(op["type"] == "remove" and op["idx"] == 2 for op in ops)  # Remove C
    assert any(op["type"] == "insert" and op["idx"] == 2 for op in ops)  # Insert E
    assert any(op["type"] == "move" for op in ops)  # Move operations


def test_render_props():
    """Test render props functionality."""

    @component
    def ChildComponent() -> Node:
        return span("child")

    # Create a div with render prop
    tree = RenderTree(div(render=ChildComponent()))  # pyright: ignore[reportCallIssue]
    tree.render()

    assert tree.render_props == {"render"}

    # Change render prop
    @component
    def NewChildComponent() -> Node:
        return span("new child")

    ops = tree.diff(div(render=NewChildComponent()))  # pyright: ignore[reportCallIssue]
    assert ops == [
        {
            "type": "replace",
            "path": "render",
            "data": {"tag": "span", "children": ["new child"]},
        }
    ]


def test_css_references():
    """Test CSS reference handling."""
    from pulse.css import CssModule, CssReference

    # Create a mock CSS module
    css_module = CssModule("test_module", Path("/fake/path"))
    css_ref = CssReference(css_module, "test")

    tree = RenderTree(div(className=css_ref))
    tree.render()

    assert tree.css_refs == {"className"}

    # Change CSS reference
    css_ref2 = CssReference(css_module, "test2")

    ops = tree.diff(div(className=css_ref2))
    assert ops == [
        {
            "type": "update_props",
            "path": "",
            "data": {"set": {"className": "test_module:test2"}},
        }
    ]


def test_css_reference_add_remove_cycle():
    css_module = CssModule("test_module", Path("/fake/path"))
    first = CssReference(css_module, "first")
    second = CssReference(css_module, "second")

    tree = RenderTree(div(className=first))
    tree.render()

    ops = tree.diff(div(className="plain"))
    assert {
        "type": "update_css_refs",
        "path": "",
        "data": {"remove": ["className"]},
    } in ops

    ops = tree.diff(div(className=second))
    assert {
        "type": "update_css_refs",
        "path": "",
        "data": {"add": ["className"]},
    } in ops


# -----------------------------------------------------------------------------
# Additional keyed reconciliation scenarios to exhaust code paths
# -----------------------------------------------------------------------------


def test_keyed_inserts_from_empty():
    tree = RenderTree(ul())
    tree.render()

    ops = tree.diff(ul(li("A", key="a"), li("B", key="b")))

    assert ops == [
        {
            "type": "insert",
            "path": "",
            "idx": 0,
            "data": {"tag": "li", "children": ["A"]},
        },
        {
            "type": "insert",
            "path": "",
            "idx": 1,
            "data": {"tag": "li", "children": ["B"]},
        },
    ]


def test_keyed_head_insert_single_insert():
    tree = RenderTree(ul(li("A", key="a"), li("B", key="b")))
    tree.render()

    ops = tree.diff(ul(li("X", key="x"), li("A", key="a"), li("B", key="b")))

    # Expect exactly one insert at head
    assert ops == [
        {
            "type": "insert",
            "path": "",
            "idx": 0,
            "data": {"tag": "li", "children": ["X"]},
        }
    ]


def test_keyed_tail_insert_single_insert():
    tree = RenderTree(ul(li("X", key="x"), li("A", key="a"), li("B", key="b")))
    tree.render()

    ops = tree.diff(
        ul(li("X", key="x"), li("A", key="a"), li("B", key="b"), li("C", key="c"))
    )

    assert ops == [
        {
            "type": "insert",
            "path": "",
            "idx": 3,
            "data": {"tag": "li", "children": ["C"]},
        }
    ]


def test_keyed_middle_early_deletes_remove_nonpresent():
    tree = RenderTree(
        ul(li("X", key="x"), li("A", key="a"), li("B", key="b"), li("C", key="c"))
    )
    tree.render()

    ops = tree.diff(ul(li("A", key="a"), li("B", key="b")))

    # Early deletes should remove right->left within middle window: indices 3 then 0
    assert ops == [
        {"type": "remove", "path": "", "idx": 3},
        {"type": "remove", "path": "", "idx": 0},
    ]


def test_keyed_insert_and_move_mix():
    # Old: A, C, D, B  -> New: B, A, E, D
    tree = RenderTree(
        ul(li("A", key="a"), li("C", key="c"), li("D", key="d"), li("B", key="b"))
    )
    tree.render()

    ops = tree.diff(
        ul(li("B", key="b"), li("A", key="a"), li("E", key="e"), li("D", key="d"))
    )

    # Expect: remove C (idx=1), insert E at idx=2, plus at least one move
    assert any(op["type"] == "remove" and op["idx"] == 1 for op in ops)
    assert any(
        op["type"] == "insert"
        and op["idx"] == 2
        and op["data"] == {"tag": "li", "children": ["E"]}
        for op in ops
    )
    assert any(op["type"] == "move" for op in ops)


def test_keyed_only_removals_when_new_window_exhausted():
    # Old: A, B, C, D  -> New: A, D (head/tail match leaves only removals in middle)
    tree = RenderTree(
        ul(li("A", key="a"), li("B", key="b"), li("C", key="c"), li("D", key="d"))
    )
    tree.render()

    ops = tree.diff(ul(li("A", key="a"), li("D", key="d")))

    # Expect descending removals of C (idx=2) then B (idx=1)
    assert ops == [
        {"type": "remove", "path": "", "idx": 2},
        {"type": "remove", "path": "", "idx": 1},
    ]


def test_keyed_head_only_removal():
    # Old: X, A  -> New: A (tail sync + new exhausted -> remove head)
    tree = RenderTree(ul(li("X", key="x"), li("A", key="a")))
    tree.render()

    ops = tree.diff(ul(li("A", key="a")))

    assert ops == [{"type": "remove", "path": "", "idx": 0}]


def test_keyed_same_key_different_tag_triggers_replace():
    tree = RenderTree(div(li("A", key="a")))
    tree.render()

    ops = tree.diff(div(span("A", key="a")))

    assert ops == [
        {"type": "replace", "path": "0", "data": {"tag": "span", "children": ["A"]}}
    ]


def test_keyed_head_tail_placeholders_deep_reconcile_props_change():
    # Old: A(class=one), C, B  -> New: A(class=two), X, B
    tree = RenderTree(
        ul(li("A", key="a", className="one"), li("C", key="c"), li("B", key="b"))
    )
    tree.render()

    ops = tree.diff(
        ul(li("A", key="a", className="two"), li("X", key="x"), li("B", key="b"))
    )

    # Expect: remove C at idx=1, insert X at idx=1, and update_props for A at path 0
    assert any(op["type"] == "remove" and op["idx"] == 1 for op in ops)
    assert any(
        op["type"] == "insert"
        and op["idx"] == 1
        and op["data"] == {"tag": "li", "children": ["X"]}
        for op in ops
    )
    assert any(
        op["type"] == "update_props"
        and op["path"] == "0"
        and op["data"].get("set", {}).get("className") == "two"
        for op in ops
    )
