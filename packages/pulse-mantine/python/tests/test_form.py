import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast

import pulse as ps
import pytest
from pulse.messages import ClientChannelRequestMessage
from pulse.routing import Route, RouteInfo, RouteTree
from pulse.serializer import serialize
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
	def page():
		return ps.div()

	route = Route("/", ps.component(page))
	routes = RouteTree([route])
	app = ps.App(routes=[route])
	dummy_render = DummyRender()
	session = SimpleNamespace(sid="session-1")

	real_render = ps.RenderSession(
		dummy_render.id, routes, server_address="http://localhost"
	)
	real_render.send = dummy_render.send  # pyright: ignore[reportAttributeAccessIssue]
	with ps.PulseContext(app=app):
		real_render.prerender(
			["/"],
			cast(
				RouteInfo,
				cast(
					object,
					{
						"pathname": "/",
						"hash": "",
						"query": "",
						"queryParams": {},
						"pathParams": {},
						"catchall": [],
					},
				),
			),
		)
	route_ctx = real_render.route_mounts["/"].route

	app.render_sessions[dummy_render.id] = real_render
	app._render_to_user[dummy_render.id] = session.sid  # pyright: ignore[reportPrivateUsage]
	app.user_sessions[session.sid] = session  # pyright: ignore[reportArgumentType]
	return app, dummy_render, session, real_render, route_ctx


def client_channel_request(message: object) -> ClientChannelRequestMessage:
	return cast(ClientChannelRequestMessage, message)


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
		first_channel_id = form._channel.id  # pyright: ignore[reportPrivateUsage]

	assert real_render.channels.release_channel(first_channel_id)
	assert form._channel.closed  # pyright: ignore[reportPrivateUsage]

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
		route=route_ctx,
	):
		form.reset()

	assert not form._channel.closed  # pyright: ignore[reportPrivateUsage]
	assert form._channel.id != first_channel_id  # pyright: ignore[reportPrivateUsage]
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
		first_channel_id = form._channel.id  # pyright: ignore[reportPrivateUsage]

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
			message=client_channel_request(
				{
					"type": "channel_message",
					"channel": form._channel.id,  # pyright: ignore[reportPrivateUsage]
					"event": "syncValues",
					"payload": {"values": {"query": "xrd"}},
				},
			),
		)
		await asyncio.sleep(0)

	assert form.values["query"] == "xrd"


def test_form_exposes_submit_state():
	app, _render, session, real_render, route_ctx = build_context()

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
		route=route_ctx,
	):
		form = MantineForm()

	assert not form.is_submitting

	form._form._start_submit()  # pyright: ignore[reportPrivateUsage]

	assert form.is_submitting


@pytest.mark.asyncio
async def test_submit_state_resets_after_successful_submit():
	app, _render, session, real_render, route_ctx = build_context()
	started = asyncio.Event()
	release = asyncio.Event()
	received: list[dict[str, Any]] = []

	async def handle_submit(values: dict[str, Any]):
		received.append(values)
		started.set()
		await release.wait()

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
		route=route_ctx,
	):
		form = MantineForm()
		form.render(onSubmit=handle_submit)

	form._form._start_submit()  # pyright: ignore[reportPrivateUsage]
	task = asyncio.create_task(
		form._form.registration.on_submit(  # pyright: ignore[reportPrivateUsage]
			{"__data__": json.dumps(serialize({"name": "Ada"}))}
		)
	)
	await asyncio.wait_for(started.wait(), timeout=1)

	assert form.is_submitting

	release.set()
	await task

	assert received == [{"name": "Ada"}]
	assert not form.is_submitting


@pytest.mark.asyncio
async def test_submit_accepts_registry_deserialized_data():
	app, _render, session, real_render, route_ctx = build_context()
	received: list[dict[str, Any]] = []

	async def handle_submit(values: dict[str, Any]):
		received.append(values)

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
		route=route_ctx,
	):
		form = MantineForm()
		form.render(onSubmit=handle_submit)

	await form._form.registration.on_submit(  # pyright: ignore[reportPrivateUsage]
		{"name": "Ada", "profile": {"role": "admin"}}
	)

	assert received == [{"name": "Ada", "profile": {"role": "admin"}}]


@pytest.mark.asyncio
async def test_submit_state_resets_after_failed_submit():
	app, _render, session, real_render, route_ctx = build_context()
	started = asyncio.Event()
	release = asyncio.Event()

	async def handle_submit(_values: dict[str, Any]):
		started.set()
		await release.wait()
		raise RuntimeError("boom")

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
		route=route_ctx,
	):
		form = MantineForm()
		form.render(onSubmit=handle_submit)

	form._form._start_submit()  # pyright: ignore[reportPrivateUsage]
	task = asyncio.create_task(
		form._form.registration.on_submit(  # pyright: ignore[reportPrivateUsage]
			{"__data__": json.dumps(serialize({"name": "Ada"}))}
		)
	)
	await asyncio.wait_for(started.wait(), timeout=1)

	assert form.is_submitting

	release.set()
	with pytest.raises(RuntimeError, match="boom"):
		await task

	assert not form.is_submitting
