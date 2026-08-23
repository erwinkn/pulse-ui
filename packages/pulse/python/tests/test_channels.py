import asyncio
import logging
from types import SimpleNamespace
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.app import App
from pulse.channel import (
	MAX_QUEUED_EVENTS,
	ChannelDetached,
	ChannelDisconnected,
	ChannelRemoteError,
)
from pulse.messages import (
	ClientChannelEventMessage,
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
)
from pulse.middleware import Deny, PulseMiddleware, stack
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteContext, RouteInfo, RouteTree
from pulse.serializer import serialize
from pulse.test_helpers import wait_for
from pulse.user_session import UserSession


class DummyRender:
	id: str

	def __init__(self, rid: str = "render-1") -> None:
		self.id = rid
		self.sent: list[dict[str, Any]] = []

	def send(self, message: dict[str, Any]):
		self.sent.append(message)


def _route_info() -> RouteInfo:
	return cast(
		RouteInfo,
		cast(
			object,
			{
				"pathname": "/",
				"hash": "",
				"query": "",
				"queryParams": {},
				"pathParams": {},
				"catchall": [],
			},
		),
	)


def as_event(message: object) -> ClientChannelEventMessage:
	return cast(ClientChannelEventMessage, message)


def as_request(message: object) -> ClientChannelRequestMessage:
	return cast(ClientChannelRequestMessage, message)


def as_response(message: object) -> ClientChannelResponseMessage:
	return cast(ClientChannelResponseMessage, message)


@ps.component
def _leaky_redirect_page():
	channel = ps.channel("leaky")
	channel.on("ping", lambda _: None)
	raise ps.RedirectInterrupt("/other", replace=True)


@ps.component
def _other_page():
	return ps.div()


def build_session(*, connected: bool = False, with_route: bool = False):
	def page():
		return ps.div()

	route = Route("/", ps.component(page))
	routes = RouteTree([route]) if with_route else None
	app = ps.App(routes=[route] if with_route else None)
	dummy = DummyRender()
	session = SimpleNamespace(sid="session-1", data={})
	real_render = ps.RenderSession(
		dummy.id, routes or app.routes, server_address="http://localhost"
	)
	real_render.send = dummy.send  # pyright: ignore[reportAttributeAccessIssue]
	real_render.connected = connected
	app.render_sessions[real_render.id] = real_render
	app._render_to_user[real_render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	route_ctx = None
	if with_route:
		with ps.PulseContext(app=app):
			real_render.prerender(["/"], _route_info())
		route_ctx = real_render.route_mounts["/"].route
	return app, dummy, session, real_render, route_ctx


def ctx(
	app: App,
	session: Any,
	render: RenderSession,
	route: RouteContext | None = None,
):
	return ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=render,
		route=route,
	)


@pytest.mark.asyncio
async def test_empty_identifier_raises():
	app, _dummy, session, render, _route = build_session()
	with ctx(app, session, render):
		with pytest.raises(ValueError, match="empty"):
			ps.channel("")


@pytest.mark.asyncio
async def test_none_identifier_generates_uuid():
	app, _dummy, session, render, route = build_session(with_route=True)
	with ctx(app, session, render, route):
		channel = ps.channel()
	assert len(channel.id) == 36


@pytest.mark.asyncio
async def test_route_lifetime_requires_route_context():
	app, _dummy, session, render, _route = build_session()
	with ctx(app, session, render):
		with pytest.raises(RuntimeError, match="route context"):
			ps.channel("x")
		handle = ps.channel("x", lifetime="tab")
	assert handle.lifetime == "tab"
	assert handle is not None


@pytest.mark.asyncio
async def test_invalid_lifetime_raises():
	app, _dummy, session, render, route = build_session(with_route=True)
	with ctx(app, session, render, route):
		with pytest.raises(ValueError, match="lifetime"):
			ps.channel("x", lifetime=cast(Any, "typo"))


@pytest.mark.asyncio
async def test_intern_same_handle_during_route_mount():
	app, _dummy, session, render, route = build_session(with_route=True)
	with ctx(app, session, render, route):
		first = ps.channel("foo")
		second = ps.channel("foo")
	assert first is second


@pytest.mark.asyncio
async def test_new_handle_after_route_detach():
	app, dummy, session, render, route = build_session(with_route=True)
	with ctx(app, session, render, route):
		first = ps.channel("foo")
		first.on("ping", lambda _: None)
	render.channels.detach_route("/")
	with pytest.raises(ChannelDetached):
		first.on("pong", lambda _: None)
	first.emit("dropped")
	assert dummy.sent == []
	with ctx(app, session, render, route):
		second = ps.channel("foo")
	assert second is not first
	second.on("ping", lambda _: None)


