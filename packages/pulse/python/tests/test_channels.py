import asyncio
from types import SimpleNamespace
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.channel import (
	DISCONNECTED_EMIT_BUFFER_CAP,
	Channel,
	ChannelClosed,
	ChannelDisconnected,
)
from pulse.messages import ChannelResponseMessage
from pulse.user_session import UserSession


class DummyRender:
	id: str

	def __init__(self, rid: str = "render-1") -> None:
		self.id = rid
		self.sent: list[dict[str, Any]] = []

	def send(self, message: dict[str, Any]):
		self.sent.append(message)


def connect_channel(
	render: ps.RenderSession,
	session: UserSession,
	channel: Channel,
	*,
	owner: str | None = None,
	subscription_id: str = "subscription-1",
) -> bool:
	message: dict[str, Any] = {
		"type": "channel",
		"action": "connect",
		"channel": channel.id,
		"subscriptionId": subscription_id,
	}
	if owner is not None:
		message["owner"] = owner
	return render.channels.handle_client_connect(
		render=render,
		session=session,
		message=cast(Any, message),
	)


def make_global_channel(
	identifier: str,
) -> tuple[ps.RenderSession, UserSession, Channel, list[dict[str, Any]]]:
	app = ps.App()
	render = ps.RenderSession("render-subscriptions", app.routes)
	session = cast(
		UserSession,
		cast(object, SimpleNamespace(sid="session-subscriptions", data={})),
	)
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	with ps.PulseContext(app=app, session=session, render=render):
		channel = render.channels.create(identifier, lifetime="tab")
	return render, session, channel, sent


def test_channel_lifetimes_define_automatic_cleanup_owner():
	app = ps.App()
	render = ps.RenderSession("render-lifetimes", app.routes)
	session = cast(
		UserSession,
		cast(object, SimpleNamespace(sid="session-lifetimes", data={})),
	)
	route = cast(Any, SimpleNamespace(route_path="/lifetime-route"))

	with ps.PulseContext(app=app, session=session, render=render, route=route):
		route_channel = ps.channel("route-channel")
		tab_channel = ps.channel("tab-channel", lifetime="tab")

	assert route_channel.lifetime == "route"
	assert route_channel.route_path == "/lifetime-route"
	assert tab_channel.lifetime == "tab"
	assert tab_channel.route_path is None

	render.channels.remove_route("/lifetime-route")

	assert route_channel.closed is True
	assert tab_channel.closed is False

	render.close()
	assert tab_channel.closed is True


def test_route_lifetime_requires_an_active_route():
	app = ps.App()
	render = ps.RenderSession("render-route-required", app.routes)
	session = cast(
		UserSession,
		cast(object, SimpleNamespace(sid="session-route-required", data={})),
	)

	with ps.PulseContext(app=app, session=session, render=render):
		with pytest.raises(RuntimeError, match="lifetime='tab'"):
			ps.channel("route-channel")
		tab_channel = ps.channel("tab-channel", lifetime="tab")

	assert tab_channel.closed is False
	render.close()


def test_channel_rejects_unknown_lifetime():
	app = ps.App()
	render = ps.RenderSession("render-invalid-lifetime", app.routes)
	session = cast(
		UserSession,
		cast(object, SimpleNamespace(sid="session-invalid-lifetime", data={})),
	)

	with ps.PulseContext(app=app, session=session, render=render):
		with pytest.raises(ValueError, match="'route' or 'tab'"):
			ps.channel("invalid-channel", lifetime=cast(Any, "process"))

	render.close()


@pytest.mark.asyncio
async def test_channel_emit_sends_message():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-1")

	real_render = ps.RenderSession(render.id, app.routes)
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]

	app.render_sessions[render.id] = real_render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		channel = real_render.channels.create("form-channel", lifetime="tab")
		assert connect_channel(
			real_render,
			cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
			channel,
		)
		render.sent.clear()
		channel.emit("setValues", {"values": {"a": 1}})

	assert len(render.sent) == 1
	message = render.sent[0]
	assert message["type"] == "channel"
	assert message["action"] == "event"
	assert message["channel"] == "form-channel"
	assert message["event"] == "setValues"
	assert message["payload"] == {"values": {"a": 1}}
	assert message["subscriptionId"] == "subscription-1"


