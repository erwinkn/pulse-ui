"""
Socket connect/disconnect lifecycle tests at the App level.

A render session has at most one current socket. When a client reconnects
before the old socket's disconnect event fires, the stale disconnect must not
tear down the new connection or strand the render session's cleanup timer.
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, cast, override

import httpx
import pulse as ps
import pytest
from pulse.messages import ServerMessage
from pulse.queries.query import KeyedQueryResult
from pulse.reactive import Computed
from pulse.serializer import Serialized, deserialize, serialize
from pulse.test_helpers import wait_for
from pulse.user_session import CookieSessionStore
from socketio.exceptions import ConnectionRefusedError as SocketIOConnectionRefusedError

type ConnectHandler = Callable[
	[str, dict[str, str], dict[str, str] | None], Coroutine[Any, Any, None]
]


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


def connect_handler(app: ps.App) -> ConnectHandler:
	return cast(ConnectHandler, app.sio.handlers["/"]["connect"])


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
	auth = {
		"render_id": "render-1",
		"__pulse_page_instance_id": "page-a",
	}

	connect = connect_handler(app)
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
		render.prerender(["/"], make_route_info("/"))

	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-a",
		serialize(
			{
				"type": "attach",
				"path": "/",
				"routeInfo": make_route_info("/"),
				"attachId": "attach-a",
			}
		),
	)
	await wait_for(
		lambda: any(
			message["type"] == "attach_ack" for message in messages.get("socket-a", [])
		)
	)
	assert not [
		message for message in messages["socket-a"] if message["type"] == "vdom_init"
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
	render.execute_callback("/", callback, [])
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
				"attachId": "attach-b",
			}
		),
	)
	await wait_for(lambda: fetch_count == 2)
	await wait_for(
		lambda: any(
			message["type"] == "attach_ack" for message in messages.get("socket-b", [])
		)
	)

	init_messages = [
		message for message in messages["socket-b"] if message["type"] == "vdom_init"
	]
	assert len(init_messages) == 1
	assert "after-dead" in str(init_messages[0]["vdom"])
	assert fresh_fetch_count == 1

	query.dispose()
	fresh_query.dispose()
	await app.close()


@pytest.mark.asyncio
async def test_legacy_client_reconnect_still_replaces_its_socket(
	monkeypatch: pytest.MonkeyPatch,
):
	app = make_app(monkeypatch)
	environ = make_environ(app, "user-1")
	connect = connect_handler(app)
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect("socket-a", environ, {"render_id": "render-1"})
	await connect("socket-b", environ, {"render_id": "render-1"})
	disconnect("socket-a")

	assert app.render_sessions["render-1"].connected
	assert app._socket_to_render == {"socket-b": "render-1"}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_page_instance == {"render-1": None}  # pyright: ignore[reportPrivateUsage]

	await app.close()


@pytest.mark.asyncio
async def test_different_page_instance_cannot_evict_live_render(
	monkeypatch: pytest.MonkeyPatch,
):
	app = make_app(monkeypatch)
	environ = make_environ(app, "user-1")
	connect = connect_handler(app)
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect(
		"socket-a",
		environ,
		{"render_id": "render-1", "__pulse_page_instance_id": "page-a"},
	)
	render = app.render_sessions["render-1"]

	with pytest.raises(SocketIOConnectionRefusedError) as exc_info:
		await connect(
			"socket-b",
			environ,
			{"render_id": "render-1", "__pulse_page_instance_id": "page-b"},
		)

	assert exc_info.value.error_args == {
		"message": "Render session is active in another page instance",
		"data": {"code": "render_id_collision"},
	}
	assert render.connected
	assert app._socket_to_render == {"socket-a": "render-1"}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_socket == {"render-1": "socket-a"}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_page_instance == {"render-1": "page-a"}  # pyright: ignore[reportPrivateUsage]

	disconnect("socket-a")
	with pytest.raises(SocketIOConnectionRefusedError):
		await connect(
			"socket-c",
			environ,
			{"render_id": "render-1", "__pulse_page_instance_id": "page-b"},
		)
	assert not render.connected
	assert app._render_to_page_instance == {"render-1": "page-a"}  # pyright: ignore[reportPrivateUsage]

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


class BlockingReconnectMiddleware(ps.PulseMiddleware):
	calls: int
	reconnect_started: asyncio.Event
	release_reconnect: asyncio.Event
	successor_started: asyncio.Event
	release_successor: asyncio.Event

	def __init__(self) -> None:
		super().__init__()
		self.calls = 0
		self.reconnect_started = asyncio.Event()
		self.release_reconnect = asyncio.Event()
		self.successor_started = asyncio.Event()
		self.release_successor = asyncio.Event()

	@override
	async def connect(self, *, request: Any, session: Any, next: Any) -> Any:
		self.calls += 1
		if self.calls == 2:
			self.reconnect_started.set()
			await self.release_reconnect.wait()
		elif self.calls == 3:
			self.successor_started.set()
			await self.release_successor.wait()
		return await next()


class OrderedConnectMiddleware(ps.PulseMiddleware):
	deny_first: bool
	calls: int
	first_started: asyncio.Event
	release_first: asyncio.Event

	def __init__(self, *, deny_first: bool) -> None:
		super().__init__()
		self.deny_first = deny_first
		self.calls = 0
		self.first_started = asyncio.Event()
		self.release_first = asyncio.Event()

	@override
	async def connect(self, *, request: Any, session: Any, next: Any) -> Any:
		self.calls += 1
		if self.calls == 1:
			self.first_started.set()
			await self.release_first.wait()
			if self.deny_first:
				return ps.Deny()
			return await next()
		if not self.deny_first:
			return ps.Deny()
		return await next()


@pytest.mark.asyncio
@pytest.mark.parametrize("successor_page", ["page-a", "page-b"])
async def test_reconnect_cannot_overwrite_render_recreated_during_middleware(
	monkeypatch: pytest.MonkeyPatch,
	successor_page: str,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	middleware = BlockingReconnectMiddleware()
	app = ps.App(routes=[], middleware=middleware)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = connect_handler(app)
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect(
		"socket-a",
		environ,
		{"render_id": "render-1", "__pulse_page_instance_id": "page-a"},
	)
	disconnect("socket-a")
	stale_reconnect = asyncio.create_task(
		connect(
			"socket-a2",
			environ,
			{"render_id": "render-1", "__pulse_page_instance_id": "page-a"},
		)
	)
	await middleware.reconnect_started.wait()

	app.close_render("render-1")
	successor = asyncio.create_task(
		connect(
			"socket-b",
			environ,
			{"render_id": "render-1", "__pulse_page_instance_id": successor_page},
		)
	)
	await middleware.successor_started.wait()
	new_render = app.render_sessions["render-1"]
	middleware.release_reconnect.set()

	with pytest.raises(SocketIOConnectionRefusedError) as exc_info:
		await stale_reconnect

	assert exc_info.value.error_args["data"] == {"code": "render_id_collision"}
	assert app._render_to_page_instance == {"render-1": successor_page}  # pyright: ignore[reportPrivateUsage]
	middleware.release_successor.set()
	await successor

	assert new_render.connected
	assert app._socket_to_render == {"socket-b": "render-1"}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_socket == {"render-1": "socket-b"}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_page_instance == {"render-1": successor_page}  # pyright: ignore[reportPrivateUsage]

	await app.close()


@pytest.mark.asyncio
async def test_older_same_page_connect_cannot_evict_newer_socket(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	middleware = BlockingReconnectMiddleware()
	app = ps.App(routes=[], middleware=middleware)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = connect_handler(app)
	auth = {
		"render_id": "render-1",
		"__pulse_page_instance_id": "page-a",
	}

	await connect("socket-initial", environ, auth)
	older_connect = asyncio.create_task(connect("socket-older", environ, auth))
	await middleware.reconnect_started.wait()
	newer_connect = asyncio.create_task(connect("socket-newer", environ, auth))
	await middleware.successor_started.wait()

	middleware.release_successor.set()
	await newer_connect
	middleware.release_reconnect.set()
	with pytest.raises(SocketIOConnectionRefusedError):
		await older_connect

	assert app.render_sessions["render-1"].connected
	assert app._socket_to_render == {"socket-newer": "render-1"}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_socket == {"render-1": "socket-newer"}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_page_instance == {"render-1": "page-a"}  # pyright: ignore[reportPrivateUsage]

	await app.close()


@pytest.mark.asyncio
async def test_older_denied_connect_cannot_close_newer_socket(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	middleware = OrderedConnectMiddleware(deny_first=True)
	app = ps.App(routes=[], middleware=middleware)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = connect_handler(app)
	auth = {
		"render_id": "render-1",
		"__pulse_page_instance_id": "page-a",
	}

	older_connect = asyncio.create_task(connect("socket-older", environ, auth))
	await middleware.first_started.wait()
	await connect("socket-newer", environ, auth)
	middleware.release_first.set()

	with pytest.raises(SocketIOConnectionRefusedError):
		await older_connect
	assert app.render_sessions["render-1"].connected
	assert app._render_to_socket == {"render-1": "socket-newer"}  # pyright: ignore[reportPrivateUsage]

	await app.close()


@pytest.mark.asyncio
async def test_newer_denied_connect_leaves_stale_render_expirable(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	middleware = OrderedConnectMiddleware(deny_first=False)
	app = ps.App(routes=[], middleware=middleware)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = connect_handler(app)
	auth = {
		"render_id": "render-1",
		"__pulse_page_instance_id": "page-a",
	}

	older_connect = asyncio.create_task(connect("socket-older", environ, auth))
	await middleware.first_started.wait()
	with pytest.raises(ConnectionRefusedError):
		await connect("socket-newer", environ, auth)
	middleware.release_first.set()
	with pytest.raises(SocketIOConnectionRefusedError):
		await older_connect

	assert not app.render_sessions["render-1"].connected
	assert "render-1" in app._render_cleanups  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_socket == {}  # pyright: ignore[reportPrivateUsage]

	await app.close()


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
	connect = connect_handler(app)

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
	connect = connect_handler(app)

	# A brand-new render created for this attempt is cleaned up on deny
	with pytest.raises(ConnectionRefusedError):
		await connect("socket-a", environ, {"render_id": "render-new"})

	assert app.render_sessions == {}
	assert app._socket_to_render == {}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_socket == {}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_page_instance == {}  # pyright: ignore[reportPrivateUsage]
	assert app._render_connect_attempts == {}  # pyright: ignore[reportPrivateUsage]

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
	connect = connect_handler(app)

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


@ps.component
def _hello():
	return ps.div()["hello"]


@pytest.mark.asyncio
async def test_shell_render_reaped_on_short_ttl(monkeypatch: pytest.MonkeyPatch):
	"""A render minted on stale-render-id reconnect (no mounts, only told the
	client to reload) is reaped on the short shell TTL, not the long
	session_timeout reconnect grace window."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[], session_timeout=600.0, shell_render_timeout=5.0)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]

	# render id the server no longer has -> placeholder shell render
	await connect("socket-a", environ, {"render_id": "shell-1"})
	render = app.render_sessions["shell-1"]
	assert render.is_shell
	assert render.route_mounts == {}

	loop = asyncio.get_running_loop()
	disconnect("socket-a")
	handle = app._render_cleanups["shell-1"]  # pyright: ignore[reportPrivateUsage]
	delay = handle.when() - loop.time()
	assert delay == pytest.approx(5.0, abs=0.5)
	assert delay < app.session_timeout

	await app.close()


