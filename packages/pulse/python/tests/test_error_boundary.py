"""Tests for Python ErrorBoundary wiring to React."""

from typing import Any

from pulse.dom.tags import div
from pulse.error_boundary import ErrorBoundary, RenderError
from pulse.renderer import MOUNT_PREFIX, RenderTree
from pulse.transpiler.nodes import Element


def test_error_boundary_renders_as_react_mount_point() -> None:
	"""ErrorBoundary renders as $$ErrorBoundary mount point in VDOM."""
	boundary = ErrorBoundary(div("Hello"))
	tree: Any = RenderTree(boundary)  # pyright: ignore[reportArgumentType]
	vdom: Any = tree.render()

	assert isinstance(vdom, dict)
	assert vdom["tag"] == f"{MOUNT_PREFIX}ErrorBoundary"
	assert "children" in vdom
	# Children should contain the rendered div
	assert len(vdom["children"]) == 1  # pyright: ignore[reportUnknownArgumentType]
	child = vdom["children"][0]
	assert child["tag"] == "div"
	assert child["children"] == ["Hello"]


def test_error_boundary_passes_client_fallback_as_callback() -> None:
	"""client_fallback prop is registered as callback for React fallback."""

	def my_fallback(error: Any, reset: Any) -> Element:
		return div(f"Error: {error}")

	boundary = ErrorBoundary(div("Content"), client_fallback=my_fallback)
	tree: Any = RenderTree(boundary)  # pyright: ignore[reportArgumentType]
	vdom: Any = tree.render()

	# Should have eval array with fallback marked
	assert "eval" in vdom
	assert "fallback" in vdom["eval"]

	# Should have fallback prop with callback placeholder
	assert "props" in vdom
	assert vdom["props"]["fallback"] == "$cb"

	# Callback should be registered
	assert "fallback" in tree.callbacks


def test_error_boundary_catches_server_side_errors() -> None:
	"""Server-side rendering errors are caught and show Python fallback."""
	from pulse.component import component

	@component
	def Thrower() -> Element:
		raise ValueError("Server error")

	boundary = ErrorBoundary(Thrower())
	tree: Any = RenderTree(boundary)  # pyright: ignore[reportArgumentType]
	vdom: Any = tree.render()

	# Should render the fallback, not the error
	assert isinstance(vdom, dict)
	# The fallback is rendered inside the ErrorBoundary
	child = vdom["children"][0]
	# Default fallback renders a div with error styling
	assert child["tag"] == "div"
	# Should contain "Something went wrong" text
	children = child.get("children", [])
	assert isinstance(children, list)
	assert any(
		isinstance(c, dict)
		and c.get("tag") == "h2"
		and "Something went wrong" in str(c.get("children", []))  # pyright: ignore[reportUnknownArgumentType]
		for c in children
	)


def test_error_boundary_with_custom_server_fallback() -> None:
	"""Custom server-side fallback function is used when provided."""
	from pulse.component import component

	def custom_fallback(error: RenderError) -> Element:
		return div(f"Custom: {error.message}")

	@component
	def Thrower() -> Element:
		raise ValueError("My error")

	boundary = ErrorBoundary(Thrower(), fallback=custom_fallback)
	tree: Any = RenderTree(boundary)  # pyright: ignore[reportArgumentType]
	vdom: Any = tree.render()

	# Should render custom fallback
	child = vdom["children"][0]
	assert child["tag"] == "div"
	children = child.get("children", [])
	assert isinstance(children, list)
	assert "Custom: My error" in children


def test_error_boundary_without_error_renders_children() -> None:
	"""When no error occurs, children are rendered normally."""
	boundary = ErrorBoundary(div("Normal content"))
	tree: Any = RenderTree(boundary)  # pyright: ignore[reportArgumentType]
	vdom: Any = tree.render()

	child = vdom["children"][0]
	assert child["tag"] == "div"
	assert child["children"] == ["Normal content"]


def test_error_boundary_multiple_children() -> None:
	"""ErrorBoundary with multiple children renders all."""
	boundary = ErrorBoundary(div("First"), div("Second"))
	tree: Any = RenderTree(boundary)  # pyright: ignore[reportArgumentType]
	vdom: Any = tree.render()

	# Multiple children are wrapped in a fragment
	child = vdom["children"][0]
	# Fragment tag is empty string
	assert child["tag"] == ""
	children = child["children"]
	assert isinstance(children, list)
	assert len(children) == 2  # pyright: ignore[reportUnknownArgumentType]
	assert children[0]["tag"] == "div"
	assert children[1]["tag"] == "div"


def test_render_error_from_exception() -> None:
	"""RenderError captures exception message and stack."""
	try:
		raise ValueError("Test message")
	except ValueError as exc:
		error = RenderError.from_exception(exc)

	assert error.message == "Test message"
	assert error.stack is not None
	assert "ValueError" in error.stack
	assert "Test message" in error.stack


def test_render_error_empty_message_uses_type_name() -> None:
	"""RenderError uses exception type name when message is empty."""
	try:
		raise ValueError()
	except ValueError as exc:
		error = RenderError.from_exception(exc)

	assert error.message == "ValueError"