@pytest.mark.asyncio
async def test_channel_request_resolves_on_response():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-2")

	real_render = ps.RenderSession(render.id, app.routes)
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]

	app.render_sessions[render.id] = real_render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		channel = real_render.channels.create("req-channel", lifetime="tab")
		assert connect_channel(
			real_render,
			cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
			channel,
		)
		render.sent.clear()
		pending = asyncio.create_task(channel.request("get", {"x": 1}))

	await asyncio.sleep(0)
	assert len(render.sent) == 1
	request_message = render.sent[0]
	request_id = request_message.get("requestId")
	assert request_id

	real_render.channels.handle_client_response(
		message=cast(
			ChannelResponseMessage,
			cast(
				object,
				{
					"type": "channel",
					"action": "response",
					"channel": "req-channel",
					"responseTo": request_id,
					"payload": {"x": 2},
					"subscriptionId": "subscription-1",
				},
			),
		)
	)

	result = await pending
	assert result == {"x": 2}


@pytest.mark.asyncio
async def test_channel_event_dispatch():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-3")

	real_render = ps.RenderSession(render.id, app.routes)
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]

	app.render_sessions[render.id] = real_render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]

	received: list[Any] = []

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		channel = real_render.channels.create("event-channel", lifetime="tab")
		assert connect_channel(
			real_render,
			cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
			channel,
		)
		render.sent.clear()
		channel.on("ping", lambda payload: received.append(payload))

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		real_render.channels.handle_client_event(
			render=real_render,
			session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
			message={
				"type": "channel",
				"action": "event",
				"channel": "event-channel",
				"event": "ping",
				"payload": {"value": 42},
				"subscriptionId": "subscription-1",
			},
		)

	await asyncio.sleep(0)
	assert received == [{"value": 42}]


@pytest.mark.asyncio
async def test_channel_pending_cancelled_on_render_close():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-4")

	real_render = ps.RenderSession(render.id, app.routes)
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]

	app.render_sessions[render.id] = real_render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		channel = real_render.channels.create("close-channel", lifetime="tab")
		assert connect_channel(
			real_render,
			cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
			channel,
		)
		render.sent.clear()
		pending = asyncio.create_task(channel.request("get", None))

	real_render.close()
	with pytest.raises(ChannelClosed):
		await pending


def test_disconnect_and_reconnect_preserve_channel_and_flush_buffer():
	render, session, channel, sent = make_global_channel("reconnect-channel")
	assert connect_channel(render, session, channel)
	assert sent == [
		{
			"type": "channel",
			"action": "connect_ack",
			"channel": channel.id,
			"subscriptionId": "subscription-1",
			"accepted": True,
		}
	]
	sent.clear()

	assert render.channels.handle_client_disconnect(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "disconnect",
			"channel": channel.id,
			"subscriptionId": "subscription-1",
		},
	)
	channel.emit("queued", {"value": 1})

	assert channel.closed is False
	assert channel.connected is False
	assert channel.id in render.channels._channels  # pyright: ignore[reportPrivateUsage]
	assert sent == []

	assert connect_channel(
		render,
		session,
		channel,
		subscription_id="subscription-2",
	)
	assert sent == [
		{
			"type": "channel",
			"action": "connect_ack",
			"channel": channel.id,
			"subscriptionId": "subscription-2",
			"accepted": True,
		},
		{
			"type": "channel",
			"action": "event",
			"channel": channel.id,
			"event": "queued",
			"payload": {"value": 1},
			"subscriptionId": "subscription-2",
		},
	]


def test_disconnected_emit_snapshots_payload_at_emit_time():
	render, session, channel, sent = make_global_channel("snapshot-channel")
	payload = {"items": [1]}
	channel.emit("queued", payload)
	payload["items"].append(2)

	assert connect_channel(render, session, channel)
	assert sent[-1] == {
		"type": "channel",
		"action": "event",
		"channel": channel.id,
		"event": "queued",
		"payload": {"items": [1]},
		"subscriptionId": "subscription-1",
	}


def test_disconnected_emit_validates_payload_before_connect():
	_, _, channel, _ = make_global_channel("invalid-buffer-channel")

	with pytest.raises(TypeError, match="Unsupported value in serialization"):
		channel.emit("invalid", lambda: None)


def test_disconnected_emit_buffer_is_capped_and_drops_oldest():
	render, session, channel, sent = make_global_channel("buffered-channel")
	for value in range(DISCONNECTED_EMIT_BUFFER_CAP + 3):
		channel.emit("value", value)

	assert connect_channel(render, session, channel)
	flushed = [message for message in sent if message.get("action") == "event"]
	assert len(flushed) == DISCONNECTED_EMIT_BUFFER_CAP
	assert flushed[0]["payload"] == 3
	assert flushed[-1]["payload"] == DISCONNECTED_EMIT_BUFFER_CAP + 2


