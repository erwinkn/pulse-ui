"""Command-line interface for pulse-railway."""

from __future__ import annotations

import argparse
import asyncio

from pulse_railway.commands.common import env, normalize_optional_service_prefix
from pulse_railway.commands.deploy import (
	_add_deploy_args,
	_run_deploy,
)
from pulse_railway.commands.deploy import (
	register as register_deploy,
)
from pulse_railway.commands.init import (
	_add_init_args,
	_run_init,
)
from pulse_railway.commands.init import (
	register as register_init,
)
from pulse_railway.commands.upgrade import (
	_add_upgrade_args,
	_run_upgrade,
)
from pulse_railway.commands.upgrade import (
	register as register_upgrade,
)
from pulse_railway.config import RailwayProject
from pulse_railway.deployment import (
	default_redis_service_name,
	delete_deployment,
	resolve_deployment_id_by_name,
)
from pulse_railway.janitor import JanitorResult, run_janitor
from pulse_railway.railway import validate_deployment_id

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


def _running_on_railway() -> bool:
	return any(env(name) for name in RAILWAY_RUNTIME_ENV_VARS)


def _require_railway_runtime() -> None:
	if _running_on_railway():
		return
	raise SystemExit(JANITOR_RUN_RUNTIME_ERROR)


def _print_janitor_result(result: JanitorResult) -> None:
	if not result.lock_acquired:
		print("skipped; lock already held")
		return

	print(f"scan start; draining={result.scanned_count}")
	for deployment_id in result.deleted_deployments:
		if deployment_id in result.force_deleted_deployments:
			print(f"delete {deployment_id}; reason=max_drain_age")
			continue
		print(f"delete {deployment_id}; reason=drainable")
	for deployment_id in result.skipped_deployments:
		print(f"keep {deployment_id}; reason=still_active")
	print(
		"scan complete; "
		f"deleted={len(result.deleted_deployments)} "
		f"skipped={len(result.skipped_deployments)}"
	)


def _railway_project(
	args: argparse.Namespace,
	*,
	project_id: str | None = None,
	environment_id: str | None = None,
	token: str | None = None,
	service_name: str | None = None,
	service_prefix: str | None = None,
	redis_service_name: str | None = None,
	**overrides: object,
) -> RailwayProject:
	service_name = (
		service_name or args.service or env("PULSE_RAILWAY_SERVICE") or "pulse-router"
	)
	service_prefix = (
		service_prefix or args.service_prefix or env("PULSE_RAILWAY_SERVICE_PREFIX")
	)
	return RailwayProject(
		project_id=project_id or args.project_id or env("RAILWAY_PROJECT_ID") or "",
		environment_id=environment_id
		or args.environment_id
		or env("RAILWAY_ENVIRONMENT_ID")
		or "",
		token=token or args.token or env("RAILWAY_TOKEN") or "",
		service_name=service_name,
		service_prefix=normalize_optional_service_prefix(service_prefix),
		redis_url=args.redis_url,
		redis_service_name=redis_service_name
		or args.redis_service
		or env("PULSE_RAILWAY_REDIS_SERVICE")
		or default_redis_service_name(service_name),
		redis_prefix=args.redis_prefix,
		**overrides,
	)


def _add_delete_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument("--service", required=True, help="Stable router service name")
	parser.add_argument(
		"--deployment-id", required=True, help="Deployment id to delete"
	)
	parser.add_argument("--project-id", default=env("RAILWAY_PROJECT_ID"))
	parser.add_argument("--environment-id", default=env("RAILWAY_ENVIRONMENT_ID"))
	parser.add_argument("--token", default=env("RAILWAY_TOKEN"))
	parser.add_argument("--service-prefix", default=env("PULSE_RAILWAY_SERVICE_PREFIX"))
	parser.add_argument(
		"--keep-active-variable",
		action="store_true",
		help="Do not delete PULSE_ACTIVE_DEPLOYMENT when it points at the removed deployment",
	)
	parser.add_argument("--redis-url", default=env("REDIS_URL"))
	parser.add_argument("--redis-service", default=env("PULSE_RAILWAY_REDIS_SERVICE"))
	parser.add_argument(
		"--redis-prefix",
		default=env("PULSE_RAILWAY_REDIS_PREFIX") or "pulse:railway",
	)


def _add_remove_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument("--service", required=True, help="Stable router service name")
	parser.add_argument(
		"--deployment-name",
		required=True,
		help="Deployment name or exact deployment id to remove",
	)
	parser.add_argument("--project-id", default=env("RAILWAY_PROJECT_ID"))
	parser.add_argument("--environment-id", default=env("RAILWAY_ENVIRONMENT_ID"))
	parser.add_argument("--token", default=env("RAILWAY_TOKEN"))
	parser.add_argument("--service-prefix", default=env("PULSE_RAILWAY_SERVICE_PREFIX"))
	parser.add_argument(
		"--keep-active-variable",
		action="store_true",
		help="Do not delete PULSE_ACTIVE_DEPLOYMENT when it points at the removed deployment",
	)
	parser.add_argument("--redis-url", default=env("REDIS_URL"))
	parser.add_argument("--redis-service", default=env("PULSE_RAILWAY_REDIS_SERVICE"))
	parser.add_argument(
		"--redis-prefix",
		default=env("PULSE_RAILWAY_REDIS_PREFIX") or "pulse:railway",
	)


