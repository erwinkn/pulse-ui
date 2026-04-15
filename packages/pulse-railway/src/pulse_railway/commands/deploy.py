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
	parse_kv_items,
	resolve_path,
)
from pulse_railway.config import DockerBuild
from pulse_railway.deployment import deploy


def _add_deploy_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument(
		"--deployment-name",
		default=None,
		help="Deployment prefix used when generating deployment ids",
	)
	parser.add_argument(
		"--deployment-id",
		default=env("PULSE_DEPLOYMENT_ID"),
		help="Explicit deployment id override",
	)
	parser.add_argument("--project-id", default=None, help="Railway project id")
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
		help="Backend Railway service prefix. Defaults to the RailwayPlugin service prefix.",
	)
	parser.add_argument(
		"--server-address",
		default=env("PULSE_SERVER_ADDRESS"),
		help="Public server address override. Defaults to the existing router service address.",
	)
	parser.add_argument(
		"--app-file",
		default=env("PULSE_RAILWAY_APP_FILE") or "main.py",
		help="App entry file for Docker build args and RailwayPlugin config",
	)
	parser.add_argument(
		"--web-root",
		default=env("PULSE_RAILWAY_WEB_ROOT") or "web",
		help="Web root for Docker build args",
	)
	parser.add_argument(
		"--dockerfile",
		default=env("PULSE_RAILWAY_DOCKERFILE") or "Dockerfile",
		help="Path to Dockerfile",
	)
	parser.add_argument(
		"--context",
		default=env("PULSE_RAILWAY_CONTEXT") or ".",
		help="Docker build context",
	)
	parser.add_argument(
		"--image-repository",
		default=env("PULSE_RAILWAY_IMAGE_REPOSITORY"),
		help="Registry repository for pushed images. Defaults to ttl.sh.",
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
		default=int(env("PULSE_RAILWAY_BACKEND_PORT") or "8000"),
		help="Backend container port",
	)
	parser.add_argument(
		"--backend-replicas",
		type=int,
		default=int(env("PULSE_RAILWAY_BACKEND_REPLICAS") or "1"),
		help="Backend Railway replicas. Use 1 for Pulse session affinity.",
	)


async def _run_deploy(args: argparse.Namespace) -> int:
	invocation_cwd = Path.cwd()
	dockerfile_path = resolve_path(invocation_cwd, args.dockerfile)
	context_path = resolve_path(invocation_cwd, args.context)
	if not dockerfile_path.exists():
		raise ValueError(f"Dockerfile not found: {dockerfile_path}")
	if not context_path.exists():
		raise ValueError(f"Context path not found: {context_path}")
	if Path(args.app_file).is_absolute():
		raise ValueError("app-file must be relative to the Docker build context")
	if Path(args.web_root).is_absolute():
		raise ValueError("web-root must be relative to the Docker build context")
	app_path, deploy_target = load_deploy_target(
		app_file=args.app_file,
		base_path=context_path,
	)
	web_root_path = resolve_path(context_path, args.web_root)
	if not web_root_path.exists():
		raise ValueError(f"Web root not found: {web_root_path}")
	project_id = (
		args.project_id or deploy_target.project_id or env("RAILWAY_PROJECT_ID")
	)
	environment_id = (
		args.environment_id
		or deploy_target.environment_id
		or env("RAILWAY_ENVIRONMENT_ID")
	)
	token = args.token or env("RAILWAY_TOKEN")
	deployment_name = (
		args.deployment_name
		or env("PULSE_RAILWAY_DEPLOYMENT_NAME")
		or deploy_target.deployment_name
		or "prod"
	)
	if not project_id or not environment_id or not token:
		raise ValueError("project id, environment id, and token are required")
	project = build_target_project(
		args,
		deploy_target=deploy_target,
		project_id=project_id,
		environment_id=environment_id,
		token=token,
		env_vars=parse_kv_items(args.env, "--env"),
		backend_port=args.backend_port,
		backend_replicas=args.backend_replicas,
		server_address=args.server_address,
	)
	docker = DockerBuild(
		dockerfile_path=dockerfile_path,
		context_path=context_path,
		build_args=parse_kv_items(args.build_arg, "--build-arg"),
		image_repository=args.image_repository,
	)
	result = await deploy(
		project=project,
		docker=docker,
		deployment_name=deployment_name,
		deployment_id=args.deployment_id,
		app_file=str(app_path.relative_to(context_path)),
		web_root=args.web_root,
	)
	print(json.dumps(asdict(result), indent=2, sort_keys=True))
	return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
	deploy_parser = subparsers.add_parser(
		"deploy",
		help="Deploy a new application version onto an existing pulse-railway stack.",
	)
	_add_deploy_args(deploy_parser)


def main(args: argparse.Namespace) -> int:
	return asyncio.run(_run_deploy(args))
