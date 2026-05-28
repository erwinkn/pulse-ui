import asyncio
from types import SimpleNamespace
from typing import cast

import pulse as ps
import pytest
from pulse.messages import ClientPulseMessage
from pulse.render_session import RenderSession
from pulse.serializer import serialize
from pulse.user_session import UserSession


@pytest.mark.asyncio
async def test_socket_messages_for_render_are_serialized(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = cast(UserSession, cast(object, session))
	app._socket_to_render["socket-1"] = render.id  # pyright: ignore[reportPrivateUsage]

	started_attach = asyncio.Event()
	release_attach = asyncio.Event()
	events: list[str] = []

	async def handle_pulse_message(
		_render: RenderSession, _session: UserSession, msg: ClientPulseMessage
	) -> None:
		events.append(f"start:{msg['type']}")
		if msg["type"] == "attach":
			started_attach.set()
			await release_attach.wait()
		events.append(f"end:{msg['type']}")

	monkeypatch.setattr(app, "_handle_pulse_message", handle_pulse_message)

	attach_task = asyncio.create_task(
		app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize(
				{
					"type": "attach",
					"path": "/",
					"routeInfo": {
						"pathname": "/",
						"hash": "",
						"query": "",
						"queryParams": {},
						"pathParams": {},
						"catchall": [],
					},
				}
			),
		)
	)
	await started_attach.wait()

	callback_task = asyncio.create_task(
		app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize(
				{
					"type": "callback",
					"path": "/",
					"callback": "1.onClick",
					"args": [],
				}
			),
		)
	)
	await asyncio.sleep(0)
	assert events == ["start:attach"]

	release_attach.set()
	await asyncio.gather(attach_task, callback_task)

	assert events == [
		"start:attach",
		"end:attach",
		"start:callback",
		"end:callback",
	]

	render.close()


def test_socketio_handlers_are_ordered():
	app = ps.App()

	assert app.sio.async_handlers is False


@pytest.mark.asyncio
async def test_socket_messages_wait_for_connect_to_finish(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	events: list[str] = []

	async def handle_pulse_message(
		_render: RenderSession, _session: UserSession, msg: ClientPulseMessage
	) -> None:
		events.append(msg["type"])

	monkeypatch.setattr(app, "_handle_pulse_message", handle_pulse_message)

	app._connecting_sockets.add("socket-1")  # pyright: ignore[reportPrivateUsage]

	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize(
			{
				"type": "attach",
				"path": "/",
				"routeInfo": {
					"pathname": "/",
					"hash": "",
					"query": "",
					"queryParams": {},
					"pathParams": {},
					"catchall": [],
				},
			}
		),
	)
	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize(
			{
				"type": "callback",
				"path": "/",
				"callback": "1.onClick",
				"args": [],
			}
		),
	)

	assert events == []

	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = cast(UserSession, cast(object, session))
	app._socket_to_render["socket-1"] = render.id  # pyright: ignore[reportPrivateUsage]

	await app._drain_pending_socket_messages(  # pyright: ignore[reportPrivateUsage]
		"socket-1"
	)

	assert events == ["attach", "callback"]
	assert "socket-1" not in app._connecting_sockets  # pyright: ignore[reportPrivateUsage]

	render.close()
