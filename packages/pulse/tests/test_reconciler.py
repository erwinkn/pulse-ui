import json
from copy import deepcopy

from pulse.reactive import flush_effects
from pulse.reconciler import Resolver
from pulse.reconciler import RenderNode, RenderRoot
from pulse.reconciler import lis
import pulse as ps

import pytest


def _sanitize_vdom_with_callbacks(node):
    callback_keys: set[str] = set()

    def join_path(prefix: str, part: str | int) -> str:
        part_str = str(part)
        return f"{prefix}.{part_str}" if prefix else part_str

    def register(path_prefix: str, entry: str) -> None:
        if not entry:
            return
        if "." in entry:
            callback_keys.add(entry)
        else:
            callback_keys.add(join_path(path_prefix, entry))

    def visit(value, path: str):
        if (
            isinstance(value, (str, int, float))
            or value is None
            or isinstance(value, bool)
        ):
            return value
        if isinstance(value, list):
            return [visit(item, path) for item in value]
        if isinstance(value, dict):
            working = deepcopy(value)
            callbacks = working.pop("__callbacks__", None)
            if callbacks:
                for item in callbacks:
                    register(path, item)

            if "tag" in working:
                sanitized: dict = {"tag": working["tag"]}
                if "key" in working:
                    sanitized["key"] = working["key"]
                if "lazy" in working:
                    sanitized["lazy"] = working["lazy"]

                props = working.get("props") or {}
                sanitized_props: dict[str, object] = {}
                for prop_key, prop_value in props.items():
                    if isinstance(prop_value, str) and prop_value.startswith("$$fn:"):
                        register("", prop_value[len("$$fn:") :])
                        continue
                    prop_path = join_path(path, prop_key)
                    sanitized_props[prop_key] = visit(prop_value, prop_path)
                if sanitized_props:
                    sanitized["props"] = sanitized_props

                children = working.get("children")
                if children is not None:
                    sanitized_children = []
                    for idx, child in enumerate(children):
                        child_path = join_path(path, idx)
                        sanitized_children.append(visit(child, child_path))
                    sanitized["children"] = sanitized_children
                return sanitized

            return {k: visit(v, path) for k, v in working.items()}

        return value

    sanitized_vdom = visit(deepcopy(node), "")
    return sanitized_vdom, sorted(callback_keys)


def assert_vdom_with_callbacks(
    actual_vdom, resolver: Resolver, expected, *, expected_callbacks=None
):
    actual_sanitized, _ = _sanitize_vdom_with_callbacks(actual_vdom)
    expected_sanitized, callbacks_from_expected = _sanitize_vdom_with_callbacks(
        expected
    )
    assert actual_sanitized == expected_sanitized

    expected_callback_keys = set(callbacks_from_expected)
    if expected_callbacks:
        expected_callback_keys.update(expected_callbacks)

    actual_keys = sorted(resolver.callbacks.keys())
    assert actual_keys == sorted(expected_callback_keys)


def _transform_expected_ops(expected_ops):
    sanitized_ops: list[dict] = []
    callback_adds: set[str] = set()
    callback_removes: set[str] = set()

    for op in expected_ops:
        op_copy = deepcopy(op)
        callback_adds.update(op_copy.pop("__callback_adds__", []))
        callback_removes.update(op_copy.pop("__callback_removes__", []))

        op_type = op_copy["type"]
        if op_type in {"replace", "insert"}:
            sanitized_data, callback_keys = _sanitize_vdom_with_callbacks(
                op_copy["data"]
            )
            sanitized_op: dict[str, object] = {
                "type": op_type,
                "path": op_copy.get("path", ""),
                "data": sanitized_data,
            }
            if op_type == "insert":
                sanitized_op["idx"] = op_copy["idx"]
            sanitized_ops.append(sanitized_op)
            callback_adds.update(callback_keys)
        elif op_type == "update_props":
            data = op_copy["data"]
            sanitized_data: dict[str, dict | list] = {}
            if "set" in data:
                sanitized_set: dict[str, object] = {}
                for key, value in data["set"].items():
                    if isinstance(value, dict) and "tag" in value:
                        sanitized_value, callback_keys = _sanitize_vdom_with_callbacks(
                            value
                        )
                        sanitized_set[key] = sanitized_value
                        callback_adds.update(callback_keys)
                    else:
                        sanitized_set[key] = value
                if sanitized_set:
                    sanitized_data["set"] = sanitized_set
            if "remove" in data:
                sanitized_data["remove"] = data["remove"]
            if sanitized_data:
                sanitized_ops.append(
                    {
                        "type": "update_props",
                        "path": op_copy["path"],
                        "data": sanitized_data,
                    }
                )
        else:
            sanitized_ops.append(op_copy)

    callback_ops = []
    if callback_adds or callback_removes:
        data: dict[str, list[str]] = {}
        if callback_adds:
            data["add"] = sorted(callback_adds)
        if callback_removes:
            data["remove"] = sorted(callback_removes)
        callback_ops.append({"type": "update_callbacks", "path": "", "data": data})

    return sanitized_ops, callback_ops


