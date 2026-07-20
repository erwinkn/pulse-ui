import pytest
from fastapi import Response
from pulse.app import App
from pulse.cookies import Cookie


def _setup_app(monkeypatch: pytest.MonkeyPatch, env: str, public_origin: str):
	monkeypatch.setenv("PULSE_ENV", env)
	if env in ("prod", "ci"):
		monkeypatch.setenv("PULSE_SECRET", "test-secret")
	app = App(public_origin=public_origin)
	app.setup()
	return app


def test_secure_resolves_https_dev(monkeypatch: pytest.MonkeyPatch):
	app = _setup_app(monkeypatch, "dev", "https://example.com")
	assert app.cookie.secure is True


def test_secure_resolves_http_dev(monkeypatch: pytest.MonkeyPatch):
	app = _setup_app(monkeypatch, "dev", "http://localhost:8000")
	assert app.cookie.secure is False


def test_secure_blocks_http_prod(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_ENV", "prod")
	monkeypatch.setenv("PULSE_SECRET", "test-secret")
	with pytest.raises(ValueError, match="HTTPS"):
		App(public_origin="http://example.com")


def test_secure_blocks_unknown_scheme_prod(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_ENV", "prod")
	monkeypatch.setenv("PULSE_SECRET", "test-secret")
	with pytest.raises(ValueError, match="public_origin"):
		App(public_origin="example.com")


def test_secure_respects_explicit_override(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_ENV", "dev")
	app = App(cookie=Cookie("pulse.sid", secure=True))
	app.setup()
	assert app.cookie.secure is True


def test_prod_rejects_explicit_insecure_cookie(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_ENV", "prod")
	monkeypatch.setenv("PULSE_SECRET", "test-secret")
	app = App(cookie=Cookie("pulse.sid", secure=False))
	with pytest.raises(RuntimeError, match="insecure cookies"):
		app.setup()


@pytest.mark.asyncio
async def test_session_cookie_is_host_only(monkeypatch: pytest.MonkeyPatch):
	app = _setup_app(monkeypatch, "dev", "https://example.com")
	session = await app.get_or_create_session(None)
	response = Response()
	await session.handle_response(response)

	header = response.headers["set-cookie"]
	assert "Domain=" not in header
	assert "HttpOnly" in header
	assert "Secure" in header
