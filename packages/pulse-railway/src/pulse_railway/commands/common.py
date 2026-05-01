from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import NotRequired, TypedDict, TypeVar, Unpack

from pulse.cli.helpers import load_app_from_target
from pulse.env import (
	ENV_PULSE_APP_DIR,
	ENV_PULSE_APP_FILE,
	ENV_PULSE_ENV,
)
from pulse.env import (
	env as pulse_env,
)

from pulse_railway.config import RailwayProject
from pulse_railway.constants import DEFAULT_REDIS_PREFIX
from pulse_railway.plugin import RailwayPlugin, RailwayPluginError
from pulse_railway.railway.client import (
	EnvironmentRecord,
	ProjectRecord,
	ProjectTokenRecord,
	RailwayGraphQLClient,
	WorkspaceRecord,
)

DEFAULT_RAILWAY_ENVIRONMENT_NAME = "production"
RailwayNameRecord = TypeVar(
	"RailwayNameRecord",
	ProjectRecord,
	EnvironmentRecord,
	WorkspaceRecord,
)


class RailwayProjectOverrides(TypedDict):
	backend_replicas: NotRequired[int]
	router_port: NotRequired[int]
	router_replicas: NotRequired[int]
	server_address: NotRequired[str | None]
	redis_template_code: NotRequired[str]
	janitor_replicas: NotRequired[int]
	janitor_cron_schedule: NotRequired[str]
	drain_ttl_seconds: NotRequired[int]


def env(name: str) -> str | None:
	return os.environ.get(name)


def clean_optional(value: str | None) -> str | None:
	if value is None:
		return None
	candidate = value.strip()
	return candidate or None


def normalize_optional_service_prefix(value: str | None) -> str | None:
	from pulse_railway.railway.client import normalize_service_prefix

	if value is None:
		return None
	candidate = value.strip()
	if not candidate:
		return None
	return normalize_service_prefix(candidate)


def add_railway_target_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument(
		"--workspace",
		default=None,
		help="Railway workspace name used to disambiguate project lookup.",
	)
	parser.add_argument(
		"--workspace-id",
		default=None,
		help="Railway workspace id used to disambiguate project lookup.",
	)
	parser.add_argument(
		"--project",
		default=None,
		help="Railway project name. Optional when using a project token.",
	)
	parser.add_argument(
		"--project-id",
		default=None,
		help="Railway project id. Optional when using a project token.",
	)
	parser.add_argument(
		"--environment",
		default=None,
		help="Railway environment name. Defaults to production.",
	)
	parser.add_argument(
		"--environment-id",
		default=None,
		help="Railway environment id. Optional when using a project token.",
	)


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


def load_railway_plugin(
	*,
	app_file: str,
	base_path: Path,
) -> tuple[Path, RailwayPlugin]:
	app_path = resolve_path(base_path, app_file)
	if not app_path.exists():
		raise ValueError(f"App file not found: {app_path}")
	previous_env = {
		ENV_PULSE_APP_DIR: os.environ.get(ENV_PULSE_APP_DIR),
		ENV_PULSE_APP_FILE: os.environ.get(ENV_PULSE_APP_FILE),
		ENV_PULSE_ENV: os.environ.get(ENV_PULSE_ENV),
	}
	previous_cwd = Path.cwd()
	try:
		os.chdir(base_path)
		pulse_env.pulse_env = "ci"
		pulse_env.pulse_app_file = str(app_path)
		pulse_env.pulse_app_dir = str(app_path.parent)
		app_ctx = load_app_from_target(str(app_path))
		if app_ctx.app.codegen.cfg.base_dir is None:
			app_ctx.app.codegen.cfg.base_dir = app_path.parent
		return app_path, RailwayPlugin.from_app(app_ctx.app)
	except RailwayPluginError as exc:
		raise ValueError(str(exc)) from exc
	finally:
		os.chdir(previous_cwd)
		for key, value in previous_env.items():
			if value is None:
				os.environ.pop(key, None)
			else:
				os.environ[key] = value


def project_name_from_sources(
	args: argparse.Namespace,
	plugin: RailwayPlugin,
) -> str | None:
	return clean_optional(getattr(args, "project", None) or plugin.project)


