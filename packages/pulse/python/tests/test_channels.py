import asyncio
from types import SimpleNamespace
from typing import Any, cast, override

import pulse as ps
import pytest
from pulse.channel import Channel, ChannelClosed
from pulse.messages import ClientChannelResponseMessage
from pulse.render_session import RenderSession
from pulse.test_helpers import wait_for
from pulse.user_session import UserSession


class DummyRender:
	id: str

	def __init__(self, rid: str = "render-1") -> None:
		self.id = rid
		self.sent: list[dict[str, Any]] = []

	def send(self, message: dict[str, Any]):
		self.sent.append(message)


def connect_channel(
	render: RenderSession, channel: Channel, view_id: str | None = None
) -> None:
	render.channels.handle_client_connect(
		{
			"type": "channel_connect",
			"channel": channel.id,
			"view": view_id if view_id is not None else (channel.view_id or ""),
		}
	)


def make_route_render(
	path: str = "/",
	*,
	dev_strict_mode_detach_timeout: float = 0.0,
	middleware: ps.PulseMiddleware | None = None,
) -> tuple[ps.App, RenderSession, UserSession]:
	@ps.component
	def view():
		return ps.div()

	app = ps.App([ps.Route(path, view)], middleware=middleware)
	render = ps.RenderSession(
		"render-1",
		app.routes,
		dev_strict_mode_detach_timeout=dev_strict_mode_detach_timeout,
	)
	session = cast(UserSession, cast(object, SimpleNamespace(sid="session-1", data={})))
	render.connect(lambda _: None)
	with ps.PulseContext(app=app, session=session, render=render):
		render.prerender([path])
		render.attach(
			render.view_for_path(path).id, app.routes.find(path).default_route_info()
		)
	return app, render, session


def create_route_channel(
	app: ps.App,
	render: RenderSession,
	session: UserSession,
	identifier: str,
	path: str = "/",
) -> Channel:
	view = render.view_for_path(path)
	with ps.PulseContext(
		app=app,
		session=session,
		render=render,
		route=view.route,
		view=view,
		source_pathname=view.route.pathname,
	):
		return render.channels.create(identifier)


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
		connect_channel(real_render, channel)
		channel.emit("setValues", {"values": {"a": 1}})

	assert len(render.sent) == 1
	message = render.sent[0]
	assert message["type"] == "channel_message"
	assert message["channel"] == "form-channel"
	assert message["event"] == "setValues"
	assert message["payload"] == {"values": {"a": 1}}


def test_route_bound_channel_emit_includes_view():
	app, render, session = make_route_render()
	channel = create_route_channel(app, render, session, "route-channel")
	connect_channel(render, channel)
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]

	channel.emit("setValues", {"values": {"a": 1}})

	assert len(sent) == 1
	message = sent[0]
	assert message["type"] == "channel_message"
	assert message["view"] == render.view_for_path("/").id
	assert message["channel"] == channel.id
	assert message["event"] == "setValues"
	assert message["payload"] == {"values": {"a": 1}}


def test_channel_emit_without_endpoint_raises_channel_closed():
	app, render, session = make_route_render()
	channel = create_route_channel(app, render, session, "closed-channel")

	with pytest.raises(ChannelClosed, match="no connected client"):
		channel.emit("notify", None)


def test_connect_requires_matching_active_view():
	app, render, session = make_route_render()
	channel = create_route_channel(app, render, session, "owned-channel")

	render.channels.handle_client_connect(
		{"type": "channel_connect", "channel": channel.id, "view": "other-view"}
	)
	assert channel.connected is False

	connect_channel(render, channel)
	assert channel.connected is True


@pytest.mark.asyncio
async def test_dev_strict_mode_detach_preserves_route_channel_until_dispose():
	app, render, session = make_route_render(dev_strict_mode_detach_timeout=0.01)
	channel = create_route_channel(app, render, session, "strict-channel")
	connect_channel(render, channel)

	render.detach(render.view_for_path("/").id)

	assert channel.closed is False
	assert channel.connected is True
	assert channel.id in render.channels._channels  # pyright: ignore[reportPrivateUsage]

	await wait_for(lambda: channel.id not in render.channels._channels)  # pyright: ignore[reportPrivateUsage]
	assert channel.closed is True


def test_dev_strict_mode_replay_reconnects_route_channel():
	app, render, session = make_route_render(dev_strict_mode_detach_timeout=10.0)
	channel = create_route_channel(app, render, session, "replay-channel")
	connect_channel(render, channel)

	view = render.view_for_path("/")
	render.detach(view.id)
	render.channels.handle_client_disconnect(
		{"type": "channel_disconnect", "channel": channel.id}
	)
	assert channel.closed is False
	assert channel.connected is False

	# The view keeps its id through the StrictMode replay, so the channel
	# binding stays valid without any rebinding.
	with ps.PulseContext(app=app, session=session, render=render):
		render.attach(view.id, app.routes.find("/").default_route_info())
	connect_channel(render, channel)

	assert channel.view_id == view.id
	assert channel.connected is True


