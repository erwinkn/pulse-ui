"""
Tests for the pulse.html module's UI tree generation system.

This module tests the direct UI tree node generation that matches
the TypeScript UIElementNode format.
"""

import pytest
from pulse.nodes import (
    UITreeNode,
    div, p, span, h1, h2, h3, button, a, img, br, hr, meta,
    strong, em, ul, li, script, style, form, input, label,
    define_tag, define_self_closing_tag
)


class TestUITreeNode:
    """Test the core UITreeNode functionality."""
    
    def test_basic_node_creation(self):
        """Test creating basic UI tree nodes."""
        node = UITreeNode("div")
        assert node.tag == "div"
        assert node.props == {}
        assert node.children == []
        assert node.id.startswith("py_")
        
    def test_node_with_props(self):
        """Test creating nodes with props."""
        node = UITreeNode("div", {"className": "container", "id": "main"})
        assert node.tag == "div"
        assert node.props == {"className": "container", "id": "main"}
        assert node.children == []
        
    def test_node_with_children(self):
        """Test creating nodes with children."""
        child1 = UITreeNode("p")
        child2 = "text content"
        node = UITreeNode("div", children=[child1, child2])
        
        assert node.tag == "div"
        assert len(node.children) == 2
        assert node.children[0] == child1
        assert node.children[1] == "text content"
        
    def test_node_to_dict(self):
        """Test converting nodes to dictionary format."""
        child = UITreeNode("p", {"className": "text"}, ["Hello"])
        node = UITreeNode("div", {"id": "container"}, [child, "world"])
        
        result = node.to_dict()
        expected = {
            "id": node.id,
            "tag": "div", 
            "props": {"id": "container"},
            "children": [
                {
                    "id": child.id,
                    "tag": "p",
                    "props": {"className": "text"},
                    "children": ["Hello"]
                },
                "world"
            ]
        }
        
        assert result == expected
        
    def test_indexing_syntax(self):
        """Test the indexing syntax for adding children."""
        node = UITreeNode("div")
        
        # Single child
        result = node["Hello world"]
        assert result.children == ["Hello world"]
        assert result.tag == "div"
        
        # Multiple children
        child1 = UITreeNode("p")
        result = node[child1, "text"]
        assert len(result.children) == 2
        assert result.children[0] == child1
        assert result.children[1] == "text"
        
    def test_indexing_with_existing_children_fails(self):
        """Test that indexing fails when children already exist."""
        node = UITreeNode("div", children=["existing"])
        
        with pytest.raises(ValueError, match="Node already has children"):
            node["new child"]


class TestHTMLTags:
    """Test the HTML tag generation functions."""
    
    def test_basic_tags(self):
        """Test basic tag creation."""
        node = div()
        assert node.tag == "div"
        assert node.props == {}
        assert node.children == []
        
        node = p()
        assert node.tag == "p"
        
        node = span()
        assert node.tag == "span"
        
    def test_tags_with_props(self):
        """Test tags with props/attributes."""
        node = div(className="container", id="main")
        assert node.tag == "div"
        assert node.props == {"className": "container", "id": "main"}
        
        node = a(href="https://example.com", target="_blank")
        assert node.tag == "a"
        assert node.props == {"href": "https://example.com", "target": "_blank"}
        
    def test_tags_with_children(self):
        """Test tags with children passed as arguments."""
        text_child = "Hello world"
        element_child = span()
        
        node = div(text_child, element_child, className="container")
        
        assert node.tag == "div"
        assert node.props == {"className": "container"}
        assert len(node.children) == 2
        assert node.children[0] == text_child
        assert node.children[1] == element_child
        
    def test_indexing_syntax_with_tags(self):
        """Test using indexing syntax with HTML tags."""
        # Simple indexing
        node = div()["Hello world"]
        assert node.tag == "div"
        assert node.children == ["Hello world"]
        
        # Multiple children with indexing
        child_p = p()["Paragraph text"]
        node = div(className="container")[child_p, "Additional text"]
        
        assert node.tag == "div"
        assert node.props == {"className": "container"}
        assert len(node.children) == 2
        assert node.children[0] == child_p
        assert node.children[1] == "Additional text"
        
    def test_nested_structure(self):
        """Test creating nested HTML structures."""
        structure = div(className="page")[
            h1()["Page Title"],
            div(className="content")[
                p()["First paragraph"],
                p()["Second paragraph with ", strong()["bold text"], " inside."]
            ]
        ]
        
        result = structure.to_dict()
        
        # Verify structure
        assert result["tag"] == "div"
        assert result["props"] == {"className": "page"}
        assert len(result["children"]) == 2
        
        # Check h1
        h1_child = result["children"][0]
        assert h1_child["tag"] == "h1"
        assert h1_child["children"] == ["Page Title"]
        
        # Check content div
        content_div = result["children"][1]
        assert content_div["tag"] == "div"
        assert content_div["props"] == {"className": "content"}
        assert len(content_div["children"]) == 2
        
    def test_self_closing_tags(self):
        """Test self-closing tags."""
        node = br()
        assert node.tag == "br"
        assert node.children == []
        
        node = hr()
        assert node.tag == "hr"
        assert node.children == []
        
        node = img(src="/image.jpg", alt="Description")
        assert node.tag == "img"
        assert node.props == {"src": "/image.jpg", "alt": "Description"}
        assert node.children == []
        
    def test_default_props(self):
        """Test tags with default props."""
        node = script()
        assert node.tag == "script"
        assert node.props == {"type": "text/javascript"}
        
        node = style()
        assert node.tag == "style"
        assert node.props == {"type": "text/css"}
        
        node = form()
        assert node.tag == "form"
        assert node.props == {"method": "POST"}
        
    def test_prop_merging(self):
        """Test that custom props merge with default props."""
        node = script(src="/app.js")
        assert node.props == {"type": "text/javascript", "src": "/app.js"}
        
        # Custom props should override defaults
        node = form(method="GET", action="/search")
        assert node.props == {"method": "GET", "action": "/search"}


