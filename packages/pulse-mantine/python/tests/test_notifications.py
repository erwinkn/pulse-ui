from types import SimpleNamespace
from typing import cast

import pulse as ps
from pulse.user_session import UserSession
from pulse_mantine import Notifications
from pulse_mantine.core.feedback.notifications import (
	NOTIFICATIONS_CHANNEL_ID,
	notifications_state,
)


@ps.component
def EmptyPage():
	return ps.div()


def test_notifications_channel_has_tab_lifetime():
	app = ps.App([ps.Route("/", EmptyPage)])
	render = ps.RenderSession("notifications-render", app.routes)
	session = cast(UserSession, cast(object, SimpleNamespace(sid="notifications-user")))

	with ps.PulseContext(app=app, session=session, render=render):
		render.prerender(["/"])
	mount = render.get_route_mount("/")
	with ps.PulseContext(app=app, session=session, render=render, route=mount.route):
		Notifications()
		store = notifications_state()
		channel = store._channel  # pyright: ignore[reportPrivateUsage]

	assert NOTIFICATIONS_CHANNEL_ID in render.channels._channels  # pyright: ignore[reportPrivateUsage]
	assert channel.lifetime == "tab"
	render.detach("/")
	assert channel.closed is False

	with ps.PulseContext(app=app, session=session, render=render):
		render.prerender(["/"])
	mount = render.get_route_mount("/")
	with ps.PulseContext(app=app, session=session, render=render, route=mount.route):
		Notifications()

	assert store._channel is channel  # pyright: ignore[reportPrivateUsage]
	assert NOTIFICATIONS_CHANNEL_ID in render.channels._channels  # pyright: ignore[reportPrivateUsage]
	render.close()
	assert channel.closed is True
