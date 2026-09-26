from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pulse as ps
import pytest
from pulse.hooks.core import HookContext
from pulse.messages import ServerMessage, ServerNavigateToMessage
from pulse.reactive import flush_effects
from pulse.render_session import RenderSession
from pulse.resources import ResourceScope
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
	effect = session.url._sync_effect  # pyright: ignore[reportPrivateUsage]
	if effect is not None:
		effect.flush()


def navigations(messages: list[ServerMessage]) -> list[ServerNavigateToMessage]:
	return [m for m in messages if m["type"] == "navigate_to"]


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

	def test_same_route_states_share_query_param(self):
		class First(ps.State):
			q: ps.QueryParam[str] = ""

		class Second(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "hello"})
		)
		messages: list[ServerMessage] = []
		session.connect(messages.append)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			first = First()
			second = Second()
			assert first.q == "hello"
			assert second.q == "hello"
			assert First.__dict__["q"].get_signal(first) is Second.__dict__[
				"q"
			].get_signal(second)
			flush_effects()
			messages.clear()

			first.q = "from-first"
			assert second.q == "from-first"
			flush_query_param_sync(session)
			navs = navigations(messages)
			assert len(navs) == 1
			assert parse_qs(urlparse(str(navs[0]["path"])).query)["q"] == ["from-first"]

			messages.clear()
			second.q = "from-second"
			assert first.q == "from-second"
			flush_query_param_sync(session)
			navs = navigations(messages)
			assert len(navs) == 1
			assert parse_qs(urlparse(str(navs[0]["path"])).query)["q"] == [
				"from-second"
			]

		assert "q" in session.url._slots  # pyright: ignore[reportPrivateUsage]

	def test_same_route_sibling_unregister_keeps_remaining_writer(self):
		class First(ps.State):
			q: ps.QueryParam[str] = ""

		class Second(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "hello"})
		)
		messages: list[ServerMessage] = []
		session.connect(messages.append)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			first = First()
			second = Second()
			flush_effects()
			first.dispose()
			flush_effects()
			messages.clear()
			second.q = "only-second"
			flush_query_param_sync(session)

		navs = navigations(messages)
		assert len(navs) == 1
		assert parse_qs(urlparse(str(navs[0]["path"])).query)["q"] == ["only-second"]
		assert "q" in session.url._slots  # pyright: ignore[reportPrivateUsage]

	def test_conflicting_codec_or_default_uses_independent_views(self):
		class AsStr(ps.State):
			q: ps.QueryParam[str] = ""

		class AsInt(ps.State):
			q: ps.QueryParam[int] = 0

		class OtherDefault(ps.State):
			q: ps.QueryParam[str] = "other"

		app, session, route_ctx = make_context(make_route_info("/", query_params={}))
		session.connect(lambda _msg: None)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			first = AsStr()
			second = AsInt()
			third = OtherDefault()
			assert first.q == ""
			assert second.q == 0
			assert third.q == "other"
			first.q = "12"
			flush_query_param_sync(session)
			assert first.q == "12"
			assert second.q == 12
			assert third.q == "12"

	def test_query_param_access_requires_pulse_context(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(
			make_route_info("/", query_params={"q": "hello"})
		)
		session.connect(lambda _msg: None)
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			state = QState()
			sig = QState.__dict__["q"].get_signal(state)
		with pytest.raises(RuntimeError, match="require a render context"):
			_ = state.q
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			assert QState.__dict__["q"].get_signal(state) is sig
			assert state.q == "hello"

	def test_state_key_change_releases_query_param_binding(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(make_route_info("/", query_params={}))
		session.connect(lambda _msg: None)
		ctx = HookContext()
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			with ctx:
				first = ps.state(QState, key="1")
			with ctx:
				second = ps.state(QState, key="2")

		assert first.__disposed__
		assert not second.__disposed__
		assert "q" in session.url._slots  # pyright: ignore[reportPrivateUsage]
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			assert second.q == ""

	def test_disposed_state_still_uses_session_owned_slot(self):
		"""Pinned: slots outlive states, so a disposed state reads/writes the live slot."""

		class QState(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(make_route_info("/", query_params={}))
		session.connect(lambda _msg: None)
		ctx = HookContext()
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			with ctx:
				stale = ps.state(QState, key="1")
			with ctx:
				live = ps.state(QState, key="2")

			assert stale.__disposed__
			live.q = "from-live"
			assert stale.q == "from-live"
			stale.q = "from-stale"
			assert live.q == "from-stale"

	def test_state_key_change_disposes_eager_query_param_instance(self):
		class QState(ps.State):
			q: ps.QueryParam[str] = ""

		app, session, route_ctx = make_context(make_route_info("/", query_params={}))
		session.connect(lambda _msg: None)
		ctx = HookContext()
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			with ctx:
				first = ps.state(QState(), key="1")
			with ctx:
				second = ps.state(QState(), key="2")

		assert first.__disposed__
		assert not second.__disposed__
		assert "q" in session.url._slots  # pyright: ignore[reportPrivateUsage]
		with ps.PulseContext(app=app, render=session, route=route_ctx):
			assert second.q == ""

	def test_path_id_state_key_does_not_collide(self):
		"""Same mount, new path id: keyed ps.state must release the old binding."""

		class ItemState(ps.State):
			q: ps.QueryParam[str] = ""

		created: list[ItemState] = []

		@ps.component
		def ItemPage():
			item_id = ps.route()["pathParams"]["id"]
			item = ps.state(ItemState, key=item_id)
			created.append(item)
			return ps.div(item.q)

		route = Route("items/:id", ItemPage)
		session = RenderSession("test", RouteTree([route]))
		app = ps.App(routes=[route])
		mount_path = route.unique_path()

		def info(item_id: str) -> RouteInfo:
			return {
				"pathname": f"/items/{item_id}",
				"hash": "",
				"query": "",
				"queryParams": {"q": "hello"},
				"pathParams": {"id": item_id},
				"catchall": [],
			}

		with ps.PulseContext(app=app, render=session):
			session.prerender([mount_path], info("1"))
		assert len(created) == 1
		first = created[0]

		with ps.PulseContext(app=app, render=session):
			session.prerender([mount_path], info("2"))

		assert len(created) == 2
		assert first.__disposed__
		assert not created[1].__disposed__
		assert "q" in session.url._slots  # pyright: ignore[reportPrivateUsage]
		with ps.PulseContext(app=app, render=session):
			assert created[1].q == "hello"

	def test_path_id_key_change_keeps_unkeyed_sibling(self):
		class Shared(ps.State):
			n: int = 0

		class ItemState(ps.State):
			q: ps.QueryParam[str] = ""

		shareds: list[Shared] = []
		items: list[ItemState] = []

		@ps.component
		def ItemPage():
			item_id = ps.route()["pathParams"]["id"]
			item = ps.state(ItemState, key=item_id)
			shared = ps.state(Shared)
			items.append(item)
			shareds.append(shared)
			return ps.div(item.q)

		route = Route("items/:id", ItemPage)
		session = RenderSession("test", RouteTree([route]))
		app = ps.App(routes=[route])
		mount_path = route.unique_path()

		def info(item_id: str) -> RouteInfo:
			return {
				"pathname": f"/items/{item_id}",
				"hash": "",
				"query": "",
				"queryParams": {"q": "hello"},
				"pathParams": {"id": item_id},
				"catchall": [],
			}

		with ps.PulseContext(app=app, render=session):
			session.prerender([mount_path], info("1"))
		first_item = items[0]
		first_shared = shareds[0]

		with ps.PulseContext(app=app, render=session):
			session.prerender([mount_path], info("2"))

		assert len(items) == 2
		assert first_item.__disposed__
		assert items[1] is not first_item
		assert shareds[-1] is first_shared
		assert not first_shared.__disposed__


def test_f1_pending_write_survives_stale_route_update():
	class QState(ps.State):
		q: ps.QueryParam[str] = ""

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"q": "hello"})
	)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = QState()
		flush_query_param_sync(session)
		messages.clear()
		state.q = "user-typed"
		route_ctx.update(make_route_info("/", query_params={"q": "hello"}))
		flush_query_param_sync(session)
		assert state.q == "user-typed"
		navs = navigations(messages)
		assert len(navs) == 1
		assert parse_qs(urlparse(str(navs[0]["path"])).query)["q"] == ["user-typed"]