def assert_ops_with_callbacks(actual_ops, expected_ops):
    sanitized_expected_ops, expected_callback_ops = _transform_expected_ops(
        expected_ops
    )
    actual_vdom_ops = [op for op in actual_ops if op["type"] != "update_callbacks"]
    actual_callback_ops = [op for op in actual_ops if op["type"] == "update_callbacks"]
    assert actual_vdom_ops == sanitized_expected_ops
    assert actual_callback_ops == expected_callback_ops


def non_callback_ops(ops):
    return [op for op in ops if op.get("type") != "update_callbacks"]


def assert_first_replace(ops):
    filtered = non_callback_ops(ops)
    assert filtered and filtered[0]["type"] == "replace"
    return filtered


def assert_render_tree_vdom(render_node, tree, expected):
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(render_node, tree, "", "")
    assert_vdom_with_callbacks(vdom, temp_resolver, expected)
    return vdom


# TODO: props diffing tests
# 1) Should remove callbacks and capture them globally
# 2) Should render element props


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

    expected = {
        "tag": "button",
        "__callbacks__": ["onClick"],
        "children": ["Go"],
    }
    assert_vdom_with_callbacks(vdom, resolver, expected)
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

    expected = {
        "tag": "div",
        "props": {"id": "top"},
        "children": [
            {
                "tag": "div",
                "props": {"className": "mid"},
                "children": [
                    {
                        "tag": "button",
                        "__callbacks__": ["0.0.onClick"],
                        "children": ["X"],
                    }
                ],
            }
        ],
    }
    assert_vdom_with_callbacks(vdom, resolver, expected)

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

    expected = {
        "tag": "div",
        "props": {"id": "w"},
        "children": [
            {"tag": "button", "__callbacks__": ["0.onClick"], "children": ["X"]}
        ],
    }
    assert_vdom_with_callbacks(vdom, resolver, expected)
    assert "0.onClick" in resolver.callbacks


# =====================
# Render props
# =====================


class _RenderPropCounter(ps.State):
    label: str
    n: int = 0

    def __init__(self, label: str):
        self.label = label

    def inc(self):
        self.n += 1


@ps.component
def _render_prop_button(label: str):
    counter = ps.states(_RenderPropCounter(label))

    def handle_click():
        counter.inc()

    return ps.button(onClick=handle_click)[f"{counter.label}:{counter.n}"]


def test_render_prop_state_preserved_and_emits_updates():
    @ps.component
    def Host():
        return ps.div(render=_render_prop_button(label="A"))

    root = RenderRoot(Host)
    first = root.render_diff()

    assert_ops_with_callbacks(
        first.ops,
        [
            {"type": "update_render_props", "path": "", "data": {"add": ["render"]}},
            {
                "type": "replace",
                "path": "",
                "data": {
                    "tag": "div",
                    "props": {
                        "render": {
                            "tag": "button",
                            "__callbacks__": ["render.onClick"],
                            "children": ["A:0"],
                        }
                    },
                },
            },
        ],
    )
    assert first.render_props == {"render"}
    assert "render.onClick" in first.callbacks

    first.callbacks["render.onClick"].fn()
    second = root.render_diff()

    assert_ops_with_callbacks(
        second.ops,
        [
            {"type": "replace", "path": "render.0", "data": "A:1"},
        ],
    )

    assert second.render_props == {"render"}


