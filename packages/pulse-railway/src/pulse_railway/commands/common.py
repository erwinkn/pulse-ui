from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import NotRequired, TypedDict, TypeVar, Unpack

from pulse.cli.helpers import load_app_from_target

from pulse_railway.config import RailwayProject
from pulse_railway.constants import DEFAULT_REDIS_PREFIX
from pulse_railway.railway import (
	EnvironmentRecord,
	ProjectRecord,
	ProjectTokenRecord,
	RailwayGraphQLClient,
)
from pulse_railway.target import (
	RailwayDeployTarget,
	RailwayDeployTargetError,
	railway_deploy_target_from_app,
)

DEFAULT_RAILWAY_ENVIRONMENT_NAME = "production"
RailwayNameRecord = TypeVar(
	"RailwayNameRecord",
	ProjectRecord,
	EnvironmentRecord,
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


def clean_optional(value: str | None) -> str | None:
	if value is None:
		return None
	candidate = value.strip()
	return candidate or None


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


def project_name_from_sources(
	args: argparse.Namespace,
	deploy_target: RailwayDeployTarget,
) -> str | None:
	return clean_optional(getattr(args, "project", None) or deploy_target.project)


def environment_name_from_sources(
	args: argparse.Namespace,
	deploy_target: RailwayDeployTarget,
) -> str | None:
	return clean_optional(
		getattr(args, "environment", None) or deploy_target.environment
	)


def _match_record_by_name(
	records: list[RailwayNameRecord],
	*,
	name: str,
	label: str,
) -> RailwayNameRecord:
	matches = [record for record in records if record.name == name]
	if len(matches) == 1:
		return matches[0]
	if not matches:
		available = ", ".join(record.name for record in records) or "none"
		raise ValueError(
			f"Railway {label} not found by name: {name}. Available: {available}"
		)
	raise ValueError(f"multiple Railway {label}s named {name}")


async def _resolve_project_id(
	client: RailwayGraphQLClient,
	*,
	project_name: str | None,
	project_token: ProjectTokenRecord | None,
	workspace_id: str | None,
) -> str:
	if project_name is None:
		if project_token is None:
			raise ValueError(
				"Railway project is required unless token is a project token"
			)
		return project_token.project_id
	if project_token is not None:
		project = await client.get_project(project_id=project_token.project_id)
		if project.name != project_name:
			raise ValueError(
				f"project token is scoped to Railway project {project.name}, not {project_name}"
			)
		return project.id
	projects = await client.list_projects(workspace_id=workspace_id)
	return _match_record_by_name(
		projects,
		name=project_name,
		label="project",
	).id


async def _resolve_environment_id(
	client: RailwayGraphQLClient,
	*,
	project_id: str,
	environment_name: str | None,
	project_token_environment_id: str | None,
) -> str:
	if project_token_environment_id is not None:
		if environment_name is None:
			return project_token_environment_id
		environment = await client.get_environment(
			environment_id=project_token_environment_id
		)
		if environment.name == environment_name:
			return environment.id
		raise ValueError(
			"project token is scoped to Railway environment "
			+ f"{environment.name}, not {environment_name}"
		)
	resolved_environment_name = environment_name or DEFAULT_RAILWAY_ENVIRONMENT_NAME
	environments = await client.list_environments(project_id=project_id)
	return _match_record_by_name(
		environments,
		name=resolved_environment_name,
		label="environment",
	).id


async def resolve_railway_target_ids(
	*,
	project_name: str | None,
	environment_name: str | None,
	token: str,
	workspace_id: str | None = None,
) -> tuple[str, str]:
	async with RailwayGraphQLClient(token=token) as client:
		project_token = await client.get_project_token()
		project_id = await _resolve_project_id(
			client,
			project_name=project_name,
			project_token=project_token,
			workspace_id=workspace_id,
		)
		project_token_environment_id = (
			project_token.environment_id
			if project_token is not None and project_token.project_id == project_id
			else None
		)
		environment_id = await _resolve_environment_id(
			client,
			project_id=project_id,
			environment_name=environment_name,
			project_token_environment_id=project_token_environment_id,
		)
	return project_id, environment_id


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
	service_prefix = args.service_prefix or deploy_target.service_prefix
	return RailwayProject(
		project_id=project_id,
		environment_id=environment_id,
		token=token,
		service_name=deploy_target.router_service_name,
		service_prefix=normalize_optional_service_prefix(service_prefix),
		redis_url=redis_url,
		redis_service_name=deploy_target.redis_service_name,
		redis_prefix=getattr(args, "redis_prefix", None) or DEFAULT_REDIS_PREFIX,
		janitor_service_name=deploy_target.janitor_service_name,
		env_vars={} if env_vars is None else env_vars,
		**overrides,
	)