@pytest.mark.asyncio
async def test_real_render_with_mounts_honors_session_timeout(
	monkeypatch: pytest.MonkeyPatch,
):
	"""A real render with route mounts is NOT reaped early; it keeps the full
	session_timeout reconnect grace window."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(
		routes=[ps.Route("a", _hello)],
		session_timeout=600.0,
		shell_render_timeout=5.0,
	)
	app.setup("http://example.com")
	store = app.session_store
	assert isinstance(store, CookieSessionStore)
	session = await app.get_or_create_session(store.encode("user-1", {}))

	# A real render (created via prerender, not the socket-stale branch) with a mount
	render = app.create_render("real-1", session)
	with ps.PulseContext.update(render=render):
		render.prerender(["/a"])
	assert not render.is_shell
	assert render.route_mounts

	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]
	await connect("socket-a", environ, {"render_id": "real-1"})
	assert render.connected

	loop = asyncio.get_running_loop()
	disconnect("socket-a")
	handle = app._render_cleanups["real-1"]  # pyright: ignore[reportPrivateUsage]
	delay = handle.when() - loop.time()
	assert delay == pytest.approx(600.0, abs=1.0)

	await app.close()


@pytest.mark.asyncio
async def test_shell_reconnect_cancels_short_ttl(monkeypatch: pytest.MonkeyPatch):
	"""If the client reconnects to the shell render before the short TTL fires,
	the pending cleanup is cancelled and the render survives."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[], session_timeout=600.0, shell_render_timeout=5.0)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect("socket-a", environ, {"render_id": "shell-1"})
	disconnect("socket-a")
	assert "shell-1" in app._render_cleanups  # pyright: ignore[reportPrivateUsage]

	# Reconnect to the same render id before the short TTL fires
	await connect("socket-b", environ, {"render_id": "shell-1"})
	assert "shell-1" not in app._render_cleanups  # pyright: ignore[reportPrivateUsage]
	assert app.render_sessions["shell-1"].connected

	await app.close()


