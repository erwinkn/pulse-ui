import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pulse as ps
import pytest
from pulse.messages import ClientChannelResponseMessage
from pulse.user_session import UserSession
from pulse_mantine.core.combobox.combobox import Combobox, ComboboxStore


class DummyRender:
	id: str

	def __init__(self, rid: str = "render-1") -> None:
		self.id = rid
		self.sent: list[dict[str, Any]] = []

	def send(self, message: dict[str, Any]):
		self.sent.append(message)


def build_context():
	app = ps.App()
	render = DummyRender()
	session = SimpleNamespace(sid="session-1")

	real_render = ps.RenderSession(render.id, app.routes)
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]

	app.render_sessions[render.id] = real_render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	return app, render, session, real_render


@pytest.mark.asyncio
async def test_combobox_store_emits_actions():
	app, render, session, real_render = build_context()

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		store = ComboboxStore()
		store.open_dropdown("keyboard")
		store.select_option(3)

	assert len(render.sent) == 2
	open_msg = render.sent[0]
	assert open_msg["event"] == "openDropdown"
	assert open_msg["payload"] == {"eventSource": "keyboard"}

	select_msg = render.sent[1]
	assert select_msg["event"] == "selectOption"
	assert select_msg["payload"] == {"index": 3}


@pytest.mark.asyncio
async def test_combobox_store_request_roundtrip():
	app, render, session, real_render = build_context()

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		store = ComboboxStore()
		pending = asyncio.create_task(store.get_dropdown_opened())

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
					"channel": request_message["channel"],
					"responseTo": request_id,
					"payload": True,
				},
			),
		)
	)

	result = await pending
	assert result is True


@pytest.mark.asyncio
async def test_combobox_store_callbacks():
	app, render, session, real_render = build_context()
	opened: list[bool] = []
	opened_sources: list[str] = []
	closed_sources: list[str] = []

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		store = ComboboxStore(
			onOpenedChange=lambda value: opened.append(value),
			onDropdownOpen=lambda source: opened_sources.append(source),
			onDropdownClose=lambda source: closed_sources.append(source),
		)

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
				"channel": store._channel.id,
				"event": "openedChange",
				"payload": {"opened": True},
			},
		)
		real_render.channels.handle_client_event(
			render=real_render,
			session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
			message={
				"type": "channel_message",
				"channel": store._channel.id,
				"event": "dropdownOpen",
				"payload": {"eventSource": "mouse"},
			},
		)
		real_render.channels.handle_client_event(
			render=real_render,
			session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
			message={
				"type": "channel_message",
				"channel": store._channel.id,
				"event": "dropdownClose",
				"payload": {"eventSource": "keyboard"},
			},
		)

	await asyncio.sleep(0)
	assert opened == [True]
	assert opened_sources == ["mouse"]
	assert closed_sources == ["keyboard"]


def test_combobox_requires_store():
	with pytest.raises(TypeError):
		Combobox()