def test_f2_reconnect_echo_does_not_revert_server_write():
	class QState(ps.State):
		q: ps.QueryParam[str] = ""

	app, session, route_ctx = make_context(make_route_info("/", query_params={}))
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = QState()
		flush_query_param_sync(session)
		messages.clear()
		state.q = "server-write"
		flush_query_param_sync(session)
		assert len(navigations(messages)) == 1
	session.disconnect()
	session.connect(messages.append)
	session.update_route("/", make_route_info("/", query_params={}))
	flush_query_param_sync(session)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		assert state.q == "server-write"
	assert len(navigations(messages)) == 2
	assert parse_qs(urlparse(str(navigations(messages)[-1]["path"])).query)["q"] == [
		"server-write"
	]


def test_r1_stale_command_does_not_block_client_navigation():
	class QState(ps.State):
		q: ps.QueryParam[str] = ""

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"q": "a"})
	)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = QState()
		state.q = "b"
		flush_query_param_sync(session)
		messages.clear()
		route_ctx.update(make_route_info("/", query_params={"q": "c"}))
		flush_query_param_sync(session)
		messages.clear()
		route_ctx.update(make_route_info("/", query_params={"q": "b"}))
		flush_query_param_sync(session)
		assert state.q == "b"
		assert navigations(messages) == []