@pytest.mark.asyncio
async def test_shell_that_gains_mount_is_not_reaped_early(
	monkeypatch: pytest.MonkeyPatch,
):
	"""A shell that gains a real mount (e.g. a prerender reuses its id) stops
	being a shell and falls back to the full session_timeout on disconnect."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(
		routes=[ps.Route("a", _hello)],
		session_timeout=600.0,
		shell_render_timeout=5.0,
	)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect("socket-a", environ, {"render_id": "shell-1"})
	render = app.render_sessions["shell-1"]
	assert render.is_shell

	# A prerender reuses this id and mounts a real route
	with ps.PulseContext.update(render=render):
		render.prerender(["/a"])
	assert not render.is_shell

	loop = asyncio.get_running_loop()
	disconnect("socket-a")
	handle = app._render_cleanups["shell-1"]  # pyright: ignore[reportPrivateUsage]
	delay = handle.when() - loop.time()
	assert delay == pytest.approx(600.0, abs=1.0)

	await app.close()


@pytest.mark.asyncio
async def test_shell_ttl_fires_and_closes_render(monkeypatch: pytest.MonkeyPatch):
	"""When the shell TTL fires, the render is actually removed."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[], session_timeout=600.0, shell_render_timeout=0.05)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect("socket-a", environ, {"render_id": "shell-1"})
	disconnect("socket-a")
	assert "shell-1" in app.render_sessions

	await wait_for(lambda: "shell-1" not in app.render_sessions)

	await app.close()


