from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from pulse_railway.commands.common import (
	build_target_project,
	env,
	load_deploy_target,
)
from pulse_railway.constants import RAILWAY_WORKSPACE_ID
from pulse_railway.railway import RailwayGraphQLClient
from pulse_railway.stack import bootstrap_stack


def _add_init_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument(
		"--app-file",
		default=env("PULSE_RAILWAY_APP_FILE") or "main.py",
		help="App entry file used to load RailwayPlugin config",
	)
	parser.add_argument("--project-id", default=None, help="Railway project id")
	parser.add_argument(
		"--environment-id",
		default=None,
		help="Railway environment id",
	)
	parser.add_argument(
		"--workspace-id",
		default=env(RAILWAY_WORKSPACE_ID),
		help="Railway workspace id. Required when creating a new project.",
	)
	parser.add_argument(
		"--project-name",
		default=None,
		help="Railway project name when creating a new project. Defaults to the app file stem.",
	)
	parser.add_argument(
		"--token",
		default=None,
		help="Railway project access token",
	)
	parser.add_argument(
		"--service-prefix",
		default=None,
		help="Backend Railway service prefix. Defaults to the RailwayPlugin service prefix.",
	)
	parser.add_argument(
		"--redis-url",
		default=env("REDIS_URL"),
		help="Explicit shared Redis URL. If omitted, pulse-railway manages a Redis service in Railway.",
	)
	parser.add_argument(
		"--redis-prefix",
		default=env("PULSE_RAILWAY_REDIS_PREFIX") or "pulse:railway",
		help="Redis key prefix for pulse-railway control-plane state.",
	)
	parser.add_argument(
		"--router-image",
		default=env("PULSE_RAILWAY_ROUTER_IMAGE"),
		help="Prebuilt router image. If omitted, pulse-railway builds one when needed.",
	)
	parser.add_argument(
		"--janitor-image",
		default=env("PULSE_RAILWAY_JANITOR_IMAGE"),
		help="Prebuilt janitor image. Defaults to the router image.",
	)
	parser.add_argument(
		"--janitor-cron-schedule",
		default=env("PULSE_RAILWAY_JANITOR_CRON_SCHEDULE") or "*/5 * * * *",
		help="Railway cron schedule for the janitor service. Defaults to every 5 minutes.",
	)
	parser.add_argument(
		"--drain-grace-seconds",
		type=int,
		default=int(env("PULSE_RAILWAY_JANITOR_DRAIN_GRACE_SECONDS") or "60"),
		help="Minimum idle and drain duration before janitor cleanup.",
	)
	parser.add_argument(
		"--max-drain-age-seconds",
		type=int,
		default=int(env("PULSE_RAILWAY_JANITOR_MAX_DRAIN_AGE_SECONDS") or "86400"),
		help="Maximum time to keep a draining deployment before forced cleanup.",
	)
	parser.add_argument(
		"--backend-port",
		type=int,
		default=int(env("PULSE_RAILWAY_BACKEND_PORT") or "8000"),
		help="Backend container port used by the router and janitor.",
	)
	parser.add_argument(
		"--router-replicas",
		type=int,
		default=int(env("PULSE_RAILWAY_ROUTER_REPLICAS") or "1"),
		help="Router Railway replicas",
	)


async def _resolve_init_target(
	*,
	app_path: Path,
	deploy_target_project_id: str | None,
	deploy_target_environment_id: str | None,
	args: argparse.Namespace,
	token: str | None,
) -> tuple[str, str]:
	project_id = (
		args.project_id or deploy_target_project_id or env("RAILWAY_PROJECT_ID")
	)
	environment_id = (
		args.environment_id
		or deploy_target_environment_id
		or env("RAILWAY_ENVIRONMENT_ID")
	)
	if project_id:
		if not environment_id or not token:
			raise ValueError("project id, environment id, and token are required")
		return project_id, environment_id
	if environment_id:
		raise ValueError(
			"environment id requires an existing project id; omit both to create a new project"
		)
	if not token:
		raise ValueError("token is required")
	workspace_id = args.workspace_id or env(RAILWAY_WORKSPACE_ID)
	if not workspace_id:
		async with RailwayGraphQLClient(token=token) as client:
			try:
				data = await client.graphql(
					"""
					query {
						projectToken {
							projectId
							environmentId
						}
					}
					""",
					auth_mode="project-token",
				)
			except Exception:
				data = {}
		project_token = data.get("projectToken") if isinstance(data, dict) else None
		if isinstance(project_token, dict):
			project_id = project_token.get("projectId")
			environment_id = project_token.get("environmentId")
			if project_id and environment_id:
				return project_id, environment_id
	if not workspace_id:
		raise ValueError("workspace id is required when creating a new project")
	project_name = (args.project_name or app_path.stem).strip()
	if not project_name:
		raise ValueError("project name must not be empty")
	async with RailwayGraphQLClient(token=token) as client:
		project_id = await client.create_project(
			name=project_name,
			workspace_id=workspace_id,
		)
		environments = await client.list_environments(project_id=project_id)
	if not environments:
		raise ValueError(
			f"created Railway project {project_id} without any environments"
		)
	return project_id, environments[0].id


async def _run_init(args: argparse.Namespace) -> int:
	base_path = Path.cwd()
	app_path, deploy_target = load_deploy_target(
		app_file=args.app_file,
		base_path=base_path,
	)
	token = args.token or env("RAILWAY_TOKEN")
	project_id, environment_id = await _resolve_init_target(
		app_path=app_path,
		deploy_target_project_id=deploy_target.project_id,
		deploy_target_environment_id=deploy_target.environment_id,
		args=args,
		token=token,
	)
	project = build_target_project(
		args,
		deploy_target=deploy_target,
		project_id=project_id,
		environment_id=environment_id,
		token=token,
		redis_url=args.redis_url,
		backend_port=args.backend_port,
		router_replicas=args.router_replicas,
		router_image=args.router_image,
		janitor_image=args.janitor_image,
		janitor_cron_schedule=args.janitor_cron_schedule,
		drain_grace_seconds=args.drain_grace_seconds,
		max_drain_age_seconds=args.max_drain_age_seconds,
	)
	result = await bootstrap_stack(project=project)
	print(json.dumps(asdict(result), indent=2, sort_keys=True))
	return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
	init_parser = subparsers.add_parser(
		"init",
		help="Bootstrap the stable Railway router, redis, and janitor stack.",
	)
	_add_init_args(init_parser)


def main(args: argparse.Namespace) -> int:
	return asyncio.run(_run_init(args))
