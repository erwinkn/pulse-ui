from __future__ import annotations

import json

import pytest
from pulse_railway.auth import (
	RailwayCliAuthError,
	railway_access_token,
	railway_access_token_name,
	resolve_railway_access_token,
)


def test_resolve_railway_access_token_prefers_explicit_token(
	monkeypatch,
) -> None:
	monkeypatch.setenv("RAILWAY_TOKEN", "project-token")
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")

	token = resolve_railway_access_token("explicit-token")

	assert token.value == "explicit-token"
	assert token.env_name is None


def test_resolve_railway_access_token_prefers_railway_token(
	monkeypatch,
) -> None:
	monkeypatch.setenv("RAILWAY_TOKEN", "project-token")
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")

	token = resolve_railway_access_token()

	assert token.value == "project-token"
	assert token.env_name == "RAILWAY_TOKEN"
	assert railway_access_token() == "project-token"
	assert railway_access_token_name() == "RAILWAY_TOKEN"


def test_resolve_railway_access_token_falls_back_to_api_token(
	monkeypatch,
) -> None:
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")

	token = resolve_railway_access_token()

	assert token.value == "api-token"
	assert token.env_name == "RAILWAY_API_TOKEN"


def test_resolve_railway_access_token_falls_back_to_railway_cli_login(
	monkeypatch, tmp_path
) -> None:
	monkeypatch.setenv("HOME", str(tmp_path))
	config_path = tmp_path / ".railway" / "config.json"
	config_path.parent.mkdir()
	config_path.write_text(json.dumps({"user": {"accessToken": "cli-access-token"}}))

	token = resolve_railway_access_token()

	assert token.value == "cli-access-token"
	assert token.env_name is None
	assert railway_access_token() == "cli-access-token"
	assert railway_access_token_name() is None


def test_resolve_railway_access_token_prefers_env_over_railway_cli_login(
	monkeypatch, tmp_path
) -> None:
	monkeypatch.setenv("HOME", str(tmp_path))
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")
	config_path = tmp_path / ".railway" / "config.json"
	config_path.parent.mkdir()
	config_path.write_text(json.dumps({"user": {"accessToken": "cli-access-token"}}))

	token = resolve_railway_access_token()

	assert token.value == "api-token"
	assert token.env_name == "RAILWAY_API_TOKEN"


def test_resolve_railway_access_token_refreshes_expired_railway_cli_token(
	monkeypatch, tmp_path
) -> None:
	monkeypatch.setenv("HOME", str(tmp_path))
	monkeypatch.setattr("pulse_railway.auth.time.time", lambda: 1000.0)
	config_path = tmp_path / ".railway" / "config.json"
	config_path.parent.mkdir()
	config_path.write_text(
		json.dumps(
			{
				"user": {
					"accessToken": "expired-token",
					"refreshToken": "refresh-token",
					"tokenExpiresAt": 1,
				}
			}
		)
	)

	class _Response:
		def raise_for_status(self) -> None:
			return None

		def json(self) -> dict[str, object]:
			return {
				"access_token": "fresh-token",
				"refresh_token": "rotated-refresh-token",
				"expires_in": 3600,
			}

	def fake_post(url: str, *, data: dict[str, str], timeout: float) -> _Response:
		assert url == "https://backboard.railway.com/oauth/token"
		assert data == {
			"grant_type": "refresh_token",
			"refresh_token": "refresh-token",
			"client_id": "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12",
		}
		assert timeout == 30.0
		return _Response()

	monkeypatch.setattr("pulse_railway.auth.httpx.post", fake_post)

	token = resolve_railway_access_token()

	assert token.value == "fresh-token"
	assert token.env_name is None
	user = json.loads(config_path.read_text())["user"]
	assert user["accessToken"] == "fresh-token"
	assert user["refreshToken"] == "rotated-refresh-token"
	assert user["tokenExpiresAt"] == 4600.0


def test_resolve_railway_access_token_fails_when_expired_cli_token_cannot_refresh(
	monkeypatch, tmp_path
) -> None:
	monkeypatch.setenv("HOME", str(tmp_path))
	config_path = tmp_path / ".railway" / "config.json"
	config_path.parent.mkdir()
	config_path.write_text(
		json.dumps(
			{
				"user": {
					"accessToken": "expired-token",
					"tokenExpiresAt": 1,
				}
			}
		)
	)

	with pytest.raises(RailwayCliAuthError, match="expired and cannot refresh"):
		resolve_railway_access_token()
