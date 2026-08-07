import pulse as ps
import pytest
from pulse.render_session import RenderSession
from pulse.routing import (
	Layout,
	Location,
	Route,
	RouteContext,
	RouteTree,
	match_route_path,
)


@ps.component
def Page():
	return ps.div()


def build(*routes: Route | Layout) -> RouteTree:
	return RouteTree(list(routes))


class TestMatchRoutePath:
	def test_static(self):
		route = Route("users", Page)
		build(route)
		assert match_route_path(route, "/users") == ({}, [])
		assert match_route_path(route, "/other") is None

	def test_static_case_insensitive(self):
		route = Route("Users", Page)
		build(route)
		assert match_route_path(route, "/users") == ({}, [])

	def test_dynamic_param(self):
		route = Route("users/:id", Page)
		build(route)
		assert match_route_path(route, "/users/123") == ({"id": "123"}, [])
		assert match_route_path(route, "/users") is None

	def test_param_is_percent_decoded(self):
		route = Route("files/:name", Page)
		build(route)
		assert match_route_path(route, "/files/a%20b") == ({"name": "a b"}, [])

	def test_static_prefix_allows_children_segments(self):
		child = Route(":id", Page)
		parent = Route("users", Page, children=[child])
		build(parent)
		# The parent mount matches even though the URL goes deeper.
		assert match_route_path(parent, "/users/123") == ({}, [])
		assert match_route_path(child, "/users/123") == ({"id": "123"}, [])

	def test_nested_params_accumulate(self):
		child = Route(":repo", Page)
		parent = Route("orgs/:org", Page, children=[child])
		build(parent)
		assert match_route_path(child, "/orgs/pulse/ui") == (
			{"org": "pulse", "repo": "ui"},
			[],
		)

	def test_layout_contributes_no_segments(self):
		leaf = Route(":id", Page)
		layout = Layout(Page, children=[leaf])
		parent = Route("users", Page, children=[layout])
		build(parent)
		assert match_route_path(layout, "/users/123") == ({}, [])
		assert match_route_path(leaf, "/users/123") == ({"id": "123"}, [])

	def test_optional_dynamic(self):
		route = Route("posts/:page?", Page)
		build(route)
		assert match_route_path(route, "/posts/2") == ({"page": "2"}, [])
		assert match_route_path(route, "/posts") == ({}, [])

	def test_optional_static(self):
		route = Route("settings/advanced?", Page)
		build(route)
		assert match_route_path(route, "/settings/advanced") == ({}, [])
		assert match_route_path(route, "/settings") == ({}, [])

	def test_optional_prefers_consuming(self):
		route = Route("a/:b?/:c?", Page)
		build(route)
		# Same expansion ranking as React Router: params present win.
		assert match_route_path(route, "/a/x") == ({"b": "x"}, [])
		assert match_route_path(route, "/a/x/y") == ({"b": "x", "c": "y"}, [])
		assert match_route_path(route, "/a") == ({}, [])

	def test_splat_catchall(self):
		route = Route("docs/*", Page)
		build(route)
		assert match_route_path(route, "/docs/a/b/c") == ({}, ["a", "b", "c"])
		assert match_route_path(route, "/docs") == ({}, [])

	def test_splat_segments_decoded(self):
		route = Route("docs/*", Page)
		build(route)
		assert match_route_path(route, "/docs/a%20b/c") == ({}, ["a b", "c"])

	def test_root_route(self):
		route = Route("/", Page)
		build(route)
		assert match_route_path(route, "/") == ({}, [])
		# Root is a prefix of everything.
		assert match_route_path(route, "/anything") == ({}, [])

	def test_param_and_splat(self):
		route = Route(":lang/docs/*", Page)
		build(route)
		assert match_route_path(route, "/en/docs/api/v2") == (
			{"lang": "en"},
			["api", "v2"],
		)


class TestDerivedRouteInfo:
	"""The session URL is the single source of truth: every mount's route
	info is derived server-side from it, never supplied by the client."""

	def make_session(self):
		detail = Route(":id", Page)
		items = Route("items", Page, children=[detail])
		docs = Route("docs/*", Page)
		routes = RouteTree([items, docs])
		return RenderSession("test", routes)

	def location(
		self, pathname: str, query_params: dict[str, str] | None = None
	) -> Location:
		return {
			"pathname": pathname,
			"hash": "",
			"query": "",
			"queryParams": query_params or {},
		}

	def test_path_params_derived_on_prerender(self):
		session = self.make_session()
		session.prerender(["/items/:id"], self.location("/items/123"))
		ctx = session.route_mounts["/items/:id"].route
		assert ctx.pathParams == {"id": "123"}
		assert ctx.pathname == "/items/123"
		session.close()

	def test_catchall_derived_on_prerender(self):
		session = self.make_session()
		session.prerender(["/docs/*"], self.location("/docs/a/b"))
		ctx = session.route_mounts["/docs/*"].route
		assert ctx.catchall == ["a", "b"]
		session.close()

	def test_set_url_pushes_to_every_matching_mount(self):
		session = self.make_session()
		loc = self.location("/items/123")
		session.prerender(["/items", "/items/:id"], loc)
		parent = session.route_mounts["/items"].route
		child = session.route_mounts["/items/:id"].route

		session.update_route(
			"/items/:id", self.location("/items/456", {"tab": "specs"})
		)
		assert child.pathParams == {"id": "456"}
		assert child.queryParams == {"tab": "specs"}
		# The parent mount was updated too, without its own client message.
		assert parent.pathname == "/items/456"
		assert parent.queryParams == {"tab": "specs"}
		session.close()

	def test_non_matching_mount_keeps_last_snapshot(self):
		session = self.make_session()
		session.prerender(["/items/:id"], self.location("/items/123"))
		ctx = session.route_mounts["/items/:id"].route

		# Navigation overlap: the URL moves on to a route this mount does not
		# match while the mount is still alive.
		session.prerender(["/docs/*"], self.location("/docs/guide"))
		assert ctx.pathname == "/items/123"
		assert ctx.pathParams == {"id": "123"}
		session.close()

	def test_route_context_rejects_non_matching_pathname(self):
		detail = Route("items/:id", Page)
		build(detail)
		with pytest.raises(ValueError, match="does not match route"):
			RouteContext(detail, self.location("/other/1"))
