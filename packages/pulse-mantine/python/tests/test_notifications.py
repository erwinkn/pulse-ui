from types import SimpleNamespace
from typing import Any, cast

import pulse as ps
from pulse.user_session import UserSession
from pulse_mantine.core.feedback.notifications import NotificationsStore


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


def connect_channel(real_render: ps.RenderSession, channel_id: str) -> None:
	real_render.channels.handle_client_connect(
		{"type": "channel_connect", "channel": channel_id, "path": "/"}
	)


def test_notification_show_keeps_callback_server_side():
	app, render, session, real_render = build_context()

	def on_open(notification: dict[str, Any]) -> None:
		notification["opened"] = True

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		store = NotificationsStore()
		connect_channel(real_render, store._channel.id)  # pyright: ignore[reportPrivateUsage]
		ident = store.show({"message": "Saved", "onOpen": on_open})

	assert store.registry[ident]["onOpen"] is on_open
	assert render.sent[0]["event"] == "show"
	assert render.sent[0]["payload"] == {"message": "Saved", "id": ident}


def test_notification_update_keeps_callbacks_server_side():
	app, render, session, real_render = build_context()

	def on_close(notification: dict[str, Any]) -> None:
		notification["closed"] = True

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		store = NotificationsStore()
		connect_channel(real_render, store._channel.id)  # pyright: ignore[reportPrivateUsage]
		store.show({"id": "toast", "message": "Saving"})
		store.update({"id": "toast", "message": "Saved", "onClose": on_close})

	assert store.registry["toast"]["onClose"] is on_close
	assert render.sent[1]["event"] == "update"
	assert render.sent[1]["payload"] == {"id": "toast", "message": "Saved"}


def test_notification_update_state_keeps_callbacks_server_side():
	app, render, session, real_render = build_context()

	def on_close(notification: dict[str, Any]) -> None:
		notification["closed"] = True

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		store = NotificationsStore()
		connect_channel(real_render, store._channel.id)  # pyright: ignore[reportPrivateUsage]
		store.updateState(
			[
				{
					"id": "toast",
					"message": "Synced",
					"onClose": on_close,
				}
			]
		)

	assert store.registry["toast"]["onClose"] is on_close
	assert render.sent[0]["event"] == "updateState"
	assert render.sent[0]["payload"] == {
		"notifications": [{"id": "toast", "message": "Synced"}]
	}
