from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx

from pulse_railway.constants import RAILWAY_API_TOKEN, RAILWAY_TOKEN

DEFAULT_RAILWAY_OAUTH_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
RAILWAY_OAUTH_TOKEN_REFRESH_TIMEOUT_SECONDS = 30.0
RAILWAY_OAUTH_TOKEN_EXPIRY_BUFFER_SECONDS = 60


@dataclass(frozen=True, slots=True)
class RailwayAccessToken:
	value: str | None
	env_name: str | None


@dataclass(frozen=True, slots=True)
class RailwayCliConfig:
	path: Path
	payload: dict[str, object]
	user: dict[str, object]


class RailwayCliAuthError(RuntimeError):
	pass


def _railway_cli_user_value(
	user: dict[str, object],
	primary_key: str,
	legacy_key: str,
) -> object:
	value = user.get(primary_key)
	if value is not None:
		return value
	return user.get(legacy_key)


def _railway_environment_name() -> str:
	return (os.environ.get("RAILWAY_ENV") or "production").strip().lower()


def _railway_cli_config_path() -> Path:
	environment = _railway_environment_name()
	suffix = ""
	if environment == "staging":
		suffix = "-staging"
	elif environment in {"dev", "develop"}:
		suffix = "-dev"
	return Path.home() / ".railway" / f"config{suffix}.json"


def _load_railway_cli_config() -> RailwayCliConfig | None:
	path = _railway_cli_config_path()
	try:
		payload = json.loads(path.read_text())
	except (OSError, ValueError):
		return None
	if not isinstance(payload, dict):
		return None
	user = payload.get("user")
	if not isinstance(user, dict):
		return None
	railway_payload = cast(dict[str, object], payload)
	railway_user = cast(dict[str, object], user)
	return RailwayCliConfig(path=path, payload=railway_payload, user=railway_user)


def _write_railway_cli_config(config: RailwayCliConfig) -> None:
	for key in ("token", "access_token", "refresh_token", "token_expires_at"):
		if config.user.get(key) is None:
			config.user.pop(key, None)
	try:
		config.path.write_text(json.dumps(config.payload, indent=2) + "\n")
	except OSError as exc:
		raise RailwayCliAuthError(
			f"failed to update Railway CLI auth config: {config.path}"
		) from exc


def _railway_cli_token_is_expired(expires_at: object) -> bool:
	if not isinstance(expires_at, int | float):
		return False
	return time.time() >= float(expires_at) - RAILWAY_OAUTH_TOKEN_EXPIRY_BUFFER_SECONDS


def _railway_oauth_host() -> str:
	environment = _railway_environment_name()
	if environment == "staging":
		return "railway-staging.com"
	if environment in {"dev", "develop"}:
		return "railway-develop.com"
	return "railway.com"


def _refresh_railway_cli_access_token(
	config: RailwayCliConfig,
	refresh_token: object,
) -> str:
	if not isinstance(refresh_token, str) or not refresh_token:
		raise RailwayCliAuthError("Railway CLI access token expired and cannot refresh")
	client_id = (
		os.environ.get("RAILWAY_OAUTH_CLIENT_ID") or DEFAULT_RAILWAY_OAUTH_CLIENT_ID
	)
	try:
		response = httpx.post(
			f"https://backboard.{_railway_oauth_host()}/oauth/token",
			data={
				"grant_type": "refresh_token",
				"refresh_token": refresh_token,
				"client_id": client_id,
			},
			timeout=RAILWAY_OAUTH_TOKEN_REFRESH_TIMEOUT_SECONDS,
		)
		response.raise_for_status()
		payload = response.json()
	except (httpx.HTTPError, ValueError):
		raise RailwayCliAuthError("Railway CLI access token refresh failed") from None
	access_token = payload.get("access_token")
	if not isinstance(access_token, str) or not access_token:
		raise RailwayCliAuthError("Railway CLI access token refresh failed")
	config.user["accessToken"] = access_token
	rotated_refresh_token = payload.get("refresh_token")
	if isinstance(rotated_refresh_token, str) and rotated_refresh_token:
		config.user["refreshToken"] = rotated_refresh_token
	token_expires_at = payload.get("token_expires_at")
	if isinstance(token_expires_at, int | float):
		config.user["tokenExpiresAt"] = int(token_expires_at)
	else:
		expires_in = payload.get("expires_in")
		if isinstance(expires_in, int | float):
			config.user["tokenExpiresAt"] = int(time.time() + float(expires_in))
	_write_railway_cli_config(config)
	return access_token


def _railway_cli_access_token() -> str | None:
	config = _load_railway_cli_config()
	if config is None:
		return None
	user = config.user
	access_token = _railway_cli_user_value(user, "accessToken", "access_token")
	if isinstance(access_token, str) and access_token:
		expires_at = _railway_cli_user_value(
			user,
			"tokenExpiresAt",
			"token_expires_at",
		)
		if _railway_cli_token_is_expired(expires_at):
			refresh_token = _railway_cli_user_value(
				user,
				"refreshToken",
				"refresh_token",
			)
			return _refresh_railway_cli_access_token(config, refresh_token)
		return access_token
	legacy_token = user.get("token")
	if not isinstance(legacy_token, str) or not legacy_token:
		return None
	return legacy_token


def resolve_railway_access_token(token: str | None = None) -> RailwayAccessToken:
	if token is not None:
		return RailwayAccessToken(
			value=token,
			env_name=railway_access_token_name_for_value(token),
		)
	railway_token = os.environ.get(RAILWAY_TOKEN)
	if railway_token is not None:
		return RailwayAccessToken(value=railway_token, env_name=RAILWAY_TOKEN)
	railway_api_token = os.environ.get(RAILWAY_API_TOKEN)
	if railway_api_token is not None:
		return RailwayAccessToken(value=railway_api_token, env_name=RAILWAY_API_TOKEN)
	return RailwayAccessToken(value=_railway_cli_access_token(), env_name=None)


def railway_access_token() -> str | None:
	return resolve_railway_access_token().value


def railway_access_token_name_for_value(token: str | None) -> str | None:
	if token is None:
		return None
	if token == os.environ.get(RAILWAY_API_TOKEN):
		return RAILWAY_API_TOKEN
	if token == os.environ.get(RAILWAY_TOKEN):
		return RAILWAY_TOKEN
	return None


def railway_access_token_name() -> str | None:
	return resolve_railway_access_token().env_name


def railway_cli_token_env_name_for_auth_mode(auth_mode: str) -> str:
	if auth_mode == "bearer":
		return RAILWAY_API_TOKEN
	if auth_mode == "project-token":
		return RAILWAY_TOKEN
	raise ValueError(f"unsupported Railway auth mode: {auth_mode}")


def railway_cli_token_env(token: str, *, env_name: str | None = None) -> dict[str, str]:
	if env_name is None:
		env_name = RAILWAY_TOKEN
	if env_name not in {RAILWAY_API_TOKEN, RAILWAY_TOKEN}:
		raise ValueError(f"unsupported Railway token env var: {env_name}")
	return {env_name: token}
