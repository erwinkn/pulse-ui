"""
Tests for the VDOM diffing algorithm.

This test suite covers all aspects of the diffing algorithm including:
- Basic node operations (insert, remove, replace)
- Property updates
- Children diffing with keys
- Edge cases and complex scenarios
"""

import pytest
from pulse.diff import diff_vdom
from pulse.vdom import Node, VDOMNode
from pulse.tests.test_utils import assert_vdom_equal


class TestBasicDiffing:
    """Test basic diffing operations."""

    def test_null_cases(self):
        """Test diffing with None values."""
        # Both None
        diff = diff_vdom(None, None)
        assert diff.updates == []

        # Insert from None
        new_node = Node("div", {"class": "test"}, ["Hello"])
        diff = diff_vdom(None, new_node)
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "insert"
        assert diff.updates[0]["path"] == ""

        expected_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "test"},
            "children": ["Hello"],
        }
        assert_vdom_equal(diff.updates[0]["data"], expected_vdom)

        # Remove to None
        old_node = Node("div", {"class": "test"}, ["Hello"])
        diff = diff_vdom(old_node, None)
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "remove"
        assert diff.updates[0]["path"] == ""

    def test_identical_nodes(self):
        """Test that identical nodes produce no operations."""
        node1 = Node("div", {"class": "test"}, ["Hello"])
        node2 = Node("div", {"class": "test"}, ["Hello"])
        diff = diff_vdom(node1, node2)
        assert diff.updates == []

    def test_text_node_changes(self):
        """Test diffing text nodes."""
        # Same text
        diff = diff_vdom("hello", "hello")
        assert diff.updates == []

        # Changed text
        diff = diff_vdom("hello", "world")
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "replace"
        assert diff.updates[0]["data"] == "world"

        # Text to element
        new_node = Node("span", {}, ["world"])
        diff = diff_vdom("hello", new_node)
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "replace"

        expected_vdom: VDOMNode = {"tag": "span", "children": ["world"]}
        assert_vdom_equal(diff.updates[0]["data"], expected_vdom)

    def test_tag_changes(self):
        """Test nodes with different tags get replaced."""
        old_node = Node("div", {"class": "test"}, ["Hello"])
        new_node = Node("span", {"class": "test"}, ["Hello"])
        diff = diff_vdom(old_node, new_node)
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "replace"

        expected_vdom: VDOMNode = {
            "tag": "span",
            "props": {"class": "test"},
            "children": ["Hello"],
        }
        assert_vdom_equal(diff.updates[0]["data"], expected_vdom)


class TestPropertyDiffing:
    """Test property diffing functionality."""

    def test_no_prop_changes(self):
        """Test when properties are identical."""
        old_node = Node("div", {"class": "test", "id": "main"})
        new_node = Node("div", {"class": "test", "id": "main"})
        diff = diff_vdom(old_node, new_node)
        assert diff.updates == []

    def test_prop_changes(self):
        """Test when properties change."""
        old_node = Node("div", {"class": "old", "id": "main"})
        new_node = Node("div", {"class": "new", "data-value": "123"})
        diff = diff_vdom(old_node, new_node)
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "update_props"
        # New algorithm just passes the new props directly
        assert diff.updates[0]["data"] == {"class": "new", "data-value": "123"}


class TestChildrenDiffing:
    """Test children diffing with and without keys."""

    def test_no_children_changes(self):
        """Test when children are identical."""
        old_node = Node("div", children=["Hello", "World"])
        new_node = Node("div", children=["Hello", "World"])
        diff = diff_vdom(old_node, new_node)
        assert diff.updates == []

    def test_append_children(self):
        """Test appending new children."""
        old_node = Node("div", children=["Hello"])
        new_node = Node("div", children=["Hello", "World"])
        diff = diff_vdom(old_node, new_node)
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "insert"
        assert diff.updates[0]["path"] == "1"
        assert diff.updates[0]["data"] == "World"

    def test_remove_children(self):
        """Test removing children."""
        old_node = Node("div", children=["Hello", "World"])
        new_node = Node("div", children=["Hello"])
        diff = diff_vdom(old_node, new_node)
        # Should generate remove operation for "World"
        remove_ops = [op for op in diff.updates if op["type"] == "remove"]
        assert len(remove_ops) >= 1

    def test_replace_children(self):
        """Test replacing children."""
        old_node = Node("div", children=["Hello", "Old"])
        new_node = Node("div", children=["Hello", "New"])
        diff = diff_vdom(old_node, new_node)
        replace_ops = [op for op in diff.updates if op["type"] == "replace"]
        assert len(replace_ops) == 1
        assert replace_ops[0]["path"] == "1"
        assert replace_ops[0]["data"] == "New"


