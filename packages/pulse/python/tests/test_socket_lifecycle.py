"""
Socket connect/disconnect lifecycle tests at the App level.

A render session has at most one current socket. When a client reconnects
before the old socket's disconnect event fires, the stale disconnect must not
tear down the new connection or strand the render session's cleanup timer.
"""

import asyncio
from typing import Any, override

import pulse as ps
import pytest
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