@pytest.mark.asyncio
async def test_tab_handle_survives_route_unmount():
	app, _dummy, session, render, route = build_session(with_route=True)
	received: list[Any] = []
	with ctx(app, session, render, route):
		handle = ps.channel("tab-box", lifetime="tab")
		handle.on("ping", lambda payload: received.append(payload))
	render.channels.detach_route("/")
	handle.on("still-ok", lambda _: None)
	with ctx(app, session, render, route):
		render.channels.handle_event(
			as_event(
				{
					"type": "channel",
					"action": "event",
					"channel": "tab-box",
					"event": "ping",
					"payload": 1,
				},
			)
		)
	await asyncio.sleep(0)
	assert received == [1]


@pytest.mark.asyncio
async def test_emit_sends_channel_event():
	app, dummy, session, render, _route = build_session()
	with ctx(app, session, render):
		channel = ps.channel("form-channel", lifetime="tab")
		channel.emit("setValues", {"values": {"a": 1}})
	assert dummy.sent == [
		{
			"type": "channel",
			"action": "event",
			"channel": "form-channel",
			"event": "setValues",
			"payload": {"values": {"a": 1}},
		}
	]


@pytest.mark.asyncio
async def test_request_resolves_on_response():
	app, dummy, session, render, _route = build_session(connected=True)
	with ctx(app, session, render):
		channel = ps.channel("req-channel", lifetime="tab")
		pending = asyncio.create_task(channel.request("get", {"x": 1}))
	await asyncio.sleep(0)
	assert dummy.sent[0]["type"] == "channel"
	assert dummy.sent[0]["action"] == "request"
	request_id = dummy.sent[0]["requestId"]
	render.channels.handle_response(
		as_response(
			{
				"type": "channel",
				"action": "response",
				"channel": "req-channel",
				"responseTo": request_id,
				"payload": {"x": 2},
			},
		)
	)
	assert await pending == {"x": 2}


@pytest.mark.asyncio
async def test_request_maps_remote_error():
	app, dummy, session, render, _route = build_session(connected=True)
	with ctx(app, session, render):
		channel = ps.channel("err-channel", lifetime="tab")
		pending = asyncio.create_task(channel.request("get"))
	await asyncio.sleep(0)
	render.channels.handle_response(
		as_response(
			{
				"type": "channel",
				"action": "response",
				"channel": "err-channel",
				"responseTo": dummy.sent[0]["requestId"],
				"error": {"code": "no_handler", "message": "missing"},
			},
		)
	)
	with pytest.raises(ChannelRemoteError, match="no_handler") as exc:
		await pending
	assert exc.value.code == "no_handler"


@pytest.mark.asyncio
async def test_request_fail_fast_when_disconnected():
	app, dummy, session, render, _route = build_session(connected=False)
	with ctx(app, session, render):
		channel = ps.channel("down", lifetime="tab")
		with pytest.raises(ChannelDisconnected):
			await channel.request("get")
	assert dummy.sent == []


@pytest.mark.asyncio
async def test_request_nacks_without_handler():
	app, dummy, session, render, _route = build_session()
	with ctx(app, session, render):
		ps.channel("empty", lifetime="tab")
	with ctx(app, session, render):
		await render.channels.handle_request(
			as_request(
				{
					"type": "channel",
					"action": "request",
					"channel": "empty",
					"event": "missing",
					"requestId": "req-1",
				},
			)
		)
	assert dummy.sent[-1] == {
		"type": "channel",
		"action": "response",
		"channel": "empty",
		"responseTo": "req-1",
		"error": {
			"code": "no_handler",
			"message": "No handler for 'missing' on channel 'empty'",
		},
	}


@pytest.mark.asyncio
async def test_event_without_listener_is_dropped():
	app, dummy, session, render, _route = build_session()
	with ctx(app, session, render):
		ps.channel("quiet", lifetime="tab")
	with ctx(app, session, render):
		render.channels.handle_event(
			as_event(
				{
					"type": "channel",
					"action": "event",
					"channel": "quiet",
					"event": "ping",
					"payload": 1,
				},
			)
		)
	assert dummy.sent == []


