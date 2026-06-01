from types import SimpleNamespace
from typing import Any, cast

import pulse as ps
from pulse.channel import Channel
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


def connect_channel(channel: Channel) -> None:
	channel.connected = True


def test_notifications_keep_callbacks_server_side():
	app, render, session, real_render = build_context()
	opened: list[str] = []

	with ps.PulseContext(
		app=app,
		session=cast(UserSession, session),  # pyright: ignore[reportInvalidCast]
		render=real_render,
	):
		store = NotificationsStore()
		connect_channel(store._channel)  # pyright: ignore[reportPrivateUsage]
		ident = store.show(
			{
				"message": "Saved",
				"onOpen": lambda notification: opened.append(notification["id"]),
			}
		)

	assert store.registry[ident]["onOpen"]
	assert render.sent[0]["payload"] == {"message": "Saved", "id": ident}
