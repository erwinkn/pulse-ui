import asyncio
from types import SimpleNamespace
from typing import cast

import pulse as ps
import pytest
from pulse.messages import ClientPulseMessage, ServerAttachAckMessage, ServerMessage
from pulse.render_session import RenderSession
from pulse.serializer import Serialized, deserialize, serialize
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
					"viewId": "view-1",
					"revision": 0,
					"attachId": "attach-1",
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
					"viewId": "view-1",
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
async def test_attach_sends_ack_after_route_is_attached(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	events: list[tuple[str, object]] = []
	ack = ServerAttachAckMessage(
		type="attach_ack",
		path="/",
		attachId="attach-1",
		viewId="view-1",
		revision=7,
	)

	def attach(
		path: str,
		route_info: object,
		view_id: str,
		revision: int,
		attach_id: str,
	) -> ServerAttachAckMessage:
		events.append(("attach", (path, route_info, view_id, revision, attach_id)))
		return ack

	def send(message: ServerMessage) -> None:
		events.append(("send", message))

	monkeypatch.setattr(render, "attach", attach)
	monkeypatch.setattr(render, "send", send)

	await app._handle_pulse_message(  # pyright: ignore[reportPrivateUsage]
		render,
		cast(UserSession, cast(object, session)),
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
			"viewId": "view-1",
			"revision": 3,
			"attachId": "attach-1",
		},
	)

	assert [event[0] for event in events] == ["attach", "send"]
	assert events[0][1] == (
		"/",
		{
			"pathname": "/",
			"hash": "",
			"query": "",
			"queryParams": {},
			"pathParams": {},
			"catchall": [],
		},
		"view-1",
		3,
		"attach-1",
	)
	assert events[1][1] == ack


@pytest.mark.asyncio
async def test_attach_does_not_ack_when_route_needs_reload(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	sent: list[ServerMessage] = []

	def attach(
		_path: str,
		_route_info: object,
		_view_id: str,
		_revision: int,
		_attach_id: str,
	) -> None:
		return None

	def send(message: ServerMessage) -> None:
		sent.append(message)

	monkeypatch.setattr(render, "attach", attach)
	monkeypatch.setattr(render, "send", send)

	await app._handle_pulse_message(  # pyright: ignore[reportPrivateUsage]
		render,
		cast(UserSession, cast(object, session)),
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
			"viewId": "view-1",
			"revision": 0,
			"attachId": "attach-1",
		},
	)

	assert sent == []


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
				"viewId": "view-1",
				"revision": 0,
				"attachId": "attach-1",
			}
		),
	)
	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize(
			{
				"type": "callback",
				"path": "/",
				"viewId": "view-1",
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


@pytest.mark.asyncio
async def test_socket_sender_is_fifo_and_non_concurrent(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	first_started = asyncio.Event()
	release_first = asyncio.Event()
	second_finished = asyncio.Event()
	events: list[str] = []
	active_sends = 0
	max_active_sends = 0

	async def emit(event: str, data: object, *, to: str) -> None:
		nonlocal active_sends, max_active_sends
		assert event == "message"
		assert to == "socket-1"
		message = cast(ServerMessage, deserialize(cast(Serialized, data)))
		active_sends += 1
		max_active_sends = max(max_active_sends, active_sends)
		events.append(f"start:{message['type']}")
		if message["type"] == "reload":
			first_started.set()
			await release_first.wait()
		active_sends -= 1
		events.append(f"end:{message['type']}")
		if message["type"] == "navigate_to":
			second_finished.set()

	monkeypatch.setattr(app.sio, "emit", emit)
	app._start_socket_sender("socket-1")  # pyright: ignore[reportPrivateUsage]
	app._send_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1", {"type": "reload"}
	)
	app._send_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		{
			"type": "navigate_to",
			"path": "/next",
			"replace": False,
			"hard": False,
		},
	)

	await asyncio.wait_for(first_started.wait(), timeout=1)
	await asyncio.sleep(0)
	assert events == ["start:reload"]
	assert max_active_sends == 1

	release_first.set()
	await asyncio.wait_for(second_finished.wait(), timeout=1)
	assert events == [
		"start:reload",
		"end:reload",
		"start:navigate_to",
		"end:navigate_to",
	]
	assert max_active_sends == 1

	await app.close()