@pytest.mark.asyncio
async def test_event_fans_out_to_two_handles():
	app, _dummy, session, render, route = build_session(with_route=True)
	seen: list[str] = []
	with ctx(app, session, render, route):
		a = ps.channel("shared")
		b = ps.channel("shared", lifetime="tab")
		a.on("ping", lambda _: seen.append("a"))
		b.on("ping", lambda _: seen.append("b"))
	with ctx(app, session, render, route):
		render.channels.handle_event(
			as_event(
				{
					"type": "channel",
					"action": "event",
					"channel": "shared",
					"event": "ping",
				},
			)
		)
	await asyncio.sleep(0)
	assert seen == ["a", "b"]


@pytest.mark.asyncio
async def test_transport_drop_rejects_rpc_and_keeps_listeners():
	app, dummy, session, render, _route = build_session(connected=True)
	received: list[Any] = []
	with ctx(app, session, render):
		channel = ps.channel("keep", lifetime="tab")
		channel.on("ping", lambda payload: received.append(payload))
		pending = asyncio.create_task(channel.request("get"))
	await asyncio.sleep(0)
	render.disconnect()
	with pytest.raises(ChannelDisconnected):
		await pending
	assert dummy.sent[0]["action"] == "request"
	with ctx(app, session, render):
		render.channels.handle_event(
			as_event(
				{
					"type": "channel",
					"action": "event",
					"channel": "keep",
					"event": "ping",
					"payload": "still-here",
				},
			)
		)
	await asyncio.sleep(0)
	assert received == ["still-here"]


@pytest.mark.asyncio
async def test_session_end_rejects_rpc():
	app, _dummy, session, render, _route = build_session(connected=True)
	with ctx(app, session, render):
		channel = ps.channel("end", lifetime="tab")
		pending = asyncio.create_task(channel.request("get"))
	await asyncio.sleep(0)
	render.close()
	with pytest.raises(ChannelDisconnected):
		await pending
	with pytest.raises(ChannelDetached):
		channel.on("x", lambda _: None)


@pytest.mark.asyncio
async def test_emit_while_disconnected_uses_global_queue():
	app = ps.App()
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession("render-q", app.routes)
	with ctx(app, session, render):
		channel = ps.channel("queued", lifetime="tab")
		channel.emit("ping", {"n": 1})
	assert render._global_queue == [  # pyright: ignore[reportPrivateUsage]
		{
			"type": "channel",
			"action": "event",
			"channel": "queued",
			"event": "ping",
			"payload": {"n": 1},
		}
	]


@pytest.mark.asyncio
async def test_middleware_deny_drops_event_and_nacks_request():
	class DenyChannel(PulseMiddleware):
		@override
		async def channel(self, **kwargs: Any):
			return Deny()

	app = ps.App(middleware=DenyChannel())
	dummy = DummyRender()
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession(dummy.id, app.routes)
	render.send = dummy.send  # pyright: ignore[reportAttributeAccessIssue]
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	user = cast(UserSession, cast(object, session))

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_event(
			{
				"type": "channel",
				"action": "event",
				"channel": "gated",
				"event": "ping",
			},
		),
	)
	assert dummy.sent == []

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_request(
			{
				"type": "channel",
				"action": "request",
				"channel": "gated",
				"event": "ping",
				"requestId": "req-deny",
			},
		),
	)
	assert dummy.sent[-1]["error"] == {"code": "denied", "message": "Denied"}


@pytest.mark.asyncio
async def test_middleware_skips_responses():
	seen: list[str] = []

	class Spy(PulseMiddleware):
		@override
		async def channel(self, **kwargs: Any):
			seen.append(kwargs["event"])
			return await kwargs["next"]()

	app = ps.App(middleware=Spy())
	dummy = DummyRender()
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession(dummy.id, app.routes)
	render.send = dummy.send  # pyright: ignore[reportAttributeAccessIssue]
	render.connected = True
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	user = cast(UserSession, cast(object, session))
	with ctx(app, session, render):
		channel = ps.channel("mid", lifetime="tab")
		pending = asyncio.create_task(channel.request("echo"))
	await asyncio.sleep(0)
	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_response(
			{
				"type": "channel",
				"action": "response",
				"channel": "mid",
				"responseTo": dummy.sent[0]["requestId"],
				"payload": "ok",
			},
		),
	)
	assert await pending == "ok"
	assert seen == []


@pytest.mark.asyncio
async def test_on_same_handler_is_idempotent():
	app, _dummy, session, render, route = build_session(with_route=True)
	calls: list[int] = []

	def handler(_: Any) -> None:
		calls.append(1)

	with ctx(app, session, render, route):
		channel = ps.channel("once")
		channel.on("ping", handler)
		channel.on("ping", handler)
	with ctx(app, session, render, route):
		render.channels.handle_event(
			as_event(
				{
					"type": "channel",
					"action": "event",
					"channel": "once",
					"event": "ping",
				},
			)
		)
	await asyncio.sleep(0)
	assert calls == [1]


