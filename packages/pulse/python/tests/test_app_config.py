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
	proxy = ps.WebProxyConfig(
		max_concurrency=7,
		disconnect_watch_timeout=2.5,
		disconnect_watch_max_sleep=0.25,
	)
	app = ps.App(proxy=proxy)

	assert app.proxy is proxy


def test_app_socketio_options_reach_the_server():
	app = ps.App(socketio_options={"cors_allowed_origins": "*"})

	assert app.sio.eio.cors_allowed_origins == "*"


def test_public_origin_prefers_explicit_value_and_normalizes_trailing_slash(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_PUBLIC_ORIGIN", "https://environment.example")
	app = ps.App(public_origin="https://EXPLICIT.example/")

	assert app.public_origin == "https://explicit.example"


def test_public_origin_falls_back_to_environment(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_PUBLIC_ORIGIN", "https://ENVIRONMENT.example:443/")

	app = ps.App()

	assert app.public_origin == "https://environment.example"


@pytest.mark.parametrize(
	"origin",
	[
		"example.com",
		"ftp://example.com",
		"https://user@example.com",
		"https://example.com/path",
		"https://example.com?query=1",
		"https://example.com#fragment",
	],
)
def test_public_origin_rejects_non_origins(origin: str):
	with pytest.raises(ValueError, match="public_origin"):
		ps.App(public_origin=origin)


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
