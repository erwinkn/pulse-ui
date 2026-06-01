import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pulse as ps
import pytest
from pulse.channel import Channel, ChannelClosed
from pulse.messages import ClientChannelResponseMessage
from pulse.render_session import RenderSession
from pulse.routing import RouteOrigin
from pulse.user_session import UserSession


def make_render(path: str = "/") -> tuple[ps.App, RenderSession, UserSession]:
	@ps.component
	def view():
		return ps.div()

	app = ps.App([ps.Route(path, view)])
	render = ps.RenderSession("render-1", app.routes)
	session = cast(UserSession, cast(object, SimpleNamespace(sid="session-1", data={})))
	with ps.PulseContext(app=app, session=session, render=render):
		render.prerender([path])
		render.attach(path, app.routes.find(path).default_route_info())
	return app, render, session


def create_channel(
	app: ps.App,
	render: RenderSession,
	session: UserSession,
	identifier: str,
	path: str = "/",
) -> Channel:
	mount = render.get_route_mount(path)
	with ps.PulseContext(
		app=app,
		session=session,
		render=render,
		route=mount.route,
		origin=RouteOrigin.from_route(mount.route),
		mount_id=mount.mount_id,
	):
		return render.channels.create(identifier)


def connect_channel(render: RenderSession, channel: Channel, path: str = "/") -> None:
	render.channels.handle_client_connect(
		{"type": "channel_connect", "channel": channel.id, "path": path}
	)


@pytest.mark.asyncio
async def test_unconnected_route_channel_disposes_on_route_unmount():
	app, render, session = make_render()
	channel = create_channel(app, render, session, "route-channel")

	render.detach("/")

	assert channel.closed is True
	assert channel.id not in render.channels._channels  # pyright: ignore[reportPrivateUsage]


def test_connect_requires_matching_path_and_mount_id():
	app, render, session = make_render()
	channel = create_channel(app, render, session, "owned-channel")

	render.channels.handle_client_connect(
		{"type": "channel_connect", "channel": channel.id, "path": "/other"}
	)
	assert channel.connected is False

	connect_channel(render, channel)
	assert channel.connected is True


def test_stale_connect_after_remount_is_rejected():
	app, render, session = make_render()
	channel = create_channel(app, render, session, "stale-channel")
	render.detach("/")

	with ps.PulseContext(app=app, session=session, render=render):
		render.prerender(["/"])
		render.attach("/", app.routes.find("/").default_route_info())
	render.channels.handle_client_connect(
		{"type": "channel_connect", "channel": channel.id, "path": "/"}
	)

	assert channel.connected is False
	assert channel.id not in render.channels._channels  # pyright: ignore[reportPrivateUsage]


def test_channel_emit_sends_one_message_without_path():
	app, render, session = make_render()
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	channel = create_channel(app, render, session, "form-channel")
	connect_channel(render, channel)

	channel.emit("setValues", {"values": {"a": 1}})

	assert sent == [
		{
			"type": "channel_message",
			"channel": "form-channel",
			"event": "setValues",
			"payload": {"values": {"a": 1}},
		}
	]


def test_channel_emit_without_endpoint_raises_channel_closed():
	app, render, session = make_render()
	channel = create_channel(app, render, session, "closed-channel")

	with pytest.raises(ChannelClosed, match="no connected client"):
		channel.emit("notify", None)


@pytest.mark.asyncio
async def test_channel_request_resolves_on_response():
	app, render, session = make_render()
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	channel = create_channel(app, render, session, "req-channel")
	connect_channel(render, channel)

	pending = asyncio.create_task(channel.request("get", {"x": 1}))
	await asyncio.sleep(0)
	assert len(sent) == 1
	request_message = sent[0]
	request_id = request_message.get("requestId")
	assert request_id
	assert "path" not in request_message

	render.channels.handle_client_response(
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
	app, render, session = make_render()
	channel = create_channel(app, render, session, "req-closed")

	with pytest.raises(ChannelClosed, match="no connected client"):
		await channel.request("get", None)


@pytest.mark.asyncio
async def test_channel_event_dispatch_uses_owner_route_context():
	app, render, session = make_render()
	channel = create_channel(app, render, session, "event-channel")
	connect_channel(render, channel)
	received: list[tuple[Any, str]] = []

	def handler(payload: Any) -> None:
		received.append((payload, ps.pulse_route().unique_path()))

	channel.on("ping", handler)
	render.channels.handle_client_event(
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
	assert received == [({"value": 42}, "/")]


@pytest.mark.asyncio
async def test_client_disconnect_detaches_without_disposing_channel():
	app, render, session = make_render()
	channel = create_channel(app, render, session, "disconnect-channel")
	connect_channel(render, channel)

	render.channels.handle_client_disconnect(
		{"type": "channel_disconnect", "channel": channel.id}
	)

	assert channel.closed is False
	assert channel.connected is False
	assert channel.id in render.channels._channels  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_channel_pending_cancelled_on_render_close():
	app, render, session = make_render()
	sent: list[dict[str, Any]] = []
	render.send = sent.append  # pyright: ignore[reportAttributeAccessIssue]
	channel = create_channel(app, render, session, "close-channel")
	connect_channel(render, channel)
	pending = asyncio.create_task(channel.request("get", None))

	await asyncio.sleep(0)
	render.close()
	with pytest.raises(ChannelClosed):
		await pending
