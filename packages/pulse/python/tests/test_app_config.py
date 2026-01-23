import pulse as ps
from pulse.user_session import UserSession


def test_app_prerender_queue_timeout_config():
	app = ps.App(prerender_queue_timeout=12.5)
	session = UserSession("test-session", {}, app)
	render = app.create_render("test-render", session)
	assert render.prerender_queue_timeout == 12.5
	render.close()
	session.dispose()
