import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pulse as ps
import pytest
from pulse.messages import ClientChannelRequestMessage
from pulse.routing import Route, RouteInfo, RouteTree
from pulse.user_session import UserSession
from pulse_mantine import MantineForm


class DummyRender:
	id: str

	def __init__(self, rid: str = "render-1") -> None:
		self.id = rid
		self.sent: list[dict[str, Any]] = []

	def send(self, message: dict[str, Any]):
		self.sent.append(message)


def build_context():
	def render():
		return ps.div()

	route = Route("/", ps.component(render))
	routes = RouteTree([route])
	app = ps.App(routes=[route])
	render = DummyRender()
	session = SimpleNamespace(sid="session-1")

	real_render = ps.RenderSession(render.id, routes, server_address="http://localhost")
	real_render.send = render.send  # pyright: ignore[reportAttributeAccessIssue]
	with ps.PulseContext(app=app):
		real_render.prerender(
			["/"],
			cast(
				RouteInfo,
				{
					"pathname": "/",
					"hash": "",
					"query": "",
					"queryParams": {},
					"pathParams": {},
					"catchall": [],
				},
			),
		)
	route_ctx = real_render.route_mounts["/"].route

	app.render_sessions[render.id] = real_render
	app._render_to_user[render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	return app, render, session, real_render, route_ctx


def test_form_recreates_channel_after_client_release():
	app, render, session, real_render, route_ctx = build_context()

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
		route=route_ctx,
	):
		form = MantineForm(
			mode="uncontrolled",
			syncMode="change",
			initialValues={"query": ""},
		)
		first_channel_id = form._channel.id

	assert real_render.channels.release_channel(first_channel_id)
	assert form._channel.closed

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
		route=route_ctx,
	):
		form.reset()

	assert not form._channel.closed
	assert form._channel.id != first_channel_id
	assert render.sent[-1]["event"] == "reset"


@pytest.mark.asyncio
async def test_form_sync_handler_survives_channel_recreation():
	app, _render, session, real_render, route_ctx = build_context()

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
		route=route_ctx,
	):
		form = MantineForm(syncMode="change", initialValues={"query": ""})
		first_channel_id = form._channel.id

	assert real_render.channels.release_channel(first_channel_id)

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
		route=route_ctx,
	):
		form.render()
		real_render.channels.handle_client_event(
			render=real_render,
			session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
			message=cast(
				ClientChannelRequestMessage,
				{
					"type": "channel_message",
					"channel": form._channel.id,
					"event": "syncValues",
					"payload": {"values": {"query": "xrd"}},
				},
			),
		)
		await asyncio.sleep(0)

	assert form.values["query"] == "xrd"