def test_nested_render_props_state_updates():
    @ps.component
    def Inner():
        return _render_prop_button(label="inner")

    @ps.component
    def Middle():
        return ps.div(inner=Inner())

    @ps.component
    def Parent():
        return ps.div(outer=Middle())

    root = RenderRoot(Parent)
    first = root.render_diff()

    assert first.render_props == {"outer", "outer.inner"}
    assert "outer.inner.onClick" in first.callbacks

    assert_ops_with_callbacks(
        first.ops,
        [
            {
                "type": "update_render_props",
                "path": "",
                "data": {"add": ["outer", "outer.inner"]},
            },
            {
                "type": "replace",
                "path": "",
                "data": {
                    "tag": "div",
                    "props": {
                        "outer": {
                            "tag": "div",
                            "props": {
                                "inner": {
                                    "tag": "button",
                                    "__callbacks__": ["outer.inner.onClick"],
                                    "children": ["inner:0"],
                                }
                            },
                        }
                    },
                },
            },
        ],
    )

    first.callbacks["outer.inner.onClick"].fn()
    second = root.render_diff()

    assert_ops_with_callbacks(
        second.ops,
        [
            {"type": "replace", "path": "outer.inner.0", "data": "inner:1"},
        ],
    )

    assert second.render_props == {"outer", "outer.inner"}


@ps.react_component("Card", "@tests/Card")
def Reactcard(*children, render, key: str | None = None):
    return None


@pytest.mark.xfail(reason="Reconciler will be rewritten soon")
def test_keyed_react_component_render_prop_preserves_state():
    order = {"keys": ["Left", "Right"]}

    @ps.component
    def List():
        return ps.div(
            *[
                Reactcard(key=label.lower(), render=_render_prop_button(label=label))
                for label in order["keys"]
            ]
        )

    root = RenderRoot(List)
    first = root.render_diff()

    assert first.render_props == {"0.render", "1.render"}
    assert "0.render.onClick" in first.callbacks

    first.callbacks["0.render.onClick"].fn()
    second = root.render_diff()

    assert_ops_with_callbacks(
        second.ops,
        [
            {"type": "replace", "path": "0.render.0", "data": "Left:1"},
        ],
    )

    assert second.render_props == {"0.render", "1.render"}

    order["keys"] = ["Right", "Left"]
    third = root.render_diff()

    assert third.render_props == {"0.render", "1.render"}

    assert "1.render.onClick" in third.callbacks
    third.callbacks["1.render.onClick"].fn()
    fourth = root.render_diff()

    assert_ops_with_callbacks(
        fourth.ops,
        [
            {"type": "replace", "path": "1.render.0", "data": "Left:2"},
        ],
    )

    assert fourth.tree.children[1].props["render"].children == ["Left:2"]


@pytest.mark.xfail(reason="Reconciler will be rewritten soon")
def test_render_prop_removed_and_readded_resets_state():
    toggle = {"render": True}

    @ps.component
    def Host():
        if toggle["render"]:
            return ps.div(render=_render_prop_button(label="A"))
        return ps.div()

    root = RenderRoot(Host)
    first = root.render_diff()
    assert first.render_props == {"render"}
    assert "render.onClick" in first.callbacks

    toggle["render"] = False
    second = root.render_diff()
    assert_ops_with_callbacks(
        second.ops,
        [
            {
                "type": "update_render_props",
                "path": "",
                "data": {"remove": ["render"]},
                "__callback_removes__": ["render.onClick"],
            },
            {"type": "update_props", "path": "", "data": {"remove": ["render"]}},
        ],
    )
    assert second.render_props == set()
    assert second.render_props == set()

    toggle["render"] = True
    third = root.render_diff()

    assert_ops_with_callbacks(
        third.ops,
        [
            {"type": "update_render_props", "path": "", "data": {"add": ["render"]}},
            {
                "type": "update_props",
                "path": "",
                "data": {
                    "set": {
                        "render": {
                            "tag": "button",
                            "__callbacks__": ["render.onClick"],
                            "children": ["A:0"],
                        }
                    }
                },
            },
        ],
    )
    assert "render.onClick" in third.callbacks
    render_prop = third.tree.props["render"]
    assert render_prop.children == ["A:0"]
    third.callbacks["render.onClick"].fn()
    fourth = root.render_diff()
    assert_ops_with_callbacks(
        fourth.ops,
        [
            {"type": "replace", "path": "render.0", "data": "A:1"},
        ],
    )
    render_prop = fourth.tree.props["render"]
    assert render_prop.children == ["A:1"]


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

    assert_ops_with_callbacks(
        result.ops,
        [
            {
                "type": "replace",
                "path": "",
                "data": {
                    "tag": "button",
                    "__callbacks__": ["onClick"],
                    "children": ["Go"],
                },
            }
        ],
    )
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
    assert_first_replace(first.ops)

    # mutate props
    attrs["className"] = "b"

    # Second render using previous VDOM -> update_props
    second = r1.render_diff()
    assert non_callback_ops(second.ops) == [
        {"type": "update_props", "path": "", "data": {"set": {"className": "b"}}}
    ]


