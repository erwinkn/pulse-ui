import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.app import MAX_PENDING_SOCKET_MESSAGES
from pulse.messages import ClientMessage, ClientPulseMessage
from pulse.middleware import Deny, Ok, PulseMiddleware
from pulse.render_session import RenderSession
from pulse.serializer import serialize
from pulse.test_helpers import wait_for
from pulse.user_session import UserSession


def _route_info(path: str) -> dict[str, object]:
	return {
		"pathname": path,
		"hash": "",
		"query": "",
		"queryParams": {},
		"pathParams": {},
		"catchall": [],
	}


def _bind_render(
	app: ps.App,
	render: RenderSession,
	session: SimpleNamespace,
	socket_sid: str = "socket-1",
) -> None:
	app.render_sessions[render.id] = render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = cast(UserSession, cast(object, session))
	app._socket_to_render[socket_sid] = render.id  # pyright: ignore[reportPrivateUsage]


def _spawn(
	app: ps.App, socket_sid: str, message: dict[str, object]
) -> asyncio.Task[None]:
	"""Live EVENT: Socket.IO async_handlers=True runs the handler as a task."""
	return asyncio.create_task(
		app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
			socket_sid, serialize(message)
		)
	)


async def _send(app: ps.App, socket_sid: str, message: dict[str, object]) -> None:
	"""Await the handler (connect-drain / reply / finished command)."""
	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		socket_sid, serialize(message)
	)


class GatingMessageMiddleware(PulseMiddleware):
	"""Parks selected pulse commands until `release` is set."""

	started: asyncio.Event
	release: asyncio.Event
	gate_paths: set[str] | None

	def __init__(self, gate_paths: set[str] | None = None) -> None:
		super().__init__()
		self.started = asyncio.Event()
		self.release = asyncio.Event()
		self.gate_paths = gate_paths

	@override
	async def message(
		self,
		*,
		data: ClientMessage,
		session: dict[str, Any],
		next: Callable[[], Awaitable[Ok[None] | Deny]],
	) -> Ok[None] | Deny:
		path = str(data.get("path", ""))
		if self.gate_paths is None or path in self.gate_paths:
			self.started.set()
			await self.release.wait()
		return await next()


@pytest.mark.asyncio
async def test_replies_resolve_while_command_middleware_is_parked():
	middleware = GatingMessageMiddleware()
	app = ps.App(middleware=middleware)
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	_bind_render(app, render, session)

	api_fut = render.replies.register("corr-1")
	js_fut = render.replies.register("js-1")
	channel_fut = render.replies.register("req-1", cancel_key="ch-1")

	parked = _spawn(
		app,
		"socket-1",
		{"type": "attach", "path": "/", "routeInfo": _route_info("/")},
	)
	await middleware.started.wait()
	assert not middleware.release.is_set()
	assert not api_fut.done()
	assert not js_fut.done()
	assert not channel_fut.done()

	await _send(
		app,
		"socket-1",
		{
			"type": "reply",
			"id": "corr-1",
			"payload": {
				"ok": True,
				"status": 200,
				"headers": {},
				"body": {"n": 1},
			},
		},
	)
	assert api_fut.done()
	assert api_fut.result()["body"] == {"n": 1}
	assert not middleware.release.is_set()

	await _send(
		app,
		"socket-1",
		{"type": "reply", "id": "js-1", "payload": 42},
	)
	assert js_fut.done()
	assert js_fut.result() == 42

	await _send(
		app,
		"socket-1",
		{"type": "reply", "id": "req-1", "payload": "pong"},
	)
	assert channel_fut.done()
	assert channel_fut.result() == "pong"

	middleware.release.set()
	await parked
	render.close()


