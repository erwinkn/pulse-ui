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