def test_stale_connect_during_detach_grace_is_rejected():
	app, render, session = make_route_render(dev_strict_mode_detach_timeout=10.0)
	channel = create_route_channel(app, render, session, "stale-channel")

	render.detach(render.view_for_path("/").id)
	connect_channel(render, channel)

	assert channel.connected is False
	assert channel.closed is False


def test_resume_omits_closed_channel_from_acceptance():
	app, render, session = make_route_render()
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	channel = create_route_channel(app, render, session, "closed-resume-channel")
	connect_channel(render, channel)
	channel.close()

	view = render.view_for_path("/")
	ok = render.resume(
		"resume-1",
		[
			{
				"view": view.id,
				"routeInfo": app.routes.find("/").default_route_info(),
				"attachId": "attach-1",
			}
		],
		[{"channel": channel.id, "view": view.id}],
	)

	assert ok is True
	assert sent[-1] == {
		"type": "server_resume",
		"resumeId": "resume-1",
		"status": "ok",
		"views": [{"view": view.id, "attachId": "attach-1"}],
		"channels": [],
	}


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
		connect_channel(real_render, channel)
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
async def test_channel_request_without_endpoint_raises_channel_closed():
	app, render, session = make_route_render()
	channel = create_route_channel(app, render, session, "req-closed")

	with pytest.raises(ChannelClosed, match="no connected client"):
		await channel.request("get", None)


def test_client_request_without_connected_endpoint_gets_error_response():
	app, render, session = make_route_render()
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	channel = create_route_channel(app, render, session, "client-req-closed")

	render.channels.handle_client_event(
		render=render,
		session=session,
		message={
			"type": "channel_message",
			"channel": channel.id,
			"event": "ping",
			"payload": None,
			"requestId": "client-req-1",
		},
	)

	assert sent == [
		{
			"type": "channel_message",
			"channel": channel.id,
			"event": None,
			"responseTo": "client-req-1",
			"payload": None,
			"error": "Channel has no connected client",
			"view": render.view_for_path("/").id,
		}
	]


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
		connect_channel(real_render, channel)
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
async def test_client_disconnect_rejects_pending_without_disposing_channel():
	app, render, session = make_route_render()
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	channel = create_route_channel(app, render, session, "disconnect-channel")
	connect_channel(render, channel)
	pending = asyncio.create_task(channel.request("get", None))

	await asyncio.sleep(0)
	render.channels.handle_client_disconnect(
		{"type": "channel_disconnect", "channel": channel.id}
	)

	assert channel.closed is False
	assert channel.connected is False
	with pytest.raises(ChannelClosed, match="no connected client"):
		await pending


@pytest.mark.asyncio
async def test_channel_lifecycle_runs_middleware_and_denial_notifies_client():
	events: list[str] = []

	class DenyConnectMiddleware(ps.PulseMiddleware):
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
			events.append(event)
			if event == "__connect__":
				return ps.Deny()
			return await next()

	app, render, session = make_route_render(middleware=DenyConnectMiddleware())
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	channel = create_route_channel(app, render, session, "denied-channel")

	view = render.view_for_path("/")
	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		session,
		{"type": "channel_connect", "channel": channel.id, "view": view.id},
	)

	assert events == ["__connect__"]
	assert channel.connected is False
	assert sent == [
		{
			"type": "channel_message",
			"channel": channel.id,
			"event": "__close__",
			"payload": {"reason": "Denied"},
			"view": view.id,
		}
	]


@pytest.mark.asyncio
async def test_channel_connect_disconnect_lifecycle_middleware_events():
	events: list[str] = []

	class LogMiddleware(ps.PulseMiddleware):
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
			events.append(event)
			return await next()

	app, render, session = make_route_render(middleware=LogMiddleware())
	channel = create_route_channel(app, render, session, "lifecycle-channel")

	view = render.view_for_path("/")
	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		session,
		{"type": "channel_connect", "channel": channel.id, "view": view.id},
	)
	await app._handle_channel_message(  # pyright: ignore[reportPrivateUsage]
		render,
		session,
		{"type": "channel_disconnect", "channel": channel.id},
	)

	assert events == ["__connect__", "__disconnect__"]
	assert channel.connected is False
	assert channel.closed is False


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
		connect_channel(real_render, channel)
		pending = asyncio.create_task(channel.request("get", None))

	real_render.close()
	with pytest.raises(ChannelClosed):
		await pending


def test_resume_accepts_unbound_channel():
	app, render, session = make_route_render()
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	with ps.PulseContext(app=app, session=session, render=render):
		channel = render.channels.create("session-channel", bind_view=False)
	connect_channel(render, channel)

	ok = render.resume(
		"resume-unbound",
		[],
		[{"channel": channel.id, "view": ""}],
	)

	assert ok is True
	assert sent[-1] == {
		"type": "server_resume",
		"resumeId": "resume-unbound",
		"status": "ok",
		"views": [],
		"channels": [{"channel": channel.id, "view": ""}],
	}
