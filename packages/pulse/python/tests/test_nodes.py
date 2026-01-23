"""
Tests for the pulse.dom module's UI tree generation system.

This module tests the direct UI tree node generation that matches
the TypeScript UIElementNode format.
"""

import inspect
import warnings
from typing import Any

import pytest
from pulse.dom.tags import (
	a,
	br,
	define_self_closing_tag,
	define_tag,
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
from pulse.react_component import react_component
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import Element, Node

from .test_utils import assert_node_equal


class TestUITreeNode:
	"""Test the core UITreeNode functionality."""

	def test_basic_node_creation(self):
		"""Test creating basic UI tree nodes."""
		node = Element("div")
		assert node.tag == "div"
		assert node.props is None
		assert node.children is None
		assert node.key is None

	def test_node_with_props(self):
		"""Test creating nodes with props."""
		node = Element("div", {"className": "container", "id": "main"})
		assert node.tag == "div"
		assert node.props == {"className": "container", "id": "main"}
		assert node.children is None

	def test_node_with_children(self):
		"""Test creating nodes with children."""
		child1 = Element("p")
		child2 = "text content"
		node = Element("div", children=[child1, child2])

		assert node.tag == "div"
		assert node.children is not None
		assert len(node.children) == 2
		assert node.children[0] == child1
		assert node.children[1] == "text content"

	def test_node_with_key(self):
		"""Test creating nodes with keys."""
		node = Element("div", key="my-key")
		assert node.key == "my-key"

	def test_indexing_syntax(self):
		"""Test the indexing syntax for adding children."""
		node = Element("div")

		# Single child
		result = node["Hello world"]
		assert result.children == ["Hello world"]
		assert result.tag == "div"

		# Multiple children
		child1 = Element("p")
		result = node[child1, "text"]
		assert result.children is not None
		assert len(result.children) == 2
		assert result.children[0] == child1
		assert result.children[1] == "text"

	def test_indexing_with_existing_children_fails(self):
		"""Test that indexing fails when children already exist."""
		node = Element("div", children=["existing"])

		with pytest.raises(ValueError, match="already has children"):
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

		expected = div(className="page")[
			h1()["Page Title"],
			div(className="content")[
				p()["First paragraph"],
				p()["Second paragraph with ", strong()["bold text"], " inside."],
			],
		]

		assert_node_equal(structure, expected)

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

		expected = ul(className="list")[
			li()["Item 1"],
			li()["Item 2"],
			li()["Item 3"],
		]

		assert_node_equal(list_structure, expected)

	def test_mixed_content_types(self):
		"""Test mixing different content types."""
		mixed_content = div(
			"Plain text",
			p("Paragraph text"),
			123,  # Number
			True,  # Boolean
			span()["More text"],
		)

		expected = div(
			"Plain text",
			p("Paragraph text"),
			123,
			True,
			span()["More text"],
		)

		assert_node_equal(mixed_content, expected)


class TestEdgeCases:
	"""Test edge cases and error conditions."""

	def test_empty_structures(self):
		"""Test empty structures."""
		node = div()
		expected = div()
		assert_node_equal(node, expected)

	def test_deeply_nested_structure(self):
		"""Test deeply nested structures."""
		deep_structure = div()[div()[div()[div()[div()["Deep content"]]]]]

		expected = div()[div()[div()[div()[div()["Deep content"]]]]]

		assert_node_equal(deep_structure, expected)

	def test_none_handling(self):
		"""Test handling of None values."""
		# None props should remain None
		node = Element("div", None)
		assert node.props is None

		# None children should remain None
		node = Element("div", children=None)
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
		"""Tag factories warn for unkeyed iterables."""
		monkeypatch.setenv("PULSE_ENV", "dev")
		items = [span() for _ in range(3)]
		with pytest.warns(
			UserWarning,
			match=r"\[Pulse\] Iterable children of <div> contain elements without 'key'",
		):
			div(items)  # pyright: ignore[reportArgumentType]

	def test_tag_factory_no_warning_with_keys(self, monkeypatch: pytest.MonkeyPatch):
		"""Test that no warning is emitted when all items have keys."""
		monkeypatch.setenv("PULSE_ENV", "dev")
		import warnings

		with warnings.catch_warnings():
			warnings.simplefilter("error")
			items = [span(key=f"item-{i}") for i in range(3)]
			div(items)  # Should not raise  # pyright: ignore[reportArgumentType]

	def test_tag_factory_no_warning_in_prod(self, monkeypatch: pytest.MonkeyPatch):
		"""Test that no warning is emitted in prod mode."""
		monkeypatch.setenv("PULSE_ENV", "prod")
		import warnings

		with warnings.catch_warnings():
			warnings.simplefilter("error")
			items = [span() for _ in range(3)]
			# Should not raise in prod
			div(items)  # pyright: ignore[reportArgumentType]

	def test_component_bracket_syntax_warns(self, monkeypatch: pytest.MonkeyPatch):
		"""Bracket syntax on components warns for unkeyed iterables."""
		from pulse.component import component

		monkeypatch.setenv("PULSE_ENV", "dev")

		@component
		def MyComponent(*children):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
			return div(*children)  # pyright: ignore[reportUnknownArgumentType]

		items = [span() for _ in range(3)]
		with pytest.warns(
			UserWarning,
			match=r"\[Pulse\] Iterable children of <MyComponent> contain elements without 'key'",
		):
			MyComponent()[items]  # pyright: ignore[reportArgumentType]

	def test_component_positional_args_warns(self, monkeypatch: pytest.MonkeyPatch):
		"""Components with `*children` flatten and warn for unkeyed iterables."""
		from pulse.component import component

		monkeypatch.setenv("PULSE_ENV", "dev")

		@component
		def MyComponent(*children):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
			return div(*children)  # pyright: ignore[reportUnknownArgumentType]

		with pytest.warns(
			UserWarning,
			match=r"\[Pulse\] Iterable children of <MyComponent> contain elements without 'key'",
		):
			items = [span() for _ in range(3)]
			MyComponent(items)

	def test_react_component_warning_points_to_user_code(
		self, monkeypatch: pytest.MonkeyPatch
	):
		"""React components warn with clean names at user callsites."""
		monkeypatch.setenv("PULSE_ENV", "dev")

		@react_component(Import("Stack", "@mantine/core"))
		def Stack(*children: Node, key: str | None = None, **props: Any) -> Element: ...

		with warnings.catch_warnings(record=True) as caught:
			warnings.simplefilter("always")
			line = inspect.currentframe().f_lineno + 1  # pyright: ignore[reportOptionalMemberAccess]
			Stack([span(), span()])  # pyright: ignore[reportArgumentType]

		assert len(caught) == 1
		warn = caught[0]
		assert (
			"[Pulse] Iterable children of <Stack> contain elements without 'key'"
			in str(warn.message)
		)
		assert warn.filename == __file__
		assert warn.lineno == line

	def test_component_sets_pulsenode_name(self):
		"""Component name is stored on PulseNode for debugging."""
		from pulse.component import component

		@component
		def NamedComponent():
			return div()

		node = NamedComponent()
		assert node.name == "NamedComponent"

	def test_component_without_children_no_flatten(
		self, monkeypatch: pytest.MonkeyPatch
	):
		"""Components without `*children` don't flatten - they're just functions."""
		from pulse.component import component

		monkeypatch.setenv("PULSE_ENV", "dev")

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
