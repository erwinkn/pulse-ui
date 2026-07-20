from __future__ import annotations

from pathlib import Path

from pulse_railway.constants import (
	PULSE_DRAIN_TTL_SECONDS,
	PULSE_INTERNAL_TOKEN,
	PULSE_RAILWAY_JANITOR_SERVICE,
	PULSE_RAILWAY_REDIS_SERVICE,
	PULSE_RAILWAY_REDIS_URL,
	PULSE_RAILWAY_SERVICE,
	PULSE_REDIS_PREFIX,
	PULSE_SERVICE_PREFIX,
	RAILWAY_TOKEN,
	REDIS_URL,
)
from pulse_railway.env import (
	PORT,
	PULSE_APP_FILE,
	PULSE_PUBLIC_ORIGIN,
	PULSE_WEB_ROOT,
	RAILWAY_DOCKERFILE_PATH,
	backend_build_env,
	backend_env,
	backend_session_env,
	janitor_env,
	pulse_env_user_references,
	router_env,
)


def test_router_env_includes_redis_vars() -> None:
	assert router_env(
		token="token",
		router_port=9000,
		service_prefix="pulse-",
		redis_url="redis://internal",
		redis_prefix="pulse:railway",
	) == {
		RAILWAY_TOKEN: "token",
		PORT: "9000",
		PULSE_SERVICE_PREFIX: "pulse-",
		REDIS_URL: "redis://internal",
		PULSE_REDIS_PREFIX: "pulse:railway",
	}


def test_janitor_env_sets_drain_ttl() -> None:
	env = janitor_env(
		token="token",
		internal_token="secret",
		redis_url="redis://internal",
		redis_prefix="pulse:railway",
		router_service_name="pulse-router",
		janitor_service_name="pulse-janitor",
		redis_service_name="pulse-redis",
		service_prefix=None,
		drain_ttl_seconds=86400,
	)

	assert env == {
		RAILWAY_TOKEN: "token",
		PULSE_INTERNAL_TOKEN: "secret",
		REDIS_URL: "redis://internal",
		PULSE_REDIS_PREFIX: "pulse:railway",
		PULSE_DRAIN_TTL_SECONDS: "86400",
		PULSE_RAILWAY_SERVICE: "pulse-router",
		PULSE_RAILWAY_JANITOR_SERVICE: "pulse-janitor",
		PULSE_RAILWAY_REDIS_SERVICE: "pulse-redis",
	}


def test_backend_env_sets_direct_token_and_no_active_deployment() -> None:
	env = backend_env(
		deployment_id="prod",
		internal_token="secret",
		app_file="main.py",
		public_origin="https://example.com",
		session_env=backend_session_env(True, redis_url="redis://internal"),
		user_env={"FEATURE_FLAG": "on"},
	)

	assert env == {
		"PULSE_DEPLOYMENT_ID": "prod",
		PULSE_INTERNAL_TOKEN: "secret",
		PULSE_APP_FILE: "main.py",
		PULSE_PUBLIC_ORIGIN: "https://example.com",
		PORT: "8000",
		PULSE_RAILWAY_REDIS_URL: "redis://internal",
		"FEATURE_FLAG": "on",
	}
	assert "PULSE_ACTIVE_DEPLOYMENT" not in env


def test_backend_build_env_uses_prefixed_names(tmp_path: Path) -> None:
	dockerfile = tmp_path / "examples" / "Dockerfile"
	dockerfile.parent.mkdir()
	dockerfile.write_text("FROM scratch\n")

	assert backend_build_env(
		build_args={"FEATURE_BUILD": "on"},
		app_file="examples/main.py",
		web_root="examples/web",
		dockerfile_path=dockerfile,
		context_path=tmp_path,
	) == {
		"FEATURE_BUILD": "on",
		PULSE_APP_FILE: "examples/main.py",
		PULSE_WEB_ROOT: "examples/web",
		RAILWAY_DOCKERFILE_PATH: "examples/Dockerfile",
	}


def test_pulse_env_user_references_filters_managed_vars() -> None:
	assert pulse_env_user_references(
		env_service_name="pulse-env",
		env_vars={
			"USER_SECRET": "secret",
			"PULSE_APP_FILE": "managed",
			"RAILWAY_PRIVATE_DOMAIN": "managed",
		},
	) == {"USER_SECRET": "${{pulse-env.USER_SECRET}}"}
