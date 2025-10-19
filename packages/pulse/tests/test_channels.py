import asyncio
from types import SimpleNamespace
from typing import Any

import pulse as ps
import pytest
from pulse.channel import PulseChannelClosed


class DummyRender:
	def __init__(self, rid: str = "render-1") -> None:
		self.id = rid
		self.sent: list[dict] = []

	def send(self, message):
		self.sent.append(message)


@pytest.mark.asyncio
async def test_channel_emit_sends_message():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-1")
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid
	app.user_sessions[session.sid] = session

	with ps.PulseContext(app=app, session=session, render=render):
		channel = app.channels.create("form-channel")
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
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid
	app.user_sessions[session.sid] = session

	with ps.PulseContext(app=app, session=session, render=render):
		channel = app.channels.create("req-channel")
		pending = asyncio.create_task(channel.request("get", {"x": 1}))

	await asyncio.sleep(0)  # let the task run
	assert len(render.sent) == 1
	request_message = render.sent[0]
	request_id = request_message.get("requestId")
	assert request_id

	app.channels.handle_client_response(
		message={
			"type": "channel_message",
			"channel": "req-channel",
			"responseTo": request_id,
			"payload": {"x": 2},
		}
	)

	result = await pending
	assert result == {"x": 2}


@pytest.mark.asyncio
async def test_channel_event_dispatch():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-3")
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid
	app.user_sessions[session.sid] = session

	received: list[Any] = []

	with ps.PulseContext(app=app, session=session, render=render):
		channel = app.channels.create("event-channel")
		channel.on("ping", lambda payload: received.append(payload))

	with ps.PulseContext(app=app, session=session, render=render):
		app.channels.handle_client_event(
			render=render,
			session=session,
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
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid
	app.user_sessions[session.sid] = session

	with ps.PulseContext(app=app, session=session, render=render):
		channel = app.channels.create("close-channel")
		pending = asyncio.create_task(channel.request("get", None))

	app.channels.remove_render(render.id)
	with pytest.raises(PulseChannelClosed):
		await pending