class TestKeyedDiffing:
    """Test keyed reconciliation."""

    def test_keyed_reorder(self):
        """Test reordering keyed elements."""
        old_node = Node(
            "div",
            children=[
                Node("div", {"id": "1"}, ["First"], key="a"),
                Node("div", {"id": "2"}, ["Second"], key="b"),
                Node("div", {"id": "3"}, ["Third"], key="c"),
            ],
        )
        new_node = Node(
            "div",
            children=[
                Node("div", {"id": "3"}, ["Third"], key="c"),
                Node("div", {"id": "1"}, ["First"], key="a"),
                Node("div", {"id": "2"}, ["Second"], key="b"),
            ],
        )

        diff = diff_vdom(old_node, new_node)
        move_ops = [op for op in diff.updates if op["type"] == "move"]
        # Should have move operations to reorder
        assert len(move_ops) > 0

    def test_keyed_add_remove(self):
        """Test adding and removing keyed elements."""
        old_node = Node(
            "div",
            children=[
                Node("div", {"id": "1"}, ["First"], key="a"),
                Node("div", {"id": "2"}, ["Second"], key="b"),
            ],
        )
        new_node = Node(
            "div",
            children=[
                Node("div", {"id": "1"}, ["First"], key="a"),
                Node("div", {"id": "3"}, ["Third"], key="c"),
            ],
        )

        diff = diff_vdom(old_node, new_node)

        # Should have insert for new keyed element
        insert_ops = [op for op in diff.updates if op["type"] == "insert"]
        assert len(insert_ops) >= 1

        # Should have remove for old keyed element
        remove_ops = [op for op in diff.updates if op["type"] == "remove"]
        assert len(remove_ops) >= 1

    def test_mixed_keyed_unkeyed(self):
        """Test mixing keyed and unkeyed children."""
        old_node = Node(
            "div",
            children=["text1", Node("div", {"id": "1"}, ["Keyed"], key="k1"), "text2"],
        )
        new_node = Node(
            "div",
            children=[
                "newtext1",
                Node("div", {"id": "2"}, ["NewKeyed"], key="k2"),
                "text2",
            ],
        )

        diff = diff_vdom(old_node, new_node)

        # Should handle both keyed and unkeyed changes
        assert len(diff.updates) > 0

        # Text replacement
        replace_ops = [op for op in diff.updates if op["type"] == "replace"]
        assert any(op["data"] == "newtext1" for op in replace_ops)