@pytest.mark.asyncio
async def test_rpc_is_not_queued_while_disconnected():
	app = ps.App()
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession("render-rpc", app.routes)
	with ctx(app, session, render):
		ps.channel("rpc", lifetime="tab")
	render.channels.send_request("rpc", "echo", None, "req-1")
	render.channels.send_response("rpc", "req-1", "ok")
	assert render._global_queue == []  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_event_handler_error_is_reported():
	app, dummy, session, render, _route = build_session()
	del render.send  # pyright: ignore[reportAttributeAccessIssue]
	render.connect(dummy.send)  # pyright: ignore[reportArgumentType]

	def boom(_: Any) -> None:
		raise RuntimeError("handler exploded")

	with ctx(app, session, render):
		channel = ps.channel("boom", lifetime="tab")
		channel.on("ping", boom)
	with ctx(app, session, render):
		render.channels.handle_event(
			as_event(
				{
					"type": "channel",
					"action": "event",
					"channel": "boom",
					"event": "ping",
				},
			)
		)
	errors: list[dict[str, Any]] = []
	for _ in range(20):
		await asyncio.sleep(0)
		errors = [msg for msg in dummy.sent if msg.get("type") == "server_error"]
		if errors:
			break
	assert errors
	assert errors[-1]["path"] == "/"
	assert errors[-1]["error"]["phase"] == "channel"
	assert "handler exploded" in errors[-1]["error"]["message"]


def _dash_route_info() -> RouteInfo:
	return cast(
		RouteInfo,
		cast(
			object,
			{
				"pathname": "/dash",
				"hash": "",
				"query": "",
				"queryParams": {},
				"pathParams": {},
				"catchall": [],
			},
		),
	)


def build_dash_session():
	def page():
		return ps.div()

	route = Route("/dash", ps.component(page))
	app = ps.App(routes=[route])
	dummy = DummyRender()
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession(dummy.id, app.routes, server_address="http://localhost")
	render.connect(dummy.send)  # pyright: ignore[reportArgumentType]
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	info = _dash_route_info()
	with ctx(app, session, render):
		render.prerender(["/dash"], info)
		render.attach("/dash", info)
	return app, dummy, session, render


@pytest.mark.asyncio
async def test_tab_handler_error_reports_on_live_mount():
	app, dummy, session, render = build_dash_session()

	def boom(_: Any) -> None:
		raise RuntimeError("tab exploded")

	with ctx(app, session, render):
		channel = ps.channel("tab-boom", lifetime="tab")
		channel.on("ping", boom)
	with ctx(app, session, render):
		render.channels.handle_event(
			as_event(
				{
					"type": "channel",
					"action": "event",
					"channel": "tab-boom",
					"event": "ping",
				},
			)
		)
	errors: list[dict[str, Any]] = []
	for _ in range(20):
		await asyncio.sleep(0)
		errors = [msg for msg in dummy.sent if msg.get("type") == "server_error"]
		if errors:
			break
	assert errors
	assert errors[-1]["path"] == "/dash"
	assert errors[-1]["error"]["phase"] == "channel"
	assert "tab exploded" in errors[-1]["error"]["message"]


@pytest.mark.asyncio
async def test_strict_mode_detach_keeps_route_handle():
	app, _dummy, session, render, route = build_session(with_route=True)
	render.dev_strict_mode_detach_timeout = 10.0
	with ctx(app, session, render, route):
		channel = ps.channel("form")
		channel.on("sync", lambda _: None)
	render.detach("/")
	assert not channel.is_detached()
	with ctx(app, session, render, route):
		again = ps.channel("form")
	assert again is channel
	mount = render.route_mounts["/"]
	render.dispose_mount("/", mount)
	assert channel.is_detached()


@pytest.mark.asyncio
async def test_middleware_exception_nacks_request():
	class Boom(PulseMiddleware):
		@override
		async def channel(self, **kwargs: Any):
			raise RuntimeError("middleware down")

	app = ps.App(middleware=Boom())
	dummy = DummyRender()
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession(dummy.id, app.routes)
	render.send = dummy.send  # pyright: ignore[reportAttributeAccessIssue]
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	user = cast(UserSession, cast(object, session))

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_request(
			{
				"type": "channel",
				"action": "request",
				"channel": "gated",
				"event": "ping",
				"requestId": "req-boom",
			},
		),
	)
	nacks = [msg for msg in dummy.sent if msg.get("type") == "channel"]
	errors = [msg for msg in dummy.sent if msg.get("type") == "server_error"]
	assert nacks[-1]["error"]["code"] == "handler_error"
	assert errors[-1]["error"]["phase"] == "channel"
	assert errors[-1]["path"] == "/"


