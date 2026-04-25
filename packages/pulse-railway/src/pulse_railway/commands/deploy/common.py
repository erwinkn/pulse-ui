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
	environment_name_from_sources,
	load_deploy_target,
	parse_kv_items,
	project_name_from_sources,
	resolve_path,
	resolve_railway_target_ids,
)
from pulse_railway.config import DockerBuild, RailwayProject
from pulse_railway.constants import DEFAULT_BACKEND_PORT
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
	uses_railway_session_store: bool
	cli_token_env_name: str | None
	no_gitignore: bool


def add_shared_deploy_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument(
		"app_file",
		help="App entry file for Docker build args and RailwayPlugin config",
	)
	parser.add_argument(
		"--deployment-name",
		default=None,
		help="Deployment prefix used when generating deployment ids",
	)
	parser.add_argument(
		"--deployment-id",
		default=None,
		help="Explicit deployment id override",
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
		default=None,
		help="Public server address override. Defaults to App.server_address, then the existing router service address.",
	)
	parser.add_argument(
		"--web-root",
		default=None,
		help="Web root override. Defaults to the app codegen web root.",
	)
	parser.add_argument(
		"--dockerfile",
		default=None,
		help="Dockerfile override. Defaults to RailwayPlugin(dockerfile=...).",
	)
	parser.add_argument(
		"--context",
		default=".",
		help="Build/upload context",
	)
	parser.add_argument(
		"--image-repository",
		default=None,
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
		default=DEFAULT_BACKEND_PORT,
		help="Backend container port",
	)
	parser.add_argument(
		"--backend-replicas",
		type=int,
		default=1,
		help="Backend Railway replicas. Use 1 for Pulse session affinity.",
	)


async def resolve_deploy_command(args: argparse.Namespace) -> ResolvedDeployCommand:
	invocation_cwd = Path.cwd()
	context_path = resolve_path(invocation_cwd, args.context)
	if not context_path.exists():
		raise ValueError(f"Context path not found: {context_path}")
	if Path(args.app_file).is_absolute():
		raise ValueError("app-file must be relative to the deploy context")
	app_path, deploy_target = load_deploy_target(
		app_file=args.app_file,
		base_path=context_path,
	)
	dockerfile = args.dockerfile or deploy_target.dockerfile
	if dockerfile is None:
		raise ValueError(
			"dockerfile is required. Pass --dockerfile or set RailwayPlugin(dockerfile=...)."
		)
	dockerfile_base = invocation_cwd if args.dockerfile else context_path
	dockerfile_path = resolve_path(dockerfile_base, dockerfile)
	if not dockerfile_path.exists():
		raise ValueError(f"Dockerfile not found: {dockerfile_path}")
	if args.web_root is None:
		try:
			web_root = deploy_target.web_root.resolve().relative_to(context_path)
		except ValueError as exc:
			raise ValueError(
				"App web root must be inside the deploy context. "
				+ "Pass --web-root to override it."
			) from exc
	else:
		if Path(args.web_root).is_absolute():
			raise ValueError("web-root must be relative to the deploy context")
		web_root = Path(args.web_root)
	web_root_path = resolve_path(context_path, web_root.as_posix())
	if not web_root_path.exists():
		raise ValueError(f"Web root not found: {web_root_path}")
	resolved_token = resolve_railway_access_token(args.token)
	token = resolved_token.value
	cli_token_env_name = resolved_token.env_name
	deployment_name = args.deployment_name or deploy_target.deployment_name or "prod"
	if not token:
		raise ValueError("token is required")
	project_id, environment_id = await resolve_railway_target_ids(
		project_name=project_name_from_sources(args, deploy_target),
		environment_name=environment_name_from_sources(args, deploy_target),
		token=token,
	)
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
		server_address=args.server_address or deploy_target.server_address,
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
		web_root=web_root.as_posix(),
		uses_railway_session_store=deploy_target.uses_railway_session_store,
		cli_token_env_name=cli_token_env_name,
		no_gitignore=args.no_gitignore,
	)
