from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pulse as ps
import pytest
from pulse.messages import ServerMessage, ServerNavigateToMessage
from pulse.reactive import flush_effects
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteInfo, RouteTree


class MissingType:
	pass


def make_route_info(
	pathname: str, *, query_params: dict[str, str] | None = None, hash: str = ""
) -> RouteInfo:
	return {
		"pathname": pathname,
		"hash": hash,
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
	app = ps.App(routes=[route])
	session.prerender(["/"], route_info)
	route_ctx = session.route_mounts["/"].route
	return app, session, route_ctx


def flush_query_param_sync(session: RenderSession) -> None:
	flush_effects()
	effect = session.query_param_sync._state_effect  # pyright: ignore[reportPrivateUsage]
	if effect is not None:
		effect.flush()


class TestQueryParam:
	def test_query_param_is_available_in_state_constructor(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = "default"
			initial_q: str = ""

			def __init__(self):
				self.initial_q = self.q

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "hello"})
		)
		session.connect(lambda _msg: None)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()

		assert state.initial_q == "hello"

	def test_state_constructor_can_override_query_param(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = "default"
			page: ps.QueryParam[int] = 1

			def __init__(self):
				assert self.q == "from-url"
				assert self.page == 2
				self.q = "from-constructor"
				self.page = 3

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "from-url", "page": "2"})
		)
		messages: list[ServerMessage] = []
		session.connect(messages.append)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()
			flush_query_param_sync(session)

		assert state.q == "from-constructor"
		assert state.page == 3
		assert len(messages) == 1
		msg = messages[0]
		assert msg["type"] == "navigate_to"
		query = parse_qs(urlparse(str(msg["path"])).query)
		assert query["q"] == ["from-constructor"]
		assert query["page"] == ["3"]

	def test_state_to_url_preserves_params(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "hello", "other": "1"})
		)
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		with ps.PulseContext(app=app, render=session, route=route_ctx):
			assert route_ctx.pathname in session.route_mounts
			state = QState()
			assert state.q == "hello"
			flush_effects()
			messages.clear()
			state.q = "next"
			flush_query_param_sync(session)

		assert len(messages) == 1
		msg = messages[0]
		assert msg["type"] == "navigate_to"
		# Session-scoped sync: attributed to the URL it was built from, not to a mount.
		assert "sourceRoutePath" not in msg
		assert "sourceMountId" not in msg
		assert msg.get("sourcePath") == "/"
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
		messages: list[ServerMessage] = []
		session.connect(messages.append)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()
			assert state.q == "hello"
			messages.clear()
			route_ctx.update(make_route_info("/", query_params={"q": "world"}))
			flush_effects()
			assert state.q == "world"
		assert messages == []

	def test_query_param_string_annotation_with_unresolved_type(self):
		class QState(ps.State):
			bad: "MissingType[int]" = ""  # pyright: ignore[reportInvalidTypeArguments,reportAssignmentType]
			q: "ps.QueryParam[str]" = ""

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "hello"})
		)
		session.connect(lambda _msg: None)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()
			assert state.q == "hello"

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
			flush_effects()
			messages.clear()
			state.tags = ["x,y", "z\\w"]
			flush_query_param_sync(session)

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
			flush_effects()
			messages.clear()
			state.tags.append("alpha")
			flush_query_param_sync(session)

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
			flush_effects()
			messages.clear()
			state.q = "hello"
			flush_query_param_sync(session)

		assert len(messages) == 1
		msg = messages[0]
		assert msg["type"] == "navigate_to"
		parsed = urlparse(str(msg["path"]))
		query = parse_qs(parsed.query)
		assert "q" not in query
		assert query["other"] == ["1"]

	def test_optional_missing_uses_default(self):
		class QState(ps.State):
			q: ps.QueryParam[str | None] = "hello"

		app, session, route_ctx = make_context(make_route_info("/", query_params={}))
		session.connect(lambda _msg: None)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()
			assert state.q == "hello"

	def test_empty_list_serializes_when_not_default(self):
		class TagState(ps.State):
			tags: ps.QueryParam[list[str]] = ["alpha"]

		app, session, route_ctx = make_context(make_route_info("/", query_params={}))
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = TagState()
			flush_effects()
			messages.clear()
			state.tags = []
			flush_query_param_sync(session)

		assert len(messages) == 1
		msg = messages[0]
		assert msg["type"] == "navigate_to"
		parsed = urlparse(str(msg["path"]))
		query = parse_qs(parsed.query, keep_blank_values=True)
		assert query["tags"] == [""]

	def test_hash_preserved_in_url(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={}, hash="section1")
		)
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()
			messages.clear()
			state.q = "next"
			flush_query_param_sync(session)

		assert len(messages) == 1
		msg = messages[0]
		assert msg["type"] == "navigate_to"
		parsed = urlparse(str(msg["path"]))
		assert parsed.fragment == "section1"

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

	def test_duplicate_param_in_same_route_raises(self):
		class First(ps.State):
			q: ps.QueryParam[str] = ""

		class Second(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(make_route_info("/", query_params={}))
		session.connect(lambda _msg: None)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			_first = First()
			with pytest.raises(ValueError, match="'q' is already bound"):
				_second = Second()


def make_two_route_session():
	"""A session with routes /a and /b, nothing mounted yet."""

	def render():
		return ps.div()

	route_a = Route("a", ps.component(render))
	route_b = Route("b", ps.component(render))
	routes = RouteTree([route_a, route_b])
	app = ps.App(routes=[route_a, route_b])
	return app, RenderSession("test", routes)


def navigations(messages: list[ServerMessage]) -> list[ServerNavigateToMessage]:
	return [m for m in messages if m["type"] == "navigate_to"]


class TestQueryParamAcrossMounts:
	"""A `QueryParam` binding is owned by the session, so it outlives mounts.

	Each test navigates /a -> /b the way the client does: the incoming route is
	prerendered while the outgoing one is still mounted, then /a detaches.
	"""

	def navigate(
		self,
		session: RenderSession,
		path: str,
		query_params: dict[str, str],
		*,
		detach: str | None = None,
	) -> None:
		info = make_route_info(path, query_params=query_params)
		session.prerender([path], info)
		if detach is not None:
			session.detach(detach)
		session.attach(path, info)

	def test_binding_survives_mount_change(self):
		class Filters(ps.State):
			q: ps.QueryParam[str] = ""

		session_filters = ps.global_state(Filters)

		app, session = make_two_route_session()
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		start = make_route_info("/a", query_params={"q": "hello", "other": "1"})
		session.prerender(["/a"], start)
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/a"].route
		):
			state = session_filters()
			assert state.q == "hello"
			flush_effects()

		self.navigate(session, "/b", {"q": "hello", "other": "1"}, detach="/a")
		assert "/a" not in session.route_mounts

		# URL -> state still works after the mount that created the state is gone
		# (back/forward, or a manual edit of the query string).
		session.update_route(
			"/b", make_route_info("/b", query_params={"q": "world", "other": "1"})
		)
		flush_effects()
		assert state.q == "world"

		# state -> URL still works, against the *current* route.
		messages.clear()
		state.q = "next"
		flush_query_param_sync(session)
		navs = navigations(messages)
		assert len(navs) == 1
		assert navs[0].get("sourcePath") == "/b"
		parsed = urlparse(str(navs[0]["path"]))
		assert parsed.path == "/b"
		query = parse_qs(parsed.query)
		assert query["q"] == ["next"]
		# Unrelated params on the new route are preserved
		assert query["other"] == ["1"]

		session.close()

	def test_param_absent_from_new_route_resets_to_default(self):
		class Filters(ps.State):
			q: ps.QueryParam[str] = "fallback"

		session_filters = ps.global_state(Filters)

		app, session = make_two_route_session()
		session.connect(lambda _msg: None)
		session.prerender(["/a"], make_route_info("/a", query_params={"q": "hello"}))
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/a"].route
		):
			state = session_filters()
			assert state.q == "hello"
			flush_effects()

		# The URL stays the source of truth: a route without the param means default.
		self.navigate(session, "/b", {}, detach="/a")
		flush_effects()
		assert state.q == "fallback"

		session.close()

	def test_same_param_on_another_route_takes_over(self):
		"""Overlapping mounts must not collide; the newest binding owns the URL."""

		class FiltersA(ps.State):
			q: ps.QueryParam[str] = ""

		class FiltersB(ps.State):
			q: ps.QueryParam[str] = ""

		app, session = make_two_route_session()
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		session.prerender(["/a"], make_route_info("/a", query_params={"q": "hello"}))
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/a"].route
		):
			a = FiltersA()
			flush_effects()

		# The new route is prerendered while /a is still mounted: no error.
		info_b = make_route_info("/b", query_params={"q": "hello"})
		session.prerender(["/b"], info_b)
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/b"].route
		):
			b = FiltersB()
			flush_effects()

		# The newest binding writes the URL...
		messages.clear()
		b.q = "from-b"
		flush_query_param_sync(session)
		navs = navigations(messages)
		assert len(navs) == 1
		assert parse_qs(urlparse(str(navs[0]["path"])).query)["q"] == ["from-b"]

		# ...the displaced one does not, while it is still mounted.
		messages.clear()
		a.q = "from-a"
		flush_query_param_sync(session)
		assert navigations(messages) == []

		# Both still follow the URL.
		session.update_route("/b", make_route_info("/b", query_params={"q": "shared"}))
		session.update_route("/a", make_route_info("/a", query_params={"q": "shared"}))
		flush_effects()
		assert a.q == "shared"
		assert b.q == "shared"

		session.close()

	def test_restored_binding_regains_url_ownership(self):
		"""Disposing the owning binding hands the URL back to the previous one.

		The restored binding must be re-tracked by the state effect, or its
		changes silently stop writing to the URL.
		"""

		class Filters(ps.State):
			q: ps.QueryParam[str] = ""

		session_filters = ps.global_state(Filters)

		class FiltersB(ps.State):
			q: ps.QueryParam[str] = ""

		def render():
			return ps.div()

		route_a = Route("a", ps.component(render))
		route_b = Route("b", ps.component(render))
		route_c = Route("c", ps.component(render))
		routes = RouteTree([route_a, route_b, route_c])
		app = ps.App(routes=[route_a, route_b, route_c])
		session = RenderSession("test", routes)
		messages: list[ServerMessage] = []
		session.connect(messages.append)

		# /a: the session-scoped state binds q.
		session.prerender(["/a"], make_route_info("/a", query_params={"q": "hello"}))
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/a"].route
		):
			state = session_filters()
			flush_effects()

		# /b: a route-local state takes over q.
		info_b = make_route_info("/b", query_params={"q": "hello"})
		session.prerender(["/b"], info_b)
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/b"].route
		):
			b = FiltersB()
			flush_effects()
		session.detach("/a")
		session.attach("/b", info_b)

		# /c: no local binding; /b unmounts and its state is disposed.
		info_c = make_route_info("/c", query_params={"q": "hello"})
		session.prerender(["/c"], info_c)
		session.detach("/b")
		session.attach("/c", info_c)
		b.dispose()
		flush_effects()

		# The session-scoped binding owns the URL again: no navigation was
		# emitted by the handover itself...
		messages.clear()
		flush_query_param_sync(session)
		assert navigations(messages) == []

		# ...and its changes write to the URL once more.
		state.q = "from-restored"
		flush_query_param_sync(session)
		navs = navigations(messages)
		assert len(navs) == 1
		assert navs[0].get("sourcePath") == "/c"
		parsed = urlparse(str(navs[0]["path"]))
		assert parsed.path == "/c"
		assert parse_qs(parsed.query)["q"] == ["from-restored"]

		session.close()
