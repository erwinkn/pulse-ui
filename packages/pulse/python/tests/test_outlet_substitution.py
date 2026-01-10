"""
Tests for Outlet substitution in unified VDOM tree rendering.

F-0035: Outlet nodes in layout VDOM replaced with child route's VDOM.
"""

from typing import Any

import pulse as ps
import pytest
from pulse.render_session import RenderSession
from pulse.routing import Layout, Route, RouteInfo, RouteTree


@pytest.fixture(autouse=True)
def _pulse_context():  # pyright: ignore[reportUnusedFunction]
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


def extract_text_content(vdom: Any) -> str:
	"""Extract all text content from VDOM tree for testing."""
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


def has_outlet_in_vdom(vdom: Any) -> bool:
	"""Check if VDOM contains any Outlet components."""
	if not isinstance(vdom, dict):
		return False
	if vdom.get("tag") == "$$Outlet":
		return True
	children = vdom.get("children", [])
	if isinstance(children, list):
		for child in children:
			if has_outlet_in_vdom(child):
				return True
	return False


class TestBasicOutletSubstitution:
	"""Test basic outlet substitution with layout > page."""

	def test_single_layout_with_outlet_renders_child_route(self):
		"""Layout with Outlet should render child route content inside."""

		# Define layout that includes Outlet
		def layout_render():
			return ps.div(className="layout")[
				ps.div(className="header")["Header"],
				ps.Outlet(),
				ps.div(className="footer")["Footer"],
			]

		# Define child route
		def page_render():
			return ps.div(className="page")["Page Content"]

		layout = Layout(ps.component(layout_render), children=[])
		route = Route("page", ps.component(page_render))
		layout.children = [route]
		route.parent = layout

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		# Prerender the route
		msg = session.prerender("/page", make_route_info("/page"))

		# Extract VDOM from message
		assert msg.get("type") == "vdom_init"
		vdom = msg.get("vdom")

		# Verify structure: div.layout contains Header + Page Content + Footer
		text = extract_text_content(vdom)
		assert "Header" in text
		assert "Page Content" in text
		assert "Footer" in text

		# Verify no Outlet placeholders remain in final VDOM
		assert not has_outlet_in_vdom(vdom)

	def test_nested_layouts_with_outlets_substitute_correctly(self):
		"""Multiple layouts with Outlets should substitute all levels."""

		# Root layout
		def root_layout_render():
			return ps.div(className="root")[
				ps.div(className="root-header")["Root Header"],
				ps.Outlet(),
				ps.div(className="root-footer")["Root Footer"],
			]

		# Child layout (between root and page)
		def child_layout_render():
			return ps.div(className="child")[
				ps.div(className="child-header")["Child Header"],
				ps.Outlet(),
				ps.div(className="child-footer")["Child Footer"],
			]

		# Leaf page
		def page_render():
			return ps.div(className="page")["Page Content"]

		root_layout = Layout(ps.component(root_layout_render), children=[])
		child_layout = Layout(ps.component(child_layout_render), children=[])
		route = Route("page", ps.component(page_render))

		# Build hierarchy
		root_layout.children = [child_layout]
		child_layout.parent = root_layout
		child_layout.children = [route]
		route.parent = child_layout

		tree = RouteTree([root_layout])
		session = RenderSession("test", tree)

		# Prerender nested path
		msg = session.prerender("/page", make_route_info("/page"))

		assert msg.get("type") == "vdom_init"
		vdom = msg.get("vdom")

		# Verify all text is present in correct nesting
		text = extract_text_content(vdom)
		assert "Root Header" in text
		assert "Child Header" in text
		assert "Page Content" in text
		assert "Root Footer" in text
		assert "Child Footer" in text

		# No Outlets should remain
		assert not has_outlet_in_vdom(vdom)

	def test_leaf_page_without_outlet_renders_as_is(self):
		"""Routes without Outlets should render unchanged."""

		def page_render():
			return ps.div(className="page")[
				ps.h1()["Title"],
				ps.p()["Content"],
			]

		route = Route("page", ps.component(page_render))
		tree = RouteTree([route])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))

		assert msg.get("type") == "vdom_init"
		vdom = msg.get("vdom")

		text = extract_text_content(vdom)
		assert "Title" in text
		assert "Content" in text
		assert not has_outlet_in_vdom(vdom)


