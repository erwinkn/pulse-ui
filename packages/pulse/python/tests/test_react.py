"""
Tests for React component integration

Focuses on the @react_component decorator behavior with Expr-backed components.
"""

from __future__ import annotations

from typing import Any

import pytest
from pulse.react_component import react_component
from pulse.transpiler.imports import Import
from pulse.transpiler.nodes import Element, Jsx, Member, Node


def test_react_component_import_expr():
	"""@react_component wraps Import-backed Exprs and returns Element nodes."""
	button_import = Import("Button", "@ui/button")

	@react_component(button_import)
	def Button(*children: Node, key: str | None = None, **props: Any) -> Element: ...

	node = Button("Click", disabled=True)
	assert isinstance(node, Element)
	assert node.tag is button_import
	assert node.props == {"disabled": True}
	assert node.children == ["Click"]


def test_react_component_member_expr():
	"""@react_component supports Member expressions for nested components."""
	app_shell = Import("AppShell", "@mantine/core")
	header_expr = Member(app_shell, "Header")

	@react_component(header_expr)
	def Header(*children: Node, key: str | None = None, **props: Any) -> Element: ...

	node = Header("Title")
	assert isinstance(node, Element)
	assert node.tag is header_expr
	assert node.children == ["Title"]


def test_react_component_jsx_expr_passthrough():
	"""@react_component accepts Jsx(expr) and does not double-wrap."""
	card_import = Import("Card", "@ui/card")
	jsx = Jsx(card_import)

	@react_component(jsx)
	def Card(*children: Node, key: str | None = None, **props: Any) -> Element: ...

	node = Card("Body")
	assert isinstance(node, Element)
	assert node.tag is card_import
	assert node.children == ["Body"]


def test_react_component_rejects_non_expr():
	"""@react_component enforces Expr-only inputs."""
	with pytest.raises(TypeError, match="expects an Expr"):

		@react_component("Button")  # pyright: ignore[reportArgumentType]
		def Button(  # pyright: ignore[reportUnusedFunction]
			*children: Node, key: str | None = None, **props: Any
		) -> Element: ...


def test_react_component_key_validation():
	"""Jsx call path enforces string key."""
	box_import = Import("Box", "@ui/box")

	@react_component(box_import)
	def Box(*children: Node, key: str | None = None, **props: Any) -> Element: ...

	with pytest.raises(ValueError, match="key must be a string"):
		Box(key=123)  # pyright: ignore[reportArgumentType]

	node = Box(key="k1")
	assert node.key == "k1"