@pytest.mark.asyncio
async def test_disconnected_request_fails_immediately():
	_, _, channel, sent = make_global_channel("disconnected-request")

	with pytest.raises(ChannelDisconnected, match="no connected client subscriber"):
		await channel.request("get")

	assert sent == []


@pytest.mark.asyncio
async def test_request_send_disconnect_race_cleans_pending_request(
	monkeypatch: pytest.MonkeyPatch,
):
	render, session, channel, _ = make_global_channel("request-send-race")
	assert connect_channel(render, session, channel)
	original_send = render.channels.send_to_client

	def disconnect_before_send(*, channel: Channel, msg: Any) -> None:
		render.channels.disconnect_all()
		original_send(channel=channel, msg=msg)

	monkeypatch.setattr(render.channels, "send_to_client", disconnect_before_send)

	with pytest.raises(ChannelDisconnected, match="no connected client subscriber"):
		await channel.request("get")

	assert render.channels.pending_requests == {}


@pytest.mark.asyncio
async def test_transport_disconnect_rejects_pending_without_disposing_channel():
	render, session, channel, sent = make_global_channel("pending-disconnect")
	assert connect_channel(render, session, channel)
	sent.clear()
	pending = asyncio.create_task(channel.request("get"))
	await asyncio.sleep(0)

	render.channels.disconnect_all()

	with pytest.raises(ChannelDisconnected, match="lost its connected client"):
		await pending
	assert channel.closed is False
	assert channel.connected is False
	assert channel.id in render.channels._channels  # pyright: ignore[reportPrivateUsage]


def test_server_close_is_the_only_remote_terminal_notification():
	render, session, channel, sent = make_global_channel("server-close")
	assert connect_channel(render, session, channel)
	sent.clear()
	assert render.channels.handle_client_disconnect(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "disconnect",
			"channel": channel.id,
			"subscriptionId": "subscription-1",
		},
	)
	assert channel.closed is False
	assert sent == []

	assert connect_channel(
		render,
		session,
		channel,
		subscription_id="subscription-2",
	)
	sent.clear()
	channel.close()

	assert channel.closed is True
	assert sent == [
		{
			"type": "channel",
			"action": "close",
			"channel": channel.id,
			"subscriptionId": "subscription-2",
			"reason": "channel.close",
		}
	]


def test_connect_rejects_missing_channel_with_correlated_ack():
	render, session, _, sent = make_global_channel("existing-channel")

	accepted = render.channels.handle_client_connect(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "connect",
			"channel": "missing-channel",
			"subscriptionId": "missing-subscription",
		},
	)

	assert accepted is False
	assert sent == [
		{
			"type": "channel",
			"action": "connect_ack",
			"channel": "missing-channel",
			"subscriptionId": "missing-subscription",
			"accepted": False,
			"error": "Channel is unavailable",
		}
	]


def test_connect_requires_matching_opaque_owner_token():
	render, session, channel, sent = make_global_channel("owned-channel")

	accepted = render.channels.handle_client_connect(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "connect",
			"channel": channel.id,
			"subscriptionId": "wrong-owner",
			"owner": "/other",
		},
	)

	assert accepted is False
	assert channel.closed is False
	assert channel.connected is False
	assert sent[-1] == {
		"type": "channel",
		"action": "connect_ack",
		"channel": channel.id,
		"subscriptionId": "wrong-owner",
		"accepted": False,
		"error": "Channel is unavailable",
	}


@pytest.mark.asyncio
async def test_middleware_denied_connect_rejects_without_closing_channel():
	class DenyChannelConnect(ps.PulseMiddleware):
		@override
		async def channel(
			self,
			*,
			channel_id: str,
			event: str,
			payload: Any,
			request_id: str | None,
			session: dict[str, Any],
			next: Any,
		):
			if event == "connect":
				return ps.Deny()
			return await next()

	app = ps.App(middleware=DenyChannelConnect())
	render = ps.RenderSession("render-denied", app.routes)
	session = cast(
		UserSession,
		cast(object, SimpleNamespace(sid="session-denied", data={})),
	)
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	with ps.PulseContext(app=app, session=session, render=render):
		channel = render.channels.create("denied-channel", lifetime="tab")

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		session,
		{
			"type": "channel",
			"action": "connect",
			"channel": channel.id,
			"subscriptionId": "denied-subscription",
		},
	)

	assert channel.closed is False
	assert channel.connected is False
	assert sent == [
		{
			"type": "channel",
			"action": "connect_ack",
			"channel": channel.id,
			"subscriptionId": "denied-subscription",
			"accepted": False,
			"error": "Denied",
		}
	]