def test_r8_foreign_param_does_not_prevent_command_ack():
	class QState(ps.State):
		q: ps.QueryParam[str] = ""

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"q": "a", "utm": "x"})
	)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = QState()
		state.q = "b"
		flush_query_param_sync(session)
		route_ctx.update(make_route_info("/", query_params={"q": "b"}))
		flush_query_param_sync(session)
		messages.clear()
		route_ctx.update(make_route_info("/", query_params={"q": "c"}))
		flush_query_param_sync(session)
		route_ctx.update(make_route_info("/", query_params={"q": "b"}))
		flush_query_param_sync(session)
		assert state.q == "b"
		assert navigations(messages) == []


def test_r2_pending_commands_preserve_latest_write():
	class QState(ps.State):
		q: ps.QueryParam[str] = ""

	app, session, route_ctx = make_context(make_route_info("/", query_params={}))
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = QState()
		flush_query_param_sync(session)
		messages.clear()
		state.q = "first"
		flush_query_param_sync(session)
		state.q = "second"
		flush_query_param_sync(session)
		messages.clear()
		route_ctx.update(make_route_info("/", query_params={"q": "first"}))
		flush_query_param_sync(session)
		assert state.q == "second"
		assert [message["path"] for message in navigations(messages)] == ["/?q=second"]
		messages.clear()
		route_ctx.update(make_route_info("/", query_params={"q": "second"}))
		flush_query_param_sync(session)
		assert state.q == "second"
		assert navigations(messages) == []


def test_r3_bad_codec_commits_route_snapshot_and_valid_views():
	class Multi(ps.State):
		page: ps.QueryParam[int] = 1
		q: ps.QueryParam[str] = ""

	route_a = Route("a", ps.component(lambda: ps.div()))
	route_b = Route("b", ps.component(lambda: ps.div()))
	routes = RouteTree([route_a, route_b])
	app = ps.App(routes=[route_a, route_b])
	session = RenderSession("test", routes)
	session.connect(lambda _message: None)
	session.prerender(
		["/a"], make_route_info("/a", query_params={"page": "2", "q": "x"})
	)
	route_ctx = session.route_mounts["/a"].route
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = Multi()
		flush_query_param_sync(session)
		with pytest.raises(ValueError, match="expected int"):
			route_ctx.update(
				make_route_info("/b", query_params={"page": "abc", "q": "y"})
			)
		assert session.url.pathname == "/b"
		assert session.url._applied_params == {  # pyright: ignore[reportPrivateUsage]
			"page": "abc",
			"q": "y",
		}
		assert session.url.query_params == {"page": "abc", "q": "y"}
		assert state.page == 2
		assert state.q == "y"


def test_r4_writing_one_default_resets_sibling_defaults():
	class First(ps.State):
		page: ps.QueryParam[int] = 1

	class Second(ps.State):
		page: ps.QueryParam[int] = 2

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"page": "7"})
	)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		first = First()
		second = Second()
		flush_query_param_sync(session)
		assert first.page == 7
		assert second.page == 7
		messages.clear()
		first.page = 1
		flush_query_param_sync(session)
		assert first.page == 1
		assert second.page == 2
		assert [message["path"] for message in navigations(messages)] == ["/"]


def test_r5_new_view_converges_after_unflushed_write():
	class First(ps.State):
		q: ps.QueryParam[str] = ""

	class Second(ps.State):
		q: ps.QueryParam[str] = "other-default"

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"q": "url"})
	)
	session.connect(lambda _message: None)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		first = First()
		flush_query_param_sync(session)
		first.q = "typed"
		second = Second()
		assert first.q == "typed"
		assert second.q == "url"
		flush_query_param_sync(session)
		assert second.q == "typed"


