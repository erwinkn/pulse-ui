"""Command-line interface for pulse-railway."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from pulse.cli.helpers import load_app_from_target

from pulse_railway.config import DockerBuild, RailwayProject
from pulse_railway.deployment import (
	default_janitor_service_name,
	default_redis_service_name,
	default_service_prefix,
	delete_deployment,
	deploy,
	resolve_deployment_id_by_name,
)
from pulse_railway.janitor import JanitorResult, run_janitor
from pulse_railway.railway import normalize_service_prefix, validate_deployment_id
from pulse_railway.target import (
	RailwayDeployTarget,
	RailwayDeployTargetError,
	railway_deploy_target_from_app,
)

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


def _env(name: str) -> str | None:
	return os.environ.get(name)


def _parse_kv_items(items: list[str] | None, label: str) -> dict[str, str]:
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


def _resolve_path(base: Path, raw: str) -> Path:
	path = Path(raw).expanduser()
	if path.is_absolute():
		return path
	return (base / path).resolve()


def _running_on_railway() -> bool:
	return any(_env(name) for name in RAILWAY_RUNTIME_ENV_VARS)


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
		service_name or args.service or _env("PULSE_RAILWAY_SERVICE") or "pulse-router"
	)
	service_prefix = (
		service_prefix
		or args.service_prefix
		or _env("PULSE_RAILWAY_SERVICE_PREFIX")
		or default_service_prefix(service_name)
	)
	return RailwayProject(
		project_id=project_id or args.project_id or _env("RAILWAY_PROJECT_ID") or "",
		environment_id=environment_id
		or args.environment_id
		or _env("RAILWAY_ENVIRONMENT_ID")
		or "",
		token=token or args.token or _env("RAILWAY_TOKEN") or "",
		service_name=service_name,
		service_prefix=normalize_service_prefix(service_prefix),
		redis_url=args.redis_url,
		redis_service_name=redis_service_name
		or args.redis_service
		or _env("PULSE_RAILWAY_REDIS_SERVICE")
		or default_redis_service_name(service_name),
		redis_prefix=args.redis_prefix,
		**overrides,
	)


def _add_deploy_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument(
		"--service",
		default=None,
		help="Stable public Railway router service name",
	)
	parser.add_argument(
		"--deployment-name",
		default=_env("PULSE_RAILWAY_DEPLOYMENT_NAME") or "prod",
		help="Deployment prefix used when generating deployment ids",
	)
	parser.add_argument(
		"--deployment-id",
		default=_env("PULSE_DEPLOYMENT_ID"),
		help="Explicit deployment id override",
	)
	parser.add_argument(
		"--project-id",
		default=None,
		help="Railway project id",
	)
	parser.add_argument(
		"--environment-id",
		default=None,
		help="Railway environment id",
	)
	parser.add_argument(
		"--token",
		default=None,
		help="Railway project access token",
	)
	parser.add_argument(
		"--service-prefix",
		default=None,
		help="Backend Railway service prefix. Defaults to a short prefix derived from --service.",
	)
	parser.add_argument(
		"--server-address",
		default=_env("PULSE_SERVER_ADDRESS"),
		help="Public server address. Defaults to the router service Railway domain.",
	)
	parser.add_argument(
		"--redis-url",
		default=_env("PULSE_RAILWAY_REDIS_URL"),
		help="Redis URL used for draining state and janitor cleanup. If omitted, pulse-railway creates or reuses a Redis service in the Railway project.",
	)
	parser.add_argument(
		"--redis-service",
		default=None,
		help="Stable Railway Redis service name. Defaults to <service>-redis.",
	)
	parser.add_argument(
		"--redis-prefix",
		default=_env("PULSE_RAILWAY_REDIS_PREFIX") or "pulse:railway",
		help="Redis key prefix for pulse-railway control-plane state.",
	)
	parser.add_argument(
		"--janitor-service",
		default=None,
		help="Stable Railway janitor service name. Defaults to <service>-janitor.",
	)
	parser.add_argument(
		"--janitor-image",
		default=_env("PULSE_RAILWAY_JANITOR_IMAGE"),
		help="Prebuilt janitor image. Defaults to the router image.",
	)
	parser.add_argument(
		"--janitor-cron-schedule",
		default=_env("PULSE_RAILWAY_JANITOR_CRON_SCHEDULE") or "*/5 * * * *",
		help="Railway cron schedule for the janitor service. Defaults to every 5 minutes.",
	)
	parser.add_argument(
		"--drain-grace-seconds",
		type=int,
		default=int(_env("PULSE_RAILWAY_JANITOR_DRAIN_GRACE_SECONDS") or "60"),
		help="Minimum idle and drain duration before janitor cleanup.",
	)
	parser.add_argument(
		"--max-drain-age-seconds",
		type=int,
		default=int(_env("PULSE_RAILWAY_JANITOR_MAX_DRAIN_AGE_SECONDS") or "86400"),
		help="Maximum time to keep a draining deployment before forced cleanup.",
	)
	parser.add_argument(
		"--app-file",
		default=_env("PULSE_RAILWAY_APP_FILE") or "main.py",
		help="App entry file for Docker build args",
	)
	parser.add_argument(
		"--web-root",
		default=_env("PULSE_RAILWAY_WEB_ROOT") or "web",
		help="Web root for Docker build args",
	)
	parser.add_argument(
		"--dockerfile",
		default=_env("PULSE_RAILWAY_DOCKERFILE") or "Dockerfile",
		help="Path to Dockerfile",
	)
	parser.add_argument(
		"--context",
		default=_env("PULSE_RAILWAY_CONTEXT") or ".",
		help="Docker build context",
	)
	parser.add_argument(
		"--image-repository",
		default=_env("PULSE_RAILWAY_IMAGE_REPOSITORY"),
		help="Registry repository for pushed images. Defaults to ttl.sh.",
	)
	parser.add_argument(
		"--router-image",
		default=_env("PULSE_RAILWAY_ROUTER_IMAGE"),
		help="Prebuilt router image. If omitted, pulse-railway builds one.",
	)
	parser.add_argument(
		"--build-arg",
		action="append",
		default=[],
		help="Extra docker build arg KEY=VALUE (repeatable)",
	)
	parser.add_argument(
		"--env",
		action="append",
		default=[],
		help="Extra backend service env var KEY=VALUE (repeatable)",
	)
	parser.add_argument(
		"--backend-port",
		type=int,
		default=int(_env("PULSE_RAILWAY_BACKEND_PORT") or "8000"),
		help="Backend container port",
	)
	parser.add_argument(
		"--backend-replicas",
		type=int,
		default=int(_env("PULSE_RAILWAY_BACKEND_REPLICAS") or "1"),
		help="Backend Railway replicas. Use 1 for Pulse session affinity.",
	)
	parser.add_argument(
		"--router-replicas",
		type=int,
		default=int(_env("PULSE_RAILWAY_ROUTER_REPLICAS") or "1"),
		help="Router Railway replicas",
	)


def _add_delete_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument("--service", required=True, help="Stable router service name")
	parser.add_argument(
		"--deployment-id", required=True, help="Deployment id to delete"
	)
	parser.add_argument(
		"--project-id",
		default=_env("RAILWAY_PROJECT_ID"),
	)
	parser.add_argument(
		"--environment-id",
		default=_env("RAILWAY_ENVIRONMENT_ID"),
	)
	parser.add_argument(
		"--token",
		default=_env("RAILWAY_TOKEN"),
	)
	parser.add_argument(
		"--service-prefix",
		default=_env("PULSE_RAILWAY_SERVICE_PREFIX"),
	)
	parser.add_argument(
		"--keep-active-variable",
		action="store_true",
		help="Do not delete PULSE_ACTIVE_DEPLOYMENT when it points at the removed deployment",
	)
	parser.add_argument("--redis-url", default=_env("PULSE_RAILWAY_REDIS_URL"))
	parser.add_argument(
		"--redis-service",
		default=_env("PULSE_RAILWAY_REDIS_SERVICE"),
	)
	parser.add_argument(
		"--redis-prefix",
		default=_env("PULSE_RAILWAY_REDIS_PREFIX") or "pulse:railway",
	)


def _add_remove_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument("--service", required=True, help="Stable router service name")
	parser.add_argument(
		"--deployment-name",
		required=True,
		help="Deployment name or exact deployment id to remove",
	)
	parser.add_argument(
		"--project-id",
		default=_env("RAILWAY_PROJECT_ID"),
	)
	parser.add_argument(
		"--environment-id",
		default=_env("RAILWAY_ENVIRONMENT_ID"),
	)
	parser.add_argument(
		"--token",
		default=_env("RAILWAY_TOKEN"),
	)
	parser.add_argument(
		"--service-prefix",
		default=_env("PULSE_RAILWAY_SERVICE_PREFIX"),
	)
	parser.add_argument(
		"--keep-active-variable",
		action="store_true",
		help="Do not delete PULSE_ACTIVE_DEPLOYMENT when it points at the removed deployment",
	)
	parser.add_argument("--redis-url", default=_env("PULSE_RAILWAY_REDIS_URL"))
	parser.add_argument(
		"--redis-service",
		default=_env("PULSE_RAILWAY_REDIS_SERVICE"),
	)
	parser.add_argument(
		"--redis-prefix",
		default=_env("PULSE_RAILWAY_REDIS_PREFIX") or "pulse:railway",
	)


def _add_janitor_run_args(parser: argparse.ArgumentParser) -> None:
	parser.description = JANITOR_RUN_DESCRIPTION
	parser.add_argument(
		"--service",
		default=_env("PULSE_RAILWAY_SERVICE") or "pulse-router",
		help="Stable public Railway router service name for the deployed janitor.",
	)
	parser.add_argument(
		"--project-id",
		default=_env("RAILWAY_PROJECT_ID"),
	)
	parser.add_argument(
		"--environment-id",
		default=_env("RAILWAY_ENVIRONMENT_ID"),
	)
	parser.add_argument(
		"--token",
		default=_env("RAILWAY_TOKEN"),
	)
	parser.add_argument(
		"--service-prefix",
		default=_env("PULSE_RAILWAY_SERVICE_PREFIX"),
	)
	parser.add_argument(
		"--redis-url",
		default=_env("PULSE_RAILWAY_REDIS_URL"),
		help="Redis URL used for draining state and janitor cleanup inside Railway.",
	)
	parser.add_argument(
		"--redis-service",
		default=_env("PULSE_RAILWAY_REDIS_SERVICE"),
		help="Stable Railway Redis service name. Defaults to <service>-redis.",
	)
	parser.add_argument(
		"--redis-prefix",
		default=_env("PULSE_RAILWAY_REDIS_PREFIX") or "pulse:railway",
	)
	parser.add_argument(
		"--drain-grace-seconds",
		type=int,
		default=int(_env("PULSE_RAILWAY_JANITOR_DRAIN_GRACE_SECONDS") or "60"),
	)
	parser.add_argument(
		"--max-drain-age-seconds",
		type=int,
		default=int(_env("PULSE_RAILWAY_JANITOR_MAX_DRAIN_AGE_SECONDS") or "86400"),
	)


async def _run_deploy(args: argparse.Namespace) -> int:
	invocation_cwd = Path.cwd()
	dockerfile_path = _resolve_path(invocation_cwd, args.dockerfile)
	context_path = _resolve_path(invocation_cwd, args.context)
	if not dockerfile_path.exists():
		raise ValueError(f"Dockerfile not found: {dockerfile_path}")
	if not context_path.exists():
		raise ValueError(f"Context path not found: {context_path}")
	if Path(args.app_file).is_absolute():
		raise ValueError("app-file must be relative to the Docker build context")
	if Path(args.web_root).is_absolute():
		raise ValueError("web-root must be relative to the Docker build context")
	app_path = _resolve_path(context_path, args.app_file)
	if not app_path.exists():
		raise ValueError(f"App file not found: {app_path}")
	web_root_path = _resolve_path(context_path, args.web_root)
	if not web_root_path.exists():
		raise ValueError(f"Web root not found: {web_root_path}")
	app_ctx = load_app_from_target(str(app_path))
	deploy_target: RailwayDeployTarget | None = None
	deploy_target_error: RailwayDeployTargetError | None = None
	try:
		deploy_target = railway_deploy_target_from_app(app_ctx.app)
	except RailwayDeployTargetError as exc:
		deploy_target_error = exc

	project_id = (
		args.project_id
		or (deploy_target.project_id if deploy_target is not None else None)
		or _env("RAILWAY_PROJECT_ID")
	)
	environment_id = (
		args.environment_id
		or (deploy_target.environment_id if deploy_target is not None else None)
		or _env("RAILWAY_ENVIRONMENT_ID")
	)
	token = args.token or _env("RAILWAY_TOKEN")
	service_name = (
		args.service
		or (deploy_target.router_service_name if deploy_target is not None else None)
		or _env("PULSE_RAILWAY_SERVICE")
		or "pulse-router"
	)
	service_prefix = (
		args.service_prefix
		or (deploy_target.service_prefix if deploy_target is not None else None)
		or _env("PULSE_RAILWAY_SERVICE_PREFIX")
		or default_service_prefix(service_name)
	)
	redis_service_name = (
		args.redis_service
		or (deploy_target.redis_service_name if deploy_target is not None else None)
		or _env("PULSE_RAILWAY_REDIS_SERVICE")
		or default_redis_service_name(service_name)
	)
	janitor_service_name = (
		args.janitor_service
		or (deploy_target.janitor_service_name if deploy_target is not None else None)
		or _env("PULSE_RAILWAY_JANITOR_SERVICE")
		or default_janitor_service_name(service_name)
	)
	if not project_id or not environment_id or not token:
		if deploy_target_error is not None:
			raise ValueError(str(deploy_target_error)) from deploy_target_error
		raise ValueError("project id, environment id, and token are required")

	project = _railway_project(
		args,
		project_id=project_id,
		environment_id=environment_id,
		token=token,
		service_name=service_name,
		service_prefix=service_prefix,
		redis_service_name=redis_service_name,
		backend_port=args.backend_port,
		backend_replicas=args.backend_replicas,
		router_replicas=args.router_replicas,
		router_image=args.router_image,
		server_address=args.server_address,
		janitor_service_name=janitor_service_name,
		janitor_image=args.janitor_image,
		janitor_cron_schedule=args.janitor_cron_schedule,
		drain_grace_seconds=args.drain_grace_seconds,
		max_drain_age_seconds=args.max_drain_age_seconds,
		env_vars=_parse_kv_items(args.env, "--env"),
	)
	docker = DockerBuild(
		dockerfile_path=dockerfile_path,
		context_path=context_path,
		build_args=_parse_kv_items(args.build_arg, "--build-arg"),
		image_repository=args.image_repository,
	)
	result = await deploy(
		project=project,
		docker=docker,
		deployment_name=args.deployment_name,
		deployment_id=args.deployment_id,
		app_file=args.app_file,
		web_root=args.web_root,
	)
	print(json.dumps(asdict(result), indent=2, sort_keys=True))
	return 0


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

	deploy_parser = subparsers.add_parser("deploy")
	_add_deploy_args(deploy_parser)

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
	if args.command == "deploy":
		raise SystemExit(asyncio.run(_run_deploy(args)))
	if args.command == "delete":
		raise SystemExit(asyncio.run(_run_delete(args)))
	if args.command == "remove":
		raise SystemExit(asyncio.run(_run_remove(args)))
	if args.command == "janitor" and args.janitor_command == "run":
		raise SystemExit(asyncio.run(_run_janitor_run(args)))
	raise SystemExit(1)
