import json
from pulse.reactive import flush_effects
from pulse.reconciler import Resolver
from pulse.reconciler import RenderNode, RenderRoot
from pulse.reconciler import lis
import pulse as ps

from pulse.vdom import Callback


# =================
# Callbacks capture
# =================
def test_capture_callbacks_no_callbacks_returns_original_and_no_side_effects():
    r = Resolver()
    props = {"id": "x", "count": 1}

    result = r._capture_callbacks(props, path="")

    # Should return the same dict object when no callables present
    assert result is props
    assert r.callbacks == {}


def test_capture_callbacks_single_with_and_without_path():
    r = Resolver()

    def cb():
        return 1

    # No path: key should be just the prop name
    props1 = {"onClick": cb, "id": "a"}
    out1 = r._capture_callbacks(props1, path="")
    assert out1 is not props1
    assert out1["onClick"] == "$$fn:onClick"
    assert r.callbacks["onClick"].fn is cb
    assert out1["id"] == "a"

    # With path: prefix and dot should be added
    r2 = Resolver()
    props2 = {"onClick": cb}
    out2 = r2._capture_callbacks(props2, path="1.child")
    assert out2["onClick"] == "$$fn:1.child.onClick"
    assert r2.callbacks["1.child.onClick"].fn is cb


def test_capture_callbacks_multiple_callbacks_preserved_and_mapped():
    r = Resolver()

    def a():
        return 1

    def b():
        return 2

    props = {"onClick": a, "onHover": b, "label": "L"}
    out = r._capture_callbacks(props, path="root")

    assert out is not props
    assert out["onClick"] == "$$fn:root.onClick"
    assert out["onHover"] == "$$fn:root.onHover"
    assert out["label"] == "L"

    assert r.callbacks == {
        "root.onClick": Callback(a, 0),
        "root.onHover": Callback(b, 0),
    }


# =====================
# Rendering new subtree
# =====================
def test_render_tree_simple_component_and_callbacks():
    @ps.component
    def Simple():
        def on_click():
            return "ok"

        return ps.button(onClick=on_click)["Go"]

    resolver = Resolver()
    root = RenderNode(Simple.fn)
    vdom, _ = resolver.render_tree(root, Simple(), path="")

    assert vdom == {
        "tag": "button",
        "props": {"onClick": "$$fn:onClick"},
        "children": ["Go"],
    }
    assert "" in root.children  # top-level component tracked
    assert callable(resolver.callbacks["onClick"].fn)  # captured


def test_render_tree_nested_components_depth_3_callbacks_and_paths():
    @ps.component
    def Leaf():
        def cb():
            return 1

        return ps.button(onClick=cb)["X"]

    @ps.component
    def Middle():
        return ps.div(className="mid")[Leaf()]

    @ps.component
    def Top():
        return ps.div(id="top")[Middle()]

    resolver = Resolver()
    root = RenderNode(lambda: None)

    vdom, _ = resolver.render_tree(root, Top(), path="")

    assert vdom == {
        "tag": "div",
        "props": {"id": "top"},
        "children": [
            {
                "tag": "div",
                "props": {"className": "mid"},
                "children": [
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.0.onClick"},
                        "children": ["X"],
                    }
                ],
            }
        ],
    }

    # Ensure nested component render nodes were tracked at each depth
    assert "" in root.children  # Top
    top_node = root.children[""]
    assert "0" in top_node.children  # Middle at child index 0
    mid_node = top_node.children["0"]
    assert "0.0" in mid_node.children  # Leaf at child index 0 within Middle

    # Callback captured with fully qualified path
    assert "0.0.onClick" in resolver.callbacks


# TODOs:
# - Verify diffs are correct (first step)
# - Verify components are mounted/unmounted
# - Verify keyed components are


def test_render_tree_component_with_children_kwarg_and_nested_component():
    @ps.component
    def Child():
        def click():
            return "ok"

        return ps.button(onClick=click)["X"]

    @ps.component
    def Wrapper(children=None, id: str = "wrap"):
        children = children or []
        return ps.div(id=id)[*children]

    @ps.component
    def Top():
        return Wrapper(id="w")[Child()]

    resolver = Resolver()
    root = RenderNode(Top.fn)
    vdom, _ = resolver.render_tree(root, Top(), path="")

    assert vdom == {
        "tag": "div",
        "props": {"id": "w"},
        "children": [
            {"tag": "button", "props": {"onClick": "$$fn:0.onClick"}, "children": ["X"]}
        ],
    }
    assert "0.onClick" in resolver.callbacks


