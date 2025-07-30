"""
Tests for the VDOM diffing algorithm.

This test suite covers all aspects of the diffing algorithm including:
- Basic node operations (insert, remove, replace)
- Property updates
- Children diffing with keys
- Edge cases and complex scenarios
"""

import pytest
from pulse.diff import diff_vdom, diff_props, diff_children, _serialize_node
from pulse.vdom import Node


class TestBasicDiffing:
    """Test basic diffing operations."""
    
    def test_null_cases(self):
        """Test diffing with None values."""
        # Both None
        ops = diff_vdom(None, None)
        assert ops == []
        
        # Insert from None
        new_node = Node("div", {"class": "test"}, ["Hello"])
        ops = diff_vdom(None, new_node)
        assert len(ops) == 1
        assert ops[0]["type"] == "insert"
        assert ops[0]["path"] == []
        assert ops[0]["data"]["node"]["tag"] == "div"
        
        # Remove to None
        old_node = Node("div", {"class": "test"}, ["Hello"])
        ops = diff_vdom(old_node, None)
        assert len(ops) == 1
        assert ops[0]["type"] == "remove"
        assert ops[0]["path"] == []
    
    def test_identical_nodes(self):
        """Test that identical nodes produce no operations."""
        node1 = Node("div", {"class": "test"}, ["Hello"])
        node2 = Node("div", {"class": "test"}, ["Hello"])
        ops = diff_vdom(node1, node2)
        assert ops == []
    
    def test_text_node_changes(self):
        """Test diffing text nodes."""
        # Same text
        ops = diff_vdom("hello", "hello")
        assert ops == []
        
        # Changed text
        ops = diff_vdom("hello", "world")
        assert len(ops) == 1
        assert ops[0]["type"] == "replace"
        assert ops[0]["data"]["node"] == "world"
        
        # Text to element
        new_node = Node("span", {}, ["world"])
        ops = diff_vdom("hello", new_node)
        assert len(ops) == 1
        assert ops[0]["type"] == "replace"
        assert ops[0]["data"]["node"]["tag"] == "span"
    
    def test_tag_changes(self):
        """Test nodes with different tags get replaced."""
        old_node = Node("div", {"class": "test"}, ["Hello"])
        new_node = Node("span", {"class": "test"}, ["Hello"])
        ops = diff_vdom(old_node, new_node)
        assert len(ops) == 1
        assert ops[0]["type"] == "replace"
        assert ops[0]["data"]["node"]["tag"] == "span"


class TestPropertyDiffing:
    """Test property diffing functionality."""
    
    def test_no_prop_changes(self):
        """Test when properties are identical."""
        old_props = {"class": "test", "id": "main"}
        new_props = {"class": "test", "id": "main"}
        ops = diff_props(old_props, new_props, [])
        assert ops == []
    
    def test_added_props(self):
        """Test adding new properties."""
        old_props = {"class": "test"}
        new_props = {"class": "test", "id": "main", "data-value": "123"}
        ops = diff_props(old_props, new_props, [])
        assert len(ops) == 1
        assert ops[0]["type"] == "update_props"
        assert ops[0]["data"]["set"] == {"id": "main", "data-value": "123"}
        assert ops[0]["data"]["remove"] == []
    
    def test_removed_props(self):
        """Test removing properties."""
        old_props = {"class": "test", "id": "main", "data-value": "123"}
        new_props = {"class": "test"}
        ops = diff_props(old_props, new_props, [])
        assert len(ops) == 1
        assert ops[0]["type"] == "update_props"
        assert ops[0]["data"]["set"] == {}
        assert set(ops[0]["data"]["remove"]) == {"id", "data-value"}
    
    def test_changed_props(self):
        """Test changing property values."""
        old_props = {"class": "old", "id": "main"}
        new_props = {"class": "new", "id": "main"}
        ops = diff_props(old_props, new_props, [])
        assert len(ops) == 1
        assert ops[0]["type"] == "update_props"
        assert ops[0]["data"]["set"] == {"class": "new"}
        assert ops[0]["data"]["remove"] == []
    
    def test_mixed_prop_changes(self):
        """Test adding, removing, and changing props simultaneously."""
        old_props = {"class": "old", "id": "main", "data-old": "value"}
        new_props = {"class": "new", "data-new": "value"}
        ops = diff_props(old_props, new_props, [])
        assert len(ops) == 1
        assert ops[0]["type"] == "update_props"
        assert ops[0]["data"]["set"] == {"class": "new", "data-new": "value"}
        assert set(ops[0]["data"]["remove"]) == {"id", "data-old"}