class TestTagDefinition:
    """Test the tag definition functions."""
    
    def test_define_tag(self):
        """Test defining custom tags."""
        custom_tag = define_tag("custom")
        
        node = custom_tag()
        assert node.tag == "custom"
        assert node.props == {}
        assert node.children == []
        
        node = custom_tag(prop1="value1")["Child content"]
        assert node.tag == "custom"
        assert node.props == {"prop1": "value1"}
        assert node.children == ["Child content"]
        
    def test_define_tag_with_defaults(self):
        """Test defining tags with default props."""
        custom_tag = define_tag("custom", {"defaultProp": "defaultValue"})
        
        node = custom_tag()
        assert node.tag == "custom"
        assert node.props == {"defaultProp": "defaultValue"}
        
        node = custom_tag(customProp="customValue")
        expected_props = {"defaultProp": "defaultValue", "customProp": "customValue"}  
        assert node.props == expected_props
        
    def test_define_self_closing_tag(self):
        """Test defining self-closing tags."""
        self_closing = define_self_closing_tag("void-element")
        
        node = self_closing()
        assert node.tag == "void-element"
        assert node.props == {}
        assert node.children == []
        
        node = self_closing(prop="value")
        assert node.tag == "void-element"
        assert node.props == {"prop": "value"}
        assert node.children == []


class TestComplexStructures:
    """Test complex UI tree structures."""
    
    def test_list_structure(self):
        """Test creating list structures."""
        items = ["Item 1", "Item 2", "Item 3"]
        list_structure = ul(className="list")[
            *[li()[item] for item in items]
        ]
        
        result = list_structure.to_dict()
        
        assert result["tag"] == "ul"
        assert result["props"] == {"className": "list"}
        assert len(result["children"]) == 3
        
        for i, child in enumerate(result["children"]):
            assert child["tag"] == "li"
            assert child["children"] == [items[i]]
            
    def test_form_structure(self):
        """Test creating form structures."""
        form_structure = form(action="/submit", method="POST")[
            div(className="form-group")[
                label(htmlFor="name")["Name:"],
                input(type="text", id="name", name="name", required=True)
            ],
            div(className="form-group")[
                label(htmlFor="email")["Email:"],
                input(type="email", id="email", name="email", required=True)
            ],
            button(type="submit")["Submit"]
        ]
        
        result = form_structure.to_dict()
        
        assert result["tag"] == "form"
        assert result["props"] == {"action": "/submit", "method": "POST"}
        assert len(result["children"]) == 3  # 2 form groups + button
        
    def test_mixed_content_types(self):
        """Test mixing different content types."""
        mixed_content = div(
            "Plain text",
            p("Paragraph text"),
            123,  # Number
            True,  # Boolean 
            span()["More text"]
        )
        
        result = mixed_content.to_dict()
        
        assert result["tag"] == "div"
        assert len(result["children"]) == 5
        assert result["children"][0] == "Plain text"
        assert result["children"][1]["tag"] == "p"
        assert result["children"][2] == 123
        assert result["children"][3] == True
        assert result["children"][4]["tag"] == "span"


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_structures(self):
        """Test empty structures."""
        node = div()
        result = node.to_dict()
        
        assert result["tag"] == "div"
        assert result["props"] == {}
        assert result["children"] == []
        
    def test_deeply_nested_structure(self):
        """Test deeply nested structures."""
        deep_structure = div()[
            div()[
                div()[
                    div()[
                        div()["Deep content"]
                    ]
                ]
            ]
        ]
        
        result = deep_structure.to_dict()
        
        # Navigate down the nesting
        current = result
        for _ in range(4):  # 4 levels of div nesting
            assert current["tag"] == "div"
            assert len(current["children"]) == 1
            current = current["children"][0]
            
        # Final level should have text content
        assert current["tag"] == "div" 
        assert current["children"] == ["Deep content"]
        
    def test_none_handling(self):
        """Test handling of None values."""
        # None props should become empty dict
        node = UITreeNode("div", None)
        assert node.props == {}
        
        # None children should become empty list
        node = UITreeNode("div", children=None)
        assert node.children == []
        
    def test_string_prop_conversion(self):
        """Test that all props are handled properly."""
        node = div(
            className="container",
            id="main",
            dataValue=123,
            enabled=True,
            disabled=False
        )
        
        expected_props = {
            "className": "container",
            "id": "main", 
            "dataValue": 123,
            "enabled": True,
            "disabled": False
        }
        
        assert node.props == expected_props


if __name__ == "__main__":
    pytest.main([__file__, "-v"])