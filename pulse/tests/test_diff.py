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
from pulse.vdom import VDOMNode
from pulse.tests.test_utils import assert_vdom_equal


class TestBasicDiffing:
    """Test basic diffing operations."""

    def test_null_cases(self):
        """Test diffing with None values."""
        # Both None
        ops = diff_vdom(None, None)
        assert ops == []

        # Insert from None
        new_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "test"},
            "children": ["Hello"],
        }
        ops = diff_vdom(None, new_vdom)
        assert len(ops) == 1
        assert ops[0] == {"type": "insert", "path": "", "data": new_vdom}

        # Remove to None
        old_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "test"},
            "children": ["Hello"],
        }
        ops = diff_vdom(old_vdom, None)
        assert len(ops) == 1
        assert ops[0] == {"type": "remove", "path": "", "data": None}

    def test_identical_nodes(self):
        """Test that identical nodes produce no operations."""
        vdom1: VDOMNode = {
            "tag": "div",
            "props": {"class": "test"},
            "children": ["Hello"],
        }
        vdom2: VDOMNode = {
            "tag": "div",
            "props": {"class": "test"},
            "children": ["Hello"],
        }
        ops = diff_vdom(vdom1, vdom2)
        assert ops == []

    def test_text_node_changes(self):
        """Test diffing text nodes."""
        # Same text
        ops = diff_vdom("hello", "hello")
        assert ops == []

        # Changed text
        ops = diff_vdom("hello", "world")
        assert len(ops) == 1
        assert ops[0] == {"type": "replace", "path": "", "data": "world"}

        # Text to element
        new_vdom: VDOMNode = {"tag": "span", "children": ["world"]}
        ops = diff_vdom("hello", new_vdom)
        assert len(ops) == 1
        assert ops[0]["type"] == "replace"
        assert_vdom_equal(ops[0]["data"], new_vdom)

    def test_tag_changes(self):
        """Test nodes with different tags get replaced."""
        old_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "test"},
            "children": ["Hello"],
        }
        new_vdom: VDOMNode = {
            "tag": "span",
            "props": {"class": "test"},
            "children": ["Hello"],
        }
        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) == 1
        assert ops[0]["type"] == "replace"
        assert_vdom_equal(ops[0]["data"], new_vdom)


class TestPropertyDiffing:
    """Test property diffing functionality."""

    def test_no_prop_changes(self):
        """Test when properties are identical."""
        old_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "test", "id": "main"},
        }
        new_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "test", "id": "main"},
        }
        ops = diff_vdom(old_vdom, new_vdom)
        assert ops == []

    def test_prop_changes(self):
        """Test when properties change."""
        old_vdom: VDOMNode = {"tag": "div", "props": {"class": "old", "id": "main"}}
        new_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "new", "data-value": "123"},
        }
        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) == 1
        assert ops[0]["type"] == "update_props"
        assert ops[0]["data"] == {"class": "new", "data-value": "123"}


class TestChildrenDiffing:
    """Test children diffing with and without keys."""

    def test_no_children_changes(self):
        """Test when children are identical."""
        old_vdom: VDOMNode = {"tag": "div", "children": ["Hello", "World"]}
        new_vdom: VDOMNode = {"tag": "div", "children": ["Hello", "World"]}
        ops = diff_vdom(old_vdom, new_vdom)
        assert ops == []

    def test_append_children(self):
        """Test appending new children."""
        old_vdom: VDOMNode = {"tag": "div", "children": ["Hello"]}
        new_vdom: VDOMNode = {"tag": "div", "children": ["Hello", "World"]}
        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) == 1
        assert ops[0] == {"type": "insert", "path": "1", "data": "World"}

    def test_remove_children(self):
        """Test removing children."""
        old_vdom: VDOMNode = {"tag": "div", "children": ["Hello", "World"]}
        new_vdom: VDOMNode = {"tag": "div", "children": ["Hello"]}
        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) == 1
        assert ops[0] == {"type": "remove", "path": "1", "data": None}

    def test_replace_children(self):
        """Test replacing children."""
        old_vdom: VDOMNode = {"tag": "div", "children": ["Hello", "Old"]}
        new_vdom: VDOMNode = {"tag": "div", "children": ["Hello", "New"]}
        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) == 1
        assert ops[0] == {"type": "replace", "path": "1", "data": "New"}


