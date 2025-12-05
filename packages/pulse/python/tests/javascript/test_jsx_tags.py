"""Tests for JSX tag function transpilation."""

from typing import Any

import pytest
from pulse.html import tags
from pulse.javascript.function import javascript


class TestJSXTagTranspilation:
	"""Tests for transpiling pulse.html.tags to JSX elements."""

	def test_simple_tag_no_props_no_children(self) -> None:
		"""Test: div() -> <div />"""

		@javascript
		def fn():
			return tags.div()

		js = fn.transpile()
		assert "<div />" in js

	def test_tag_with_single_string_child(self) -> None:
		"""Test: div("Hello") -> <div>Hello</div>"""

		@javascript
		def fn():
			return tags.div("Hello")

		js = fn.transpile()
		assert "<div>Hello</div>" in js

	def test_tag_with_props(self) -> None:
		"""Test: div(className="container") -> <div className="container" />"""

		@javascript
		def fn():
			return tags.div(className="container")

		js = fn.transpile()
		assert '<div className="container" />' in js

	def test_tag_with_props_and_children_in_call(self) -> None:
		"""Test: div("text", className="foo") -> <div className="foo">text</div>"""

		@javascript
		def fn():
			return tags.div("text", className="foo")

		js = fn.transpile()
		assert '<div className="foo">text</div>' in js

	def test_tag_with_subscript_children(self) -> None:
		"""Test: div()[span("Hi")] -> <div><span>Hi</span></div>"""

		@javascript
		def fn():
			return tags.div()[tags.span("Hi")]

		js = fn.transpile()
		assert "<div><span>Hi</span></div>" in js

	def test_tag_with_props_and_subscript_children(self) -> None:
		"""Test: div(className="outer")[span("inner")] -> <div className="outer"><span>inner</span></div>"""

		@javascript
		def fn():
			return tags.div(className="outer")[tags.span("inner")]

		js = fn.transpile()
		assert '<div className="outer"><span>inner</span></div>' in js

	def test_multiple_children(self) -> None:
		"""Test: div()[span("A"), span("B")] -> <div><span>A</span><span>B</span></div>"""

		@javascript
		def fn():
			return tags.div()[tags.span("A"), tags.span("B")]

		js = fn.transpile()
		assert "<div><span>A</span><span>B</span></div>" in js

	def test_nested_elements(self) -> None:
		"""Test deeply nested elements."""

		@javascript
		def fn():
			return tags.div()[tags.div()[tags.span("Deep")]]

		js = fn.transpile()
		assert "<div><div><span>Deep</span></div></div>" in js

	def test_self_closing_tag(self) -> None:
		"""Test: img(src="photo.jpg") -> <img src="photo.jpg" />"""

		@javascript
		def fn():
			return tags.img(src="photo.jpg")

		js = fn.transpile()
		assert '<img src="photo.jpg" />' in js

	def test_input_tag(self) -> None:
		"""Test self-closing input tag with props."""

		@javascript
		def fn():
			return tags.input(type="text", placeholder="Enter text")

		js = fn.transpile()
		assert "<input" in js
		assert 'type="text"' in js
		assert 'placeholder="Enter text"' in js
		assert "/>" in js

	def test_fragment(self) -> None:
		"""Test React fragment."""

		@javascript
		def fn():
			return tags.fragment(tags.div("A"), tags.div("B"))

		js = fn.transpile()
		assert "<><div>A</div><div>B</div></>" in js

	def test_fragment_with_subscript(self) -> None:
		"""Test that fragment with subscript syntax fails in regular Python."""

		# In regular Python, tags.fragment is a function and cannot be subscripted
		with pytest.raises(TypeError):
			# This is intentionally invalid Python code - fragment is not subscriptable
			_ = tags.fragment[tags.div("A"), tags.div("B")]  # pyright: ignore[reportIndexIssue]

	def test_dynamic_content(self) -> None:
		"""Test tag with dynamic content from parameter."""

		@javascript
		def fn(name: str):
			return tags.span(name)

		js = fn.transpile()
		assert "<span>{name}</span>" in js

	def test_expression_in_children(self) -> None:
		"""Test expression in children list."""

		@javascript
		def fn(items: list[str]):
			return tags.ul()[[tags.li(x) for x in items]]

		js = fn.transpile()
		assert "<ul>" in js
		assert "</ul>" in js
		# The list comprehension should produce mapped items

	def test_multiple_props(self) -> None:
		"""Test element with multiple props."""

		@javascript
		def fn():
			return tags.a(href="/link", target="_blank", className="link")

		js = fn.transpile()
		assert '<a href="/link" target="_blank" className="link" />' in js


class TestJSXSpreadProps:
	"""Tests for spread props in JSX."""

	def test_spread_props(self) -> None:
		"""Test: div(**props) -> <div {...props} />"""

		@javascript
		def fn(props: dict[str, Any]):
			return tags.div(**props)

		js = fn.transpile()
		assert "{...props}" in js

	def test_spread_with_named_props(self) -> None:
		"""Test: div(a=1, **p, b=2) -> <div a={1} {...p} b={2} />"""

		@javascript
		def fn(p: dict[str, Any]):  # pyright: ignore[reportUnknownParameterType]
			return tags.div(a=1, **p, b=2)  # pyright: ignore[reportCallIssue]

		js = fn.transpile()
		assert "a={1}" in js
		assert "{...p}" in js
		assert "b={2}" in js
		# Order should be preserved
		assert js.index("a={1}") < js.index("{...p}") < js.index("b={2}")


class TestJSXEdgeCases:
	"""Tests for edge cases in JSX transpilation."""

	def test_empty_fragment(self) -> None:
		"""Test empty fragment."""

		@javascript
		def fn():
			return tags.fragment()

		js = fn.transpile()
		assert "<></>" in js

	def test_svg_tag(self) -> None:
		"""Test SVG element."""

		@javascript
		def fn():
			return tags.svg(viewBox="0 0 24 24")[tags.path(d="M0 0")]

		js = fn.transpile()
		assert '<svg viewBox="0 0 24 24">' in js
		assert '<path d="M0 0" />' in js
		assert "</svg>" in js


class TestJSXModuleAccess:
	"""Tests for accessing tags module."""

	def test_direct_module_access(self) -> None:
		"""Test: tags.div() via module access."""

		@javascript
		def fn():
			return tags.div()

		js = fn.transpile()
		assert "<div />" in js

	def test_from_import_style(self) -> None:
		"""Test using from-import style."""
		from pulse.html.tags import div, span

		@javascript
		def fn():
			return div(className="test")[span("Hello")]

		js = fn.transpile()
		assert '<div className="test"><span>Hello</span></div>' in js
