from __future__ import annotations

from pulse_railway.auth import (
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