@pytest.mark.asyncio
async def test_middleware_short_circuit_rejects_connect_instead_of_stranding_it():
	class ShortCircuitChannelConnect(ps.PulseMiddleware):
		@override
		async def channel(
			self,
			*,
			channel_id: str,
			event: str,
			payload: Any,
			request_id: str | None,
			session: dict[str, Any],
			next: Any,
		):
			if event == "connect":
				return ps.Ok(None)
			return await next()

	app = ps.App(middleware=ShortCircuitChannelConnect())
	render = ps.RenderSession("render-short-circuit", app.routes)
	session = cast(
		UserSession,
		cast(object, SimpleNamespace(sid="session-short-circuit", data={})),
	)
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	with ps.PulseContext(app=app, session=session, render=render):
		channel = render.channels.create("short-circuit-channel", lifetime="tab")

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		session,
		{
			"type": "channel",
			"action": "connect",
			"channel": channel.id,
			"subscriptionId": "short-circuit-subscription",
		},
	)

	assert channel.connected is False
	assert sent == [
		{
			"type": "channel",
			"action": "connect_ack",
			"channel": channel.id,
			"subscriptionId": "short-circuit-subscription",
			"accepted": False,
			"error": "Channel subscription not accepted",
		}
	]


@pytest.mark.asyncio
async def test_middleware_error_rejects_connect_without_stranding_bridge():
	class RaiseChannelConnect(ps.PulseMiddleware):
		@override
		async def channel(
			self,
			*,
			channel_id: str,
			event: str,
			payload: Any,
			request_id: str | None,
			session: dict[str, Any],
			next: Any,
		):
			if event == "connect":
				raise RuntimeError("middleware failed")
			return await next()

	app = ps.App(middleware=RaiseChannelConnect())
	render = ps.RenderSession("render-error", app.routes)
	session = cast(
		UserSession,
		cast(object, SimpleNamespace(sid="session-error", data={})),
	)
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	with ps.PulseContext(app=app, session=session, render=render):
		channel = render.channels.create("error-channel", lifetime="tab")

	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		session,
		{
			"type": "channel",
			"action": "connect",
			"channel": channel.id,
			"subscriptionId": "error-subscription",
		},
	)

	assert channel.connected is False
	assert sent == [
		{
			"type": "channel",
			"action": "connect_ack",
			"channel": channel.id,
			"subscriptionId": "error-subscription",
			"accepted": False,
			"error": "Channel subscription failed",
		}
	]


@pytest.mark.asyncio
async def test_connect_does_not_complete_after_originating_socket_is_replaced():
	started = asyncio.Event()
	resume = asyncio.Event()

	class DelayedChannelConnect(ps.PulseMiddleware):
		@override
		async def channel(
			self,
			*,
			channel_id: str,
			event: str,
			payload: Any,
			request_id: str | None,
			session: dict[str, Any],
			next: Any,
		):
			if event == "connect":
				started.set()
				await resume.wait()
			return await next()

	app = ps.App(middleware=DelayedChannelConnect())
	render = ps.RenderSession("render-socket-generation", app.routes)
	session = cast(
		UserSession,
		cast(object, SimpleNamespace(sid="session-socket-generation", data={})),
	)
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	with ps.PulseContext(app=app, session=session, render=render):
		channel = render.channels.create("socket-generation-channel", lifetime="tab")
	app._render_to_socket[render.id] = "old-socket"  # pyright: ignore[reportPrivateUsage]

	connect = asyncio.create_task(
		app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
			render,
			session,
			{
				"type": "channel",
				"action": "connect",
				"channel": channel.id,
				"subscriptionId": "old-subscription",
			},
			socket_sid="old-socket",
		)
	)
	await started.wait()
	app._render_to_socket[render.id] = "new-socket"  # pyright: ignore[reportPrivateUsage]
	resume.set()
	await connect

	assert channel.connected is False
	assert sent == []


def test_close_includes_the_live_subscription_id():
	render, session, channel, sent = make_global_channel("close-live-sub")
	assert connect_channel(render, session, channel, subscription_id="live-sub")
	sent.clear()
	channel.close()

	assert sent == [
		{
			"type": "channel",
			"action": "close",
			"channel": channel.id,
			"subscriptionId": "live-sub",
			"reason": "channel.close",
		}
	]