class TestKeyedDiffing:
    """Test keyed reconciliation."""

    def test_keyed_reorder(self):
        """Test reordering keyed elements."""
        old_vdom: VDOMNode = {
            "tag": "div",
            "children": [
                {"tag": "div", "props": {"id": "1"}, "children": ["First"], "key": "a"},
                {
                    "tag": "div",
                    "props": {"id": "2"},
                    "children": ["Second"],
                    "key": "b",
                },
                {"tag": "div", "props": {"id": "3"}, "children": ["Third"], "key": "c"},
            ],
        }
        new_vdom: VDOMNode = {
            "tag": "div",
            "children": [
                {"tag": "div", "props": {"id": "3"}, "children": ["Third"], "key": "c"},
                {"tag": "div", "props": {"id": "1"}, "children": ["First"], "key": "a"},
                {
                    "tag": "div",
                    "props": {"id": "2"},
                    "children": ["Second"],
                    "key": "b",
                },
            ],
        }

        ops = diff_vdom(old_vdom, new_vdom)
        move_ops = [op for op in ops if op["type"] == "move"]
        assert len(move_ops) > 0

    def test_keyed_add_remove(self):
        """Test adding and removing keyed elements."""
        old_vdom: VDOMNode = {
            "tag": "div",
            "children": [
                {"tag": "div", "props": {"id": "1"}, "children": ["First"], "key": "a"},
                {
                    "tag": "div",
                    "props": {"id": "2"},
                    "children": ["Second"],
                    "key": "b",
                },
            ],
        }
        new_vdom: VDOMNode = {
            "tag": "div",
            "children": [
                {"tag": "div", "props": {"id": "1"}, "children": ["First"], "key": "a"},
                {"tag": "div", "props": {"id": "3"}, "children": ["Third"], "key": "c"},
            ],
        }

        ops = diff_vdom(old_vdom, new_vdom)
        insert_ops = [op for op in ops if op["type"] == "insert"]
        assert len(insert_ops) >= 1
        remove_ops = [op for op in ops if op["type"] == "remove"]
        assert len(remove_ops) >= 1

    def test_mixed_keyed_unkeyed(self):
        """Test mixing keyed and unkeyed children."""
        old_vdom: VDOMNode = {
            "tag": "div",
            "children": [
                "text1",
                {
                    "tag": "div",
                    "props": {"id": "1"},
                    "children": ["Keyed"],
                    "key": "k1",
                },
                "text2",
            ],
        }
        new_vdom: VDOMNode = {
            "tag": "div",
            "children": [
                "newtext1",
                {
                    "tag": "div",
                    "props": {"id": "2"},
                    "children": ["NewKeyed"],
                    "key": "k2",
                },
                "text2",
            ],
        }

        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) > 0
        replace_ops = [op for op in ops if op["type"] == "replace"]
        assert any(op["data"] == "newtext1" for op in replace_ops)


class TestComplexScenarios:
    """Test complex diffing scenarios."""

    def test_nested_changes(self):
        """Test changes in deeply nested structures."""
        old_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "container"},
            "children": [
                {"tag": "header", "children": ["Title"]},
                {
                    "tag": "main",
                    "children": [{"tag": "section", "children": ["Content"]}],
                },
            ],
        }
        new_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "container"},
            "children": [
                {"tag": "header", "children": ["New Title"]},
                {
                    "tag": "main",
                    "children": [
                        {"tag": "section", "children": ["New Content"]},
                        {"tag": "footer", "children": ["Footer"]},
                    ],
                },
            ],
        }

        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) > 0
        deep_ops = [op for op in ops if "." in op["path"]]
        assert len(deep_ops) > 0

    def test_large_list_changes(self):
        """Test performance with large lists."""
        old_vdom: VDOMNode = {
            "tag": "ul",
            "children": [
                {
                    "tag": "item",
                    "props": {"id": str(i)},
                    "children": [f"Item {i}"],
                    "key": str(i),
                }
                for i in range(100)
            ],
        }
        new_vdom: VDOMNode = {
            "tag": "ul",
            "children": [
                {
                    "tag": "item",
                    "props": {"id": str(i)},
                    "children": [f"New Item {i}"],
                    "key": str(i),
                }
                for i in range(50, 150)
            ],
        }

        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) > 0
        op_types = {op["type"] for op in ops}
        assert "remove" in op_types
        assert "insert" in op_types

    def test_empty_to_full(self):
        """Test creating a full tree from empty."""
        old_vdom = None
        new_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "app"},
            "children": [
                {"tag": "header", "children": ["My App"]},
                {
                    "tag": "main",
                    "children": [
                        {"tag": "p", "children": ["Welcome to my app!"]},
                        {
                            "tag": "button",
                            "props": {"onclick": "alert('clicked')"},
                            "children": ["Click me"],
                        },
                    ],
                },
            ],
        }

        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) == 1
        assert ops[0]["type"] == "insert"
        assert ops[0]["path"] == ""

    def test_full_to_empty(self):
        """Test removing a full tree."""
        old_vdom: VDOMNode = {
            "tag": "div",
            "props": {"class": "app"},
            "children": [
                {"tag": "header", "children": ["My App"]},
                {
                    "tag": "main",
                    "children": [
                        {"tag": "p", "children": ["Welcome to my app!"]},
                        {
                            "tag": "button",
                            "props": {"onclick": "alert('clicked')"},
                            "children": ["Click me"],
                        },
                    ],
                },
            ],
        }
        new_vdom = None

        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) == 1
        assert ops[0]["type"] == "remove"
        assert ops[0]["path"] == ""

    def test_different_types(self):
        """Test nodes of completely different types."""
        ops = diff_vdom(42, {"tag": "div", "children": ["text"]})
        assert len(ops) == 1
        assert ops[0]["type"] == "replace"

        ops = diff_vdom(True, "false")
        assert len(ops) == 1
        assert ops[0] == {"type": "replace", "path": "", "data": "false"}

    def test_deeply_nested_keys(self):
        """Test keys in deeply nested structures."""
        old_vdom: VDOMNode = {
            "tag": "div",
            "children": [
                {
                    "tag": "section",
                    "children": [
                        {"tag": "item", "children": ["A"], "key": "item-a"},
                        {"tag": "item", "children": ["B"], "key": "item-b"},
                    ],
                }
            ],
        }
        new_vdom: VDOMNode = {
            "tag": "div",
            "children": [
                {
                    "tag": "section",
                    "children": [
                        {"tag": "item", "children": ["B"], "key": "item-b"},
                        {"tag": "item", "children": ["C"], "key": "item-c"},
                    ],
                }
            ],
        }

        ops = diff_vdom(old_vdom, new_vdom)
        assert len(ops) > 0


if __name__ == "__main__":
    pytest.main([__file__])
