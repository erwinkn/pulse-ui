import asyncio
from types import SimpleNamespace
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.app import App
from pulse.channel import (
	ChannelDetached,
	ChannelDisconnected,
	ChannelRemoteError,
)
from pulse.messages import (
	ClientChannelEventMessage,
	ClientChannelRequestMessage,
	ClientChannelResponseMessage,
)
from pulse.middleware import Deny, PulseMiddleware
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteContext, RouteInfo, RouteTree
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
	app, _dummy, session, render, _route = build_session()
	with ctx(app, session, render):
		channel = ps.channel()
	assert len(channel.id) == 36


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
	first.emit("still-routes")
	assert dummy.sent[-1]["type"] == "channel"
	assert dummy.sent[-1]["action"] == "event"
	assert dummy.sent[-1]["channel"] == "foo"
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
		channel = ps.channel("form-channel")
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
		channel = ps.channel("req-channel")
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
		channel = ps.channel("err-channel")
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
		channel = ps.channel("down")
		with pytest.raises(ChannelDisconnected):
			await channel.request("get")
	assert dummy.sent == []


@pytest.mark.asyncio
async def test_request_nacks_without_handler():
	app, dummy, session, render, _route = build_session()
	with ctx(app, session, render):
		ps.channel("empty")
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
		ps.channel("quiet")
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
	app, _dummy, session, render, _route = build_session()
	seen: list[str] = []
	with ctx(app, session, render):
		a = render.channels.open_handle("shared")
		b = render.channels.open_handle("shared")
		a.on("ping", lambda _: seen.append("a"))
		b.on("ping", lambda _: seen.append("b"))
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
		channel = ps.channel("keep")
		channel.on("ping", lambda payload: received.append(payload))
		pending = asyncio.create_task(channel.request("get"))
	await asyncio.sleep(0)
	render.disconnect()
	with pytest.raises(ChannelDisconnected):
		await pending
	assert dummy.sent[0]["action"] == "request"
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
		channel = ps.channel("end")
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
		channel = ps.channel("queued")
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
		channel = ps.channel("mid")
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