@pytest.mark.asyncio
async def test_awaited_attach_then_callback_sees_mount():
	seen: list[str] = []

	@ps.component
	def Home():
		def on_click():
			ctx = ps.PulseContext.get()
			assert ctx.render is not None
			seen.append(ctx.render.route_mounts["/"].state)

		return ps.button(onClick=on_click)["inc"]

	app = ps.App(routes=[ps.Route("/", Home)])
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	_bind_render(app, render, session)
	render.connect(lambda _message: None)

	with ps.PulseContext.update(render=render):
		render.prerender(["/"])
	assert render.route_mounts["/"].state == "pending"
	callback_key = next(iter(render.route_mounts["/"].tree.callbacks))

	# Awaited commands (connect-drain). Mutation is sync, so callback
	# sees the mount. Live EVENTs are Socket.IO tasks — a parked attach
	# must not block a later callback or reply.
	await _send(
		app,
		"socket-1",
		{"type": "attach", "path": "/", "routeInfo": _route_info("/")},
	)
	await _send(
		app,
		"socket-1",
		{"type": "callback", "path": "/", "callback": callback_key, "args": []},
	)

	assert render.route_mounts["/"].state == "active"
	assert seen == ["active"]
	render.close()


@pytest.mark.asyncio
async def test_parked_command_does_not_block_other_path_or_reply():
	middleware = GatingMessageMiddleware(gate_paths={"/a"})
	clicked: list[str] = []

	@ps.component
	def PageA():
		return ps.div()["a"]

	@ps.component
	def PageB():
		def on_click():
			ctx = ps.PulseContext.get()
			assert ctx.render is not None
			clicked.append(ctx.render.route_mounts["/b"].state)

		return ps.button(onClick=on_click)["b"]

	app = ps.App(
		routes=[ps.Route("/a", PageA), ps.Route("/b", PageB)],
		middleware=middleware,
	)
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	_bind_render(app, render, session)
	render.connect(lambda _message: None)

	with ps.PulseContext.update(render=render):
		render.prerender(["/a", "/b"])
	callback_key = next(iter(render.route_mounts["/b"].tree.callbacks))

	api_fut = render.replies.register("corr-b")

	parked = _spawn(
		app,
		"socket-1",
		{"type": "attach", "path": "/a", "routeInfo": _route_info("/a")},
	)
	await middleware.started.wait()
	assert render.route_mounts["/a"].state == "pending"

	await _send(
		app,
		"socket-1",
		{"type": "attach", "path": "/b", "routeInfo": _route_info("/b")},
	)
	assert await wait_for(lambda: render.route_mounts["/b"].state == "active")
	await _send(
		app,
		"socket-1",
		{"type": "callback", "path": "/b", "callback": callback_key, "args": []},
	)
	assert await wait_for(lambda: clicked == ["active"])
	await _send(
		app,
		"socket-1",
		{
			"type": "reply",
			"id": "corr-b",
			"payload": {
				"ok": True,
				"status": 200,
				"headers": {},
				"body": None,
			},
		},
	)

	assert api_fut.done()
	assert render.route_mounts["/a"].state == "pending"
	assert not middleware.release.is_set()

	middleware.release.set()
	await parked
	assert render.route_mounts["/a"].state == "active"
	render.close()


class GatingAttachMiddleware(PulseMiddleware):
	"""Parks only `attach` commands until `release` is set."""

	started: asyncio.Event
	release: asyncio.Event

	def __init__(self) -> None:
		super().__init__()
		self.started = asyncio.Event()
		self.release = asyncio.Event()

	@override
	async def message(
		self,
		*,
		data: ClientMessage,
		session: dict[str, Any],
		next: Callable[[], Awaitable[Ok[None] | Deny]],
	) -> Ok[None] | Deny:
		if data.get("type") == "attach":
			self.started.set()
			await self.release.wait()
		return await next()


@pytest.mark.asyncio
async def test_same_path_detach_cannot_overtake_parked_attach():
	"""A later detach for the same path must wait for the parked attach:
	otherwise the attach observes a missing mount and forces a reload."""
	middleware = GatingAttachMiddleware()

	@ps.component
	def PageA():
		return ps.div()["a"]

	app = ps.App(routes=[ps.Route("/a", PageA)], middleware=middleware)
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	_bind_render(app, render, session)
	sent: list[dict[str, object]] = []
	render.connect(
		lambda message: sent.append(cast(dict[str, object], cast(object, message)))
	)

	with ps.PulseContext.update(render=render):
		render.prerender(["/a"])

	attach_task = _spawn(
		app,
		"socket-1",
		{"type": "attach", "path": "/a", "routeInfo": _route_info("/a")},
	)
	await middleware.started.wait()
	detach_task = _spawn(app, "socket-1", {"type": "detach", "path": "/a"})
	await asyncio.sleep(0.01)
	# The detach must be parked behind the attach, not applied.
	assert render.route_mounts["/a"].state == "pending"

	middleware.release.set()
	await asyncio.gather(attach_task, detach_task)

	# Attach applied first, then detach: no spurious reload was sent.
	assert not [m for m in sent if m.get("type") == "reload"]
	render.close()


