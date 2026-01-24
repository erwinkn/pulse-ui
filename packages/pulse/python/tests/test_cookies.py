import pytest
from pulse.app import App
from pulse.cookies import Cookie


def _setup_app(monkeypatch: pytest.MonkeyPatch, env: str, server_address: str):
	monkeypatch.setenv("PULSE_ENV", env)
	monkeypatch.setenv("PULSE_SSR_SERVER_ADDRESS", "http://localhost:3000")
	if env in ("prod", "ci"):
		monkeypatch.setenv("PULSE_SECRET", "test-secret")
	app = App()
	app.setup(server_address)
	return app


def test_secure_resolves_https_dev(monkeypatch: pytest.MonkeyPatch):
	app = _setup_app(monkeypatch, "dev", "https://example.com")
	assert app.cookie.secure is True


def test_secure_resolves_http_dev(monkeypatch: pytest.MonkeyPatch):
	app = _setup_app(monkeypatch, "dev", "http://localhost:8000")
	assert app.cookie.secure is False


def test_secure_blocks_http_prod(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_ENV", "prod")
	monkeypatch.setenv("PULSE_SSR_SERVER_ADDRESS", "http://localhost:3000")
	monkeypatch.setenv("PULSE_SECRET", "test-secret")
	app = App()
	with pytest.raises(RuntimeError, match="Refusing to use insecure cookies"):
		app.setup("http://example.com")


def test_secure_allows_http_localhost_prod(monkeypatch: pytest.MonkeyPatch):
	app = _setup_app(monkeypatch, "prod", "http://localhost:8000")
	assert app.cookie.secure is False


def test_secure_blocks_unknown_scheme_prod(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_ENV", "prod")
	monkeypatch.setenv("PULSE_SSR_SERVER_ADDRESS", "http://localhost:3000")
	monkeypatch.setenv("PULSE_SECRET", "test-secret")
	app = App()
	with pytest.raises(RuntimeError, match="Could not determine cookie security"):
		app.setup("example.com")


def test_secure_respects_explicit_override(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_ENV", "dev")
	monkeypatch.setenv("PULSE_SSR_SERVER_ADDRESS", "http://localhost:3000")
	app = App(cookie=Cookie("pulse.sid", secure=True))
	app.setup("http://localhost:8000")
	assert app.cookie.secure is True
