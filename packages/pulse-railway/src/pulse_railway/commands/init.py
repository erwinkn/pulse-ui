from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pulse_railway.auth import railway_access_token
from pulse_railway.commands.common import (
	build_target_project,
	environment_name_from_sources,
	load_deploy_target,
	project_name_from_sources,
	resolve_railway_target_ids,
)
from pulse_railway.constants import (
	DEFAULT_BACKEND_PORT,
	DEFAULT_DRAIN_GRACE_SECONDS,
	DEFAULT_JANITOR_CRON_SCHEDULE,
	DEFAULT_MAX_DRAIN_AGE_SECONDS,
	DEFAULT_REDIS_PREFIX,
)
from pulse_railway.stack import bootstrap_stack


def _add_init_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument(
		"--app-file",
		default="main.py",
		help="App entry file used to load RailwayPlugin config",
	)
	parser.add_argument(
		"--project",
		default=None,
		help="Railway project name. Optional when using a project token.",
	)
	parser.add_argument(
		"--environment",
		default=None,
		help="Railway environment name. Defaults to production.",
	)
	parser.add_argument(
		"--workspace-id",
		default=None,
		help="Railway workspace id used to disambiguate project lookup.",
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
		default=None,
		help="Explicit shared Redis URL. If omitted, pulse-railway manages a Redis service in Railway.",
	)
	parser.add_argument(
		"--redis-prefix",
		default=DEFAULT_REDIS_PREFIX,
		help="Redis key prefix for pulse-railway control-plane state.",
	)
	parser.add_argument(
		"--router-image",
		default=None,
		help="Router image override. Defaults to the official pulse-railway router image for this package version.",
	)
	parser.add_argument(
		"--janitor-image",
		default=None,
		help="Janitor image override. Defaults to the official pulse-railway janitor image for this package version.",
	)
	parser.add_argument(
		"--janitor-cron-schedule",
		default=DEFAULT_JANITOR_CRON_SCHEDULE,
		help="Railway cron schedule for the janitor service. Defaults to every 5 minutes.",
	)
	parser.add_argument(
		"--drain-grace-seconds",
		type=int,
		default=DEFAULT_DRAIN_GRACE_SECONDS,
		help="Minimum idle and drain duration before janitor cleanup.",
	)
	parser.add_argument(
		"--max-drain-age-seconds",
		type=int,
		default=DEFAULT_MAX_DRAIN_AGE_SECONDS,
		help="Maximum time to keep a draining deployment before forced cleanup.",
	)
	parser.add_argument(
		"--backend-port",
		type=int,
		default=DEFAULT_BACKEND_PORT,
		help="Backend container port used by the router and janitor.",
	)
	parser.add_argument(
		"--router-replicas",
		type=int,
		default=1,
		help="Router Railway replicas",
	)


async def _run_init(args: argparse.Namespace) -> int:
	base_path = Path.cwd()
	_app_path, deploy_target = load_deploy_target(
		app_file=args.app_file,
		base_path=base_path,
	)
	token = args.token or railway_access_token()
	if not token:
		raise ValueError("token is required")
	project_id, environment_id = await resolve_railway_target_ids(
		project_name=project_name_from_sources(args, deploy_target),
		environment_name=environment_name_from_sources(args, deploy_target),
		token=token,
		workspace_id=args.workspace_id,
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


add_init_args = _add_init_args
run_init = _run_init


def register(subparsers: Any) -> None:
	init_parser = subparsers.add_parser(
		"init",
		help="Bootstrap the stable Railway router, redis, and janitor stack.",
	)
	_add_init_args(init_parser)


def main(args: argparse.Namespace) -> int:
	return asyncio.run(_run_init(args))