class _DenySecondConnect(ps.PulseMiddleware):
	calls: int = 0

	@override
	async def connect(self, *, request: Any, session: Any, next: Any) -> Any:
		self.calls += 1
		if self.calls >= 2:
			return ps.Deny()
		return await next()


@pytest.mark.asyncio
async def test_failed_shell_reconnect_keeps_short_ttl(
	monkeypatch: pytest.MonkeyPatch,
):
	"""A failed reconnect (e.g. connect middleware Deny) to a disconnected
	shell must reschedule the short shell TTL, not the full session_timeout."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(
		routes=[],
		middleware=_DenySecondConnect(),
		session_timeout=600.0,
		shell_render_timeout=5.0,
	)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect("socket-a", environ, {"render_id": "shell-1"})
	disconnect("socket-a")

	with pytest.raises(ConnectionRefusedError):
		await connect("socket-b", environ, {"render_id": "shell-1"})

	loop = asyncio.get_running_loop()
	handle = app._render_cleanups["shell-1"]  # pyright: ignore[reportPrivateUsage]
	delay = handle.when() - loop.time()
	assert delay == pytest.approx(5.0, abs=0.5)

	await app.close()


async def _post_prerender(
	app: ps.App, environ: dict[str, str], render_id: str, pathname: str
) -> httpx.Response:
	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		return await client.post(
			"/_pulse/prerender",
			json={"paths": [pathname], "routeInfo": make_route_info(pathname)},
			headers={
				"Cookie": environ["HTTP_COOKIE"],
				"X-Pulse-Render-Id": render_id,
			},
		)


@pytest.mark.asyncio
async def test_prerender_reuse_reschedules_long_timeout_after_mount(
	monkeypatch: pytest.MonkeyPatch,
):
	"""A prerender that reuses a disconnected shell's id and mounts a route
	turns it into a real render: cleanup is rescheduled to session_timeout."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(
		routes=[ps.Route("a", _hello)],
		session_timeout=600.0,
		shell_render_timeout=5.0,
	)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect("socket-a", environ, {"render_id": "shell-1"})
	disconnect("socket-a")

	resp = await _post_prerender(app, environ, "shell-1", "/a")
	assert resp.status_code == 200

	render = app.render_sessions["shell-1"]
	assert not render.is_shell
	loop = asyncio.get_running_loop()
	handle = app._render_cleanups["shell-1"]  # pyright: ignore[reportPrivateUsage]
	delay = handle.when() - loop.time()
	assert delay == pytest.approx(600.0, abs=1.0)

	await app.close()


