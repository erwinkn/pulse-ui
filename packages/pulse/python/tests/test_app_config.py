import pulse as ps
import pytest
from pulse.user_session import UserSession


def test_app_prerender_queue_timeout_config():
	app = ps.App(
		prerender_queue_timeout=12.5,
		session_store=ps.CookieSessionStore(secret="test-secret"),
	)
	session = UserSession("test-session", {}, app)
	render = app.create_render("test-render", session)
	assert render.prerender_queue_timeout == 12.5
	render.close()
	session.dispose()


def test_app_proxy_config():
	proxy = ps.Proxy(
		max_concurrency=7,
		disconnect_watch_timeout=2.5,
		disconnect_watch_max_sleep=0.25,
	)
	app = ps.App(proxy=proxy)

	assert app.proxy is proxy


@pytest.mark.parametrize(
	("pulse_env", "expected_timeout"),
	[("dev", 0.1), ("prod", 0.0), ("ci", 0.0)],
)
def test_app_enables_strict_mode_detach_grace_only_in_dev(
	monkeypatch: pytest.MonkeyPatch, pulse_env: str, expected_timeout: float
):
	monkeypatch.setenv("PULSE_ENV", pulse_env)
	app = ps.App(session_store=ps.CookieSessionStore(secret="test-secret"))
	session = UserSession("test-session", {}, app)
	render = app.create_render("test-render", session)

	assert render.dev_strict_mode_detach_timeout == expected_timeout

	render.close()
	session.dispose()
