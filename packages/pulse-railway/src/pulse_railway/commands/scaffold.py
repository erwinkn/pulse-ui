from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pulse_railway.auth import railway_access_token
from pulse_railway.commands.common import (
	add_railway_target_args,
	build_target_project,
	environment_id_from_sources,
	environment_name_from_sources,
	load_railway_plugin,
	project_id_from_sources,
	project_name_from_sources,
	resolve_railway_target_ids,
	workspace_id_from_sources,
	workspace_name_from_sources,
)
from pulse_railway.config import RailwayProject
from pulse_railway.constants import (
	DEFAULT_DRAIN_TTL_SECONDS,
	DEFAULT_JANITOR_CRON_SCHEDULE,
	DEFAULT_REDIS_PREFIX,
)
from pulse_railway.plugin import RailwayPlugin
from pulse_railway.stack import bootstrap_stack, ensure_stack


def _add_baseline_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument(
		"app_file",
		help="App entry file used to load RailwayPlugin config",
	)
	add_railway_target_args(parser)
	parser.add_argument(
		"--token",
		default=None,
		help="Railway project access token",
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
		"--janitor-cron-schedule",
		default=DEFAULT_JANITOR_CRON_SCHEDULE,
		help="Railway cron schedule for the janitor service. Defaults to every 5 minutes.",
	)
	parser.add_argument(
		"--drain-ttl-seconds",
		type=int,
		default=DEFAULT_DRAIN_TTL_SECONDS,
		help="Maximum time to keep a draining deployment before forced cleanup.",
	)
	parser.add_argument(
		"--router-replicas",
		type=int,
		default=1,
		help="Router Railway replicas",
	)


def _build_baseline_project(
	args: argparse.Namespace,
	*,
	project_id: str,
	environment_id: str,
	token: str,
	plugin: RailwayPlugin,
) -> RailwayProject:
	return build_target_project(
		args,
		plugin=plugin,
		project_id=project_id,
		environment_id=environment_id,
		token=token,
		redis_url=args.redis_url,
		router_replicas=args.router_replicas,
		janitor_cron_schedule=args.janitor_cron_schedule,
		drain_ttl_seconds=args.drain_ttl_seconds,
	)


async def _run_baseline(
	args: argparse.Namespace,
	*,
	ensure: bool,
) -> int:
	_app_path, plugin = load_railway_plugin(
		app_file=args.app_file,
		base_path=Path.cwd(),
	)
	token = args.token or railway_access_token()
	if not token:
		raise ValueError("token is required")
	project_id, environment_id = await resolve_railway_target_ids(
		project_name=project_name_from_sources(args, plugin),
		project_id=project_id_from_sources(args),
		environment_name=environment_name_from_sources(args, plugin),
		environment_id=environment_id_from_sources(args),
		token=token,
		workspace_name=workspace_name_from_sources(args),
		workspace_id=workspace_id_from_sources(args),
	)
	project = _build_baseline_project(
		args,
		project_id=project_id,
		environment_id=environment_id,
		token=token,
		plugin=plugin,
	)
	if ensure:
		result = await ensure_stack(project=project)
	else:
		result = await bootstrap_stack(project=project)
	print(json.dumps(asdict(result), indent=2, sort_keys=True))
	return 0


async def _run_scaffold(args: argparse.Namespace) -> int:
	return await _run_baseline(args, ensure=False)


async def _run_ensure(args: argparse.Namespace) -> int:
	return await _run_baseline(args, ensure=True)


add_scaffold_args = _add_baseline_args
add_ensure_args = _add_baseline_args
run_scaffold = _run_scaffold
run_ensure = _run_ensure


def register(subparsers: Any) -> None:
	scaffold_parser = subparsers.add_parser(
		"scaffold",
		help="Bootstrap the stable Railway router, redis, and janitor stack.",
	)
	_add_baseline_args(scaffold_parser)
	ensure_parser = subparsers.add_parser(
		"ensure",
		help="Create or reconcile the stable Railway baseline stack.",
	)
	_add_baseline_args(ensure_parser)


def main(args: argparse.Namespace) -> int:
	if args.command == "ensure":
		return asyncio.run(_run_ensure(args))
	return asyncio.run(_run_scaffold(args))