class _RedirectPrerender(ps.PulseMiddleware):
	@override
	async def prerender(
		self, *, payload: Any, request: Any, session: Any, next: Any
	) -> Any:
		return ps.Redirect(path="/elsewhere")


@pytest.mark.asyncio
async def test_prerender_reuse_that_stays_mountless_keeps_short_ttl(
	monkeypatch: pytest.MonkeyPatch,
):
	"""A prerender that reuses a disconnected shell's id but mounts nothing
	(e.g. redirects) leaves it a shell: cleanup stays on the short TTL."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(
		routes=[ps.Route("a", _hello)],
		middleware=_RedirectPrerender(),
		session_timeout=600.0,
		shell_render_timeout=5.0,
	)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect("socket-a", environ, {"render_id": "shell-1"})
	disconnect("socket-a")

	resp = await _post_prerender(app, environ, "shell-1", "/a")
	assert resp.status_code == 200
	assert resp.json() == {"redirect": "/elsewhere"}

	render = app.render_sessions["shell-1"]
	assert render.is_shell
	loop = asyncio.get_running_loop()
	handle = app._render_cleanups["shell-1"]  # pyright: ignore[reportPrivateUsage]
	delay = handle.when() - loop.time()
	assert delay == pytest.approx(5.0, abs=0.5)

	await app.close()


@pytest.mark.asyncio
async def test_prerender_on_render_reaped_mid_request_mints_fresh_render(
	monkeypatch: pytest.MonkeyPatch,
):
	"""If the render referenced by X-Pulse-Render-Id is closed between HTTP
	middleware resolution and the prerender handler, a fresh render is minted
	instead of prerendering on the dead one."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(
		routes=[ps.Route("a", _hello)],
		session_timeout=600.0,
		shell_render_timeout=5.0,
	)
	app.setup("http://example.com")
	environ = make_environ(app, "user-1")
	connect = app.sio.handlers["/"]["connect"]
	disconnect = app.sio.handlers["/"]["disconnect"]

	await connect("socket-a", environ, {"render_id": "shell-1"})
	disconnect("socket-a")
	stale = app.render_sessions["shell-1"]

	# Simulate the TTL firing while the request is in flight: the render is
	# closed before the prerender handler runs.
	app.close_render("shell-1")
	assert "shell-1" not in app.render_sessions

	resp = await _post_prerender(app, environ, "shell-1", "/a")
	assert resp.status_code == 200
	payload = deserialize(resp.json())
	new_render_id = payload["directives"]["headers"]["X-Pulse-Render-Id"]
	assert new_render_id != "shell-1"
	assert new_render_id in app.render_sessions
	assert app.render_sessions[new_render_id] is not stale

	await app.close()


@pytest.mark.asyncio
async def test_close_render_unmaps_socket(monkeypatch: pytest.MonkeyPatch):
	app = make_app(monkeypatch)
	environ = make_environ(app, "user-1")
	auth = {"render_id": "render-1"}

	connect = connect_handler(app)
	await connect("socket-a", environ, auth)

	app.close_render("render-1")
	assert app._socket_to_render == {}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_socket == {}  # pyright: ignore[reportPrivateUsage]
	assert app._render_to_page_instance == {}  # pyright: ignore[reportPrivateUsage]

	await app.close()
