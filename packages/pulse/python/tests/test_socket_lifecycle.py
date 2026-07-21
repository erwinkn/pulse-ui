"""
Socket connect/disconnect lifecycle tests at the App level.

A render session has at most one current socket. When a client reconnects
before the old socket's disconnect event fires, the stale disconnect must not
tear down the new connection or strand the render session's cleanup timer.
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, cast, override

import pulse as ps
import pytest
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
