from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pulse_railway.auth import (
	railway_access_token,
	resolve_railway_access_token,
)
from pulse_railway.commands.common import (
	build_target_project,
	env,
	load_deploy_target,
	parse_kv_items,
	resolve_path,
)
from pulse_railway.config import DockerBuild, RailwayProject
from pulse_railway.deployment import (
	check_reserved_source_build_args,
	validate_backend_env_vars,
)

DeployMode = Literal["image", "source"]


@dataclass(slots=True)
class ResolvedDeployCommand:
	mode: DeployMode
	project: RailwayProject
	docker: DockerBuild
	deployment_name: str
	deployment_id: str | None
	app_file: str
	web_root: str
	cli_token_env_name: str | None
	no_gitignore: bool


def add_shared_deploy_args(parser: argparse.ArgumentParser) -> None:
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
		default=railway_access_token(),
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
		help="Build/upload context",
	)
	parser.add_argument(
		"--image-repository",
		default=env("PULSE_RAILWAY_IMAGE_REPOSITORY"),
		help="Registry repository for pushed images. Enables image deploys when set.",
	)
	parser.add_argument(
		"--build-arg",
		action="append",
		default=[],
		help="Extra docker build arg KEY=VALUE (repeatable)",
	)
	parser.add_argument(
		"--no-gitignore",
		action="store_true",
		help="Upload gitignored files too. Only used for source deploys.",
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


def resolve_deploy_command(args: argparse.Namespace) -> ResolvedDeployCommand:
	invocation_cwd = Path.cwd()
	dockerfile_path = resolve_path(invocation_cwd, args.dockerfile)
	context_path = resolve_path(invocation_cwd, args.context)
	if not dockerfile_path.exists():
		raise ValueError(f"Dockerfile not found: {dockerfile_path}")
	if not context_path.exists():
		raise ValueError(f"Context path not found: {context_path}")
	if Path(args.app_file).is_absolute():
		raise ValueError("app-file must be relative to the deploy context")
	if Path(args.web_root).is_absolute():
		raise ValueError("web-root must be relative to the deploy context")
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
	resolved_token = resolve_railway_access_token(args.token)
	token = resolved_token.value
	cli_token_env_name = resolved_token.env_name
	deployment_name = (
		args.deployment_name
		or env("PULSE_RAILWAY_DEPLOYMENT_NAME")
		or deploy_target.deployment_name
		or "prod"
	)
	if not project_id or not environment_id or not token:
		raise ValueError("project id, environment id, and token are required")
	env_vars = parse_kv_items(args.env, "--env")
	validate_backend_env_vars(env_vars)
	build_args = parse_kv_items(args.build_arg, "--build-arg")
	image_repository = args.image_repository or deploy_target.image_repository
	mode: DeployMode = "image" if image_repository else "source"
	if mode == "image" and args.no_gitignore:
		raise ValueError("--no-gitignore cannot be used with --image-repository")
	if mode == "source":
		check_reserved_source_build_args(build_args)
	project = build_target_project(
		args,
		deploy_target=deploy_target,
		project_id=project_id,
		environment_id=environment_id,
		token=token,
		env_vars=env_vars,
		backend_port=args.backend_port,
		backend_replicas=args.backend_replicas,
		server_address=args.server_address,
	)
	docker = DockerBuild(
		dockerfile_path=dockerfile_path,
		context_path=context_path,
		build_args=build_args,
		image_repository=image_repository if mode == "image" else None,
	)
	return ResolvedDeployCommand(
		mode=mode,
		project=project,
		docker=docker,
		deployment_name=deployment_name,
		deployment_id=args.deployment_id,
		app_file=str(app_path.relative_to(context_path)),
		web_root=args.web_root,
		cli_token_env_name=cli_token_env_name,
		no_gitignore=args.no_gitignore,
	)
