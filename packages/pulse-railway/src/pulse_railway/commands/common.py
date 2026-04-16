from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import NotRequired, TypedDict, Unpack

from pulse.cli.helpers import load_app_from_target

from pulse_railway.config import RailwayProject
from pulse_railway.target import (
	RailwayDeployTarget,
	RailwayDeployTargetError,
	railway_deploy_target_from_app,
)


class RailwayProjectOverrides(TypedDict):
	backend_port: NotRequired[int]
	backend_replicas: NotRequired[int]
	router_port: NotRequired[int]
	router_replicas: NotRequired[int]
	router_image: NotRequired[str | None]
	server_address: NotRequired[str | None]
	redis_template_code: NotRequired[str]
	janitor_image: NotRequired[str | None]
	janitor_replicas: NotRequired[int]
	janitor_cron_schedule: NotRequired[str]
	drain_grace_seconds: NotRequired[int]
	max_drain_age_seconds: NotRequired[int]
	websocket_heartbeat_seconds: NotRequired[int]
	websocket_ttl_seconds: NotRequired[int]


def env(name: str) -> str | None:
	return os.environ.get(name)


def normalize_optional_service_prefix(value: str | None) -> str | None:
	from pulse_railway.railway import normalize_service_prefix

	if value is None:
		return None
	candidate = value.strip()
	if not candidate:
		return None
	return normalize_service_prefix(candidate)


def parse_kv_items(items: list[str] | None, label: str) -> dict[str, str]:
	parsed: dict[str, str] = {}
	if not items:
		return parsed
	for item in items:
		if "=" not in item:
			raise ValueError(f"{label} must be KEY=VALUE, got '{item}'")
		key, value = item.split("=", 1)
		if not key:
			raise ValueError(f"{label} must be KEY=VALUE, got '{item}'")
		parsed[key] = value
	return parsed


def resolve_path(base: Path, raw: str) -> Path:
	path = Path(raw).expanduser()
	if path.is_absolute():
		return path
	return (base / path).resolve()


def load_deploy_target(
	*,
	app_file: str,
	base_path: Path,
) -> tuple[Path, RailwayDeployTarget]:
	app_path = resolve_path(base_path, app_file)
	if not app_path.exists():
		raise ValueError(f"App file not found: {app_path}")
	app_ctx = load_app_from_target(str(app_path))
	try:
		return app_path, railway_deploy_target_from_app(app_ctx.app)
	except RailwayDeployTargetError as exc:
		raise ValueError(str(exc)) from exc


def build_target_project(
	args: argparse.Namespace,
	*,
	deploy_target: RailwayDeployTarget,
	project_id: str,
	environment_id: str,
	token: str,
	redis_url: str | None = None,
	env_vars: dict[str, str] | None = None,
	**overrides: Unpack[RailwayProjectOverrides],
) -> RailwayProject:
	service_prefix = (
		args.service_prefix
		or deploy_target.service_prefix
		or env("PULSE_RAILWAY_SERVICE_PREFIX")
	)
	return RailwayProject(
		project_id=project_id,
		environment_id=environment_id,
		token=token,
		service_name=deploy_target.router_service_name,
		service_prefix=normalize_optional_service_prefix(service_prefix),
		redis_url=redis_url,
		redis_service_name=deploy_target.redis_service_name,
		redis_prefix=getattr(args, "redis_prefix", None)
		or env("PULSE_RAILWAY_REDIS_PREFIX")
		or "pulse:railway",
		janitor_service_name=deploy_target.janitor_service_name,
		env_vars={} if env_vars is None else env_vars,
		**overrides,
	)
