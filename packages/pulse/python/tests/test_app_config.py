from typing import Any

import pulse as ps
import pytest
from pulse.serializer import Serializer
from pulse.user_session import UserSession


class RecordingSerializer:
	inner: Serializer

	def __init__(self) -> None:
		self.inner = Serializer()
		self.serialized: list[object] = []

	def serialize(self, data: Any):
		self.serialized.append(data)
		return self.inner.serialize(data)

	def deserialize(self, data: Any):
		return self.inner.deserialize(data)


def test_serializer_api_is_exported_from_pulse() -> None:
	assert ps.Serializer is Serializer
	assert ps.WireMap({"value": 1}) == {"value": 1}


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


def test_app_passes_serializer_to_render():
	serializer = RecordingSerializer()
	app = ps.App(
		serializer=serializer,  # pyright: ignore[reportArgumentType]
		session_store=ps.CookieSessionStore(secret="test-secret"),
	)
	user = UserSession("test-session", {}, app)
	render = app.create_render("test-render", user)

	assert app.serializer is serializer
	assert render.serializer is serializer

	render.close()
	user.dispose()


@pytest.mark.asyncio
async def test_app_uses_serializer_for_reload_messages():
	serializer = RecordingSerializer()
	app = ps.App(serializer=serializer)  # pyright: ignore[reportArgumentType]

	assert await app.reload_connected_clients() == 0
	assert serializer.serialized == [{"type": "reload"}]


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