@pytest.mark.asyncio
async def test_middleware_exception_reports_on_live_mount():
	class Boom(PulseMiddleware):
		@override
		async def channel(self, **kwargs: Any):
			raise RuntimeError("middleware down")

	def page():
		return ps.div()

	route = Route("/dash", ps.component(page))
	app = ps.App(routes=[route], middleware=Boom())
	dummy = DummyRender()
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession(dummy.id, app.routes, server_address="http://localhost")
	render.connect(dummy.send)  # pyright: ignore[reportArgumentType]
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	info = _dash_route_info()
	with ctx(app, session, render):
		render.prerender(["/dash"], info)
		render.attach("/dash", info)
	user = cast(UserSession, cast(object, session))

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_request(
			{
				"type": "channel",
				"action": "request",
				"channel": "gated",
				"event": "ping",
				"requestId": "req-dash",
			},
		),
	)
	errors = [msg for msg in dummy.sent if msg.get("type") == "server_error"]
	assert errors[-1]["path"] == "/dash"
	assert errors[-1]["error"]["phase"] == "channel"


@pytest.mark.asyncio
async def test_stacked_inner_deny_nacks_request():
	class Outer(PulseMiddleware):
		@override
		async def channel(self, **kwargs: Any):
			return await kwargs["next"]()

	class Inner(PulseMiddleware):
		@override
		async def channel(self, **kwargs: Any):
			return Deny()

	app = ps.App(middleware=stack(Outer(), Inner()))
	dummy = DummyRender()
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession(dummy.id, app.routes)
	render.send = dummy.send  # pyright: ignore[reportAttributeAccessIssue]
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	user = cast(UserSession, cast(object, session))

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_request(
			{
				"type": "channel",
				"action": "request",
				"channel": "gated",
				"event": "ping",
				"requestId": "req-inner",
			},
		),
	)
	assert dummy.sent[-1]["error"] == {"code": "denied", "message": "Denied"}


@pytest.mark.asyncio
async def test_inbound_request_does_not_hold_session_lock():
	app, dummy, session, render, route = build_session(connected=True, with_route=True)
	app._socket_to_render["socket-1"] = render.id  # pyright: ignore[reportPrivateUsage]

	with ctx(app, session, render, route):
		channel = ps.channel("rpc")

		async def do(_: Any) -> Any:
			return await channel.request("client-echo")

		channel.on("do", do)

	inbound_task = asyncio.create_task(
		app._process_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize(
				{
					"type": "channel",
					"action": "request",
					"channel": "rpc",
					"event": "do",
					"requestId": "from-client",
				}
			),
		)
	)

	echo_id: str | None = None
	for _ in range(50):
		await asyncio.sleep(0)
		for msg in dummy.sent:
			if msg.get("action") == "request" and msg.get("event") == "client-echo":
				echo_id = msg["requestId"]
				break
		if echo_id is not None:
			break
	assert echo_id is not None

	await asyncio.wait_for(
		app._process_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize(
				{
					"type": "channel",
					"action": "response",
					"channel": "rpc",
					"responseTo": echo_id,
					"payload": "pong",
				}
			),
		),
		timeout=1,
	)
	await asyncio.wait_for(inbound_task, timeout=1)
	for _ in range(50):
		await asyncio.sleep(0)
		if dummy.sent and dummy.sent[-1].get("responseTo") == "from-client":
			break
	assert dummy.sent[-1] == {
		"type": "channel",
		"action": "response",
		"channel": "rpc",
		"responseTo": "from-client",
		"payload": "pong",
	}


@pytest.mark.asyncio
async def test_stale_on_remover_does_not_drop_new_handler():
	app, _dummy, session, render, route = build_session(with_route=True)
	seen: list[str] = []
	with ctx(app, session, render, route):
		channel = ps.channel("once")
		remove_first = channel.on("ping", lambda _: seen.append("first"))
		remove_first()
		channel.on("ping", lambda _: seen.append("second"))
		remove_first()
	with ctx(app, session, render, route):
		render.channels.handle_event(
			as_event(
				{
					"type": "channel",
					"action": "event",
					"channel": "once",
					"event": "ping",
				},
			)
		)
	await asyncio.sleep(0)
	assert seen == ["second"]