def test_r9_bad_route_update_activates_mount_and_delivers_error():
	class Multi(ps.State):
		page: ps.QueryParam[int] = 1

	def render():
		Multi()
		return ps.div()

	route = Route("/", ps.component(render))
	routes = RouteTree([route])
	session = RenderSession("test", routes)
	session.prerender(["/"], make_route_info("/", query_params={"page": "2"}))
	mount = session.route_mounts["/"]
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	messages.clear()
	session.update_route("/", make_route_info("/", query_params={"page": "abc"}))
	flush_query_param_sync(session)
	assert mount.state == "active"
	assert any(message["type"] == "server_error" for message in messages)
	assert session.url._applied_params == {  # pyright: ignore[reportPrivateUsage]
		"page": "abc"
	}
	assert session.url.query_params == {"page": "abc"}


def test_client_can_renavigate_to_previously_commanded_value():
	class QState(ps.State):
		q: ps.QueryParam[str] = ""

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"q": "hello"})
	)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = QState()
		flush_query_param_sync(session)
		state.q = "world"
		flush_query_param_sync(session)
		route_ctx.update(make_route_info("/", query_params={"q": "world"}))
		flush_query_param_sync(session)
		route_ctx.update(make_route_info("/", query_params={"q": "hello"}))
		flush_query_param_sync(session)
		messages.clear()
		route_ctx.update(make_route_info("/", query_params={"q": "world"}))
		flush_query_param_sync(session)
		assert state.q == "world"
		assert navigations(messages) == []


def test_f3_write_before_first_route_info_survives_initial_apply():
	class QState(ps.State):
		q: ps.QueryParam[str] = ""

	def render():
		return ps.div()

	route = Route("/", ps.component(render))
	routes = RouteTree([route])
	session = RenderSession("test", routes)
	app = ps.App(routes=[route])
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session):
		state = QState()
		state.q = "set-before-route"
		flush_query_param_sync(session)
	session.prerender(["/"], make_route_info("/", query_params={}))
	flush_query_param_sync(session)
	with ps.PulseContext(
		app=app, render=session, route=session.route_mounts["/"].route
	):
		assert state.q == "set-before-route"
	assert len(navigations(messages)) == 1
	assert parse_qs(urlparse(str(navigations(messages)[0]["path"])).query)["q"] == [
		"set-before-route"
	]


def test_f4_failed_constructor_keeps_immediate_shared_write():
	class Boom(ps.State):
		q: ps.QueryParam[str] = ""

		def __init__(self):
			self.q = "half-written"
			raise RuntimeError("boom")

	class Later(ps.State):
		q: ps.QueryParam[str] = ""

	app, session, route_ctx = make_context(make_route_info("/", query_params={}))
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		with pytest.raises(RuntimeError, match="boom"):
			Boom()
		flush_query_param_sync(session)
		# The write belongs to the session, so it reaches the URL even though the
		# state that made it never finished constructing.
		assert len(navigations(messages)) == 1
		assert parse_qs(urlparse(str(navigations(messages)[0]["path"])).query)["q"] == [
			"half-written"
		]
		messages.clear()
		later = Later()
		flush_query_param_sync(session)
		assert later.q == "half-written"
	assert navigations(messages) == []


def test_f5_cross_route_declarations_have_independent_defaults():
	class FiltersA(ps.State):
		q: ps.QueryParam[str] = ""

	class FiltersB(ps.State):
		q: ps.QueryParam[str] = "fallback"

	app, session = make_two_route_session()
	session.connect(lambda _msg: None)
	session.prerender(["/a"], make_route_info("/a", query_params={}))
	with ps.PulseContext(
		app=app, render=session, route=session.route_mounts["/a"].route
	):
		first = FiltersA()
		flush_query_param_sync(session)
		assert first.q == ""
	session.prerender(["/b"], make_route_info("/b", query_params={}))
	with ps.PulseContext(
		app=app, render=session, route=session.route_mounts["/b"].route
	):
		second = FiltersB()
		assert second.q == "fallback"


def test_f5b_subclass_override_has_independent_default_and_shared_raw():
	class Base(ps.State):
		q: ps.QueryParam[str] = ""

	class Sub(Base):
		q: ps.QueryParam[str] = "sub-default"

	app, session, route_ctx = make_context(make_route_info("/", query_params={}))
	session.connect(lambda _msg: None)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		base = Base()
		sub = Sub()
		assert base.q == ""
		assert sub.q == "sub-default"
		base.q = "x"
		flush_query_param_sync(session)
		assert sub.q == "x"


