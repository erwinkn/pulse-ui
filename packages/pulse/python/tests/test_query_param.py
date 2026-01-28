from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pulse as ps
import pytest
from pulse.messages import ServerMessage
from pulse.reactive import flush_effects
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteContext, RouteInfo, RouteTree


def make_route_info(
	pathname: str, *, query_params: dict[str, str] | None = None
) -> RouteInfo:
	return {
		"pathname": pathname,
		"hash": "",
		"query": "",
		"queryParams": query_params or {},
		"pathParams": {},
		"catchall": [],
	}


def make_context(route_info: RouteInfo):
	def render():
		return ps.div()

	route = Route("/", ps.component(render))
	routes = RouteTree([route])
	session = RenderSession("test", routes)
	route_ctx = RouteContext(route_info, route)
	app = ps.App(routes=[route])
	return app, session, route_ctx


class TestQueryParam:
	def test_state_to_url_preserves_params(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "hello", "other": "1"})
		)
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()
			assert state.q == "hello"
			messages.clear()
			state.q = "next"
			flush_effects()

		assert len(messages) == 1
		msg = messages[0]
		assert msg["type"] == "navigate_to"
		parsed = urlparse(str(msg["path"]))
		query = parse_qs(parsed.query)
		assert query["q"] == ["next"]
		assert query["other"] == ["1"]

	def test_url_to_state_updates(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "hello"})
		)
		session.connect(lambda _msg: None)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()
			assert state.q == "hello"
			route_ctx.update(make_route_info("/", query_params={"q": "world"}))
			flush_effects()
			assert state.q == "world"

	def test_list_parsing_and_serialization(self):
		class TagState(ps.State):
			tags: ps.QueryParam[list[str]] = []

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"tags": "a\\,b,c\\\\d"})
		)
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = TagState()
			assert list(state.tags) == ["a,b", "c\\d"]
			messages.clear()
			state.tags = ["x,y", "z\\w"]
			flush_effects()

		assert len(messages) == 1
		msg = messages[0]
		assert msg["type"] == "navigate_to"
		parsed = urlparse(str(msg["path"]))
		query = parse_qs(parsed.query)
		assert query["tags"] == ["x\\,y,z\\\\w"]

	def test_list_in_place_mutation_updates_url(self):
		class TagState(ps.State):
			tags: ps.QueryParam[list[str]] = []

		app, session, route_ctx = make_context(make_route_info("/", query_params={}))
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = TagState()
			messages.clear()
			state.tags.append("alpha")
			flush_effects()

		assert len(messages) == 1
		msg = messages[0]
		assert msg["type"] == "navigate_to"
		parsed = urlparse(str(msg["path"]))
		query = parse_qs(parsed.query)
		assert query["tags"] == ["alpha"]

	def test_default_removal(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = "hello"

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "world", "other": "1"})
		)
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()
			messages.clear()
			state.q = "hello"
			flush_effects()

		assert len(messages) == 1
		msg = messages[0]
		assert msg["type"] == "navigate_to"
		parsed = urlparse(str(msg["path"]))
		query = parse_qs(parsed.query)
		assert "q" not in query
		assert query["other"] == ["1"]

	def test_datetime_naive_warns(self):
		class TimeState(ps.State):
			ts: ps.QueryParam[datetime] = datetime(2024, 1, 1, tzinfo=timezone.utc)

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"ts": "2024-01-02T01:02:03"})
		)
		session.connect(lambda _msg: None)
		with pytest.warns(UserWarning, match="naive datetime"):
			with ps.PulseContext(app=app, render=session, route=route_ctx):
				state = TimeState()
				assert state.ts.tzinfo == timezone.utc