@pytest.mark.asyncio
async def test_prerender_redirect_detaches_route_handles():
	route = Route("/", _leaky_redirect_page)
	app = ps.App(routes=[route, Route("/other", _other_page)])
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession("render-redirect", app.routes)
	with ctx(app, session, render):
		result = render.prerender(["/"], _route_info())["/"]
	assert result["type"] == "navigate_to"
	assert "/" not in render.route_mounts
	assert render.channels._handles_for("leaky") == []  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_unserializable_request_result_nacks():
	from pulse.serializer import serialize as wire_serialize

	app, dummy, session, render, route = build_session(with_route=True)
	del render.send  # pyright: ignore[reportAttributeAccessIssue]

	def send(message: dict[str, Any]) -> None:
		wire_serialize(message)
		dummy.sent.append(message)

	render.connect(send)  # pyright: ignore[reportArgumentType]
	with ctx(app, session, render, route):
		channel = ps.channel("bad")
		channel.on("get", lambda _: object)
	with ctx(app, session, render, route):
		await render.channels.handle_request(
			as_request(
				{
					"type": "channel",
					"action": "request",
					"channel": "bad",
					"event": "get",
					"requestId": "req-bad",
				},
			)
		)
	nacks = [msg for msg in dummy.sent if msg.get("type") == "channel"]
	assert nacks[-1]["error"]["code"] == "handler_error"


def build_middleware_session(middleware: PulseMiddleware):
	app = ps.App(middleware=middleware)
	dummy = DummyRender()
	session = SimpleNamespace(sid="session-1", data={})
	render = ps.RenderSession(dummy.id, app.routes)
	render.send = dummy.send  # pyright: ignore[reportAttributeAccessIssue]
	render.connected = True
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	return app, dummy, session, render, cast(UserSession, cast(object, session))


@pytest.mark.asyncio
async def test_deny_after_next_sends_single_nack():
	class DenyAfterNext(PulseMiddleware):
		@override
		async def channel(self, **kwargs: Any):
			await kwargs["next"]()
			return Deny()

	app, dummy, session, render, user = build_middleware_session(DenyAfterNext())
	calls: list[Any] = []
	with ctx(app, session, render):
		channel = ps.channel("late-deny", lifetime="tab")
		channel.on("ping", lambda payload: calls.append(payload))

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_request(
			{
				"type": "channel",
				"action": "request",
				"channel": "late-deny",
				"event": "ping",
				"requestId": "req-late-deny",
			},
		),
	)
	for _ in range(10):
		await asyncio.sleep(0)
	responses = [msg for msg in dummy.sent if msg.get("action") == "response"]
	assert len(responses) == 1
	assert responses[0]["error"] == {"code": "denied", "message": "Denied"}
	assert calls == []


@pytest.mark.asyncio
async def test_raise_after_next_sends_single_nack():
	class BoomAfterNext(PulseMiddleware):
		@override
		async def channel(self, **kwargs: Any):
			await kwargs["next"]()
			raise RuntimeError("middleware down")

	app, dummy, session, render, user = build_middleware_session(BoomAfterNext())
	calls: list[Any] = []
	with ctx(app, session, render):
		channel = ps.channel("late-boom", lifetime="tab")
		channel.on("ping", lambda payload: calls.append(payload))

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_request(
			{
				"type": "channel",
				"action": "request",
				"channel": "late-boom",
				"event": "ping",
				"requestId": "req-late-boom",
			},
		),
	)
	for _ in range(10):
		await asyncio.sleep(0)
	responses = [msg for msg in dummy.sent if msg.get("action") == "response"]
	assert len(responses) == 1
	assert responses[0]["error"]["code"] == "handler_error"
	assert calls == []


@pytest.mark.asyncio
async def test_request_without_request_id_is_dropped():
	app, dummy, session, render, user = build_middleware_session(PulseMiddleware())
	with ctx(app, session, render):
		ps.channel("no-id", lifetime="tab")

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_request(
			{
				"type": "channel",
				"action": "request",
				"channel": "no-id",
				"event": "ping",
			},
		),
	)
	for _ in range(10):
		await asyncio.sleep(0)
	assert dummy.sent == []


