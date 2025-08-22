import json
from pulse.reactive import flush_effects
from pulse.reconciler import Resolver
from pulse.reconciler import RenderNode, RenderRoot
from pulse.reconciler import lis
import pulse as ps

from pulse.vdom import Callback
import pytest


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
        def on_click(): ...

        return ps.button(onClick=on_click)["Go"]

    resolver = Resolver()
    root = RenderNode(Simple.fn)
    vdom, _ = resolver.render_tree(root, Simple(), path="", relative_path="")

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
        def cb(): ...

        return ps.button(onClick=cb)["X"]

    @ps.component
    def Middle():
        return ps.div(className="mid")[Leaf()]

    @ps.component
    def Top():
        return ps.div(id="top")[Middle()]

    resolver = Resolver()
    root = RenderNode(lambda: None)

    vdom, _ = resolver.render_tree(root, Top(), path="", relative_path="")

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
    # RenderNode children are stored by path relative to the component itself
    assert "0" in mid_node.children  # Leaf at child index 0 within Middle

    # Callback captured with fully qualified path
    assert "0.0.onClick" in resolver.callbacks


# TODOs:
# - Verify diffs are correct (first step)
# - Verify components are mounted/unmounted
# - Verify keyed components are


def test_render_tree_component_with_children_kwarg_and_nested_component():
    @ps.component
    def Child():
        def click(): ...

        return ps.button(onClick=click)["X"]

    @ps.component
    def Wrapper(*children, id: str = "wrap"):
        return ps.div(id=id)[*children]

    @ps.component
    def Top():
        return Wrapper(id="w")[Child()]

    resolver = Resolver()
    root = RenderNode(Top.fn)
    vdom, _ = resolver.render_tree(root, Top(), path="", relative_path="")

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
        def on_click(): ...

        return ps.button(onClick=on_click)["Go"]

    root = RenderRoot(Simple)
    result = root.render_diff()

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
    first = r1.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # mutate props
    attrs["className"] = "b"

    # Second render using previous VDOM -> update_props
    second = r1.render_diff()
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
    first = root.render_diff()
    assert first.ops == [{"type": "insert", "path": "", "data": "A"}]

    # Change primitive -> replace
    val["text"] = "B"
    second = root.render_diff()
    assert second.ops == [{"type": "replace", "path": "", "data": "B"}]

    # Change to None -> remove
    val["text"] = None
    third = root.render_diff()
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
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # Add extra child -> insert at path 1
    show_extra["flag"] = True
    second = root.render_diff()
    assert second.ops == [
        {"type": "insert", "path": "1", "data": {"tag": "span", "children": ["B"]}}
    ]

    # Remove extra child -> remove at path 1
    show_extra["flag"] = False
    third = root.render_diff()
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
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    content["b"] = "BB"
    second = root.render_diff()
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
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # Simulate an effect execution after first render
    flush_effects()

    state["on"] = False
    second = root.render_diff()
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
        print("rendering B")

        def eff():
            def cleanup():
                logs.append("B_cleanup")

            return cleanup

        ps.effects(eff)
        return ps.span("Bchild")

    @ps.component
    def Parent():
        print("rendering parent, switch =", which["a"])
        child = A() if which["a"] else B()
        return ps.div(child)

    root = RenderRoot(Parent)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # Simulate an effect execution after first render
    flush_effects()

    which["a"] = False
    second = root.render_diff()
    print("Second.ops:", second.ops)
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
    first = root.render_diff()
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
    second = root.render_diff()
    print("second.ops = ", second.ops)
    assert second.ops == [{"type": "replace", "path": "0.0.0", "data": "A:1"}]

    # Increment A's nested counter
    cbs = second.callbacks
    cbs["0.2.1.onClick"].fn()
    third = root.render_diff()
    print("third.ops = ", second.ops)
    assert third.ops == [{"type": "replace", "path": "0.2.0.0", "data": "A-child:1"}]

    # Increment B's own counter; A should not change
    cbs = third.callbacks
    cbs["1.1.onClick"].fn()
    fourth = root.render_diff()
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
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"
    assert first.callbacks["onClick"].fn is f1

    fn["cur"] = f2
    second = root.render_diff()
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
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    name["msg"] = "B"
    second = root.render_diff()
    assert second.ops == [{"type": "replace", "path": "0.0", "data": "B"}]
    assert logs == []