def _add_janitor_run_args(parser: argparse.ArgumentParser) -> None:
	parser.description = JANITOR_RUN_DESCRIPTION
	parser.add_argument(
		"--service",
		default=env("PULSE_RAILWAY_SERVICE") or "pulse-router",
		help="Stable public Railway router service name for the deployed janitor.",
	)
	parser.add_argument("--project-id", default=env("RAILWAY_PROJECT_ID"))
	parser.add_argument("--environment-id", default=env("RAILWAY_ENVIRONMENT_ID"))
	parser.add_argument("--token", default=env("RAILWAY_TOKEN"))
	parser.add_argument("--service-prefix", default=env("PULSE_RAILWAY_SERVICE_PREFIX"))
	parser.add_argument(
		"--redis-url",
		default=env("REDIS_URL"),
		help="Redis URL used for draining state and janitor cleanup inside Railway.",
	)
	parser.add_argument(
		"--redis-service",
		default=env("PULSE_RAILWAY_REDIS_SERVICE"),
		help="Stable Railway Redis service name. Defaults to <service>-redis.",
	)
	parser.add_argument(
		"--redis-prefix",
		default=env("PULSE_RAILWAY_REDIS_PREFIX") or "pulse:railway",
	)
	parser.add_argument(
		"--drain-grace-seconds",
		type=int,
		default=int(env("PULSE_RAILWAY_JANITOR_DRAIN_GRACE_SECONDS") or "60"),
	)
	parser.add_argument(
		"--max-drain-age-seconds",
		type=int,
		default=int(env("PULSE_RAILWAY_JANITOR_MAX_DRAIN_AGE_SECONDS") or "86400"),
	)


async def _run_delete(args: argparse.Namespace) -> int:
	if not args.project_id or not args.environment_id or not args.token:
		raise ValueError("project id, environment id, and token are required")
	await delete_deployment(
		project=_railway_project(args),
		deployment_id=validate_deployment_id(args.deployment_id),
		clear_active=not args.keep_active_variable,
	)
	return 0


async def _run_remove(args: argparse.Namespace) -> int:
	if not args.project_id or not args.environment_id or not args.token:
		raise ValueError("project id, environment id, and token are required")
	project = _railway_project(args)
	deployment_id = await resolve_deployment_id_by_name(
		project=project,
		deployment_name=args.deployment_name,
	)
	await delete_deployment(
		project=project,
		deployment_id=deployment_id,
		clear_active=not args.keep_active_variable,
	)
	print(deployment_id)
	return 0


async def _run_janitor_run(args: argparse.Namespace) -> int:
	_require_railway_runtime()
	if not args.project_id or not args.environment_id or not args.token:
		raise ValueError("project id, environment id, and token are required")
	result = await run_janitor(
		project=_railway_project(
			args,
			drain_grace_seconds=args.drain_grace_seconds,
			max_drain_age_seconds=args.max_drain_age_seconds,
		)
	)
	_print_janitor_result(result)
	return 0


def main() -> None:
	parser = argparse.ArgumentParser(prog="pulse-railway")
	subparsers = parser.add_subparsers(dest="command", required=True)

	register_init(subparsers)
	register_upgrade(subparsers)
	register_deploy(subparsers)

	delete_parser = subparsers.add_parser("delete")
	_add_delete_args(delete_parser)

	remove_parser = subparsers.add_parser("remove")
	_add_remove_args(remove_parser)

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

	args = parser.parse_args()
	if args.command == "init":
		raise SystemExit(asyncio.run(_run_init(args)))
	if args.command == "upgrade":
		raise SystemExit(asyncio.run(_run_upgrade(args)))
	if args.command == "deploy":
		raise SystemExit(asyncio.run(_run_deploy(args)))
	if args.command == "delete":
		raise SystemExit(asyncio.run(_run_delete(args)))
	if args.command == "remove":
		raise SystemExit(asyncio.run(_run_remove(args)))
	if args.command == "janitor" and args.janitor_command == "run":
		raise SystemExit(asyncio.run(_run_janitor_run(args)))
	raise SystemExit(1)


__all__ = [
	"JANITOR_RUN_DESCRIPTION",
	"JANITOR_RUN_RUNTIME_ERROR",
	"_add_deploy_args",
	"_add_init_args",
	"_add_janitor_run_args",
	"_add_remove_args",
	"_add_upgrade_args",
	"_print_janitor_result",
	"_run_delete",
	"_run_deploy",
	"_run_init",
	"_run_janitor_run",
	"_run_remove",
	"_run_upgrade",
	"main",
]