@pytest.mark.asyncio
async def test_same_path_lock_normalizes_leading_slash():
	class RecordingMiddleware(PulseMiddleware):
		paths: list[str]
		started: asyncio.Event
		release: asyncio.Event

		def __init__(self) -> None:
			super().__init__()
			self.paths = []
			self.started = asyncio.Event()
			self.release = asyncio.Event()

		@override
		async def message(
			self,
			*,
			data: ClientMessage,
			session: dict[str, Any],
			next: Callable[[], Awaitable[Ok[None] | Deny]],
		) -> Ok[None] | Deny:
			self.paths.append(str(data.get("path", "")))
			if len(self.paths) == 1:
				self.started.set()
				await self.release.wait()
			return await next()

	middleware = RecordingMiddleware()
	app = ps.App(middleware=middleware)
	render = RenderSession("render-1", app.routes)
	session = SimpleNamespace(sid="session-1", data={})
	_bind_render(app, render, session)

	first = _spawn(
		app,
		"socket-1",
		{"type": "callback", "path": "foo", "callback": "missing", "args": []},
	)
	await middleware.started.wait()
	second = _spawn(
		app,
		"socket-1",
		{"type": "callback", "path": "/foo", "callback": "missing", "args": []},
	)
	await asyncio.sleep(0)
	assert middleware.paths == ["foo"]

	middleware.release.set()
	await first
	await second
	assert middleware.paths == ["foo", "/foo"]
	render.close()


def test_socketio_async_handlers():
	app = ps.App()

	assert app.sio.async_handlers is True


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

	fut = render.replies.register("corr-1")
	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1", serialize({"type": "reply", "id": "corr-1", "payload": 7})
	)

	assert fut.done()
	assert fut.result() == 7
	assert app._pending_socket_messages.get("socket-1", []) == []  # pyright: ignore[reportPrivateUsage]
	render.close()


@pytest.mark.asyncio
async def test_connect_queue_overflow_never_drops_replies(
	monkeypatch: pytest.MonkeyPatch,
):
	app = ps.App()
	app._connecting_sockets.add("socket-1")  # pyright: ignore[reportPrivateUsage]

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
		"socket-1", serialize({"type": "reply", "id": "corr-1", "payload": 1})
	)
	queue = app._pending_socket_messages["socket-1"]  # pyright: ignore[reportPrivateUsage]
	assert len(queue) == 101
	assert queue[-1]["type"] == "reply"

	render = _wire_render(app, "socket-1")
	fut = render.replies.register("corr-1")

	async def handle_pulse_message(*_args: object) -> None:
		pass

	monkeypatch.setattr(app, "_handle_pulse_message", handle_pulse_message)
	await app._drain_pending_socket_messages(  # pyright: ignore[reportPrivateUsage]
		"socket-1"
	)
	assert fut.done()
	assert fut.result() == 1
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

	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1",
		serialize(
			{"type": "callback", "path": "/", "callback": "1.onClick", "args": []}
		),
	)
	await app._handle_socket_message(  # pyright: ignore[reportPrivateUsage]
		"socket-1", serialize({"type": "reply", "id": "corr-1", "payload": 3})
	)

	render = _wire_render(app, "socket-1")
	fut = render.replies.register("corr-1")

	started = asyncio.Event()
	release = asyncio.Event()

	async def handle_pulse_message(*_args: object) -> None:
		started.set()
		await release.wait()

	monkeypatch.setattr(app, "_handle_pulse_message", handle_pulse_message)

	drain = asyncio.create_task(
		app._drain_pending_socket_messages(  # pyright: ignore[reportPrivateUsage]
			"socket-1"
		)
	)
	await started.wait()
	# The command is parked, but the reply already resolved.
	assert fut.done()
	assert fut.result() == 3

	release.set()
	await drain
	render.close()
