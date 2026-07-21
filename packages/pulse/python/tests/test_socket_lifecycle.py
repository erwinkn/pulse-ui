"""
Socket connect/disconnect lifecycle tests at the App level.

A render session has at most one current socket. When a client reconnects
before the old socket's disconnect event fires, the stale disconnect must not
tear down the new connection or strand the render session's cleanup timer.
"""

import asyncio
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.messages import ServerMessage
from pulse.queries.query import KeyedQueryResult
from pulse.reactive import Computed
from pulse.serializer import Serialized, deserialize, serialize
from pulse.test_helpers import wait_for
from pulse.user_session import CookieSessionStore


def make_app(monkeypatch: pytest.MonkeyPatch) -> ps.App:
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[])
	app.setup("http://example.com")
	return app


def make_environ(app: ps.App, sid: str) -> dict[str, str]:
	store = app.session_store
	assert isinstance(store, CookieSessionStore)
	cookie = store.encode(sid, {})
	return {"HTTP_COOKIE": f"{app.cookie.name}={cookie}"}


def make_route_info(pathname: str) -> ps.RouteInfo:
	return {
		"pathname": pathname,
		"hash": "",
		"query": "",
		"queryParams": {},
		"pathParams": {},
		"catchall": [],
	}


class CounterState(ps.State):
	value: str = "before"

	def mark_after_dead(self) -> None:
		self.value = "after-dead"


@ps.component
def Counter():
	with ps.init():
		state = CounterState()
	return ps.button(onClick=state.mark_after_dead)[state.value]


@pytest.mark.asyncio
async def test_stale_socket_disconnect_does_not_clobber_live_connection(
	monkeypatch: pytest.MonkeyPatch,
):
	app = make_app(monkeypatch)
	environ = make_environ(app, "user-1")
	auth = {"render_id": "render-1"}

	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect("socket-a", environ, auth)
	render = app.render_sessions["render-1"]
	assert render.connected

	# Client reconnects before the old socket's disconnect event fires
	await connect("socket-b", environ, auth)
	assert render.connected

	# The stale socket's disconnect must not disconnect the render
	disconnect("socket-a")
	assert render.connected
	assert app._render_cleanups == {}  # pyright: ignore[reportPrivateUsage]
	assert app._socket_to_render == {"socket-b": "render-1"}  # pyright: ignore[reportPrivateUsage]

	# Disconnect from the current socket tears it down and schedules cleanup
	disconnect("socket-b")
	assert not render.connected
	assert "render-1" in app._render_cleanups  # pyright: ignore[reportPrivateUsage]
	assert app._socket_to_render == {}  # pyright: ignore[reportPrivateUsage]

	await app.close()


@pytest.mark.asyncio
async def test_reconnect_before_disconnect_resyncs_mount_and_stale_queries(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[ps.Route("/", Counter)])
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	auth = {"render_id": "render-1"}
	connect = app.sio.handlers["/"]["connect"]
	messages: dict[str, list[ServerMessage]] = {}

	async def fake_emit(event: str, data: Any, *, to: str) -> None:
		if event == "message":
			message = deserialize(cast(Serialized, data))
			messages.setdefault(to, []).append(cast(ServerMessage, message))

	monkeypatch.setattr(app.sio, "emit", fake_emit)

	await connect("socket-a", environ, auth)
	render = app.render_sessions["render-1"]
	user_session = app.user_sessions["user-1"]
	with ps.PulseContext.update(session=user_session, render=render):
		initial = render.prerender(["/"], make_route_info("/"))["/"]
	assert initial["type"] == "vdom_init"

	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-a",
		serialize(
			{
				"type": "attach",
				"path": "/",
				"routeInfo": make_route_info("/"),
				"viewId": initial["viewId"],
				"revision": initial["revision"],
				"attachId": "attach-a",
				"instanceId": "instance-1",
			}
		),
	)
	await wait_for(
		lambda: any(
			message["type"] == "attach_ack" for message in messages.get("socket-a", [])
		)
	)
	assert messages["socket-a"] == [
		{
			"type": "attach_ack",
			"path": "/",
			"attachId": "attach-a",
			"viewId": initial["viewId"],
			"revision": initial["revision"],
		}
	]

	fetch_count = 0
	fresh_fetch_count = 0

	async def fetch() -> int:
		nonlocal fetch_count
		fetch_count += 1
		return fetch_count

	async def fetch_fresh() -> int:
		nonlocal fresh_fetch_count
		fresh_fetch_count += 1
		return fresh_fetch_count

	with ps.PulseContext.update(session=user_session, render=render):
		render.query_store.ensure(("value",))
		query = KeyedQueryResult(
			Computed(lambda: render.query_store.ensure(("value",))),
			fetch_fn=fetch,
			stale_time=0.0,
		)
		render.query_store.ensure(("fresh-value",))
		fresh_query = KeyedQueryResult(
			Computed(lambda: render.query_store.ensure(("fresh-value",))),
			fetch_fn=fetch_fresh,
			stale_time=1000.0,
		)
	await wait_for(lambda: query.data == 1)
	await wait_for(lambda: fresh_query.data == 1)

	# The browser has lost socket-a, but the server still considers it live.
	callback = next(iter(render.route_mounts["/"].tree.callbacks))
	render.execute_callback(
		"/", initial["viewId"], render.route_mounts["/"].revision, callback, []
	)
	render.flush()
	await wait_for(
		lambda: any(
			message["type"] == "vdom_update" for message in messages.get("socket-a", [])
		)
	)

	await connect("socket-b", environ, auth)
	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-b",
		serialize(
			{
				"type": "attach",
				"path": "/",
				"routeInfo": make_route_info("/"),
				"viewId": initial["viewId"],
				"revision": initial["revision"],
				"attachId": "attach-b",
				"instanceId": "instance-1",
			}
		),
	)
	await wait_for(lambda: fetch_count == 2)
	await wait_for(
		lambda: any(
			message["type"] == "attach_ack" for message in messages.get("socket-b", [])
		)
	)

	assert len(messages["socket-b"]) == 1
	ack = messages["socket-b"][0]
	assert ack["type"] == "attach_ack"
	assert ack["path"] == "/"
	assert ack["attachId"] == "attach-b"
	assert ack["viewId"] == initial["viewId"]
	assert ack["revision"] > initial["revision"]
	snapshot = ack.get("snapshot")
	assert snapshot is not None
	assert snapshot["viewId"] == ack["viewId"]
	assert snapshot["revision"] == ack["revision"]
	assert "after-dead" in str(snapshot["vdom"])
	assert fresh_fetch_count == 1

	query.dispose()
	fresh_query.dispose()
	await app.close()