@pytest.mark.asyncio
async def test_incoming_event_with_wrong_subscription_id_is_ignored():
	render, session, channel, sent = make_global_channel("stale-event")
	assert connect_channel(render, session, channel)
	received: list[Any] = []
	channel.on("ping", lambda payload: received.append(payload))
	sent.clear()

	render.channels.handle_client_event(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "event",
			"channel": channel.id,
			"event": "ping",
			"payload": {"stale": True},
			"subscriptionId": "not-the-live-sub",
		},
	)
	render.channels.handle_client_event(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "event",
			"channel": channel.id,
			"event": "ping",
			"payload": {"missing": True},
		},
	)
	await asyncio.sleep(0)
	assert received == []
	assert sent == []

	render.channels.handle_client_event(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "event",
			"channel": channel.id,
			"event": "ping",
			"payload": {"live": True},
			"subscriptionId": "subscription-1",
		},
	)
	await asyncio.sleep(0)
	assert received == [{"live": True}]


@pytest.mark.asyncio
async def test_incoming_request_with_wrong_subscription_id_is_ignored():
	render, session, channel, sent = make_global_channel("stale-request")
	assert connect_channel(render, session, channel)
	received: list[Any] = []
	channel.on("ask", lambda payload: received.append(payload) or {"ok": True})
	sent.clear()

	render.channels.handle_client_event(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "request",
			"channel": channel.id,
			"event": "ask",
			"requestId": "stale-req",
			"payload": {},
			"subscriptionId": "not-the-live-sub",
		},
	)
	render.channels.handle_client_event(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "request",
			"channel": channel.id,
			"event": "ask",
			"requestId": "missing-sub-req",
			"payload": {},
		},
	)
	await asyncio.sleep(0)
	assert received == []
	assert sent == []

	render.channels.handle_client_event(
		render=render,
		session=session,
		message={
			"type": "channel",
			"action": "request",
			"channel": channel.id,
			"event": "ask",
			"requestId": "live-req",
			"payload": {},
			"subscriptionId": "subscription-1",
		},
	)
	await asyncio.sleep(0)
	assert received == [{}]
	assert sent == [
		{
			"type": "channel",
			"action": "response",
			"channel": channel.id,
			"responseTo": "live-req",
			"payload": {"ok": True},
			"subscriptionId": "subscription-1",
		}
	]


@pytest.mark.asyncio
async def test_incoming_response_with_wrong_subscription_id_is_ignored():
	render, session, channel, sent = make_global_channel("stale-response")
	assert connect_channel(render, session, channel)
	sent.clear()
	pending = asyncio.create_task(channel.request("get"))
	await asyncio.sleep(0)
	request_id = sent[0]["requestId"]

	render.channels.handle_client_response(
		message=cast(
			ChannelResponseMessage,
			cast(
				object,
				{
					"type": "channel",
					"action": "response",
					"channel": channel.id,
					"responseTo": request_id,
					"payload": {"stale": True},
					"subscriptionId": "not-the-live-sub",
				},
			),
		)
	)
	assert pending.done() is False

	render.channels.handle_client_response(
		message=cast(
			ChannelResponseMessage,
			cast(
				object,
				{
					"type": "channel",
					"action": "response",
					"channel": channel.id,
					"responseTo": request_id,
					"payload": {"live": True},
					"subscriptionId": "subscription-1",
				},
			),
		)
	)
	assert await pending == {"live": True}


@pytest.mark.asyncio
async def test_invoke_response_send_after_disconnect_does_not_raise_unhandled(
	monkeypatch: pytest.MonkeyPatch,
):
	render, session, channel, _sent = make_global_channel("invoke-send-race")
	assert connect_channel(render, session, channel)
	channel.on("ask", lambda _payload: {"ok": True})
	original_send = render.channels.send_to_client

	def disconnect_before_send(*, channel: Channel, msg: Any) -> None:
		render.channels.disconnect_all()
		original_send(channel=channel, msg=msg)

	monkeypatch.setattr(render.channels, "send_to_client", disconnect_before_send)

	loop = asyncio.get_running_loop()
	prev_handler = loop.get_exception_handler()
	unhandled: list[dict[str, Any]] = []

	def handler(_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
		unhandled.append(context)

	loop.set_exception_handler(handler)
	try:
		render.channels.handle_client_event(
			render=render,
			session=session,
			message={
				"type": "channel",
				"action": "request",
				"channel": channel.id,
				"event": "ask",
				"requestId": "req-race",
				"payload": None,
				"subscriptionId": "subscription-1",
			},
		)
		await asyncio.sleep(0)
		await asyncio.sleep(0)
		assert unhandled == []
		assert channel.closed is False
		assert channel.connected is False
	finally:
		loop.set_exception_handler(prev_handler)