def test_f6_nested_state_construction_coalesces_navigation():
	class Inner(ps.State):
		page: ps.QueryParam[int] = 1

	class Outer(ps.State):
		q: ps.QueryParam[str] = ""
		_inner: Inner

		def __init__(self):
			self.q = "outer"
			self._inner = Inner()
			self._inner.page = 5

	app, session, route_ctx = make_context(make_route_info("/", query_params={}))
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		Outer()
		flush_query_param_sync(session)
	navs = navigations(messages)
	assert len(navs) == 1
	query = parse_qs(urlparse(str(navs[0]["path"])).query)
	assert query["q"] == ["outer"]
	assert query["page"] == ["5"]


def test_f7_close_is_idempotent_and_prevents_resurrection():
	class QState(ps.State):
		q: ps.QueryParam[str] = ""

	app, session, route_ctx = make_context(make_route_info("/", query_params={}))
	session.connect(lambda _msg: None)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		QState()
		flush_query_param_sync(session)
	session.close()
	session.close()
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		with pytest.raises(RuntimeError, match="SessionUrl is closed"):
			QState()
	assert session.url._slots == {}  # pyright: ignore[reportPrivateUsage]
	assert session.url._sync_effect is None  # pyright: ignore[reportPrivateUsage]


def make_two_route_session():
	"""A session with routes /a and /b, nothing mounted yet."""

	def render():
		return ps.div()

	route_a = Route("a", ps.component(render))
	route_b = Route("b", ps.component(render))
	routes = RouteTree([route_a, route_b])
	app = ps.App(routes=[route_a, route_b])
	return app, RenderSession("test", routes)


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
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/b"].route
		):
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
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/b"].route
		):
			assert state.q == "fallback"

		session.close()

	def test_same_param_on_another_route_shares_slot(self):
		"""Overlapping mounts share the session slot; either write updates both."""

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

		info_b = make_route_info("/b", query_params={"q": "hello"})
		session.prerender(["/b"], info_b)
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/b"].route
		):
			b = FiltersB()
			flush_effects()

		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/b"].route
		):
			assert FiltersA.__dict__["q"].get_signal(a) is FiltersB.__dict__[
				"q"
			].get_signal(b)

			messages.clear()
			b.q = "from-b"
			assert a.q == "from-b"
			flush_query_param_sync(session)
			navs = navigations(messages)
			assert len(navs) == 1
			assert parse_qs(urlparse(str(navs[0]["path"])).query)["q"] == ["from-b"]

			messages.clear()
			a.q = "from-a"
			assert b.q == "from-a"
			flush_query_param_sync(session)
			navs = navigations(messages)
			assert len(navs) == 1
			assert parse_qs(urlparse(str(navs[0]["path"])).query)["q"] == ["from-a"]

		session.close()

	def test_release_keeps_slot_while_other_state_remains(self):
		"""Disposing one registrant leaves the session slot for the other."""

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
		with ps.PulseContext(
			app=app, render=session, route=session.route_mounts["/c"].route
		):
			state.q = "from-restored"
			flush_query_param_sync(session)
		navs = navigations(messages)
		assert len(navs) == 1
		assert navs[0].get("sourcePath") == "/c"
		parsed = urlparse(str(navs[0]["path"]))
		assert parsed.path == "/c"
		assert parse_qs(parsed.query)["q"] == ["from-restored"]

		session.close()


def test_r10_loading_a_value_equal_to_the_default_keeps_the_url():
	class QState(ps.State):
		q: ps.QueryParam[str] = "hello"

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"q": "hello", "other": "1"})
	)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = QState()
		flush_query_param_sync(session)
		assert state.q == "hello"
	assert navigations(messages) == []
	assert session.url.query_params == {"q": "hello", "other": "1"}


def test_r11_loading_a_sibling_default_does_not_reset_the_other_view():
	class First(ps.State):
		q: ps.QueryParam[str] = "a"

	class Second(ps.State):
		q: ps.QueryParam[str] = "b"

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"q": "a"})
	)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		first = First()
		second = Second()
		flush_query_param_sync(session)
		assert first.q == "a"
		assert second.q == "a"

		# A client navigation to the other view's default is just as authoritative.
		route_ctx.update(make_route_info("/", query_params={"q": "b"}))
		flush_query_param_sync(session)
		assert first.q == "b"
		assert second.q == "b"
	assert navigations(messages) == []
	assert session.url.query_params == {"q": "b"}