# =====================
# Reconciliation (unkeyed)
# =====================


def test_reconcile_initial_insert_simple_component():
    @ps.component
    def Simple():
        def on_click():
            return "ok"

        return ps.button(onClick=on_click)["Go"]

    root = RenderRoot(Simple)
    result = root.render()

    assert result.ops == [
        {
            "type": "insert",
            "path": "",
            "data": {
                "tag": "button",
                "props": {"onClick": "$$fn:onClick"},
                "children": ["Go"],
            },
        }
    ]
    assert "onClick" in result.callbacks


def test_reconcile_props_update_between_renders():
    attrs = {"className": "a"}

    @ps.component
    def View():
        res = ps.div(className=attrs["className"])["x"]
        return res

    # First render -> insert
    r1 = RenderRoot(View)
    first = r1.render()
    assert first.ops and first.ops[0]["type"] == "insert"

    # mutate props
    attrs["className"] = "b"

    # Second render using previous VDOM -> update_props
    second = r1.render()
    assert second.ops == [
        {"type": "update_props", "path": "", "data": {"className": "b"}}
    ]


def test_reconcile_primitive_changes_and_none():
    val: dict[str, str | None] = {"text": "A"}

    @ps.component
    def P():
        return val["text"]

    # Initial insert of primitive
    root = RenderRoot(P)
    first = root.render()
    assert first.ops == [{"type": "insert", "path": "", "data": "A"}]

    # Change primitive -> replace
    val["text"] = "B"
    second = root.render()
    assert second.ops == [{"type": "replace", "path": "", "data": "B"}]

    # Change to None -> remove
    val["text"] = None
    third = root.render()
    assert third.ops == [{"type": "remove", "path": ""}]


def test_reconcile_conditional_children_insert_remove():
    show_extra = {"flag": False}

    @ps.component
    def View():
        children = [ps.span("A")]
        if show_extra["flag"]:
            children.append(ps.span("B"))
        return ps.div(*children)

    # First render (no extra) -> insert
    root = RenderRoot(View)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"

    # Add extra child -> insert at path 1
    show_extra["flag"] = True
    second = root.render()
    assert second.ops == [
        {"type": "insert", "path": "1", "data": {"tag": "span", "children": ["B"]}}
    ]

    # Remove extra child -> remove at path 1
    show_extra["flag"] = False
    third = root.render()
    assert third.ops == [{"type": "remove", "path": "1"}]


def test_reconcile_deep_nested_text_replace():
    content = {"b": "B"}

    @ps.component
    def View():
        # div()[ div()[ span("A"), span(content['b']) ] ]
        return ps.div(
            ps.div(
                ps.span("A"),
                ps.span(content["b"]),
            )
        )

    root = RenderRoot(View)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"

    content["b"] = "BB"
    second = root.render()
    print("second.ops = ", second.ops)
    assert second.ops == [{"type": "replace", "path": "0.1.0", "data": "BB"}]


def test_component_unmount_on_remove_runs_cleanup():
    logs: list[str] = []
    state = {"on": True}

    @ps.component
    def Child():
        def eff():
            def cleanup():
                logs.append("child_cleanup")

            return cleanup

        ps.effects(eff)
        return ps.div("child")

    @ps.component
    def Parent():
        return ps.div(Child()) if state["on"] else ps.div()

    root = RenderRoot(Parent)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"

    # Simulate an effect execution after first render
    flush_effects()

    state["on"] = False
    second = root.render()
    print("Finished rendering")
    assert second.ops == [{"type": "remove", "path": "0"}]
    assert logs == ["child_cleanup"]


def test_component_unmount_on_replace_runs_cleanup_and_replaces_subtree():
    logs: list[str] = []
    which = {"a": True}

    @ps.component
    def A():
        def eff():
            def cleanup():
                logs.append("A_cleanup")

            return cleanup

        ps.effects(eff)
        return ps.span("Achild")

    @ps.component
    def B():
        def eff():
            def cleanup():
                logs.append("B_cleanup")

            return cleanup

        ps.effects(eff)
        return ps.span("Bchild")

    @ps.component
    def Parent():
        child = A() if which["a"] else B()
        return ps.div(child)

    root = RenderRoot(Parent)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"

    # Simulate an effect execution after first render
    flush_effects()

    which["a"] = False
    second = root.render()
    assert second.ops == [
        {
            "type": "replace",
            "path": "0",
            "data": {"tag": "span", "children": ["Bchild"]},
        }
    ]
    # Only A should have been cleaned up
    assert logs.count("A_cleanup") == 1
    assert logs.count("B_cleanup") == 0


