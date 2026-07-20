from types import SimpleNamespace
from typing import Any, cast

import httpx
import pulse as ps
import pytest
from fastapi import Request
from pulse_msal.plugin import (
	MSALPlugin,
	_callback_uri,  # pyright: ignore[reportPrivateUsage]
	_relative_path,  # pyright: ignore[reportPrivateUsage]
)


class _FakeCCA:
	def __init__(self) -> None:
		self.initiate_calls: list[dict[str, Any]] = []
		self.acquire_calls: list[tuple[dict[str, Any], dict[str, str]]] = []

	def initiate_auth_code_flow(self, **kwargs: Any) -> dict[str, str]:
		self.initiate_calls.append(kwargs)
		return {
			"auth_uri": "https://login.microsoftonline.com/authorize",
			"state": "test-state",
		}

	def acquire_token_by_auth_code_flow(
		self, flow: dict[str, Any], query: dict[str, str]
	) -> dict[str, Any]:
		self.acquire_calls.append((flow, query))
		return {"id_token_claims": {"sub": "user-1"}}


def _app(
	*, public_origin: str | None = "https://app.example.com"
) -> tuple[ps.App, ps.InMemorySessionStore, _FakeCCA]:
	cca = _FakeCCA()
	store = ps.InMemorySessionStore()
	plugin = MSALPlugin(
		client_id="client-id",
		client_secret="client-secret",
		tenant_id="tenant-id",
	)

	def fake_cca(_cache: Any) -> _FakeCCA:
		return cca

	cast(Any, plugin).cca = fake_cca
	app = ps.App(
		plugins=[plugin],
		public_origin=public_origin,
		session_store=store,
	)
	return app, store, cca


def _request(*, scheme: str = "https", host: str = "dev.example.com") -> Request:
	return Request(
		{
			"type": "http",
			"method": "GET",
			"scheme": scheme,
			"path": "/auth/login",
			"raw_path": b"/auth/login",
			"query_string": b"",
			"headers": [(b"host", host.encode())],
			"server": (host, 443 if scheme == "https" else 80),
			"client": ("127.0.0.1", 1234),
		}
	)


@pytest.mark.parametrize(
	"path",
	["/", "/secret", "/users?tab=active", "/docs#install"],
)
def test_relative_path_accepts_same_origin_paths(path: str) -> None:
	assert _relative_path(path) == path


@pytest.mark.parametrize(
	"path",
	[
		"https://evil.example/secret",
		"//evil.example/secret",
		"/\\evil.example/secret",
		"secret",
		"",
		None,
		123,
	],
)
def test_relative_path_rejects_external_or_ambiguous_paths(path: object) -> None:
	with pytest.raises(ValueError, match="relative path"):
		_relative_path(path)


def test_callback_uri_uses_configured_public_origin() -> None:
	app = SimpleNamespace(public_origin="https://app.example.com", env="prod")

	assert _callback_uri(
		cast(ps.App, cast(object, app)), _request(), "/auth/callback"
	) == ("https://app.example.com/auth/callback")


def test_callback_uri_requires_public_origin_in_production() -> None:
	app = SimpleNamespace(public_origin=None, env="prod")

	with pytest.raises(RuntimeError, match="public_origin"):
		_callback_uri(cast(ps.App, cast(object, app)), _request(), "/auth/callback")


def test_callback_uri_uses_request_origin_in_development() -> None:
	app = SimpleNamespace(public_origin=None, env="dev")

	assert (
		_callback_uri(
			cast(ps.App, cast(object, app)),
			_request(host="dev.example.com:8443"),
			"/auth/callback",
		)
		== "https://dev.example.com:8443/auth/callback"
	)


def test_plugin_requires_public_origin_during_production_setup(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv("PULSE_ENV", "prod")
	monkeypatch.delenv("PULSE_PUBLIC_ORIGIN", raising=False)
	app, _, _ = _app(public_origin=None)

	with pytest.raises(RuntimeError, match="public_origin"):
		app.setup()


@pytest.mark.asyncio
async def test_login_uses_public_origin_for_callback() -> None:
	app, _, cca = _app()
	app.setup()
	try:
		transport = httpx.ASGITransport(app=app.fastapi)
		async with httpx.AsyncClient(
			transport=transport,
			base_url="https://app.example.com",
		) as client:
			response = await client.get(
				"/auth/login",
				params={"next": "/dashboard"},
			)

		assert response.status_code == 307
		assert response.headers["location"] == (
			"https://login.microsoftonline.com/authorize"
		)
		assert cca.initiate_calls == [
			{
				"scopes": ["User.Read"],
				"redirect_uri": "https://app.example.com/auth/callback",
				"prompt": "select_account",
			}
		]
	finally:
		await app.close()


@pytest.mark.asyncio
async def test_login_rejects_absolute_next_before_starting_msal() -> None:
	app, _, cca = _app()
	app.setup()
	try:
		transport = httpx.ASGITransport(app=app.fastapi)
		async with httpx.AsyncClient(
			transport=transport,
			base_url="https://app.example.com",
		) as client:
			response = await client.get(
				"/auth/login",
				params={"next": "https://evil.example/steal"},
			)

		assert response.status_code == 400
		assert response.json() == {"detail": "next must be a same-origin relative path"}
		assert cca.initiate_calls == []
	finally:
		await app.close()


@pytest.mark.asyncio
async def test_callback_redirects_to_relative_next() -> None:
	app, _, cca = _app()
	app.setup()
	try:
		transport = httpx.ASGITransport(app=app.fastapi)
		async with httpx.AsyncClient(
			transport=transport,
			base_url="https://app.example.com",
		) as client:
			login_response = await client.get(
				"/auth/login",
				params={"next": "/dashboard?tab=profile"},
			)
			assert login_response.status_code == 307

			callback_response = await client.get(
				"/auth/callback",
				params={"code": "auth-code", "state": "test-state"},
			)

		assert callback_response.status_code == 307
		assert callback_response.headers["location"] == "/dashboard?tab=profile"
		assert len(cca.acquire_calls) == 1
	finally:
		await app.close()


@pytest.mark.asyncio
async def test_callback_rejects_unsafe_next_restored_from_session() -> None:
	app, store, cca = _app()
	app.setup()
	try:
		transport = httpx.ASGITransport(app=app.fastapi)
		async with httpx.AsyncClient(
			transport=transport,
			base_url="https://app.example.com",
		) as client:
			login_response = await client.get(
				"/auth/login",
				params={"next": "/dashboard"},
			)
			assert login_response.status_code == 307

			session_id = client.cookies[app.cookie.name]
			session = await store.get(session_id)
			assert session is not None
			session["msal"]["next"] = "https://evil.example/steal"

			callback_response = await client.get(
				"/auth/callback",
				params={"code": "auth-code", "state": "test-state"},
			)

		assert callback_response.status_code == 400
		assert callback_response.json() == {
			"detail": "next must be a same-origin relative path"
		}
		assert cca.acquire_calls == []
	finally:
		await app.close()
