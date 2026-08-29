import asyncio
from types import SimpleNamespace
from typing import cast

import pulse as ps
import pytest
from pulse.app import MAX_PENDING_SOCKET_MESSAGES
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
async def test_attach_sends_ack_after_route_is_attached(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	sent: list[dict[str, str]] = []

	def attach(_path: str, _route_info: object) -> bool:
		return True

	def send(message: dict[str, str]) -> None:
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
			"attachId": "attach-1",
		},
	)

	assert sent == [{"type": "attach_ack", "path": "/", "attachId": "attach-1"}]


@pytest.mark.asyncio
async def test_attach_does_not_ack_when_route_needs_reload(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	sent: list[dict[str, str]] = []

	def attach(_path: str, _route_info: object) -> bool:
		return False

	def send(message: dict[str, str]) -> None:
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


def _wire_render(app: ps.App, sid: str) -> RenderSession:
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = cast(UserSession, cast(object, session))
	app._socket_to_render[sid] = render.id  # pyright: ignore[reportPrivateUsage]
	return render


@pytest.mark.asyncio
async def test_reply_applies_immediately_while_connect_is_pending():
	app = ps.App()
	render = _wire_render(app, "socket-1")
	app._connecting_sockets.add("socket-1")  # pyright: ignore[reportPrivateUsage]

	with render.replies.pending() as reply:
		await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize({"type": "reply", "id": reply.id, "payload": 7}),
		)

		assert reply.future.done()
		assert reply.future.result() == 7
		assert app._pending_socket_messages.get("socket-1", []) == []  # pyright: ignore[reportPrivateUsage]
	render.close()


@pytest.mark.asyncio
async def test_connect_queue_overflow_never_drops_replies(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	app._connecting_sockets.add("socket-1")  # pyright: ignore[reportPrivateUsage]
	render = _wire_render(app, "socket-1")
	app._socket_to_render.pop("socket-1")  # pyright: ignore[reportPrivateUsage]

	async def handle_pulse_message(*_args: object) -> None:
		pass

	monkeypatch.setattr(app, "_handle_pulse_message", handle_pulse_message)
	with render.replies.pending() as reply:
		for i in range(150):
			await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
				"socket-1",
				serialize(
					{
						"type": "callback",
						"path": "/",
						"callback": f"{i}.onClick",
						"args": [],
					}
				),
			)
		# Queue is full of commands; a reply must still be queued.
		await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize({"type": "reply", "id": reply.id, "payload": 1}),
		)
		queue = app._pending_socket_messages["socket-1"]  # pyright: ignore[reportPrivateUsage]
		assert len(queue) == 101
		assert queue[-1]["type"] == "reply"
		app._socket_to_render["socket-1"] = render.id  # pyright: ignore[reportPrivateUsage]
		await app._drain_pending_socket_messages(  # pyright: ignore[reportPrivateUsage]
			"socket-1"
		)
		assert reply.future.done()
		assert reply.future.result() == 1
	render.close()


@pytest.mark.asyncio
async def test_connect_queue_caps_commands_and_replies_independently():
	app = ps.App()
	app._connecting_sockets.add("socket-1")  # pyright: ignore[reportPrivateUsage]

	for i in range(MAX_PENDING_SOCKET_MESSAGES):
		await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize(
				{
					"type": "callback",
					"path": "/",
					"callback": f"{i}.onClick",
					"args": [],
				}
			),
		)
	for i in range(MAX_PENDING_SOCKET_MESSAGES):
		await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize({"type": "reply", "id": f"corr-{i}", "payload": i}),
		)

	queue = app._pending_socket_messages["socket-1"]  # pyright: ignore[reportPrivateUsage]
	assert (
		sum(message["type"] != "reply" for message in queue)
		== MAX_PENDING_SOCKET_MESSAGES
	)
	assert (
		sum(message["type"] == "reply" for message in queue)
		== MAX_PENDING_SOCKET_MESSAGES
	)

	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize(
			{
				"type": "callback",
				"path": "/",
				"callback": "overflow.onClick",
				"args": [],
			}
		),
	)
	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize({"type": "reply", "id": "corr-overflow", "payload": None}),
	)

	assert (
		sum(message["type"] != "reply" for message in queue)
		== MAX_PENDING_SOCKET_MESSAGES
	)
	assert (
		sum(message["type"] == "reply" for message in queue)
		== MAX_PENDING_SOCKET_MESSAGES
	)


@pytest.mark.asyncio
async def test_drain_applies_replies_before_parked_commands(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	app._connecting_sockets.add("socket-1")  # pyright: ignore[reportPrivateUsage]
	render = _wire_render(app, "socket-1")

	started = asyncio.Event()
	release = asyncio.Event()

	async def handle_pulse_message(*_args: object) -> None:
		started.set()
		await release.wait()

	monkeypatch.setattr(app, "_handle_pulse_message", handle_pulse_message)

	with render.replies.pending() as reply:
		await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize(
				{"type": "callback", "path": "/", "callback": "1.onClick", "args": []}
			),
		)
		await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			"socket-1",
			serialize({"type": "reply", "id": reply.id, "payload": 3}),
		)
		drain = asyncio.create_task(
			app._drain_pending_socket_messages(  # pyright: ignore[reportPrivateUsage]
				"socket-1"
			)
		)
		await started.wait()
		# The command is parked, but the reply already resolved.
		assert reply.future.done()
		assert reply.future.result() == 3

		release.set()
		await drain
	render.close()
