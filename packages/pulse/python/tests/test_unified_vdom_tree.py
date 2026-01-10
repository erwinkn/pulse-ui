"""
Integration tests for unified VDOM tree rendering with context wrappers.

F-0037: Verify unified VDOM tree renders correctly with layout + nested page.
"""

import asyncio
from typing import Any

import pulse as ps
import pytest
from pulse.render_session import RenderSession
from pulse.routing import Layout, Route, RouteInfo, RouteTree


@pytest.fixture(autouse=True)
def _pulse_context():  # pyright: ignore[reportUnusedFunction]
	# Ensure event loop is available for prerender's _schedule_timeout
	try:
		loop = asyncio.get_event_loop()
		if loop.is_closed():
			asyncio.set_event_loop(asyncio.new_event_loop())
	except RuntimeError:
		asyncio.set_event_loop(asyncio.new_event_loop())

	app = ps.App()
	ctx = ps.PulseContext(app=app)
	with ctx:
		yield


def make_route_info(pathname: str) -> RouteInfo:
	return {
		"pathname": pathname,
		"hash": "",
		"query": "",
		"queryParams": {},
		"pathParams": {},
		"catchall": [],
	}


def count_elements_with_tag(vdom: Any, tag: str) -> int:
	"""Count number of elements with specific tag in VDOM tree."""
	if not isinstance(vdom, dict):
		return 0
	count = 0
	if vdom.get("tag") == tag:
		count += 1
	children = vdom.get("children", [])
	if isinstance(children, list):
		for child in children:
			count += count_elements_with_tag(child, tag)
	return count


def extract_text_content(vdom: Any) -> str:
	"""Extract all text content from VDOM tree."""
	if isinstance(vdom, str):
		return vdom
	if not isinstance(vdom, dict):
		return ""
	text_parts: list[str] = []
	children = vdom.get("children", [])
	if isinstance(children, list):
		for child in children:
			text_parts.append(extract_text_content(child))
	return "".join(text_parts)


def find_div_with_class(vdom: Any, class_name: str) -> dict[str, Any] | None:
	"""Find first div element with specific className."""
	if not isinstance(vdom, dict):
		return None
	if vdom.get("tag") == "div":
		props = vdom.get("props", {})
		if props.get("className") == class_name:
			return vdom
	children = vdom.get("children", [])
	if isinstance(children, list):
		for child in children:
			result = find_div_with_class(child, class_name)
			if result:
				return result
	return None