@pytest.mark.asyncio
async def test_inbound_handlers_receive_session_render_and_route_context():
	app, dummy, session, render, route = build_session(connected=True, with_route=True)
	assert route is not None
	observed: dict[str, Any] = {}

	with ctx(app, session, render, route):
		request_channel = ps.channel("context-request")
		event_channel = ps.channel("context-event")
		tab_channel = ps.channel("context-tab", lifetime="tab")

		def request_handler(_: Any) -> str:
			observed["request_session"] = ps.session()
			observed["request_render"] = ps.websocket_id()
			observed["request_route"] = ps.route()
			return "request-ok"

		def event_handler(_: Any) -> None:
			observed["event_session"] = ps.session()
			observed["event_render"] = ps.websocket_id()
			observed["event_route"] = ps.route()

		def tab_handler(_: Any) -> None:
			observed["tab_session"] = ps.session()
			observed["tab_render"] = ps.websocket_id()
			observed["tab_route"] = ps.PulseContext.get().route

		request_channel.on("read", request_handler)
		event_channel.on("changed", event_handler)
		tab_channel.on("changed", tab_handler)

	user = cast(UserSession, cast(object, session))
	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_request(
			{
				"type": "channel",
				"action": "request",
				"channel": "context-request",
				"event": "read",
				"requestId": "req-context",
			},
		),
	)
	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_event(
			{
				"type": "channel",
				"action": "event",
				"channel": "context-event",
				"event": "changed",
			},
		),
	)
	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		user,
		as_event(
			{
				"type": "channel",
				"action": "event",
				"channel": "context-tab",
				"event": "changed",
			},
		),
	)

	await wait_for(lambda: "tab_route" in observed)
	assert dummy.sent[-1]["payload"] == "request-ok"
	assert observed["request_session"] is session.data
	assert observed["request_render"] == render.id
	assert observed["request_route"] == route.info
	assert observed["event_session"] is session.data
	assert observed["event_render"] == render.id
	assert observed["event_route"] == route.info
	assert observed["tab_session"] is session.data
	assert observed["tab_render"] == render.id
	assert observed["tab_route"] is None


@pytest.mark.asyncio
async def test_cancelled_request_clears_pending():
	app, _dummy, session, render, _route = build_session(connected=True)
	with ctx(app, session, render):
		channel = ps.channel("cancelled", lifetime="tab")
		pending = asyncio.create_task(channel.request("get"))
	await asyncio.sleep(0)
	assert render.channels._pending  # pyright: ignore[reportPrivateUsage]
	pending.cancel()
	with pytest.raises(asyncio.CancelledError):
		await pending
	assert render.channels._pending == {}  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_timed_out_request_clears_pending():
	app, _dummy, session, render, _route = build_session(connected=True)
	with ctx(app, session, render):
		channel = ps.channel("slow", lifetime="tab")
		with pytest.raises(ps.ChannelTimeout):
			await channel.request("get", timeout=0.01)
	assert render.channels._pending == {}  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_unserializable_emit_raises_at_emitter():
	app, dummy, session, render, _route = build_session()
	with ctx(app, session, render):
		channel = ps.channel("bad-emit", lifetime="tab")
		with pytest.raises(TypeError, match="not serializable"):
			channel.emit("ping", {"cls": object})
	assert dummy.sent == []
	assert render._global_queue == []  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_response_channel_mismatch_is_ignored():
	app, dummy, session, render, _route = build_session(connected=True)
	with ctx(app, session, render):
		channel = ps.channel("mine", lifetime="tab")
		pending = asyncio.create_task(channel.request("get"))
	await asyncio.sleep(0)
	request_id = dummy.sent[0]["requestId"]
	render.channels.handle_response(
		as_response(
			{
				"type": "channel",
				"action": "response",
				"channel": "theirs",
				"responseTo": request_id,
				"payload": "stolen",
			},
		)
	)
	await asyncio.sleep(0)
	assert not pending.done()
	render.channels.handle_response(
		as_response(
			{
				"type": "channel",
				"action": "response",
				"channel": "mine",
				"responseTo": request_id,
				"payload": "ok",
			},
		)
	)
	assert await pending == "ok"


@pytest.mark.asyncio
async def test_detached_handle_rejects_request():
	app, _dummy, session, render, _route = build_session(connected=True)
	with ctx(app, session, render):
		channel = ps.channel("dead", lifetime="tab")
	channel.detach()
	with pytest.raises(ChannelDetached):
		await channel.request("get")


@pytest.mark.asyncio
async def test_events_run_in_arrival_order():
	app, _dummy, session, render, _route = build_session()
	seen: list[str] = []

	async def slow(_: Any) -> None:
		await asyncio.sleep(0.02)
		seen.append("first")

	async def fast(_: Any) -> None:
		seen.append("second")

	with ctx(app, session, render):
		channel = ps.channel("ordered", lifetime="tab")
		channel.on("first", slow)
		channel.on("second", fast)
	for event in ("first", "second"):
		with ctx(app, session, render):
			render.channels.handle_event(
				as_event(
					{
						"type": "channel",
						"action": "event",
						"channel": "ordered",
						"event": event,
					},
				)
			)
	await wait_for(lambda: len(seen) == 2)
	assert seen == ["first", "second"]


