import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pulse as ps
import pytest
from pulse.channel import ChannelClosed
from pulse.messages import ClientChannelResponseMessage
from pulse.user_session import UserSession


class DummyRender:
	id: str

	def __init__(self, rid: str = "render-1") -> None:
		self.id = rid
		self.sent: list[dict[str, Any]] = []

	def send(self, message: dict[str, Any]):
		self.sent.append(message)


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
		channel = real_render.channels.create("form-channel")
		channel.emit("setValues", {"values": {"a": 1}})

	assert len(render.sent) == 1
	message = render.sent[0]
	assert message["type"] == "channel_event"
	assert message["channel"] == "form-channel"
	assert message["event"] == "setValues"
	assert message["payload"] == {"values": {"a": 1}}


@pytest.mark.asyncio
async def test_channel_emit_defaults_payload_to_none():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-payload")
	real_render = ps.RenderSession(render.id, app.routes)
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		channel = real_render.channels.create("payload-channel")
		channel.emit("omitted")
		channel.emit("null", None)

	assert render.sent == [
		{
			"type": "channel_event",
			"channel": "payload-channel",
			"event": "omitted",
			"payload": None,
		},
		{
			"type": "channel_event",
			"channel": "payload-channel",
			"event": "null",
			"payload": None,
		},
	]


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
		channel = real_render.channels.create("req-channel")
		pending = asyncio.create_task(channel.request("get", {"x": 1}))

	await asyncio.sleep(0)
	assert len(render.sent) == 1
	request_message = render.sent[0]
	request_id = request_message.get("requestId")
	assert request_id

	real_render.channels.handle_client_response(
		message=cast(
			ClientChannelResponseMessage,
			cast(
				object,
				{
					"type": "channel_response",
					"channel": "req-channel",
					"responseTo": request_id,
					"ok": True,
					"payload": {"x": 2},
				},
			),
		)
	)

	result = await pending
	assert result == {"x": 2}


@pytest.mark.asyncio
async def test_channel_request_defaults_payload_to_none():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-request-payload")
	real_render = ps.RenderSession(render.id, app.routes)
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		channel = real_render.channels.create("request-payload-channel")
		omitted = asyncio.create_task(channel.request("omitted"))
		null = asyncio.create_task(channel.request("null", None))

	await asyncio.sleep(0)
	assert len(render.sent) == 2
	omitted_message, null_message = render.sent
	assert omitted_message["payload"] is None
	assert null_message["payload"] is None

	for message in render.sent:
		response: ClientChannelResponseMessage = {
			"type": "channel_response",
			"channel": "request-payload-channel",
			"responseTo": cast(str, message["requestId"]),
			"ok": True,
			"payload": None,
		}
		real_render.channels.handle_client_response(response)

	assert await omitted is None
	assert await null is None


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
		channel = real_render.channels.create("event-channel")
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
				"type": "channel_event",
				"channel": "event-channel",
				"event": "ping",
				"payload": {"value": 42},
			},
		)

	await asyncio.sleep(0)
	assert received == [{"value": 42}]


@pytest.mark.asyncio
async def test_channel_event_receives_none_payload():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-event-payload")
	real_render = ps.RenderSession(render.id, app.routes)
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]
	received: list[Any] = []

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		channel = real_render.channels.create("event-payload-channel")
		channel.on("null", received.append)
		real_render.channels.handle_client_event(
			render=real_render,
			session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
			message={
				"type": "channel_event",
				"channel": "event-payload-channel",
				"event": "null",
				"payload": None,
			},
		)

	await asyncio.sleep(0)
	assert received == [None]


@pytest.mark.asyncio
async def test_channel_response_always_contains_payload():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-response")
	real_render = ps.RenderSession(render.id, app.routes)
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		channel = real_render.channels.create("response-channel")
		channel.on("compute-null", lambda _payload: None)
		channel.on("compute-value", lambda _payload: 42)
		channel.on("compute-chain", lambda _payload: None)
		channel.on("compute-chain", lambda _payload: 43)
		for request_id, event in (
			("request-1", "compute-null"),
			("request-2", "compute-value"),
			("request-3", "compute-chain"),
		):
			real_render.channels.handle_client_event(
				render=real_render,
				session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
				message={
					"type": "channel_request",
					"channel": "response-channel",
					"event": event,
					"requestId": request_id,
					"payload": None,
				},
			)

	await asyncio.sleep(0)
	assert render.sent == [
		{
			"type": "channel_response",
			"channel": "response-channel",
			"responseTo": "request-1",
			"ok": True,
			"payload": None,
		},
		{
			"type": "channel_response",
			"channel": "response-channel",
			"responseTo": "request-2",
			"ok": True,
			"payload": 42,
		},
		{
			"type": "channel_response",
			"channel": "response-channel",
			"responseTo": "request-3",
			"ok": True,
			"payload": 43,
		},
	]
	real_render.close()


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
		channel = real_render.channels.create("close-channel")
		pending = asyncio.create_task(channel.request("get", None))

	real_render.close()
	with pytest.raises(ChannelClosed):
		await pending