def test_props_removal_emits_empty_update_props():
    toggle = {"on": True}

    @ps.component
    def View():
        return ps.div(className="a") if toggle["on"] else ps.div()

    root = RenderRoot(View)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    toggle["on"] = False
    second = root.render_diff()
    assert second.ops == [{"type": "update_props", "path": "", "data": {}}]


def test_keyed_component_move_preserves_state_and_no_cleanup():
    logs: list[str] = []
    order = {"keys": ["a", "b"]}

    class C(ps.State):
        n: int = 0

        def __init__(self, label: str):
            self._label = label

        def inc(self):
            print(f"Incrementing {self._label}")
            self.n += 1

    @ps.component
    def Item(label: str, key=None):
        s = ps.states(C(label))

        def eff():
            def cleanup():
                logs.append(f"cleanup:{label}")

            return cleanup

        print(f"Rendering {label}, count = {s.n}")

        ps.effects(eff)
        return ps.div(
            ps.span(f"{label}:{s.n}"),
            ps.button(onClick=s.inc)["inc"],
        )

    @ps.component
    def List():
        return ps.div(*[Item(label=k, key=k) for k in order["keys"]])

    root = RenderRoot(List)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    flush_effects()  # simulate effect pass after render

    # inc first item (key 'a')
    first.callbacks["0.1.onClick"].fn()
    second = root.render_diff()
    assert second.ops == [{"type": "replace", "path": "0.0.0", "data": "a:1"}]

    flush_effects()  # simulate effect pass after render

    # reorder: move 'a' to the end
    order["keys"] = ["b", "a"]
    third = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, third.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["inc"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["inc"],
                    },
                ],
            },
        ],
    }

    flush_effects()  # simulate effect pass after render

    # inc 'a' at its new index 1, should go to 2
    third.callbacks["1.1.onClick"].fn()
    fourth = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, fourth.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["inc"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:2"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["inc"],
                    },
                ],
            },
        ],
    }


def test_keyed_nested_components_move_preserves_nested_state():
    order = {"keys": ["x", "y"]}

    class C(ps.State):
        n: int = 0

        def inc(self):
            self.n += 1

    @ps.component
    def Leaf(tag: str):
        s = ps.states(C)
        print(f"Rendering {tag} with count {s.n}")
        return ps.div(ps.span(f"{tag}:{s.n}"), ps.button(onClick=s.inc)["+"])

    @ps.component
    def Wrapper(tag: str, key=None):
        return ps.div(Leaf(tag=tag))

    @ps.component
    def List():
        return ps.div(*(Wrapper(key=k, tag=k) for k in order["keys"]))

    root = RenderRoot(List)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # bump x
    first.callbacks["0.0.1.onClick"].fn()  # path: wrapper0 -> leaf -> button
    print("--- Second render ---")
    second = root.render_diff()
    print("---------------------")
    assert second.ops == [{"type": "replace", "path": "0.0.0.0", "data": "x:1"}]

    # reorder: x to the end
    order["keys"] = ["y", "x"]
    print("--- Third render ---")
    third = root.render_diff()
    print("---------------------")
    vdom, _ = Resolver().render_tree(root.render_tree, third.tree, "", "")
    print("3rd render VDOM:", json.dumps(vdom, indent=2))
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {
                        "tag": "div",
                        "children": [
                            {"tag": "span", "children": ["y:0"]},
                            {
                                "tag": "button",
                                "props": {"onClick": "$$fn:0.0.1.onClick"},
                                "children": ["+"],
                            },
                        ],
                    }
                ],
            },
            {
                "tag": "div",
                "children": [
                    {
                        "tag": "div",
                        "children": [
                            {"tag": "span", "children": ["x:1"]},
                            {
                                "tag": "button",
                                "props": {"onClick": "$$fn:1.0.1.onClick"},
                                "children": ["+"],
                            },
                        ],
                    }
                ],
            },
        ],
    }

    # bump x again at new path
    third.callbacks["1.0.1.onClick"].fn()
    fourth = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, fourth.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {
                        "tag": "div",
                        "children": [
                            {"tag": "span", "children": ["y:0"]},
                            {
                                "tag": "button",
                                "props": {"onClick": "$$fn:0.0.1.onClick"},
                                "children": ["+"],
                            },
                        ],
                    }
                ],
            },
            {
                "tag": "div",
                "children": [
                    {
                        "tag": "div",
                        "children": [
                            {"tag": "span", "children": ["x:2"]},
                            {
                                "tag": "button",
                                "props": {"onClick": "$$fn:1.0.1.onClick"},
                                "children": ["+"],
                            },
                        ],
                    }
                ],
            },
        ],
    }


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
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"
    # Simulate an effect pass after render
    flush_effects()

    show["on"] = False
    _ = root.render_diff()
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