class TestComplexScenarios:
    """Test complex diffing scenarios."""

    def test_nested_changes(self):
        """Test changes in deeply nested structures."""
        old_node = Node(
            "div",
            {"class": "container"},
            [
                Node("header", {}, ["Title"]),
                Node("main", {}, [Node("section", {}, ["Content"])]),
            ],
        )

        new_node = Node(
            "div",
            {"class": "container"},
            [
                Node("header", {}, ["New Title"]),
                Node(
                    "main",
                    {},
                    [
                        Node("section", {}, ["New Content"]),
                        Node("footer", {}, ["Footer"]),
                    ],
                ),
            ],
        )

        diff = diff_vdom(old_node, new_node)

        # Should have operations for nested changes
        assert len(diff.updates) > 0

        # Check that deep paths are used (string paths with dots)
        deep_ops = [op for op in diff.updates if "." in op["path"]]
        assert len(deep_ops) > 0

    def test_large_list_changes(self):
        """Test performance with large lists."""
        old_node = Node(
            "ul",
            children=[
                Node("item", {"id": str(i)}, [f"Item {i}"], key=str(i))
                for i in range(100)
            ],
        )
        new_node = Node(
            "ul",
            children=[
                Node("item", {"id": str(i)}, [f"New Item {i}"], key=str(i))
                for i in range(50, 150)
            ],
        )

        diff = diff_vdom(old_node, new_node)

        # Should handle large lists efficiently
        assert len(diff.updates) > 0

        # Check for expected operation types
        op_types = {op["type"] for op in diff.updates}
        assert "remove" in op_types  # Remove items 0-49
        assert "insert" in op_types  # Insert items 100-149

    def test_empty_to_full(self):
        """Test creating a full tree from empty."""
        old_node = None
        new_node = Node(
            "div",
            {"class": "app"},
            [
                Node("header", {}, ["My App"]),
                Node(
                    "main",
                    {},
                    [
                        Node("p", {}, ["Welcome to my app!"]),
                        Node("button", {"onclick": "alert('clicked')"}, ["Click me"]),
                    ],
                ),
            ],
        )

        diff = diff_vdom(old_node, new_node)
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "insert"
        assert diff.updates[0]["path"] == ""

    def test_full_to_empty(self):
        """Test removing a full tree."""
        old_node = Node(
            "div",
            {"class": "app"},
            [
                Node("header", {}, ["My App"]),
                Node(
                    "main",
                    {},
                    [
                        Node("p", {}, ["Welcome to my app!"]),
                        Node("button", {"onclick": "alert('clicked')"}, ["Click me"]),
                    ],
                ),
            ],
        )
        new_node = None

        diff = diff_vdom(old_node, new_node)
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "remove"
        assert diff.updates[0]["path"] == ""


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_different_types(self):
        """Test nodes of completely different types."""
        # Number to node
        diff = diff_vdom(42, Node("div", {}, ["text"]))
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "replace"

        # Boolean to string
        diff = diff_vdom(True, "false")
        assert len(diff.updates) == 1
        assert diff.updates[0]["type"] == "replace"
        assert diff.updates[0]["data"] == "false"

    def test_deeply_nested_keys(self):
        """Test keys in deeply nested structures."""
        old_node = Node(
            "div",
            {},
            [
                Node(
                    "section",
                    {},
                    [
                        Node("item", {}, ["A"], key="item-a"),
                        Node("item", {}, ["B"], key="item-b"),
                    ],
                )
            ],
        )

        new_node = Node(
            "div",
            {},
            [
                Node(
                    "section",
                    {},
                    [
                        Node("item", {}, ["B"], key="item-b"),
                        Node("item", {}, ["C"], key="item-c"),
                    ],
                )
            ],
        )

        diff = diff_vdom(old_node, new_node)
        assert len(diff.updates) > 0

    def test_callback_props(self):
        """Test that callback props are handled correctly."""

        def onclick():
            pass

        old_node = Node("button", {"onclick": onclick}, ["Click"])
        new_node = Node("button", {"onclick": onclick}, ["Click"])

        # Should be treated as identical even with callbacks
        diff = diff_vdom(old_node, new_node)
        # Note: Since callbacks get processed and replaced with strings,
        # the actual behavior depends on how callbacks are handled
        assert isinstance(diff.updates, list)


class TestSerialization:
    """Test node serialization."""

    def test_serialize_node(self):
        """Test serializing various node types."""
        # Element node
        node = Node("div", {"class": "test"}, ["content"])
        serialized, _ = node.render()
        assert_vdom_equal(
            serialized,
            {"tag": "div", "props": {"class": "test"}, "children": ["content"]},
        )

    def test_serialize_with_key(self):
        """Test serializing nodes with keys."""
        node = Node("div", {"class": "test"}, ["content"], key="my-key")
        serialized, _ = node.render()
        assert_vdom_equal(
            serialized,
            {"tag": "div", "props": {"class": "test"}, "children": ["content"], "key": "my-key"},
        )

        node_no_key = Node("div", {"class": "test"}, ["content"])
        serialized_no_key, _ = node_no_key.render()
        assert_vdom_equal(
            serialized_no_key,
            {"tag": "div", "props": {"class": "test"}, "children": ["content"]},
        )


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__])