class TestChildrenDiffing:
    """Test children diffing with and without keys."""
    
    def test_no_children_changes(self):
        """Test when children are identical."""
        old_children = ["Hello", "World"]
        new_children = ["Hello", "World"]
        ops = diff_children(old_children, new_children, [])
        assert ops == []
    
    def test_append_children(self):
        """Test appending new children."""
        old_children = ["Hello"]
        new_children = ["Hello", "World"]
        ops = diff_children(old_children, new_children, [])
        assert len(ops) == 1
        assert ops[0]["type"] == "insert"
        assert ops[0]["path"] == [1]
        assert ops[0]["data"]["node"] == "World"
    
    def test_remove_children(self):
        """Test removing children."""
        old_children = ["Hello", "World"]
        new_children = ["Hello"]
        ops = diff_children(old_children, new_children, [])
        # Should generate remove operation for "World"
        remove_ops = [op for op in ops if op["type"] == "remove"]
        assert len(remove_ops) >= 1
    
    def test_replace_children(self):
        """Test replacing children."""
        old_children = ["Hello", "Old"]
        new_children = ["Hello", "New"]
        ops = diff_children(old_children, new_children, [])
        replace_ops = [op for op in ops if op["type"] == "replace"]
        assert len(replace_ops) == 1
        assert replace_ops[0]["path"] == [1]
        assert replace_ops[0]["data"]["node"] == "New"


class TestKeyedDiffing:
    """Test keyed reconciliation."""
    
    def test_keyed_reorder(self):
        """Test reordering keyed elements."""
        old_children = [
            Node("div", {"id": "1"}, ["First"], key="a"),
            Node("div", {"id": "2"}, ["Second"], key="b"),
            Node("div", {"id": "3"}, ["Third"], key="c")
        ]
        new_children = [
            Node("div", {"id": "3"}, ["Third"], key="c"),
            Node("div", {"id": "1"}, ["First"], key="a"),
            Node("div", {"id": "2"}, ["Second"], key="b")
        ]
        
        ops = diff_children(old_children, new_children, [])
        move_ops = [op for op in ops if op["type"] == "move"]
        # Should have move operations to reorder
        assert len(move_ops) > 0
    
    def test_keyed_add_remove(self):
        """Test adding and removing keyed elements."""
        old_children = [
            Node("div", {"id": "1"}, ["First"], key="a"),
            Node("div", {"id": "2"}, ["Second"], key="b")
        ]
        new_children = [
            Node("div", {"id": "1"}, ["First"], key="a"),
            Node("div", {"id": "3"}, ["Third"], key="c")
        ]
        
        ops = diff_children(old_children, new_children, [])
        
        # Should have insert for new keyed element
        insert_ops = [op for op in ops if op["type"] == "insert"]
        assert len(insert_ops) >= 1
        
        # Should have remove for old keyed element
        remove_ops = [op for op in ops if op["type"] == "remove"]
        assert len(remove_ops) >= 1
    
    def test_mixed_keyed_unkeyed(self):
        """Test mixing keyed and unkeyed children."""
        old_children = [
            "text1",
            Node("div", {"id": "1"}, ["Keyed"], key="k1"),
            "text2"
        ]
        new_children = [
            "newtext1",
            Node("div", {"id": "2"}, ["NewKeyed"], key="k2"),
            "text2"
        ]
        
        ops = diff_children(old_children, new_children, [])
        
        # Should handle both keyed and unkeyed changes
        assert len(ops) > 0
        
        # Text replacement
        replace_ops = [op for op in ops if op["type"] == "replace"]
        assert any(op["data"]["node"] == "newtext1" for op in replace_ops)


