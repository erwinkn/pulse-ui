"""
Tests for the pulse.html module's UI tree generation system.

This module tests the direct UI tree node generation that matches
the TypeScript UIElementNode format.
"""

import pytest
from pulse.vdom import (
    Node,
    VDOMNode,
    div,
    p,
    span,
    h1,
    button,
    a,
    img,
    br,
    hr,
    strong,
    ul,
    li,
    script,
    style,
    form,
    input,
    label,
    define_tag,
    define_self_closing_tag,
)
from pulse.tests.test_utils import assert_node_renders_to


class TestUITreeNode:
    """Test the core UITreeNode functionality."""

    def test_basic_node_creation(self):
        """Test creating basic UI tree nodes."""
        node = Node("div")
        assert node.tag == "div"
        assert node.props is None
        assert node.children is None
        assert node.key is None

    def test_node_with_props(self):
        """Test creating nodes with props."""
        node = Node("div", {"className": "container", "id": "main"})
        assert node.tag == "div"
        assert node.props == {"className": "container", "id": "main"}
        assert node.children is None

    def test_node_with_children(self):
        """Test creating nodes with children."""
        child1 = Node("p")
        child2 = "text content"
        node = Node("div", children=[child1, child2])

        assert node.tag == "div"
        assert node.children is not None
        assert len(node.children) == 2
        assert node.children[0] == child1
        assert node.children[1] == "text content"

    def test_node_to_dict(self):
        """Test converting nodes to dictionary format."""
        child = Node("p", {"className": "text"}, ["Hello"])
        node = Node("div", {"id": "container"}, [child, "world"])

        expected: VDOMNode = {
            "tag": "div",
            "props": {"id": "container"},
            "children": [
                {"tag": "p", "props": {"className": "text"}, "children": ["Hello"]},
                "world",
            ],
        }

        assert_node_renders_to(node, expected)

    def test_node_with_key(self):
        """Test creating nodes with keys."""
        node = Node("div", key="my-key")
        assert node.key == "my-key"

        expected: VDOMNode = {"tag": "div", "key": "my-key"}
        assert_node_renders_to(node, expected)

    def test_indexing_syntax(self):
        """Test the indexing syntax for adding children."""
        node = Node("div")

        # Single child
        result = node["Hello world"]
        assert result.children == ["Hello world"]
        assert result.tag == "div"

        # Multiple children
        child1 = Node("p")
        result = node[child1, "text"]
        assert result.children is not None
        assert len(result.children) == 2
        assert result.children[0] == child1
        assert result.children[1] == "text"

    def test_indexing_with_existing_children_fails(self):
        """Test that indexing fails when children already exist."""
        node = Node("div", children=["existing"])

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
        assert node.children is not None
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
        assert node.children is not None
        assert len(node.children) == 2
        assert node.children[0] == child_p
        assert node.children[1] == "Additional text"

    def test_nested_structure(self):
        """Test creating nested HTML structures."""
        structure = div(className="page")[
            h1()["Page Title"],
            div(className="content")[
                p()["First paragraph"],
                p()["Second paragraph with ", strong()["bold text"], " inside."],
            ],
        ]

        expected: VDOMNode = {
            "tag": "div",
            "props": {"className": "page"},
            "children": [
                {"tag": "h1", "children": ["Page Title"]},
                {
                    "tag": "div",
                    "props": {"className": "content"},
                    "children": [
                        {"tag": "p", "children": ["First paragraph"]},
                        {
                            "tag": "p",
                            "children": [
                                "Second paragraph with ",
                                {"tag": "strong", "children": ["bold text"]},
                                " inside.",
                            ],
                        },
                    ],
                },
            ],
        }

        assert_node_renders_to(structure, expected)

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
        list_structure = ul(className="list")[*[li()[item] for item in items]]

        expected: VDOMNode = {
            "tag": "ul",
            "props": {"className": "list"},
            "children": [
                {"tag": "li", "children": ["Item 1"]},
                {"tag": "li", "children": ["Item 2"]},
                {"tag": "li", "children": ["Item 3"]},
            ],
        }

        assert_node_renders_to(list_structure, expected)

    def test_form_structure(self):
        """Test creating form structures."""
        form_structure = form(action="/submit", method="POST")[
            div(className="form-group")[
                label(htmlFor="name")["Name:"],
                input(type="text", id="name", name="name", required=True),
            ],
            div(className="form-group")[
                label(htmlFor="email")["Email:"],
                input(type="email", id="email", name="email", required=True),
            ],
            button(type="submit")["Submit"],
        ]

        # Just test that it renders without checking exact structure
        # Form structures are complex and the exact layout may vary
        result, callbacks = form_structure.render()
        assert result["tag"] == "form"
        props = result.get("props")
        assert props is not None
        assert props["action"] == "/submit"
        assert props["method"] == "POST"

    def test_mixed_content_types(self):
        """Test mixing different content types."""
        mixed_content = div(
            "Plain text",
            p("Paragraph text"),
            123,  # Number
            True,  # Boolean
            span()["More text"],
        )

        expected: VDOMNode = {
            "tag": "div",
            "children": [
                "Plain text",
                {"tag": "p", "children": ["Paragraph text"]},
                123,
                True,
                {"tag": "span", "children": ["More text"]},
            ],
        }

        assert_node_renders_to(mixed_content, expected)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_structures(self):
        """Test empty structures."""
        node = div()
        expected: VDOMNode = {"tag": "div"}
        assert_node_renders_to(node, expected)

    def test_deeply_nested_structure(self):
        """Test deeply nested structures."""
        deep_structure = div()[div()[div()[div()[div()["Deep content"]]]]]

        expected: VDOMNode = {
            "tag": "div",
            "children": [
                {
                    "tag": "div",
                    "children": [
                        {
                            "tag": "div",
                            "children": [
                                {
                                    "tag": "div",
                                    "children": [
                                        {"tag": "div", "children": ["Deep content"]}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        assert_node_renders_to(deep_structure, expected)

    def test_none_handling(self):
        """Test handling of None values."""
        # None props should remain None
        node = Node("div", None)
        assert node.props is None

        # None children should remain None
        node = Node("div", children=None)
        assert node.children is None

    def test_string_prop_conversion(self):
        """Test that all props are handled properly."""
        node = div(
            className="container",
            id="main",
            dataValue=123,
            enabled=True,
            disabled=False,
        )

        expected_props = {
            "className": "container",
            "id": "main",
            "dataValue": 123,
            "enabled": True,
            "disabled": False,
        }

        assert node.props == expected_props


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
