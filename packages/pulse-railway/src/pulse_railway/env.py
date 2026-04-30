"""Declarative Railway environment variable builders."""

from __future__ import annotations

from pathlib import Path

from pulse_railway.constants import (
	DEFAULT_REDIS_PREFIX,
	PULSE_DEPLOYMENT_ID,
	PULSE_DEPLOYMENT_STATE,
	PULSE_DRAIN_GRACE_SECONDS,
	PULSE_DRAIN_STARTED_AT,
	PULSE_INTERNAL_TOKEN,
	PULSE_MAX_DRAIN_AGE_SECONDS,
	PULSE_RAILWAY_REDIS_URL,
	PULSE_REDIS_PREFIX,
	PULSE_SERVICE_PREFIX,
	PULSE_WEBSOCKET_HEARTBEAT_SECONDS,
	PULSE_WEBSOCKET_TTL_SECONDS,
	RAILWAY_TOKEN,
	REDIS_URL,
)
from pulse_railway.errors import DeploymentError

PULSE_APP_FILE = "PULSE_APP_FILE"
PULSE_BACKEND_PORT = "PULSE_BACKEND_PORT"
PULSE_SERVER_ADDRESS = "PULSE_SERVER_ADDRESS"
PULSE_WEB_ROOT = "PULSE_WEB_ROOT"
PORT = "PORT"
RAILWAY_DOCKERFILE_PATH = "RAILWAY_DOCKERFILE_PATH"

RESERVED_BACKEND_ENV_VARS: frozenset[str] = frozenset(
	{
		PULSE_DEPLOYMENT_ID,
		PULSE_DEPLOYMENT_STATE,
		PULSE_DRAIN_STARTED_AT,
		PULSE_INTERNAL_TOKEN,
		PULSE_RAILWAY_REDIS_URL,
		PULSE_APP_FILE,
		PULSE_SERVER_ADDRESS,
		PORT,
	}
)
RESERVED_ENV_REFERENCE_VARS: frozenset[str] = RESERVED_BACKEND_ENV_VARS.union(
	{"APP_FILE", "WEB_ROOT", PULSE_WEB_ROOT, RAILWAY_DOCKERFILE_PATH}
)


def is_user_managed_env_var(name: str) -> bool:
	return not name.startswith("RAILWAY_") and name not in RESERVED_ENV_REFERENCE_VARS


def validate_backend_env_vars(env_vars: dict[str, str]) -> None:
	reserved = sorted(key for key in env_vars if key in RESERVED_BACKEND_ENV_VARS)
	if reserved:
		raise DeploymentError(
			"backend env vars cannot override pulse-railway managed variables: "
			+ ", ".join(reserved)
		)


def check_reserved_source_build_args(build_args: dict[str, str]) -> None:
	reserved = sorted(key for key in build_args if key in RESERVED_BACKEND_ENV_VARS)
	if reserved:
		raise DeploymentError(
			"source build args cannot override pulse-railway managed variables: "
			+ ", ".join(reserved)
		)


def pulse_env_user_references(
	*,
	env_service_name: str,
	env_vars: dict[str, str],
) -> dict[str, str]:
	return {
		name: "${{" + f"{env_service_name}.{name}" + "}}"
		for name in env_vars
		if is_user_managed_env_var(name)
	}


def router_env(
	*,
	token: str,
	backend_port: int,
	router_port: int,
	service_prefix: str | None,
	redis_url: str | None,
	redis_prefix: str,
	websocket_heartbeat_seconds: int,
	websocket_ttl_seconds: int,
) -> dict[str, str]:
	env = {
		RAILWAY_TOKEN: token,
		PULSE_BACKEND_PORT: str(backend_port),
		PORT: str(router_port),
	}
	if service_prefix is not None:
		env[PULSE_SERVICE_PREFIX] = service_prefix
	if redis_url:
		env[REDIS_URL] = redis_url
		env[PULSE_REDIS_PREFIX] = redis_prefix
		env[PULSE_WEBSOCKET_HEARTBEAT_SECONDS] = str(websocket_heartbeat_seconds)
		env[PULSE_WEBSOCKET_TTL_SECONDS] = str(websocket_ttl_seconds)
	return env


def janitor_env(
	*,
	token: str,
	internal_token: str,
	redis_url: str,
	redis_prefix: str,
	service_prefix: str | None,
	drain_grace_seconds: int,
	max_drain_age_seconds: int,
) -> dict[str, str]:
	env = {
		RAILWAY_TOKEN: token,
		PULSE_INTERNAL_TOKEN: internal_token,
		REDIS_URL: redis_url,
		PULSE_REDIS_PREFIX: redis_prefix or DEFAULT_REDIS_PREFIX,
		PULSE_DRAIN_GRACE_SECONDS: str(drain_grace_seconds),
		PULSE_MAX_DRAIN_AGE_SECONDS: str(max_drain_age_seconds),
	}
	if service_prefix is not None:
		env[PULSE_SERVICE_PREFIX] = service_prefix
	return env


def backend_session_env(
	uses_railway_session_store: bool,
	*,
	redis_url: str | None,
) -> dict[str, str]:
	if not uses_railway_session_store:
		return {}
	if redis_url is None:
		raise DeploymentError("redis_url is required for Railway session store wiring")
	return {PULSE_RAILWAY_REDIS_URL: redis_url}


def backend_env(
	*,
	deployment_id: str,
	internal_token: str,
	app_file: str,
	server_address: str,
	backend_port: int,
	session_env: dict[str, str],
	user_env: dict[str, str],
) -> dict[str, str]:
	return {
		PULSE_DEPLOYMENT_ID: deployment_id,
		PULSE_INTERNAL_TOKEN: internal_token,
		PULSE_APP_FILE: app_file,
		PULSE_SERVER_ADDRESS: server_address,
		PORT: str(backend_port),
		**session_env,
		**user_env,
	}


def backend_build_env(
	*,
	build_args: dict[str, str],
	app_file: str,
	web_root: str,
	server_address: str,
	dockerfile_path: Path,
	context_path: Path,
) -> dict[str, str]:
	env = dict(build_args)
	env.setdefault(PULSE_APP_FILE, app_file)
	env.setdefault(PULSE_WEB_ROOT, web_root)
	env.setdefault(PULSE_SERVER_ADDRESS, server_address)
	try:
		dockerfile_relative = dockerfile_path.relative_to(context_path)
	except ValueError as exc:
		raise DeploymentError(
			"dockerfile must be inside the build context for railway up"
		) from exc
	if dockerfile_relative.as_posix() != "Dockerfile":
		env[RAILWAY_DOCKERFILE_PATH] = dockerfile_relative.as_posix()
	return env


__all__ = [
	"PULSE_APP_FILE",
	"PULSE_BACKEND_PORT",
	"PULSE_SERVER_ADDRESS",
	"PULSE_WEB_ROOT",
	"PORT",
	"RAILWAY_DOCKERFILE_PATH",
	"RESERVED_BACKEND_ENV_VARS",
	"RESERVED_ENV_REFERENCE_VARS",
	"backend_build_env",
	"backend_env",
	"backend_session_env",
	"check_reserved_source_build_args",
	"is_user_managed_env_var",
	"janitor_env",
	"pulse_env_user_references",
	"router_env",
	"validate_backend_env_vars",
]
