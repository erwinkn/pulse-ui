from pulse.diff import diff_node
from pulse.vdom import Node, div, span, button


def test_null_cases_node():
    # Both None
    ops = diff_node(None, None)
    assert ops == []

    # Insert from None
    new_node = div()["Hello"]
    ops = diff_node(None, new_node)
    new_vdom, _ = new_node.render()
    assert len(ops) == 1
    assert ops[0] == {"type": "insert", "path": "", "data": new_vdom}

    # Remove to None
    old_node = Node("div", {"class": "test"})["Hello"]
    ops = diff_node(old_node, None)
    assert len(ops) == 1
    assert ops[0] == {"type": "remove", "path": "", "data": None}


def test_identical_nodes_node():
    a = Node("div", {"class": "test"})["Hello"]
    b = Node("div", {"class": "test"})["Hello"]
    ops = diff_node(a, b)
    assert ops == []


def test_text_node_changes_node():
    # Same text
    ops = diff_node("hello", "hello")
    assert ops == []

    # Changed text
    ops = diff_node("hello", "world")
    assert len(ops) == 1
    assert ops[0] == {"type": "replace", "path": "", "data": "world"}

    # Text to element
    new_node = span()["world"]
    ops = diff_node("hello", new_node)
    new_vdom, _ = new_node.render()
    assert len(ops) == 1
    assert ops[0]["type"] == "replace"
    assert ops[0]["data"] == new_vdom


def test_tag_changes_node():
    old_node = Node("div", {"class": "test"})["Hello"]
    new_node = Node("span", {"class": "test"})["Hello"]
    ops = diff_node(old_node, new_node)
    new_vdom, _ = new_node.render()
    assert len(ops) == 1
    assert ops[0]["type"] == "replace"
    assert ops[0]["data"] == new_vdom


def test_no_prop_changes_node():
    a = Node("div", {"class": "test", "id": "main"})
    b = Node("div", {"class": "test", "id": "main"})
    ops = diff_node(a, b)
    assert ops == []


def test_prop_changes_node():
    old_node = Node("div", {"class": "old", "id": "main"})
    new_node = Node("div", {"class": "new", "data-value": "123"})
    ops = diff_node(old_node, new_node)
    assert len(ops) == 1
    assert ops[0]["type"] == "update_props"
    assert ops[0]["data"] == {"class": "new", "data-value": "123"}


def test_children_no_changes_node():
    old_node = div()["Hello", "World"]
    new_node = div()["Hello", "World"]
    ops = diff_node(old_node, new_node)
    assert ops == []


def test_append_children_node():
    old_node = div()["Hello"]
    new_node = div()["Hello", "World"]
    ops = diff_node(old_node, new_node)
    assert len(ops) == 1
    assert ops[0] == {"type": "insert", "path": "1", "data": "World"}


def test_remove_children_node():
    old_node = div()["Hello", "World"]
    new_node = div()["Hello"]
    ops = diff_node(old_node, new_node)
    assert len(ops) == 1
    assert ops[0] == {"type": "remove", "path": "1", "data": None}


def test_replace_children_node():
    old_node = div()["Hello", "Old"]
    new_node = div()["Hello", "New"]
    ops = diff_node(old_node, new_node)
    assert len(ops) == 1
    assert ops[0] == {"type": "replace", "path": "1", "data": "New"}


def test_keyed_reorder_node():
    old_node = Node("div")[
        Node("div", {"id": "1"}, key="a")["First"],
        Node("div", {"id": "2"}, key="b")["Second"],
        Node("div", {"id": "3"}, key="c")["Third"],
    ]
    new_node = Node("div")[
        Node("div", {"id": "3"}, key="c")["Third"],
        Node("div", {"id": "1"}, key="a")["First"],
        Node("div", {"id": "2"}, key="b")["Second"],
    ]
    ops = diff_node(old_node, new_node)
    assert any(op["type"] == "move" for op in ops)


def test_keyed_add_remove_node():
    old_node = Node("div")[
        Node("div", {"id": "1"}, key="a")["First"],
        Node("div", {"id": "2"}, key="b")["Second"],
    ]
    new_node = Node("div")[
        Node("div", {"id": "1"}, key="a")["First"],
        Node("div", {"id": "3"}, key="c")["Third"],
    ]
    ops = diff_node(old_node, new_node)
    assert any(op["type"] == "insert" for op in ops)
    assert any(op["type"] == "remove" for op in ops)


def test_mixed_keyed_unkeyed_node():
    old_node = Node("div")[
        "text1",
        Node("div", {"id": "1"}, key="k1")["Keyed"],
        "text2",
    ]
    new_node = Node("div")[
        "newtext1",
        Node("div", {"id": "2"}, key="k2")["NewKeyed"],
        "text2",
    ]
    ops = diff_node(old_node, new_node)
    assert len(ops) > 0
    assert any(op["type"] == "replace" and op["data"] == "newtext1" for op in ops)


def test_nested_changes_node():
    old_node = Node("div", {"class": "container"})[
        Node("header")["Title"],
        Node("main")[Node("section")["Content"]],
    ]
    new_node = Node("div", {"class": "container"})[
        Node("header")["New Title"],
        Node("main")[Node("section")["New Content"], Node("footer")["Footer"]],
    ]
    ops = diff_node(old_node, new_node)
    assert len(ops) > 0
    assert any("." in op["path"] for op in ops)


def test_button_callbacks_props_diff_node():
    # Ensure callback placeholders are part of props diff
    def cb():
        pass

    old_node = button(onClick=cb)["X"]
    new_node = button(onClick=cb)["X"]
    ops = diff_node(old_node, new_node)
    assert ops == []