def test_r12_write_after_loading_the_default_still_reaches_the_url():
	class QState(ps.State):
		q: ps.QueryParam[str] = "hello"

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"q": "hello"})
	)
	messages: list[ServerMessage] = []
	session.connect(messages.append)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = QState()
		flush_query_param_sync(session)
		state.q = "world"
		flush_query_param_sync(session)
		assert state.q == "world"
		navs = navigations(messages)
		assert len(navs) == 1
		assert parse_qs(urlparse(str(navs[0]["path"])).query)["q"] == ["world"]

		# ...and going back to the default removes it again.
		state.q = "hello"
		flush_query_param_sync(session)
		navs = navigations(messages)
		assert len(navs) == 2
		assert "q" not in parse_qs(urlparse(str(navs[1]["path"])).query)


def test_r13_list_default_is_not_shared_across_sessions():
	class TagState(ps.State):
		tags: ps.QueryParam[list[str]] = []

	app, session, route_ctx = make_context(make_route_info("/", query_params={}))
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		first = TagState()
		flush_query_param_sync(session)
		first.tags.append("alpha")
		flush_query_param_sync(session)
		assert list(first.tags) == ["alpha"]

	app2, session2, route_ctx2 = make_context(make_route_info("/", query_params={}))
	messages: list[ServerMessage] = []
	session2.connect(messages.append)
	with ps.PulseContext(app=app2, render=session2, route=route_ctx2):
		second = TagState()
		flush_query_param_sync(session2)
		# The mutation above must not have leaked into the declaration default.
		assert list(second.tags) == []
	assert navigations(messages) == []


def test_r14_repr_outside_a_render_context_does_not_raise():
	class QState(ps.State):
		q: ps.QueryParam[str] = "hello"
		other: int = 3

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"q": "world"})
	)
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		state = QState()
		assert "q='world'" in repr(state)

	# Outside the render context the URL-synced field is unreadable, but a repr
	# must still work (logging, pytest assertion messages, ...).
	text = repr(state)
	assert "q=<unavailable>" in text
	assert "other=3" in text


def test_r15_disposing_the_last_holder_drops_the_view_but_keeps_the_slot():
	class QState(ps.State):
		page: ps.QueryParam[int] = 1

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"page": "3"})
	)
	session.connect(lambda _msg: None)
	scope = ResourceScope()
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		with scope:
			state = QState()
		assert state.page == 3
	slot = session.url._slots["page"]  # pyright: ignore[reportPrivateUsage]
	assert len(slot.views) == 1

	scope.dispose()
	assert slot.views == []
	# The URL string is the source of truth: the slot and its raw value stay.
	assert session.url._slots["page"] is slot  # pyright: ignore[reportPrivateUsage]
	assert slot.raw.value == "3"


def test_r16_view_survives_while_another_state_holds_it():
	class QState(ps.State):
		page: ps.QueryParam[int] = 1

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"page": "3"})
	)
	session.connect(lambda _msg: None)
	first_scope = ResourceScope()
	second_scope = ResourceScope()
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		with first_scope:
			QState()
		with second_scope:
			second = QState()

	slot = session.url._slots["page"]  # pyright: ignore[reportPrivateUsage]
	assert len(slot.views) == 1

	first_scope.dispose()
	assert len(slot.views) == 1
	session.update_route("/", make_route_info("/", query_params={"page": "7"}))
	flush_effects()
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		assert second.page == 7

	second_scope.dispose()
	assert slot.views == []


def test_r17_disposed_strict_view_does_not_break_later_url_updates():
	class StrictState(ps.State):
		page: ps.QueryParam[int] = 1

	class LooseState(ps.State):
		page: ps.QueryParam[str] = ""

	app, session, route_ctx = make_context(
		make_route_info("/", query_params={"page": "3"})
	)
	session.connect(lambda _msg: None)
	strict_scope = ResourceScope()
	loose_scope = ResourceScope()
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		with strict_scope:
			StrictState()
		with loose_scope:
			loose = LooseState()

	slot = session.url._slots["page"]  # pyright: ignore[reportPrivateUsage]
	assert len(slot.views) == 2

	strict_scope.dispose()
	assert len(slot.views) == 1

	# "not-a-number" does not decode for the strict view. Now that the view went
	# away with its state, it cannot fail the URL update for the live one.
	session.update_route("/", make_route_info("/", query_params={"page": "later"}))
	flush_effects()
	with ps.PulseContext(app=app, render=session, route=route_ctx):
		assert loose.page == "later"

	loose_scope.dispose()
