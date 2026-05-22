"""Command-line interface for pulse-railway."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from typing import Unpack

from pulse_railway.auth import railway_access_token
from pulse_railway.commands.common import (
	RailwayProjectOverrides,
	add_railway_target_args,
	clean_optional,
	env,
	normalize_optional_service_prefix,
)
from pulse_railway.commands.deploy import (
	add_deploy_args as _add_deploy_args,
)
from pulse_railway.commands.deploy import (
	register as register_deploy,
)
from pulse_railway.commands.deploy import (
	run_deploy as _run_deploy,
)
from pulse_railway.commands.scaffold import (
	add_ensure_args as _add_ensure_args,
)
from pulse_railway.commands.scaffold import (
	add_scaffold_args as _add_scaffold_args,
)
from pulse_railway.commands.scaffold import (
	register as register_scaffold,
)
from pulse_railway.commands.scaffold import (
	run_ensure as _run_ensure,
)
from pulse_railway.commands.scaffold import (
	run_scaffold as _run_scaffold,
)
from pulse_railway.config import RailwayProject
from pulse_railway.constants import (
	DEFAULT_DRAIN_TTL_SECONDS,
	DEFAULT_REDIS_PREFIX,
	PULSE_DRAIN_TTL_SECONDS,
	PULSE_RAILWAY_JANITOR_SERVICE,
	PULSE_RAILWAY_REDIS_SERVICE,
	PULSE_RAILWAY_SERVICE,
)
from pulse_railway.control import (
	DrainingDeployment,
	delete_deployment_state,
	deployment_store_from_env,
	get_active_deployment,
	promote_deployment,
	register_deployment,
)
from pulse_railway.deployment import (
	delete_deployment,
	redeploy_deployment,
	resolve_deployment_id_by_name,
)
from pulse_railway.janitor import JanitorResult, run_janitor
from pulse_railway.railway.client import validate_deployment_id
from pulse_railway.railway.ops import resolve_railway_target_ids

RAILWAY_RUNTIME_ENV_VARS = (
	"RAILWAY_SERVICE_ID",
	"RAILWAY_REPLICA_ID",
	"RAILWAY_PRIVATE_DOMAIN",
)
JANITOR_RUN_DESCRIPTION = (
	"Run janitor cleanup inside a Railway service runtime. "
	"This command probes private Railway hostnames and fails immediately "
	"outside Railway."
)
JANITOR_RUN_RUNTIME_ERROR = (
	"pulse-railway janitor run must execute inside Railway. "
	"Expected at least one Railway runtime variable: "
	"RAILWAY_SERVICE_ID, RAILWAY_REPLICA_ID, or RAILWAY_PRIVATE_DOMAIN. "
	"Run it from the deployed janitor cron service, not a local shell."
)
CONTROL_RUN_DESCRIPTION = (
	"Run private deployment-control mutations inside the Railway router service. "
	"This command writes Redis state directly and fails outside Railway."
)
CONTROL_RUN_RUNTIME_ERROR = (
	"pulse-railway control must execute inside Railway. "
	"Run it through `railway ssh --service <router> -- pulse-railway control ...`, "
	"not from a local shell."
)


def _running_on_railway() -> bool:
	return any(env(name) for name in RAILWAY_RUNTIME_ENV_VARS)


def _require_railway_runtime() -> None:
	if _running_on_railway():
		return
	raise SystemExit(JANITOR_RUN_RUNTIME_ERROR)


def _require_control_runtime() -> None:
	if _running_on_railway():
		return
	raise SystemExit(CONTROL_RUN_RUNTIME_ERROR)


def _print_janitor_result(result: JanitorResult) -> None:
	if not result.lock_acquired:
		print("skipped; lock already held")
		return

	print(f"scan start; draining={result.scanned_count}")
	for deployment_id in result.deleted_deployments:
		if deployment_id in result.force_deleted_deployments:
			print(f"delete {deployment_id}; reason=drain_ttl")
			continue
		print(f"delete {deployment_id}; reason=drainable")
	for deployment_id in result.skipped_deployments:
		print(f"keep {deployment_id}; reason=still_active")
	message = (
		f"scan complete; deleted={len(result.deleted_deployments)} "
		+ f"skipped={len(result.skipped_deployments)}"
	)
	print(message)


def _railway_project(
	args: argparse.Namespace,
	*,
	project_id: str | None = None,
	environment_id: str | None = None,
	token: str | None = None,
	service_name: str | None = None,
	service_prefix: str | None = None,
	redis_service_name: str | None = None,
	**overrides: Unpack[RailwayProjectOverrides],
) -> RailwayProject:
	resolved_service_name = (
		service_name or getattr(args, "service", None) or "pulse-router"
	)
	resolved_service_prefix = service_prefix or getattr(args, "service_prefix", None)
	return RailwayProject(
		project_id=project_id or getattr(args, "project_id", None) or "",
		environment_id=environment_id or getattr(args, "environment_id", None) or "",
		token=token or getattr(args, "token", None) or railway_access_token() or "",
		service_name=resolved_service_name,
		service_prefix=normalize_optional_service_prefix(resolved_service_prefix),
		redis_url=getattr(args, "redis_url", None),
		redis_service_name=redis_service_name
		or getattr(args, "redis_service", None)
		or "",
		janitor_service_name=getattr(args, "janitor_service", None) or "",
		redis_prefix=getattr(args, "redis_prefix", None) or DEFAULT_REDIS_PREFIX,
		**overrides,
	)


def _add_management_target_args(
	parser: argparse.ArgumentParser,
	*,
	service_required: bool,
	include_redis_args: bool,
) -> None:
	if service_required:
		parser.add_argument(
			"--service", required=True, help="Stable router service name"
		)
	else:
		parser.add_argument(
			"--service",
			default="pulse-router",
			help="Stable router service name",
		)
	add_railway_target_args(parser)
	parser.add_argument("--token", default=railway_access_token())
	parser.add_argument("--service-prefix", default=None)
	if not include_redis_args:
		return
	parser.add_argument("--redis-url", default=None)
	parser.add_argument("--redis-service", default=None)
	parser.add_argument(
		"--redis-prefix",
		default=DEFAULT_REDIS_PREFIX,
	)


def _add_delete_args(parser: argparse.ArgumentParser) -> None:
	_add_management_target_args(
		parser,
		service_required=True,
		include_redis_args=True,
	)
	parser.add_argument(
		"--deployment-id", required=True, help="Deployment id to delete"
	)


def _add_remove_args(parser: argparse.ArgumentParser) -> None:
	_add_management_target_args(
		parser,
		service_required=True,
		include_redis_args=True,
	)
	parser.add_argument(
		"--deployment-name",
		required=True,
		help="Deployment name or exact deployment id to remove",
	)


def _add_redeploy_args(parser: argparse.ArgumentParser) -> None:
	_add_management_target_args(
		parser,
		service_required=False,
		include_redis_args=False,
	)
	parser.add_argument(
		"--deployment-id",
		default=None,
		help="Pulse deployment id to redeploy. Defaults to the active deployment in Redis.",
	)


def _add_janitor_run_args(parser: argparse.ArgumentParser) -> None:
	parser.description = JANITOR_RUN_DESCRIPTION
	parser.add_argument(
		"--service",
		default=env(PULSE_RAILWAY_SERVICE) or "pulse-router",
		help="Stable public Railway router service name for the deployed janitor.",
	)
	parser.add_argument(
		"--janitor-service",
		default=env(PULSE_RAILWAY_JANITOR_SERVICE),
		help="Stable Railway janitor service name. Defaults to <service>-janitor.",
	)
	parser.add_argument("--project-id", default=env("RAILWAY_PROJECT_ID"))
	parser.add_argument("--environment-id", default=env("RAILWAY_ENVIRONMENT_ID"))
	parser.add_argument("--token", default=railway_access_token())
	parser.add_argument("--service-prefix", default=env("PULSE_RAILWAY_SERVICE_PREFIX"))
	parser.add_argument(
		"--redis-url",
		default=env("REDIS_URL"),
		help="Redis URL used for draining state and janitor cleanup inside Railway.",
	)
	parser.add_argument(
		"--redis-service",
		default=env(PULSE_RAILWAY_REDIS_SERVICE),
		help="Stable Railway Redis service name. Defaults to <service>-redis.",
	)
	parser.add_argument(
		"--redis-prefix",
		default=env("PULSE_RAILWAY_REDIS_PREFIX") or DEFAULT_REDIS_PREFIX,
	)
	parser.add_argument(
		"--drain-ttl-seconds",
		type=int,
		default=int(env(PULSE_DRAIN_TTL_SECONDS) or str(DEFAULT_DRAIN_TTL_SECONDS)),
	)


def _add_control_args(parser: argparse.ArgumentParser) -> None:
	parser.description = CONTROL_RUN_DESCRIPTION
	control_subparsers = parser.add_subparsers(
		dest="control_command",
		required=True,
	)

	control_subparsers.add_parser("active", help="Print active deployment JSON.")

	register_parser = control_subparsers.add_parser(
		"register",
		help="Register a pending deployment in Redis.",
	)
	register_parser.add_argument("--deployment-id", required=True)
	register_parser.add_argument("--service-name", required=True)

	promote_parser = control_subparsers.add_parser(
		"promote",
		help="Promote a deployment and mark previous deployments draining.",
	)
	promote_parser.add_argument("--active-deployment-id", required=True)
	promote_parser.add_argument("--active-service-name", required=True)
	promote_parser.add_argument("--draining-json", default="[]")

	delete_parser = control_subparsers.add_parser(
		"delete",
		help="Delete inactive deployment state from Redis.",
	)
	delete_parser.add_argument("--deployment-id", required=True)


async def _named_railway_project(args: argparse.Namespace) -> RailwayProject:
	token = args.token or railway_access_token()
	if not token:
		raise ValueError("token is required")
	project_id, environment_id = await resolve_railway_target_ids(
		project_name=clean_optional(getattr(args, "project", None)),
		project_id=clean_optional(getattr(args, "project_id", None)),
		environment_name=clean_optional(getattr(args, "environment", None)),
		environment_id=clean_optional(getattr(args, "environment_id", None)),
		token=token,
		workspace_name=clean_optional(getattr(args, "workspace", None)),
		workspace_id=clean_optional(getattr(args, "workspace_id", None)),
	)
	return _railway_project(
		args,
		project_id=project_id,
		environment_id=environment_id,
		token=token,
	)


async def _run_delete(args: argparse.Namespace) -> int:
	project = await _named_railway_project(args)
	await delete_deployment(
		project=project,
		deployment_id=validate_deployment_id(args.deployment_id),
	)
	return 0


async def _run_remove(args: argparse.Namespace) -> int:
	project = await _named_railway_project(args)
	deployment_id = await resolve_deployment_id_by_name(
		project=project,
		deployment_name=args.deployment_name,
	)
	await delete_deployment(
		project=project,
		deployment_id=deployment_id,
	)
	print(deployment_id)
	return 0


async def _run_redeploy(args: argparse.Namespace) -> int:
	project = await _named_railway_project(args)
	result = await redeploy_deployment(
		project=project,
		deployment_id=args.deployment_id,
	)
	print(json.dumps(asdict(result), indent=2, sort_keys=True))
	return 0


async def _run_janitor_run(args: argparse.Namespace) -> int:
	_require_railway_runtime()
	if not args.project_id or not args.environment_id or not args.token:
		raise ValueError("project id, environment id, and token are required")
	result = await run_janitor(
		project=_railway_project(
			args,
			drain_ttl_seconds=args.drain_ttl_seconds,
		)
	)
	_print_janitor_result(result)
	return 0


def _parse_draining_deployments(value: str) -> list[DrainingDeployment]:
	try:
		payload = json.loads(value)
	except ValueError as exc:
		raise ValueError("draining-json must be valid JSON") from exc
	if not isinstance(payload, list):
		raise ValueError("draining-json must be a JSON list")
	deployments: list[DrainingDeployment] = []
	for item in payload:
		if not isinstance(item, dict):
			raise ValueError("draining-json entries must be objects")
		deployment_id = item.get("deployment_id")
		service_name = item.get("service_name")
		drain_started_at = item.get("drain_started_at")
		if not isinstance(deployment_id, str) or not isinstance(service_name, str):
			raise ValueError(
				"draining-json entries require deployment_id and service_name"
			)
		if drain_started_at is not None:
			if not isinstance(drain_started_at, str | int | float):
				raise ValueError("drain_started_at must be numeric")
			drain_started_at = float(drain_started_at)
		deployments.append(
			DrainingDeployment(
				deployment_id=deployment_id,
				service_name=service_name,
				drain_started_at=drain_started_at,
			)
		)
	return deployments


async def _run_control(args: argparse.Namespace) -> int:
	_require_control_runtime()
	store = deployment_store_from_env()
	try:
		if args.control_command == "active":
			deployment_id = await get_active_deployment(store)
			print(json.dumps({"deployment_id": deployment_id}, sort_keys=True))
			return 0
		if args.control_command == "register":
			await register_deployment(
				store,
				deployment_id=validate_deployment_id(args.deployment_id),
				service_name=args.service_name,
			)
			print(json.dumps({"ok": True}, sort_keys=True))
			return 0
		if args.control_command == "promote":
			await promote_deployment(
				store,
				active_deployment_id=validate_deployment_id(args.active_deployment_id),
				active_service_name=args.active_service_name,
				draining=_parse_draining_deployments(args.draining_json),
			)
			print(json.dumps({"ok": True}, sort_keys=True))
			return 0
		if args.control_command == "delete":
			await delete_deployment_state(
				store,
				deployment_id=validate_deployment_id(args.deployment_id),
			)
			print(json.dumps({"ok": True}, sort_keys=True))
			return 0
	finally:
		await store.close()
	return 1


def main() -> None:
	parser = argparse.ArgumentParser(prog="pulse-railway")
	subparsers = parser.add_subparsers(dest="command", required=True)

	register_scaffold(subparsers)
	register_deploy(subparsers)

	delete_parser = subparsers.add_parser("delete")
	_add_delete_args(delete_parser)

	remove_parser = subparsers.add_parser("remove")
	_add_remove_args(remove_parser)

	redeploy_parser = subparsers.add_parser(
		"redeploy",
		help="Redeploy the active backend deployment or an explicit deployment id.",
	)
	_add_redeploy_args(redeploy_parser)

	janitor_parser = subparsers.add_parser(
		"janitor",
		help="Janitor commands intended for the deployed Railway janitor service.",
	)
	janitor_subparsers = janitor_parser.add_subparsers(
		dest="janitor_command", required=True
	)
	janitor_run_parser = janitor_subparsers.add_parser(
		"run",
		help="Run janitor cleanup inside Railway. Fails outside Railway.",
		description=JANITOR_RUN_DESCRIPTION,
	)
	_add_janitor_run_args(janitor_run_parser)

	control_parser = subparsers.add_parser(
		"control",
		help="Private deployment-control commands for Railway runtime.",
		description=CONTROL_RUN_DESCRIPTION,
	)
	_add_control_args(control_parser)

	args = parser.parse_args()
	if args.command == "scaffold":
		raise SystemExit(asyncio.run(_run_scaffold(args)))
	if args.command == "ensure":
		raise SystemExit(asyncio.run(_run_ensure(args)))
	if args.command == "deploy":
		raise SystemExit(asyncio.run(_run_deploy(args)))
	if args.command == "delete":
		raise SystemExit(asyncio.run(_run_delete(args)))
	if args.command == "remove":
		raise SystemExit(asyncio.run(_run_remove(args)))
	if args.command == "redeploy":
		raise SystemExit(asyncio.run(_run_redeploy(args)))
	if args.command == "janitor" and args.janitor_command == "run":
		raise SystemExit(asyncio.run(_run_janitor_run(args)))
	if args.command == "control":
		raise SystemExit(asyncio.run(_run_control(args)))
	raise SystemExit(1)


__all__ = [
	"JANITOR_RUN_DESCRIPTION",
	"JANITOR_RUN_RUNTIME_ERROR",
	"CONTROL_RUN_DESCRIPTION",
	"CONTROL_RUN_RUNTIME_ERROR",
	"_add_deploy_args",
	"_add_ensure_args",
	"_add_janitor_run_args",
	"_add_redeploy_args",
	"_add_remove_args",
	"_add_scaffold_args",
	"_print_janitor_result",
	"_run_delete",
	"_run_control",
	"_run_deploy",
	"_run_ensure",
	"_run_janitor_run",
	"_run_redeploy",
	"_run_remove",
	"_run_scaffold",
	"main",
]