class TogglableDenyMiddleware(ps.PulseMiddleware):
	deny: bool

	def __init__(self) -> None:
		super().__init__()
		self.deny = False

	@override
	async def connect(self, *, request: Any, session: Any, next: Any) -> Any:
		if self.deny:
			return ps.Deny()
		return await next()


@pytest.mark.asyncio
async def test_denied_reconnect_does_not_destroy_existing_render(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	mw = TogglableDenyMiddleware()
	app = ps.App(routes=[], middleware=mw)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	auth = {"render_id": "render-1"}
	connect = app.sio.handlers["/"]["connect"]

	# Initial connection is allowed
	await connect("socket-a", environ, auth)
	render = app.render_sessions["render-1"]
	assert render.connected

	# Client reconnects (e.g. flaky network) but is now denied. The denied
	# reconnect must NOT tear down the live render the original socket uses.
	mw.deny = True
	with pytest.raises(ConnectionRefusedError):
		await connect("socket-b", environ, auth)

	assert "render-1" in app.render_sessions
	assert render.connected
	# The original socket's mapping is untouched
	assert app._socket_to_render == {"socket-a": "render-1"}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_socket == {"render-1": "socket-a"}  # pyright: ignore[reportPrivateUsage]

	await app.close()


@pytest.mark.asyncio
async def test_denied_fresh_connection_disposes_created_render(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	mw = TogglableDenyMiddleware()
	mw.deny = True
	app = ps.App(routes=[], middleware=mw)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]

	# A brand-new render created for this attempt is cleaned up on deny
	with pytest.raises(ConnectionRefusedError):
		await connect("socket-a", environ, {"render_id": "render-new"})

	assert app.render_sessions == {}
	assert app._socket_to_render == {}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_socket == {}  # pyright: ignore[reportPrivateUsage]

	await app.close()


class RaisingConnectMiddleware(ps.PulseMiddleware):
	@override
	async def connect(self, *, request: Any, session: Any, next: Any) -> Any:
		raise RuntimeError("boom in connect middleware")


@pytest.mark.asyncio
async def test_connect_middleware_exception_is_surfaced_after_bind(
	monkeypatch: pytest.MonkeyPatch,
):
	"""A connect-middleware exception is treated as allow, and the error is
	delivered to the now-bound client (not dropped pre-bind)."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[], middleware=RaisingConnectMiddleware())
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]

	sent: list[tuple[Any, ...]] = []

	async def fake_emit(*args: Any, **kwargs: Any) -> None:
		sent.append(args)

	monkeypatch.setattr(app.sio, "emit", fake_emit)

	# Fresh render: connection is allowed despite the middleware raising
	await connect("socket-a", environ, {"render_id": "render-1"})
	render = app.render_sessions["render-1"]
	assert render.connected

	# Give the emit task a tick to run
	await asyncio.sleep(0)

	# A server_error for the connect phase reached the (bound) client, and it
	# carries the real traceback (not the "NoneType: None" that format_exc()
	# yields when report_error runs outside the except block).
	connect_errors = [
		args
		for args in sent
		if args
		and args[0] == "message"
		and "server_error" in str(args)
		and "connect" in str(args)
	]
	assert connect_errors, sent
	payload_text = str(connect_errors[0])
	assert "boom in connect middleware" in payload_text
	assert "NoneType: None" not in payload_text

	await app.close()


@pytest.mark.asyncio
async def test_close_render_unmaps_socket(monkeypatch: pytest.MonkeyPatch):
	app = make_app(monkeypatch)
	environ = make_environ(app, "user-1")
	auth = {"render_id": "render-1"}

	connect = app.sio.handlers["/"]["connect"]
	await connect("socket-a", environ, auth)

	app.close_render("render-1")
	assert app._socket_to_render == {}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_socket == {}  # pyright: ignore[reportPrivateUsage]

	await app.close()