def test_state_persistence_nested_siblings_and_isolation():
    class Counter(ps.State):
        count: int = 0

        def inc(self):
            self.count += 1

    @ps.component
    def Nested(label: str):
        s = ps.states(Counter)

        def do_inc():
            s.inc()

        return ps.div(
            ps.span(f"{label}:{s.count}"),
            ps.button(onClick=do_inc)["incN"],
        )

    @ps.component
    def Sibling(name: str):
        s = ps.states(Counter)

        def do_inc():
            s.inc()

        return ps.div(
            ps.span(f"{name}:{s.count}"),  # 0
            ps.button(onClick=do_inc)["inc"],  # 1
            Nested(label=f"{name}-child"),  # 2
        )

    @ps.component
    def Top():
        return ps.div(
            Sibling(name="A"),  # path 0
            Sibling(name="B"),  # path 1
        )

    root = RenderRoot(Top)
    first = root.render()
    cbs = first.callbacks

    # Sanity: expected callbacks are present
    assert set(cbs.keys()) >= {
        "0.1.onClick",
        "0.2.1.onClick",
        "1.1.onClick",
        "1.2.1.onClick",
    }

    # Increment A's own counter
    cbs["0.1.onClick"].fn()  # simulate button click
    second = root.render()
    print("second.ops = ", second.ops)
    assert second.ops == [{"type": "replace", "path": "0.0.0", "data": "A:1"}]

    # Increment A's nested counter
    cbs = second.callbacks
    cbs["0.2.1.onClick"].fn()
    third = root.render()
    print("third.ops = ", second.ops)
    assert third.ops == [{"type": "replace", "path": "0.2.0.0", "data": "A-child:1"}]

    # Increment B's own counter; A should not change
    cbs = third.callbacks
    cbs["1.1.onClick"].fn()
    fourth = root.render()
    print("fourth.ops = ", second.ops)
    assert fourth.ops == [{"type": "replace", "path": "1.0.0", "data": "B:1"}]


def test_callback_identity_change_no_update_props_and_callbacks_swap():
    fn = {}

    def f1():
        return None

    def f2():
        return None

    fn["cur"] = f1

    @ps.component
    def View():
        return ps.button(onClick=fn["cur"])["X"]

    root = RenderRoot(View)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"
    assert first.callbacks["onClick"].fn is f1

    fn["cur"] = f2
    second = root.render()
    assert second.ops == []
    assert second.callbacks["onClick"].fn is f2


def test_component_arg_change_rerenders_leaf_not_remount():
    logs: list[str] = []
    name = {"msg": "A"}

    @ps.component
    def Child(msg: str):
        def eff():
            def cleanup():
                logs.append("cleanup")

            return cleanup

        ps.effects(eff)
        return ps.span(msg)

    @ps.component
    def Parent():
        return ps.div(Child(msg=name["msg"]))

    root = RenderRoot(Parent)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"

    name["msg"] = "B"
    second = root.render()
    assert second.ops == [{"type": "replace", "path": "0.0", "data": "B"}]
    assert logs == []


def test_props_removal_emits_empty_update_props():
    toggle = {"on": True}

    @ps.component
    def View():
        return ps.div(className="a") if toggle["on"] else ps.div()

    root = RenderRoot(View)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"

    toggle["on"] = False
    second = root.render()
    assert second.ops == [{"type": "update_props", "path": "", "data": {}}]


