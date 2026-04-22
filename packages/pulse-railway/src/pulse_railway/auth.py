from __future__ import annotations

import os
from dataclasses import dataclass

from pulse_railway.constants import RAILWAY_API_TOKEN, RAILWAY_TOKEN


@dataclass(frozen=True, slots=True)
class RailwayAccessToken:
	value: str | None
	env_name: str | None


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
	return RailwayAccessToken(value=None, env_name=None)


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