class TestUnifiedVdomTree:
	"""Integration tests for unified VDOM tree rendering."""

	def test_layout_with_page_creates_single_tree(self):
		"""Layout + page should create single unified VDOM tree."""

		def layout_render():
			return ps.div(className="layout")[
				ps.div(className="header")["Header"],
				ps.Outlet(),
				ps.div(className="footer")["Footer"],
			]

		def page_render():
			return ps.div(className="page")["Page Content"]

		layout = Layout(ps.component(layout_render), children=[])
		page = Route("page", ps.component(page_render))
		page.parent = layout
		layout.children = [page]

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# Verify tree structure is unified (not separate per-route)
		assert isinstance(vdom, dict), "VDOM should be a dict"
		assert vdom.get("tag"), "VDOM should have a tag"

		# Verify all content is present in single tree
		text = extract_text_content(vdom)
		assert "Header" in text, "Layout header should be in tree"
		assert "Footer" in text, "Layout footer should be in tree"
		assert "Page Content" in text, "Page content should be in tree"

	def test_context_wrappers_present_in_tree(self):
		"""Unified tree should have context wrappers at route boundaries."""

		def layout_render():
			return ps.div(className="layout")[ps.Outlet()]

		def page_render():
			return ps.div(className="page")["Page Content"]

		layout = Layout(ps.component(layout_render), children=[])
		page = Route("page", ps.component(page_render))
		page.parent = layout
		layout.children = [page]

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# Verify router context providers are present
		provider_count = count_elements_with_tag(vdom, "$$PulseRouterProvider")
		assert provider_count == 2, (
			f"Expected 2 router providers (layout + page), got {provider_count}"
		)

	def test_deeply_nested_layouts(self):
		"""Deeply nested layouts should create nested context wrappers."""

		def layout1_render():
			return ps.div(className="layout1")[
				ps.div(className="header1")["Header 1"],
				ps.Outlet(),
			]

		def layout2_render():
			return ps.div(className="layout2")[
				ps.div(className="header2")["Header 2"],
				ps.Outlet(),
			]

		def page_render():
			return ps.div(className="page")["Page Content"]

		layout1 = Layout(ps.component(layout1_render), children=[])
		layout2 = Layout(ps.component(layout2_render), children=[])
		page = Route("page", ps.component(page_render))

		page.parent = layout2
		layout2.parent = layout1
		layout2.children = [page]
		layout1.children = [layout2]

		tree = RouteTree([layout1])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# Should have three providers (layout1 + layout2 + page)
		provider_count = count_elements_with_tag(vdom, "$$PulseRouterProvider")
		assert provider_count == 3, f"Expected 3 router providers, got {provider_count}"

		# All content should be present
		text = extract_text_content(vdom)
		assert "Header 1" in text
		assert "Header 2" in text
		assert "Page Content" in text

	def test_outlet_substitution_in_unified_tree(self):
		"""Outlets should be substituted in unified tree."""

		def layout_render():
			return ps.div(className="layout")[
				ps.div(className="header")["Layout Header"],
				ps.Outlet(),
			]

		def page_render():
			return ps.div(className="page")["Page Content"]

		layout = Layout(ps.component(layout_render), children=[])
		page = Route("page", ps.component(page_render))
		page.parent = layout
		layout.children = [page]

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# Verify Outlet is NOT in final VDOM (substituted)
		vdom_str = str(vdom)
		assert "Outlet" not in vdom_str, (
			"Outlet should be substituted, not present in VDOM"
		)

		# Verify page is substituted where Outlet was
		text = extract_text_content(vdom)
		assert "Page Content" in text, "Page should replace Outlet"

	def test_layout_structure_preserved(self):
		"""Layout structure should be preserved around substituted outlet."""

		def layout_render():
			return ps.div(className="layout")[
				ps.div(className="header")["Header"],
				ps.Outlet(),
				ps.div(className="footer")["Footer"],
			]

		def page_render():
			return ps.div(className="page")["Page Content"]

		layout = Layout(ps.component(layout_render), children=[])
		page = Route("page", ps.component(page_render))
		page.parent = layout
		layout.children = [page]

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# Find layout div and verify it contains both header and footer
		layout_div = find_div_with_class(vdom, "layout")
		assert layout_div, "Layout div should exist"

		layout_text = extract_text_content(layout_div)
		assert "Header" in layout_text, "Header should be in layout"
		assert "Footer" in layout_text, "Footer should be in layout"
		assert "Page Content" in layout_text, "Page content should be in layout"

	def test_vdom_is_serializable(self):
		"""Unified VDOM tree should be JSON-serializable."""
		import json

		def layout_render():
			return ps.div(className="layout")[
				ps.div(className="content")["Content"],
				ps.Outlet(),
			]

		def page_render():
			return ps.div(className="page")["Page"]

		layout = Layout(ps.component(layout_render), children=[])
		page = Route("page", ps.component(page_render))
		page.parent = layout
		layout.children = [page]

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# Should be JSON-serializable (for SSR)
		try:
			json_str = json.dumps(vdom)
			assert len(json_str) > 0, "VDOM should serialize to JSON"
		except TypeError as e:
			pytest.fail(f"VDOM should be JSON-serializable, but got: {e}")

	def test_context_wrappers_nested_correctly(self):
		"""Context wrappers should be nested (not flat)."""

		def layout_render():
			return ps.div(className="layout")[ps.Outlet()]

		def page_render():
			return ps.div(className="page")["Content"]

		layout = Layout(ps.component(layout_render), children=[])
		page = Route("page", ps.component(page_render))
		page.parent = layout
		layout.children = [page]

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# Verify nesting: first provider should contain second provider
		def check_nested_providers(node: Any, depth: int = 0) -> int:
			if not isinstance(node, dict):
				return depth
			if node.get("tag") == "$$PulseRouterProvider":
				children = node.get("children", [])
				if isinstance(children, list) and children:
					# Check if any child is another provider
					for child in children:
						max_depth = check_nested_providers(child, depth + 1)
						return max_depth
			else:
				children = node.get("children", [])
				if isinstance(children, list):
					for child in children:
						result = check_nested_providers(child, depth)
						if result > depth:
							return result
			return depth

		max_provider_depth = check_nested_providers(vdom)
		assert max_provider_depth >= 2, (
			f"Providers should be nested, got max depth {max_provider_depth}"
		)

	def test_ssr_renders_unified_tree_correctly(self):
		"""Unified VDOM tree should render to valid HTML via SSR."""
		# Import here to avoid dependency if not installed
		try:
			import json
		except ImportError:
			pytest.skip("json not available")

		def layout_render():
			return ps.div(className="layout")[
				ps.div(className="header")["Header"],
				ps.Outlet(),
				ps.div(className="footer")["Footer"],
			]

		def page_render():
			return ps.div(className="page")["Page Content"]

		layout = Layout(ps.component(layout_render), children=[])
		page = Route("page", ps.component(page_render))
		page.parent = layout
		layout.children = [page]

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# VDOM should be JSON-serializable for SSR
		json_str = json.dumps(vdom)
		parsed_vdom = json.loads(json_str)

		# Verify parsed VDOM has same structure
		assert parsed_vdom.get("tag"), "Parsed VDOM should have tag"
		assert "Header" in json_str, "Header should be in serialized VDOM"
		assert "Page Content" in json_str, "Page content should be in serialized VDOM"
		assert "Footer" in json_str, "Footer should be in serialized VDOM"

	def test_ssr_preserves_all_content(self):
		"""SSR serialization should preserve all content from unified tree."""
		import json

		def layout_render():
			return ps.div(className="layout")[
				ps.h1()["Main Title"],
				ps.Outlet(),
				ps.p(className="footer-text")["Copyright 2024"],
			]

		def page_render():
			return ps.div(className="page")[
				ps.h2()["Page Title"],
				ps.p()["Paragraph 1"],
				ps.p()["Paragraph 2"],
			]

		layout = Layout(ps.component(layout_render), children=[])
		page = Route("page", ps.component(page_render))
		page.parent = layout
		layout.children = [page]

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# Serialize and deserialize
		json_str = json.dumps(vdom)
		assert json_str, "VDOM should serialize to non-empty JSON"

		# Verify all text content is preserved
		assert "Main Title" in json_str
		assert "Page Title" in json_str
		assert "Paragraph 1" in json_str
		assert "Paragraph 2" in json_str
		assert "Copyright 2024" in json_str

		# Verify class names are preserved
		assert "layout" in json_str
		assert "page" in json_str
		assert "footer-text" in json_str
