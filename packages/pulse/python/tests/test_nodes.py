"""
Tests for the pulse.html module's UI tree generation system.

This module tests the direct UI tree node generation that matches
the TypeScript UIElementNode format.
"""

from typing import Any

import pytest
from pulse import (
	Node,
	VDOMNode,
	a,
	br,
	div,
	form,
	h1,
	hr,
	img,
	li,
	p,
	script,
	span,
	strong,
	style,
	ul,
)
from pulse.html.tags import define_self_closing_tag, define_tag
from pulse.vdom import Callback

from .test_utils import assert_node_equal


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

	def test_node_with_key(self):
		"""Test creating nodes with keys."""
		node = Node("div", key="my-key")
		assert node.key == "my-key"

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
		assert node.props is None
		assert node.children is None

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

		assert_node_equal(structure, Node.from_vdom(expected))

	def test_self_closing_tags(self):
		"""Test self-closing tags."""
		node = br()
		assert node.tag == "br"
		assert node.children is None

		node = hr()
		assert node.tag == "hr"
		assert node.children is None

		node = img(src="/image.jpg", alt="Description")
		assert node.tag == "img"
		assert node.props == {"src": "/image.jpg", "alt": "Description"}
		assert node.children is None

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
		assert node.props is None
		assert node.children is None

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
		assert node.props is None
		assert node.children is None

		node = self_closing(prop="value")
		assert node.tag == "void-element"
		assert node.props == {"prop": "value"}
		assert node.children is None


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

		assert_node_equal(list_structure, Node.from_vdom(expected))

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

		assert_node_equal(mixed_content, Node.from_vdom(expected))


class TestEdgeCases:
	"""Test edge cases and error conditions."""

	def test_empty_structures(self):
		"""Test empty structures."""
		node = div()
		expected: VDOMNode = {"tag": "div"}
		assert_node_equal(node, Node.from_vdom(expected))

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

		assert_node_equal(deep_structure, Node.from_vdom(expected))

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
			tabIndex=123,
			hidden=True,
			spellCheck=False,
		)

		expected_props = {
			"className": "container",
			"id": "main",
			"tabIndex": 123,
			"hidden": True,
			"spellCheck": False,
		}

		assert node.props == expected_props


class TestMissingKeyWarnings:
	"""Test that missing key warnings are emitted at the correct location."""

	def test_tag_factory_warns_for_unkeyed_iterable(
		self, monkeypatch: pytest.MonkeyPatch
	):
		"""Test that tag factories emit warning for iterables without keys."""
		monkeypatch.setenv("PULSE_MODE", "dev")
		with pytest.warns(
			UserWarning,
			match=r"\[Pulse\] Iterable children of <div> contain elements without 'key'",
		):
			items = [span() for _ in range(3)]
			div(items)

	def test_tag_factory_no_warning_with_keys(self, monkeypatch: pytest.MonkeyPatch):
		"""Test that no warning is emitted when all items have keys."""
		monkeypatch.setenv("PULSE_MODE", "dev")
		import warnings

		with warnings.catch_warnings():
			warnings.simplefilter("error")
			items = [span(key=f"item-{i}") for i in range(3)]
			div(items)  # Should not raise

	def test_tag_factory_no_warning_in_prod(self, monkeypatch: pytest.MonkeyPatch):
		"""Test that no warning is emitted in prod mode."""
		monkeypatch.setenv("PULSE_MODE", "prod")
		import warnings

		with warnings.catch_warnings():
			warnings.simplefilter("error")
			items = [span() for _ in range(3)]
			div(items)  # Should not raise in prod

	def test_component_bracket_syntax_warns(self, monkeypatch: pytest.MonkeyPatch):
		"""Components with `*children` flatten and warn for unkeyed iterables."""
		from pulse.vdom import component

		monkeypatch.setenv("PULSE_MODE", "dev")

		@component
		def MyComponent(*children):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
			return div(*children)  # pyright: ignore[reportUnknownArgumentType]

		with pytest.warns(
			UserWarning,
			match=r"\[Pulse\] Iterable children of <MyComponent> contain elements without 'key'",
		):
			items = [span() for _ in range(3)]
			MyComponent()[items]

	def test_component_positional_args_warns(self, monkeypatch: pytest.MonkeyPatch):
		"""Components with `*children` flatten and warn for unkeyed iterables."""
		from pulse.vdom import component

		monkeypatch.setenv("PULSE_MODE", "dev")

		@component
		def MyComponent(*children):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
			return div(*children)  # pyright: ignore[reportUnknownArgumentType]

		with pytest.warns(
			UserWarning,
			match=r"\[Pulse\] Iterable children of <MyComponent> contain elements without 'key'",
		):
			items = [span() for _ in range(3)]
			MyComponent(items)

	def test_component_without_children_no_flatten(
		self, monkeypatch: pytest.MonkeyPatch
	):
		"""Components without `*children` don't flatten - they're just functions."""
		from pulse.vdom import component

		monkeypatch.setenv("PULSE_MODE", "dev")

		@component
		def MyComponent(data: Any, value_col: str = "value"):
			return div()

		# Component without *children doesn't flatten - args passed as-is
		items = [span() for _ in range(3)]
		node = MyComponent(items, value_col="test")
		# The list is passed as a single positional arg, not flattened into individual elements
		assert len(node.args) == 1
		assert node.args[0] == items  # Still a list, not flattened
		assert node.kwargs == {"value_col": "test"}


class TestFromVDOM:
	def test_from_vdom_primitives(self):
		for value in ["text", 123, 3.14, True, None]:
			assert Node.from_vdom(value) == value

	def test_from_vdom_simple_element(self):
		vdom: VDOMNode = {"tag": "div"}
		node = Node.from_vdom(vdom)
		assert isinstance(node, Node)
		assert node.tag == "div"
		assert_node_equal(node, Node("div"))

	def test_from_vdom_with_props_and_children(self):
		vdom: VDOMNode = {
			"tag": "div",
			"props": {"className": "container"},
			"children": [
				"Hello",
				{"tag": "span", "children": ["World"]},
			],
		}

		node = Node.from_vdom(vdom)
		assert isinstance(node, Node)
		expected = Node(
			"div",
			{"className": "container"},
			[
				"Hello",
				Node("span", None, ["World"]),
			],
		)
		assert_node_equal(node, expected)

	def test_from_vdom_preserves_key_and_maps_callbacks(self):
		vdom: VDOMNode = {
			"tag": "button",
			"key": "k1",
			"props": {
				"type": "button",
			},
			"children": ["Click"],
		}

		onClick = lambda: None  # noqa: E731
		callbacks = {"onClick": Callback(onClick, 0)}

		node = Node.from_vdom(vdom, callbacks)
		assert isinstance(node, Node)
		# onClick should be restored from callbacks registry
		assert node.props == {"type": "button", "onClick": onClick}
		assert node.key == "k1"
		assert_node_equal(
			node,
			Node("button", {"type": "button", "onClick": onClick}, ["Click"], key="k1"),
		)