def test_reconcile_primitive_changes_and_none():
    val: dict[str, str | None] = {"text": "A"}

    @ps.component
    def P():
        return val["text"]

    # Initial insert of primitive
    root = RenderRoot(P)
    first = root.render_diff()
    assert non_callback_ops(first.ops) == [{"type": "replace", "path": "", "data": "A"}]

    # Change primitive -> replace
    val["text"] = "B"
    second = root.render_diff()
    assert non_callback_ops(second.ops) == [
        {"type": "replace", "path": "", "data": "B"}
    ]

    # Change to None -> remove
    val["text"] = None
    third = root.render_diff()
    assert non_callback_ops(third.ops) == [
        {"type": "replace", "path": "", "data": None}
    ]


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
    ops = assert_first_replace(first.ops)

    # Add extra child -> insert at path 1
    show_extra["flag"] = True
    second = root.render_diff()
    assert non_callback_ops(second.ops) == [
        {
            "type": "insert",
            "path": "",
            "idx": 1,
            "data": {"tag": "span", "children": ["B"]},
        }
    ]

    # Remove extra child -> remove at path 1
    show_extra["flag"] = False
    third = root.render_diff()
    assert non_callback_ops(third.ops) == [{"type": "remove", "path": "", "idx": 1}]


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
    assert_first_replace(first.ops)

    content["b"] = "BB"
    second = root.render_diff()
    print("second.ops = ", second.ops)
    assert non_callback_ops(second.ops) == [
        {"type": "replace", "path": "0.1.0", "data": "BB"}
    ]


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
    assert_first_replace(first.ops)

    # Simulate an effect execution after first render
    flush_effects()

    state["on"] = False
    second = root.render_diff()
    assert non_callback_ops(second.ops) == [{"type": "remove", "path": "", "idx": 0}]
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
    assert_first_replace(first.ops)

    # Simulate an effect execution after first render
    flush_effects()

    which["a"] = False
    second = root.render_diff()
    print("Second.ops:", second.ops)
    assert non_callback_ops(second.ops) == [
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
    assert non_callback_ops(second.ops) == [
        {"type": "replace", "path": "0.0.0", "data": "A:1"}
    ]

    # Increment A's nested counter
    cbs = second.callbacks
    cbs["0.2.1.onClick"].fn()
    third = root.render_diff()
    print("third.ops = ", second.ops)
    assert non_callback_ops(third.ops) == [
        {"type": "replace", "path": "0.2.0.0", "data": "A-child:1"}
    ]

    # Increment B's own counter; A should not change
    cbs = third.callbacks
    cbs["1.1.onClick"].fn()
    fourth = root.render_diff()
    print("fourth.ops = ", second.ops)
    assert non_callback_ops(fourth.ops) == [
        {"type": "replace", "path": "1.0.0", "data": "B:1"}
    ]


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
    assert_first_replace(first.ops)
    assert first.callbacks["onClick"].fn is f1

    fn["cur"] = f2
    second = root.render_diff()
    assert non_callback_ops(second.ops) == []
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
    assert_first_replace(first.ops)

    name["msg"] = "B"
    second = root.render_diff()
    assert non_callback_ops(second.ops) == [
        {"type": "replace", "path": "0.0", "data": "B"}
    ]
    assert logs == []


def test_props_removal_emits_empty_update_props():
    toggle = {"on": True}

    @ps.component
    def View():
        return ps.div(className="a") if toggle["on"] else ps.div()

    root = RenderRoot(View)
    first = root.render_diff()
    assert_first_replace(first.ops)

    toggle["on"] = False
    second = root.render_diff()
    assert non_callback_ops(second.ops) == [
        {"type": "update_props", "path": "", "data": {"remove": ["className"]}}
    ]


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
    assert_first_replace(first.ops)

    flush_effects()  # simulate effect pass after render

    # inc first item (key 'a')
    first.callbacks["0.1.onClick"].fn()
    second = root.render_diff()
    assert non_callback_ops(second.ops) == [
        {"type": "replace", "path": "0.0.0", "data": "a:1"}
    ]

    flush_effects()  # simulate effect pass after render

    # reorder: move 'a' to the end
    order["keys"] = ["b", "a"]
    third = root.render_diff()
    tmp_resolver = Resolver()
    vdom, _ = tmp_resolver.render_tree(root.render_tree, third.tree, "", "")
    expected = {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:0"]},
                    {
                        "tag": "button",
                        "__callbacks__": ["0.1.onClick"],
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
                        "__callbacks__": ["1.1.onClick"],
                        "children": ["inc"],
                    },
                ],
            },
        ],
    }
    assert_vdom_with_callbacks(vdom, tmp_resolver, expected)

    flush_effects()  # simulate effect pass after render

    # inc 'a' at its new index 1, should go to 2
    third.callbacks["1.1.onClick"].fn()
    fourth = root.render_diff()
    tmp_resolver = Resolver()
    vdom, _ = tmp_resolver.render_tree(root.render_tree, fourth.tree, "", "")
    expected = {
        "tag": "div",
        "children": [
            {
                "tag": "div",
                "children": [
                    {"tag": "span", "children": ["b:0"]},
                    {
                        "tag": "button",
                        "__callbacks__": ["0.1.onClick"],
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
                        "__callbacks__": ["1.1.onClick"],
                        "children": ["inc"],
                    },
                ],
            },
        ],
    }
    assert_vdom_with_callbacks(vdom, tmp_resolver, expected)


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
    assert_first_replace(first.ops)

    # bump x
    first.callbacks["0.0.1.onClick"].fn()  # path: wrapper0 -> leaf -> button
    print("--- Second render ---")
    second = root.render_diff()
    print("---------------------")
    assert non_callback_ops(second.ops) == [
        {"type": "replace", "path": "0.0.0.0", "data": "x:1"}
    ]

    # reorder: x to the end
    order["keys"] = ["y", "x"]
    print("--- Third render ---")
    third = root.render_diff()
    print("---------------------")
    tmp_resolver = Resolver()
    vdom, _ = tmp_resolver.render_tree(root.render_tree, third.tree, "", "")
    print("3rd render VDOM:", json.dumps(vdom, indent=2))
    assert_vdom_with_callbacks(
        vdom,
        tmp_resolver,
        {
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
                                    "__callbacks__": ["0.0.1.onClick"],
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
                                    "__callbacks__": ["1.0.1.onClick"],
                                    "children": ["+"],
                                },
                            ],
                        }
                    ],
                },
            ],
        },
    )

    # bump x again at new path
    third.callbacks["1.0.1.onClick"].fn()
    fourth = root.render_diff()
    assert_render_tree_vdom(
        root.render_tree,
        fourth.tree,
        {
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
                                    "__callbacks__": ["0.0.1.onClick"],
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
                                    "__callbacks__": ["1.0.1.onClick"],
                                    "children": ["+"],
                                },
                            ],
                        }
                    ],
                },
            ],
        },
    )


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
    assert_first_replace(first.ops)
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
    assert_first_replace(first.ops)
    flush_effects()

    # bump b twice and d once
    first.callbacks["1.1.onClick"].fn()
    first.callbacks["1.1.onClick"].fn()
    first.callbacks["3.1.onClick"].fn()
    second = root.render_diff()

    assert_render_tree_vdom(
        root.render_tree,
        second.tree,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["a:0"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
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
                            "__callbacks__": ["2.1.onClick"],
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
                            "__callbacks__": ["3.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )
    flush_effects()

    # Reorder with insert and remove: remove 'c', insert 'e', move others
    order["keys"] = ["d", "b", "e", "a"]
    third = root.render_diff()
    assert_render_tree_vdom(
        root.render_tree,
        third.tree,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["d:1"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
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
                            "__callbacks__": ["2.1.onClick"],
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
                            "__callbacks__": ["3.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )

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
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, fourth.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["d:1"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
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
                            "__callbacks__": ["2.1.onClick"],
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
                            "__callbacks__": ["3.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )

    # Reverse-ish reorder and verify states still preserved
    order["keys"] = ["a", "e", "b", "d"]
    fifth = root.render_diff()
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, fifth.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["a:1"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
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
                            "__callbacks__": ["2.1.onClick"],
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
                            "__callbacks__": ["3.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )

    # bump 'd' at its new index 3
    fifth.callbacks["3.1.onClick"].fn()
    sixth = root.render_diff()
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, sixth.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["a:1"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
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
                            "__callbacks__": ["2.1.onClick"],
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
                            "__callbacks__": ["3.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )


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
    assert_first_replace(first.ops)

    # bump counts: k1->1, k2->2, k3->3, k4->4
    first.callbacks["0.1.onClick"].fn()
    first.callbacks["1.1.onClick"].fn()
    first.callbacks["1.1.onClick"].fn()
    for _ in range(3):
        first.callbacks["2.1.onClick"].fn()
    for _ in range(4):
        first.callbacks["3.1.onClick"].fn()
    second = root.render_diff()

    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, second.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["k1:1"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
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
                            "__callbacks__": ["2.1.onClick"],
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
                            "__callbacks__": ["3.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )

    # Reverse order
    order["keys"] = ["k4", "k3", "k2", "k1"]
    third = root.render_diff()
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, third.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["k4:4"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
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
                            "__callbacks__": ["2.1.onClick"],
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
                            "__callbacks__": ["3.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )


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
    assert_first_replace(first.ops)
    flush_effects()

    # bump 'a'
    first.callbacks["0.1.onClick"].fn()
    second = root.render_diff()
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, second.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["a:1"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )
    flush_effects()

    # remove 'a'
    order["keys"] = ["b"]
    _ = root.render_diff()
    flush_effects()
    assert logs.count("cleanup:a") == 1

    # re-add 'a' at end -> should reset to 0
    order["keys"] = ["b", "a"]
    third = root.render_diff()
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, third.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["b:0"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )


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
    assert_first_replace(first.ops)

    # bump first item and second item
    first.callbacks["0.1.onClick"].fn()
    first.callbacks["2.1.onClick"].fn()
    second = root.render_diff()
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, second.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["a:1"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["2.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )

    # swap keys around the separator
    order["keys"] = ["b", "a"]
    third = root.render_diff()
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, third.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["b:1"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["2.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )


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
    assert_first_replace(first.ops)

    # remove trailing two items -> should emit two removes at paths 4 then 3
    items["vals"] = ["a", "b", "c"]
    second = root.render_diff()
    assert non_callback_ops(second.ops) == [
        {"type": "remove", "path": "", "idx": 4},
        {"type": "remove", "path": "", "idx": 3},
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
    assert_first_replace(first.ops)

    # Remove last two spans inside the middle container div
    items["vals"] = ["x1", "x2", "x3"]
    second = root.render_diff()
    # Expect removes on the inner container's children at paths 1.4 and 1.3 in that order
    assert non_callback_ops(second.ops) == [
        {"type": "remove", "path": "1", "idx": 4},
        {"type": "remove", "path": "1", "idx": 3},
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

    assert_vdom_with_callbacks(
        vdom,
        r,
        {
            "tag": "div",
            "children": [
                {"tag": "span", "children": ["0"]},
                {"tag": "span", "children": ["1"]},
                {"tag": "span", "children": ["2"]},
            ],
        },
    )


def test_iterable_children_list_is_flattened_in_render():
    @ps.component
    def View():
        children = [ps.span("a"), ps.span("b")]
        return ps.div()[children]

    temp_resolver = Resolver()
    with pytest.warns(UserWarning, match=r"Iterable children of <div>.*without 'key'"):
        vdom, _ = temp_resolver.render_tree(RenderNode(View.fn), View(), "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {"tag": "span", "children": ["a"]},
                {"tag": "span", "children": ["b"]},
            ],
        },
    )


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

    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(RenderNode(View.fn), View(), "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {"tag": "div", "children": ["abc"]},
    )


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
    assert_first_replace(first.ops)

    # bump 'x' once
    first.callbacks["0.1.onClick"].fn()
    second = root.render_diff()
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, second.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["x:1"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )

    # reorder: move 'x' to the end
    order["keys"] = ["y", "x"]
    third = root.render_diff()
    temp_resolver = Resolver()
    vdom, _ = temp_resolver.render_tree(root.render_tree, third.tree, "", "")
    assert_vdom_with_callbacks(
        vdom,
        temp_resolver,
        {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {"tag": "span", "children": ["y:0"]},
                        {
                            "tag": "button",
                            "__callbacks__": ["0.1.onClick"],
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
                            "__callbacks__": ["1.1.onClick"],
                            "children": ["+"],
                        },
                    ],
                },
            ],
        },
    )
