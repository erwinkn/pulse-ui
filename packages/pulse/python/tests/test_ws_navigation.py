"""WebSocket-native navigation: the client navigates by asking the server for
the target's views over the socket. The server matches the URL against the
Python route tree, reuses live views (state persists), and renders only the
missing ones with a dispose TTL."""

from types import SimpleNamespace
from typing import Any, cast

import pulse as ps
import pytest
from pulse.messages import (
	ClientNavigateMessage,
	ServerMessage,
	ServerNavigateResultMessage,
)
from pulse.render_session import RenderSession
from pulse.request import PulseRequest
from pulse.routing import RouteInfo
from pulse.user_session import UserSession


def make_route_info(pathname: str) -> RouteInfo:
	return {
		"pathname": pathname,
		"hash": "",
		"query": "",
		"queryParams": {},
		"pathParams": {},
		"catchall": [],
	}


def make_request(pathname: str) -> PulseRequest:
	return PulseRequest(
		headers={},
		cookies={},
		scheme="http",
		method="GET",
		path=pathname,
		query_string="",
		client=None,
	)


def make_app() -> ps.App:
	@ps.component
	def layout():
		return ps.div(ps.Outlet())

	@ps.component
	def home():
		return ps.div("home")

	@ps.component
	def about():
		return ps.div("about")

	@ps.component
	def gated():
		ps.redirect("/about")
		return ps.div("never")

	return ps.App(
		[
			ps.Layout(
				layout,
				[
					ps.Route("/", home),
					ps.Route("about", about),
					ps.Route("gated", gated),
				],
			)
		]
	)


def setup_session(app: ps.App) -> tuple[RenderSession, Any, list[ServerMessage]]:
	render = RenderSession("render-nav", app.routes)
	session = SimpleNamespace(sid="session-nav", data={})
	sent: list[ServerMessage] = []
	render.connect(sent.append)
	with ps.PulseContext(
		app=app, session=cast(UserSession, cast(object, session)), render=render
	):
		render.prerender(["/<layout>", "/"], make_route_info("/"))
		for path in ("/<layout>", "/"):
			render.attach(render.view_for_path(path).id, make_route_info("/"))
	return render, session, sent


async def run_navigate(
	app: ps.App,
	render: RenderSession,
	session: Any,
	pathname: str,
	nav: str = "nav-1",
) -> ServerNavigateResultMessage:
	msg: ClientNavigateMessage = {
		"type": "navigate",
		"nav": nav,
		"routeInfo": make_route_info(pathname),
	}
	with ps.PulseContext(
		app=app, session=cast(UserSession, cast(object, session)), render=render
	):
		await app._handle_navigate(  # pyright: ignore[reportPrivateUsage]
			render,
			cast(UserSession, cast(object, session)),
			msg,
			make_request(pathname),
		)
	sent = [m for m in render_sent[id(render)] if m["type"] == "navigate_result"]
	return sent[-1]


render_sent: dict[int, list[ServerMessage]] = {}


@pytest.mark.asyncio
async def test_navigate_reuses_live_views_and_renders_missing_ones():
	app = make_app()
	render, session, sent = setup_session(app)
	render_sent[id(render)] = sent

	result = await run_navigate(app, render, session, "/about")

	assert result["status"] == "ok"
	views = result.get("views")
	assert views is not None
	# The layout survives the navigation: the client keeps its live view.
	assert views["/<layout>"] is None
	about = views["/about"]
	assert about is not None and about["type"] == "vdom_init"
	assert about["routePath"] == "/about"

	# The fresh view is pending with a dispose TTL until the client attaches.
	view = render.view_for_path("/about")
	assert view.id == about["view"]
	assert view.state == "pending"
	assert view.pending_action == "dispose"

	# The home view was not disturbed (the client detaches it after committing).
	assert render.view_for_path("/").state == "active"


@pytest.mark.asyncio
async def test_navigate_redirect_interrupt_reports_redirect():
	app = make_app()
	render, session, sent = setup_session(app)
	render_sent[id(render)] = sent

	result = await run_navigate(app, render, session, "/gated")

	assert result["status"] == "redirect"
	assert result.get("redirect") == "/about"
	# The interrupted view must not linger.
	with pytest.raises(ValueError):
		render.view_for_path("/gated")


@pytest.mark.asyncio
async def test_navigate_unknown_path_reports_not_found():
	app = make_app()
	render, session, sent = setup_session(app)
	render_sent[id(render)] = sent

	result = await run_navigate(app, render, session, "/nope")

	assert result["status"] == "notFound"
	assert result.get("redirect") == app.not_found


@pytest.mark.asyncio
async def test_navigate_disposes_idle_views_and_renders_fresh():
	app = make_app()
	render, session, sent = setup_session(app)
	render_sent[id(render)] = sent

	# Simulate the about view going idle from an earlier visit.
	with ps.PulseContext(
		app=app, session=cast(UserSession, cast(object, session)), render=render
	):
		render.prerender(["/about"], make_route_info("/about"))
	old_view = render.view_for_path("/about")
	old_view.to_idle()
	assert old_view.state == "idle"

	result = await run_navigate(app, render, session, "/about")

	assert result["status"] == "ok"
	views = result.get("views")
	assert views is not None
	about = views["/about"]
	assert about is not None
	assert about["view"] != old_view.id
	assert render.view_for_path("/about").id == about["view"]