@pytest.mark.asyncio
async def test_detach_skips_pending_handlers():
	app, _dummy, session, render, _route = build_session()
	seen: list[str] = []

	async def first(_: Any) -> None:
		await asyncio.sleep(0)
		seen.append("first")

	with ctx(app, session, render):
		channel = ps.channel("detaching", lifetime="tab")
		channel.on("ping", first)
		channel.on("ping", lambda _: seen.append("second"))
	with ctx(app, session, render):
		render.channels.handle_event(
			as_event(
				{
					"type": "channel",
					"action": "event",
					"channel": "detaching",
					"event": "ping",
				},
			)
		)
	await asyncio.sleep(0)
	channel.detach()
	for _ in range(10):
		await asyncio.sleep(0)
	# detach cancels the pump mid-await, so neither the suspended handler nor the
	# ones queued behind it resume.
	assert seen == []


@pytest.mark.asyncio
async def test_malformed_response_is_dropped():
	app, dummy, _session, render, user = build_middleware_session(PulseMiddleware())
	errors: list[Any] = []

	def report_error(*args: Any, **kwargs: Any) -> None:
		errors.append(args)

	render.report_error = report_error  # pyright: ignore[reportAttributeAccessIssue]

	for message in (
		{"type": "channel", "action": "response", "channel": "c"},
		{"type": "channel", "action": "response", "responseTo": "req-1"},
		{"type": "channel", "action": "response", "channel": "c", "responseTo": 3},
	):
		await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
			render, user, as_response(message)
		)
	assert dummy.sent == []
	assert errors == []


@pytest.mark.asyncio
async def test_event_backlog_drops_oldest_with_one_warning(
	caplog: pytest.LogCaptureFixture,
):
	app, _dummy, session, render, _route = build_session()
	release = asyncio.Event()
	seen: list[Any] = []

	async def blocked(payload: Any) -> None:
		seen.append(payload)
		await release.wait()

	with ctx(app, session, render):
		channel = ps.channel("backlog", lifetime="tab")
		channel.on("ping", blocked)

	with caplog.at_level(logging.WARNING):
		for i in range(MAX_QUEUED_EVENTS + 5):
			with ctx(app, session, render):
				render.channels.handle_event(
					as_event(
						{
							"type": "channel",
							"action": "event",
							"channel": "backlog",
							"event": "ping",
							"payload": i,
						},
					)
				)
		await asyncio.sleep(0)
		# One event is in flight on the blocked handler, the rest wait in the queue.
		assert len(channel._events) == MAX_QUEUED_EVENTS - 1  # pyright: ignore[reportPrivateUsage]
	warnings = [r for r in caplog.records if "event backlog" in r.getMessage()]
	assert len(warnings) == 1
	release.set()
	await wait_for(lambda: len(seen) == MAX_QUEUED_EVENTS)
	# The 5 oldest events were shed; the newest survive, in order.
	assert seen == list(range(5, MAX_QUEUED_EVENTS + 5))


@pytest.mark.asyncio
async def test_detach_cancels_event_pump():
	app, _dummy, session, render, _route = build_session()
	release = asyncio.Event()
	seen: list[Any] = []

	async def blocked(payload: Any) -> None:
		seen.append(payload)
		await release.wait()

	with ctx(app, session, render):
		channel = ps.channel("cancel-pump", lifetime="tab")
		channel.on("ping", blocked)
	for i in range(2):
		with ctx(app, session, render):
			render.channels.handle_event(
				as_event(
					{
						"type": "channel",
						"action": "event",
						"channel": "cancel-pump",
						"event": "ping",
						"payload": i,
					},
				)
			)
	await asyncio.sleep(0)
	pump = channel._pump  # pyright: ignore[reportPrivateUsage]
	assert pump is not None and not pump.done()
	channel.detach()
	release.set()
	await wait_for(lambda: pump.cancelled())
	assert pump.cancelled()
	assert seen == [0]


@pytest.mark.asyncio
async def test_connected_emit_still_fails_on_unserializable_payload():
	app, _dummy, session, render, _route = build_session(connected=True)
	# The live socket serializes in the emitter's frame; nothing to validate twice.
	render.send = lambda message: serialize(message)  # pyright: ignore[reportAttributeAccessIssue]
	with ctx(app, session, render):
		channel = ps.channel("live-bad", lifetime="tab")
		with pytest.raises(TypeError):
			channel.emit("ping", {"cls": object})
