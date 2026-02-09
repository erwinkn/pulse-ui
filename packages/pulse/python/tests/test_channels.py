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


def test_channel_create_accepts_explicit_render_and_session() -> None:
	app = ps.App()
	session = SimpleNamespace(sid="session-explicit")
	render = ps.RenderSession("render-explicit", app.routes)

	channel = render.channels.create(
		"explicit-channel",
		bind_route=False,
		render=render,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
	)

	assert channel.id == "explicit-channel"
	assert channel.render_id == render.id
	assert channel.session_id == session.sid
	assert channel.route_path is None


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
	assert message["type"] == "channel_message"
	assert message["channel"] == "form-channel"
	assert message["event"] == "setValues"
	assert message["payload"] == {"values": {"a": 1}}


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
					"type": "channel_message",
					"channel": "req-channel",
					"responseTo": request_id,
					"payload": {"x": 2},
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
				"type": "channel_message",
				"channel": "event-channel",
				"event": "ping",
				"payload": {"value": 42},
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
		channel = real_render.channels.create("close-channel")
		pending = asyncio.create_task(channel.request("get", None))

	real_render.close()
	with pytest.raises(ChannelClosed):
		await pending