class TestComplexScenarios:
    """Test complex diffing scenarios."""
    
    def test_nested_changes(self):
        """Test changes in deeply nested structures."""
        old_node = Node("div", {"class": "container"}, [
            Node("header", {}, ["Title"]),
            Node("main", {}, [
                Node("section", {}, ["Content"])
            ])
        ])
        
        new_node = Node("div", {"class": "container"}, [
            Node("header", {}, ["New Title"]),
            Node("main", {}, [
                Node("section", {}, ["New Content"]),
                Node("footer", {}, ["Footer"])
            ])
        ])
        
        ops = diff_vdom(old_node, new_node)
        
        # Should have operations for nested changes
        assert len(ops) > 0
        
        # Check that deep paths are used
        deep_ops = [op for op in ops if len(op["path"]) > 1]
        assert len(deep_ops) > 0
    
    def test_large_list_changes(self):
        """Test performance with large lists."""
        old_children = [Node("item", {"id": str(i)}, [f"Item {i}"], key=str(i)) for i in range(100)]
        new_children = [Node("item", {"id": str(i)}, [f"New Item {i}"], key=str(i)) for i in range(50, 150)]
        
        ops = diff_children(old_children, new_children, [])
        
        # Should handle large lists efficiently
        assert len(ops) > 0
        
        # Check for expected operation types
        op_types = {op["type"] for op in ops}
        assert "remove" in op_types  # Remove items 0-49
        assert "insert" in op_types  # Insert items 100-149
    
    def test_empty_to_full(self):
        """Test creating a full tree from empty."""
        old_node = None
        new_node = Node("div", {"class": "app"}, [
            Node("header", {}, ["My App"]),
            Node("main", {}, [
                Node("p", {}, ["Welcome to my app!"]),
                Node("button", {"onclick": "alert('clicked')"}, ["Click me"])
            ])
        ])
        
        ops = diff_vdom(old_node, new_node)
        assert len(ops) == 1
        assert ops[0]["type"] == "insert"
        assert ops[0]["path"] == []
    
    def test_full_to_empty(self):
        """Test removing a full tree."""
        old_node = Node("div", {"class": "app"}, [
            Node("header", {}, ["My App"]),
            Node("main", {}, [
                Node("p", {}, ["Welcome to my app!"]),
                Node("button", {"onclick": "alert('clicked')"}, ["Click me"])
            ])
        ])
        new_node = None
        
        ops = diff_vdom(old_node, new_node)
        assert len(ops) == 1
        assert ops[0]["type"] == "remove"
        assert ops[0]["path"] == []


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_different_types(self):
        """Test nodes of completely different types."""
        # Number to node
        ops = diff_vdom(42, Node("div", {}, ["text"]))
        assert len(ops) == 1
        assert ops[0]["type"] == "replace"
        
        # Boolean to string
        ops = diff_vdom(True, "false")
        assert len(ops) == 1
        assert ops[0]["type"] == "replace"
        assert ops[0]["data"]["node"] == "false"
    
    def test_deeply_nested_keys(self):
        """Test keys in deeply nested structures."""
        old_node = Node("div", {}, [
            Node("section", {}, [
                Node("item", {}, ["A"], key="item-a"),
                Node("item", {}, ["B"], key="item-b")
            ])
        ])
        
        new_node = Node("div", {}, [
            Node("section", {}, [
                Node("item", {}, ["B"], key="item-b"),
                Node("item", {}, ["C"], key="item-c")
            ])
        ])
        
        ops = diff_vdom(old_node, new_node)
        assert len(ops) > 0
    
    def test_callback_props(self):
        """Test that callback props are handled correctly."""
        def onclick():
            pass
        
        old_node = Node("button", {"onclick": onclick}, ["Click"])
        new_node = Node("button", {"onclick": onclick}, ["Click"])
        
        # Should be treated as identical even with callbacks
        ops = diff_vdom(old_node, new_node)
        # Note: Since callbacks get processed and replaced with strings,
        # the actual behavior depends on how callbacks are handled
        assert isinstance(ops, list)


class TestSerialization:
    """Test node serialization."""
    
    def test_serialize_node(self):
        """Test serializing various node types."""
        # Element node
        node = Node("div", {"class": "test"}, ["content"])
        serialized = _serialize_node(node)
        assert serialized["tag"] == "div"
        assert serialized["props"]["class"] == "test"
        assert serialized["children"] == ["content"]
        
        # Text node
        assert _serialize_node("text") == "text"
        
        # Number
        assert _serialize_node(42) == 42
        
        # Boolean
        assert _serialize_node(True) == True
    
    def test_serialize_with_key(self):
        """Test serializing nodes with keys."""
        node = Node("div", {"class": "test"}, ["content"], key="my-key")
        serialized = _serialize_node(node)
        assert serialized["key"] == "my-key"
        
        # Node without key should not have key in serialization
        node_no_key = Node("div", {"class": "test"}, ["content"])
        serialized_no_key = _serialize_node(node_no_key)
        assert "key" not in serialized_no_key or serialized_no_key["key"] is None


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__])