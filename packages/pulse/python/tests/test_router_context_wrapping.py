"""
Tests for PulseRouterContext injection in unified VDOM tree.

F-0036: Each route boundary wrapped with PulseRouterContext component in VDOM.
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


def count_router_providers(vdom: Any) -> int:
	"""Count number of $$PulseRouterProvider nodes in VDOM tree."""
	if not isinstance(vdom, dict):
		return 0
	count = 0
	if vdom.get("tag") == "$$PulseRouterProvider":
		count += 1
	children = vdom.get("children", [])
	if isinstance(children, list):
		for child in children:
			count += count_router_providers(child)
	return count


def extract_router_provider_structure(vdom: Any) -> str:
	"""Extract a string representation of the router provider structure."""
	if not isinstance(vdom, dict):
		return ""
	if vdom.get("tag") == "$$PulseRouterProvider":
		children_structure = ""
		children = vdom.get("children", [])
		if isinstance(children, list) and children:
			children_structure = extract_router_provider_structure(children[0])
		return f"[Provider{children_structure}]"
	children = vdom.get("children", [])
	if isinstance(children, list) and children:
		# Search all children for providers, not just the first one
		for child in children:
			result = extract_router_provider_structure(child)
			if result:
				return result
	return ""


class TestRouterContextWrapping:
	"""Test PulseRouterContext wrapping at route boundaries."""

	def test_single_route_wrapped_with_provider(self):
		"""Single route should be wrapped with one $$PulseRouterProvider."""

		def route_render():
			return ps.div(className="route")["Content"]

		route = Route("page", ps.component(route_render))
		tree = RouteTree([route])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		assert msg["type"] == "vdom_init"
		vdom = msg["vdom"]

		# Should have exactly one provider (wrapping the root)
		provider_count = count_router_providers(vdom)
		assert provider_count == 1, f"Expected 1 provider, got {provider_count}"

	def test_layout_with_page_wrapped_with_nested_providers(self):
		"""Layout > Page should have two nested $$PulseRouterProvider wrappers."""

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

		# Should have two providers (one for layout, one for page)
		provider_count = count_router_providers(vdom)
		assert provider_count == 2, f"Expected 2 providers, got {provider_count}"

		# Verify nesting structure: [Provider[Provider[content]]]
		structure = extract_router_provider_structure(vdom)
		assert "[Provider[Provider" in structure, (
			f"Expected nested providers, got: {structure}"
		)

	def test_multiple_nested_layouts_wrapped_correctly(self):
		"""Deeply nested layout > layout > page should have three providers."""

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

		# Should have three providers
		provider_count = count_router_providers(vdom)
		assert provider_count == 3, f"Expected 3 providers, got {provider_count}"

	def test_provider_contains_route_content(self):
		"""Content inside provider should render correctly."""

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

		# Verify the page content is rendered inside
		vdom_str = str(vdom)
		assert "Page Content" in vdom_str, "Page content should be in rendered VDOM"
		assert "page" in vdom_str, "Page class should be in rendered VDOM"

	def test_provider_preserves_sibling_elements(self):
		"""Provider wrapping should not affect sibling elements in layout."""

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

		vdom_str = str(vdom)
		assert "Header" in vdom_str, "Header should be present"
		assert "Footer" in vdom_str, "Footer should be present"
		assert "Page Content" in vdom_str, "Page content should be present"

	def test_all_providers_have_vdom_element_form(self):
		"""All providers should be rendered as VDOM elements."""

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

		# All providers should have correct VDOM structure
		def check_providers(node: Any) -> bool:
			if not isinstance(node, dict):
				return True
			if node.get("tag") == "$$PulseRouterProvider":
				# Should have children and be a dict
				assert isinstance(node, dict)
				assert "tag" in node
				# Recursively check children
				children = node.get("children", [])
				if isinstance(children, list):
					for child in children:
						if not check_providers(child):
							return False
			else:
				# Recursively check children for nested providers
				children = node.get("children", [])
				if isinstance(children, list):
					for child in children:
						if not check_providers(child):
							return False
			return True

		assert check_providers(vdom), "All providers should have valid VDOM structure"