def environment_name_from_sources(
	args: argparse.Namespace,
	plugin: RailwayPlugin,
) -> str | None:
	return clean_optional(getattr(args, "environment", None) or plugin.environment)


def project_id_from_sources(args: argparse.Namespace) -> str | None:
	return clean_optional(getattr(args, "project_id", None))


def environment_id_from_sources(args: argparse.Namespace) -> str | None:
	return clean_optional(getattr(args, "environment_id", None))


def workspace_name_from_sources(args: argparse.Namespace) -> str | None:
	return clean_optional(getattr(args, "workspace", None))


def workspace_id_from_sources(args: argparse.Namespace) -> str | None:
	return clean_optional(getattr(args, "workspace_id", None))


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


def _reject_name_and_id(
	*,
	name: str | None,
	record_id: str | None,
	label: str,
) -> None:
	if name is not None and record_id is not None:
		raise ValueError(f"use either Railway {label} name or {label} id, not both")


async def _resolve_workspace_id(
	client: RailwayGraphQLClient,
	*,
	workspace_name: str | None,
	workspace_id: str | None,
) -> str | None:
	_reject_name_and_id(name=workspace_name, record_id=workspace_id, label="workspace")
	if workspace_id is not None:
		return workspace_id
	if workspace_name is None:
		return None
	workspaces = await client.list_workspaces()
	return _match_record_by_name(
		workspaces,
		name=workspace_name,
		label="workspace",
	).id


async def _resolve_project_id(
	client: RailwayGraphQLClient,
	*,
	project_name: str | None,
	project_id: str | None,
	project_token: ProjectTokenRecord | None,
	workspace_id: str | None,
) -> str:
	_reject_name_and_id(name=project_name, record_id=project_id, label="project")
	if project_id is not None:
		if project_token is not None and project_token.project_id != project_id:
			project = await client.get_project(project_id=project_token.project_id)
			raise ValueError(
				f"project token is scoped to Railway project {project.name}, not {project_id}"
			)
		return project_id
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
	environment_id: str | None,
	project_token_environment_id: str | None,
) -> str:
	_reject_name_and_id(
		name=environment_name,
		record_id=environment_id,
		label="environment",
	)
	if environment_id is not None:
		if (
			project_token_environment_id is not None
			and project_token_environment_id != environment_id
		):
			environment = await client.get_environment(
				environment_id=project_token_environment_id
			)
			raise ValueError(
				"project token is scoped to Railway environment "
				+ f"{environment.name}, not {environment_id}"
			)
		return environment_id
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
	token: str,
	project_name: str | None = None,
	project_id: str | None = None,
	environment_name: str | None = None,
	environment_id: str | None = None,
	workspace_name: str | None = None,
	workspace_id: str | None = None,
) -> tuple[str, str]:
	async with RailwayGraphQLClient(token=token) as client:
		project_token = await client.get_project_token()
		resolved_workspace_id = await _resolve_workspace_id(
			client,
			workspace_name=workspace_name,
			workspace_id=workspace_id,
		)
		project_id = await _resolve_project_id(
			client,
			project_name=project_name,
			project_id=project_id,
			project_token=project_token,
			workspace_id=resolved_workspace_id,
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
			environment_id=environment_id,
			project_token_environment_id=project_token_environment_id,
		)
	return project_id, environment_id


def build_target_project(
	args: argparse.Namespace,
	*,
	plugin: RailwayPlugin,
	project_id: str,
	environment_id: str,
	token: str,
	redis_url: str | None = None,
	env_vars: dict[str, str] | None = None,
	**overrides: Unpack[RailwayProjectOverrides],
) -> RailwayProject:
	service_prefix = getattr(args, "service_prefix", None) or plugin.service_prefix
	return RailwayProject(
		project_id=project_id,
		environment_id=environment_id,
		token=token,
		service_name=plugin.router_service_name,
		service_prefix=normalize_optional_service_prefix(service_prefix),
		redis_url=redis_url,
		redis_service_name=None if redis_url is not None else plugin.redis_service_name,
		redis_prefix=getattr(args, "redis_prefix", None) or DEFAULT_REDIS_PREFIX,
		janitor_service_name=plugin.janitor_service_name,
		env_vars={} if env_vars is None else env_vars,
		**overrides,
	)