def test_keyed_component_move_preserves_state_and_no_cleanup():
    logs: list[str] = []
    order = {"keys": ["a", "b"]}

    class C(ps.State):
        n: int = 0

        def inc(self):
            self.n += 1

    @ps.component
    def Item(label: str):
        s = ps.states(C)

        def eff():
            def cleanup():
                logs.append(f"cleanup:{label}")

            return cleanup

        ps.effects(eff)
        return ps.div(
            ps.span(f"{label}:{s.n}"),
            ps.button(onClick=s.inc)["inc"],
        )

    @ps.component
    def List():
        return ps.div(*[Item(label=k, key=k) for k in order["keys"]])

    root = RenderRoot(List)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"
    print("Initial VDOM:", json.dumps(first.ops[0]["data"], indent=2))

    flush_effects()  # simulate effect pass after render

    # inc first item (key 'a')
    first.callbacks["0.1.onClick"].fn()
    second = root.render()
    print("Second.ops:", second.ops)
    assert second.ops == [{"type": "replace", "path": "0.0", "data": "a:1"}]

    flush_effects()  # simulate effect pass after render

    # reorder: move 'a' to the end
    order["keys"] = ["b", "a"]
    third = root.render()
    # Expect two moves (b->0, a->1) or at least one move including 'a'
    move_ops = [op for op in third.ops if op["type"] == "move"]
    assert any(
        op["data"]["key"] == "a" and op["data"]["to_index"] == 1 for op in move_ops
    )
    assert logs == []  # no cleanup on move

    flush_effects()  # simulate effect pass after render

    # inc 'a' at its new index 1, should go to 2
    third.callbacks["1.1.onClick"].fn()
    fourth = root.render()
    assert fourth.ops == [{"type": "replace", "path": "1.0", "data": "a:2"}]


def test_keyed_nested_components_move_preserves_nested_state():
    order = {"keys": ["x", "y"]}

    class C(ps.State):
        n: int = 0

        def inc(self):
            self.n += 1

    @ps.component
    def Leaf(tag: str):
        s = ps.states(C)
        return ps.div(ps.span(f"{tag}:{s.n}"), ps.button(onClick=s.inc)["+"])

    @ps.component
    def Wrapper(tag: str):
        return ps.div(Leaf(tag=tag))

    @ps.component
    def List():
        items = [Wrapper(tag=k) for k in order["keys"]]
        for i, k in enumerate(order["keys"]):
            items[i].key = k  # type: ignore[attr-defined]
        return ps.div(*items)

    root = RenderRoot(List)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"

    # bump x
    first.callbacks["0.0.1.onClick"].fn()  # path: wrapper0 -> leaf -> button
    second = root.render()
    assert second.ops == [{"type": "replace", "path": "0.0.0", "data": "x:1"}]

    # reorder: x to the end
    order["keys"] = ["y", "x"]
    third = root.render()
    assert any(op["type"] == "move" and op["data"]["key"] == "x" for op in third.ops)

    # bump x again at new path
    third.callbacks["1.0.1.onClick"].fn()
    fourth = root.render()
    assert fourth.ops == [{"type": "replace", "path": "1.0.0", "data": "x:2"}]


def test_unmount_parent_unmounts_children_components():
    logs: list[str] = []
    show = {"on": True}

    @ps.component
    def Child():
        def eff():
            def cleanup():
                logs.append("child_cleanup")

            return cleanup

        ps.effects(eff)
        return ps.div("child")

    @ps.component
    def Parent():
        def eff():
            def cleanup():
                logs.append("parent_cleanup")

            return cleanup

        ps.effects(eff)
        return Child()

    @ps.component
    def View():
        return Parent() if show["on"] else ps.div()

    root = RenderRoot(View)
    first = root.render()
    assert first.ops and first.ops[0]["type"] == "insert"
    # Simulate an effect pass after render
    flush_effects()

    show["on"] = False
    _ = root.render()
    # Confirm both parent and child are cleaned up
    assert "parent_cleanup" in logs and "child_cleanup" in logs


# =====================
# LIS helper
# =====================


def test_lis_empty_returns_empty_list():
    assert lis([]) == []


def test_lis_strictly_increasing_returns_all_indices():
    seq = [1, 2, 3, 4, 5]
    assert lis(seq) == [0, 1, 2, 3, 4]


def test_lis_strictly_decreasing_returns_last_index():
    seq = [5, 4, 3, 2, 1]
    out = lis(seq)
    assert out == [4]
    assert seq[out[0]] == 1


def test_lis_with_duplicates_picks_last_occurrence():
    seq = [3, 3, 3]
    assert lis(seq) == [2]


def test_lis_typical_case_matches_expected_indices():
    seq = [10, 9, 2, 5, 3, 7, 101, 18]
    # One valid LIS is indices [2, 4, 5, 7] -> values [2, 3, 7, 18]
    assert lis(seq) == [2, 4, 5, 7]


def test_lis_classic_sequence_length_and_increasing():
    seq = [
        0,
        8,
        4,
        12,
        2,
        10,
        6,
        14,
        1,
        9,
        5,
        13,
        3,
        11,
        7,
        15,
    ]
    idx = lis(seq)
    vals = [seq[i] for i in idx]
    assert len(vals) == 6  # Known LIS length for this sequence
    assert all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
