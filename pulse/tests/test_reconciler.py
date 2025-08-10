import json
from pulse.reconciler import Resolver
from pulse.reconciler import RenderNode
import pulse as ps


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
    assert r.callbacks["onClick"] is cb
    assert out1["id"] == "a"

    # With path: prefix and dot should be added
    r2 = Resolver()
    props2 = {"onClick": cb}
    out2 = r2._capture_callbacks(props2, path="1.child")
    assert out2["onClick"] == "$$fn:1.child.onClick"
    assert r2.callbacks["1.child.onClick"] is cb


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
        "root.onClick": a,
        "root.onHover": b,
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
    vdom = resolver.render_tree(root, Simple(), path="")

    print("vdom:", json.dumps(vdom, indent=2))
    assert vdom == {
        "tag": "button",
        "props": {"onClick": "$$fn:onClick"},
        "children": ["Go"],
    }
    assert "" in root.children  # top-level component tracked
    assert callable(resolver.callbacks["onClick"])  # captured


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

    vdom = resolver.render_tree(root, Top(), path="")

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