def test_keyed_complex_reorder_insert_remove_preserves_state_and_cleans_removed():
    logs: list[str] = []
    order = {"keys": ["a", "b", "c", "d"]}

    class C(ps.State):
        n: int = 0

        def __init__(self, label: str):
            self._label = label

        def inc(self):
            self.n += 1

    @ps.component
    def Item(label: str, key=None):
        s = ps.states(C(label))

        def eff():
            def cleanup():
                logs.append(f"cleanup:{label}")

            return cleanup

        ps.effects(eff)
        return ps.div(ps.span(f"{label}:{s.n}"), ps.button(onClick=s.inc)["+"])

    @ps.component
    def List():
        return ps.div(*(Item(key=k, label=k) for k in order["keys"]))

    root = RenderRoot(List)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"
    flush_effects()

    # bump b twice and d once
    first.callbacks["1.1.onClick"].fn()
    first.callbacks["1.1.onClick"].fn()
    first.callbacks["3.1.onClick"].fn()
    second = root.render_diff()

    vdom, _ = Resolver().render_tree(root.render_tree, second.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:2"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["c:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:2.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["d:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:3.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }
    flush_effects()

    # Reorder with insert and remove: remove 'c', insert 'e', move others
    order["keys"] = ["d", "b", "e", "a"]
    third = root.render_diff()

    vdom, _ = Resolver().render_tree(root.render_tree, third.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["d:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:2"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["e:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:2.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:3.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }

    # Only 'c' should have been cleaned up
    flush_effects()
    assert logs.count("cleanup:c") == 1
    assert all(x.startswith("cleanup:") for x in logs)
    assert (
        logs.count("cleanup:a") == 0
        and logs.count("cleanup:b") == 0
        and logs.count("cleanup:d") == 0
    )

    # bump 'a' at its new index 3
    third.callbacks["3.1.onClick"].fn()
    fourth = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, fourth.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["d:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:2"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["e:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:2.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:3.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }

    # Reverse-ish reorder and verify states still preserved
    order["keys"] = ["a", "e", "b", "d"]
    fifth = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, fifth.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["e:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:2"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:2.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["d:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:3.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }

    # bump 'd' at its new index 3
    fifth.callbacks["3.1.onClick"].fn()
    sixth = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, sixth.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["e:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:2"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:2.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["d:2"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:3.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }


def test_keyed_reverse_preserves_all_states():
    order = {"keys": ["k1", "k2", "k3", "k4"]}

    class C(ps.State):
        n: int = 0

        def inc(self):
            self.n += 1

    @ps.component
    def Item(label: str, key=None):
        s = ps.states(C)
        return ps.div(ps.span(f"{label}:{s.n}"), ps.button(onClick=s.inc)["+"])

    @ps.component
    def List():
        return ps.div(*(Item(key=k, label=k) for k in order["keys"]))

    root = RenderRoot(List)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # bump counts: k1->1, k2->2, k3->3, k4->4
    first.callbacks["0.1.onClick"].fn()
    first.callbacks["1.1.onClick"].fn()
    first.callbacks["1.1.onClick"].fn()
    for _ in range(3):
        first.callbacks["2.1.onClick"].fn()
    for _ in range(4):
        first.callbacks["3.1.onClick"].fn()
    second = root.render_diff()

    vdom, _ = Resolver().render_tree(root.render_tree, second.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["k1:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["k2:2"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["k3:3"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:2.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["k4:4"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:3.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }

    # Reverse order
    order["keys"] = ["k4", "k3", "k2", "k1"]
    third = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, third.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["k4:4"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["k3:3"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["k2:2"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:2.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["k1:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:3.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }


def test_keyed_remove_then_readd_same_key_resets_state_and_cleans_old():
    logs: list[str] = []
    order = {"keys": ["a", "b"]}

    class C(ps.State):
        n: int = 0

        def __init__(self, label: str):
            self._label = label

        def inc(self):
            self.n += 1

    @ps.component
    def Item(label: str, key=None):
        s = ps.states(C(label))

        def eff():
            def cleanup():
                logs.append(f"cleanup:{label}")

            return cleanup

        ps.effects(eff)
        return ps.div(ps.span(f"{label}:{s.n}"), ps.button(onClick=s.inc)["+"])

    @ps.component
    def List():
        return ps.div(*(Item(key=k, label=k) for k in order["keys"]))

    root = RenderRoot(List)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"
    flush_effects()

    # bump 'a'
    first.callbacks["0.1.onClick"].fn()
    second = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, second.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }
    flush_effects()

    # remove 'a'
    order["keys"] = ["b"]
    _ = root.render_diff()
    flush_effects()
    assert logs.count("cleanup:a") == 1

    # re-add 'a' at end -> should reset to 0
    order["keys"] = ["b", "a"]
    third = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, third.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }


def test_keyed_with_unkeyed_separators_reorder_preserves_component_state():
    order = {"keys": ["a", "b"]}

    class C(ps.State):
        n: int = 0

        def inc(self):
            self.n += 1

    @ps.component
    def Item(label: str, key=None):
        s = ps.states(C)
        return ps.div(ps.span(f"{label}:{s.n}"), ps.button(onClick=s.inc)["+"])

    @ps.component
    def List():
        # Interleave an unkeyed separator node
        return ps.div(
            Item(key=order["keys"][0], label=order["keys"][0]),
            ps.span("sep"),
            Item(key=order["keys"][1], label=order["keys"][1]),
        )

    root = RenderRoot(List)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # bump first item and second item
    first.callbacks["0.1.onClick"].fn()
    first.callbacks["2.1.onClick"].fn()
    second = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, second.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {"tag": "span", "children": ["sep"]},
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:2.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }

    # swap keys around the separator
    order["keys"] = ["b", "a"]
    third = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, third.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {"tag": "span", "children": ["sep"]},
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["a:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:2.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }


# =====================
# Multiple removes ordering
# =====================
def test_unkeyed_trailing_removes_are_emitted_in_descending_order():
    items = {"vals": ["a", "b", "c", "d", "e"]}

    @ps.component
    def View():
        return ps.ul(*(ps.li(v) for v in items["vals"]))

    root = RenderRoot(View)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # remove trailing two items -> should emit two removes at paths 4 then 3
    items["vals"] = ["a", "b", "c"]
    second = root.render_diff()
    assert second.ops == [
        {"type": "remove", "path": "4"},
        {"type": "remove", "path": "3"},
    ]


def test_nested_trailing_removes_descending_order_under_same_parent():
    items = {"vals": ["x1", "x2", "x3", "x4", "x5"]}

    @ps.component
    def View():
        # root div contains: header span, a container div with many spans, and a footer span
        return ps.div(
            ps.span("header"),
            ps.div(*(ps.span(v) for v in items["vals"])),
            ps.span("footer"),
        )

    root = RenderRoot(View)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # Remove last two spans inside the middle container div
    items["vals"] = ["x1", "x2", "x3"]
    second = root.render_diff()
    # Expect removes on the inner container's children at paths 1.4 and 1.3 in that order
    assert second.ops == [
        {"type": "remove", "path": "1.4"},
        {"type": "remove", "path": "1.3"},
    ]


# =====================
# Iterable children flattening
# =====================


def test_iterable_children_generator_is_flattened_in_render():
    @ps.component
    def View():
        gen = (ps.span(str(i)) for i in range(3))
        return ps.div()[gen]

    r = Resolver()
    root = RenderNode(View.fn)
    with pytest.warns(UserWarning, match=r"Iterable children of <div>.*without 'key'"):
        vdom, _ = r.render_tree(root, View(), path="", relative_path="")

    assert vdom == {
        "tag": "div",
        "children": [
            {"tag": "span", "children": ["0"]},
            {"tag": "span", "children": ["1"]},
            {"tag": "span", "children": ["2"]},
        ],
    }


def test_iterable_children_list_is_flattened_in_render():
    @ps.component
    def View():
        children = [ps.span("a"), ps.span("b")]
        return ps.div()[children]

    with pytest.warns(UserWarning, match=r"Iterable children of <div>.*without 'key'"):
        vdom, _ = Resolver().render_tree(RenderNode(View.fn), View(), "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {"tag": "span", "children": ["a"]},
            {"tag": "span", "children": ["b"]},
        ],
    }


def test_iterable_children_missing_keys_emits_warning_once():
    @ps.component
    def Item(label: str):
        return ps.div(ps.span(label))

    @ps.component
    def View():
        iterable = (Item(label=x) for x in ["x", "y"])  # unkeyed elements
        return ps.div()[iterable]

    r = Resolver()
    root = RenderNode(View.fn)
    with pytest.warns(
        UserWarning, match=r"Iterable children of <div>.*without 'key'"
    ) as w:
        _ = r.render_tree(root, View(), path="", relative_path="")
    assert len(w) == 1


def test_iterable_children_with_component_keys_no_warning():
    @ps.component
    def Item(label: str, key=None):
        return ps.div(ps.span(label))

    @ps.component
    def View():
        iterable = (Item(key=str(i), label=str(i)) for i in range(2))
        return ps.div()[iterable]

    r = Resolver()
    root = RenderNode(View.fn)
    _ = r.render_tree(root, View(), path="", relative_path="")


def test_string_child_is_not_treated_as_iterable():
    @ps.component
    def View():
        return ps.div()["abc"]

    vdom, _ = Resolver().render_tree(RenderNode(View.fn), View(), "", "")
    assert vdom == {"tag": "div", "children": ["abc"]}


def test_keyed_iterable_children_reorder_preserves_state_via_flattening():
    order = {"keys": ["x", "y"]}

    class C(ps.State):
        n: int = 0

        def __init__(self, label: str):
            self._label = label

        def inc(self):
            self.n += 1

    @ps.component
    def Item(label: str, key=None):
        s = ps.states(C(label))
        return ps.div(ps.span(f"{label}:{s.n}"), ps.button(onClick=s.inc)["+"])

    @ps.component
    def List():
        # Provide children as a single iterable to exercise flattening path
        iterable = (Item(key=k, label=k) for k in order["keys"])
        return ps.div()[iterable]

    root = RenderRoot(List)
    first = root.render_diff()
    assert first.ops and first.ops[0]["type"] == "insert"

    # bump 'x' once
    first.callbacks["0.1.onClick"].fn()
    second = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, second.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["x:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["y:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }

    # reorder: move 'x' to the end
    order["keys"] = ["y", "x"]
    third = root.render_diff()
    vdom, _ = Resolver().render_tree(root.render_tree, third.tree, "", "")
    assert vdom == {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["y:0"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:0.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["x:1"]},
                    {
                        "tag": "button",
                        "props": {"onClick": "$$fn:1.1.onClick"},
                        "children": ["+"],
                    },
                ],
            },
        ],
    }