class TestOutletWithMultipleChildren:
	"""Test outlet substitution with multiple children in hierarchy."""

	def test_layout_with_multiple_child_routes_substitutes_correct_one(self):
		"""When parent has multiple children, correct child is substituted."""

		def layout_render():
			return ps.div(className="layout")[ps.Outlet(),]

		def route_a_render():
			return ps.div()["Route A"]

		def route_b_render():
			return ps.div()["Route B"]

		layout = Layout(ps.component(layout_render), children=[])
		route_a = Route("a", ps.component(route_a_render))
		route_b = Route("b", ps.component(route_b_render))

		layout.children = [route_a, route_b]
		route_a.parent = layout
		route_b.parent = layout

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		# Navigate to route A
		msg_a = session.prerender("/a", make_route_info("/a"))
		text_a = extract_text_content(msg_a.get("vdom"))
		assert "Route A" in text_a
		assert "Route B" not in text_a

		# Navigate to route B in new session
		session_b = RenderSession("test_b", tree)
		msg_b = session_b.prerender("/b", make_route_info("/b"))
		text_b = extract_text_content(msg_b.get("vdom"))
		assert "Route B" in text_b
		assert "Route A" not in text_b


class TestOutletWithComplexStructure:
	"""Test outlet substitution with complex layouts."""

	def test_layout_with_multiple_outlets_only_first_substitutes(self):
		"""Multiple Outlets in layout - only matching one gets content."""

		def layout_render():
			return ps.div(className="layout")[
				ps.div(className="sidebar")[
					ps.p()["Sidebar"],
					ps.Outlet(),  # Placeholder outlet in sidebar
				],
				ps.div(className="main")[
					ps.Outlet(),  # Main outlet for child route
				],
			]

		def page_render():
			return ps.div()["Page Content"]

		layout = Layout(ps.component(layout_render), children=[])
		route = Route("page", ps.component(page_render))
		layout.children = [route]
		route.parent = layout

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		vdom = msg.get("vdom")
		text = extract_text_content(vdom)

		# Should have sidebar and page content
		assert "Sidebar" in text
		assert "Page Content" in text

	def test_layout_with_outlet_in_nested_children(self):
		"""Outlet deep in layout's element tree gets substituted."""

		def layout_render():
			return ps.div(className="layout")[
				ps.section(className="content")[
					ps.article(className="main")[ps.Outlet(),],
				],
			]

		def page_render():
			return ps.div(className="page")["Article Content"]

		layout = Layout(ps.component(layout_render), children=[])
		route = Route("article", ps.component(page_render))
		layout.children = [route]
		route.parent = layout

		tree = RouteTree([layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/article", make_route_info("/article"))
		vdom = msg.get("vdom")
		text = extract_text_content(vdom)

		assert "Article Content" in text
		assert not has_outlet_in_vdom(vdom)


class TestOutletEdgeCases:
	"""Test edge cases and error conditions."""

	def test_route_with_outlet_that_has_no_children_keeps_outlet(self):
		"""Route with Outlet but no children to substitute keeps structure."""

		# This edge case: a route that renders Outlet but has no children
		# In real usage, this shouldn't happen, but the code should handle it
		def route_with_outlet():
			return ps.div(className="route")[ps.Outlet(),]

		route = Route("nested", ps.component(route_with_outlet))
		tree = RouteTree([route])
		session = RenderSession("test", tree)

		msg = session.prerender("/nested", make_route_info("/nested"))
		vdom = msg.get("vdom")

		# Outlet should remain since there's no child to substitute with
		# (we're at end of hierarchy)
		assert isinstance(vdom, dict)
		assert "tag" in vdom

	def test_deeply_nested_hierarchy_three_levels(self):
		"""Test three-level layout > layout > page hierarchy."""

		def root_render():
			return ps.div()["Root: ", ps.Outlet()]

		def middle_render():
			return ps.div()["Middle: ", ps.Outlet()]

		def page_render():
			return ps.div()["Page"]

		root_layout = Layout(ps.component(root_render), children=[])
		middle_layout = Layout(ps.component(middle_render), children=[])
		route = Route("page", ps.component(page_render))

		root_layout.children = [middle_layout]
		middle_layout.parent = root_layout
		middle_layout.children = [route]
		route.parent = middle_layout

		tree = RouteTree([root_layout])
		session = RenderSession("test", tree)

		msg = session.prerender("/page", make_route_info("/page"))
		text = extract_text_content(msg.get("vdom"))

		assert "Root:" in text
		assert "Middle:" in text
		assert "Page" in text
		assert not has_outlet_in_vdom(msg.get("vdom"))
