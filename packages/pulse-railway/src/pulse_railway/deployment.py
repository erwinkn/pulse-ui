from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pulse.cli.helpers import load_app_from_target

from pulse_railway.auth import (
	railway_cli_token_env,
	railway_cli_token_env_name_for_auth_mode,
)
from pulse_railway.config import (
	DEFAULT_BACKEND_INSTANCE,
	DockerBuild,
	RailwayProject,
	ServiceInstanceConfig,
)
from pulse_railway.constants import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	DEPLOYMENT_STATE_ACTIVE,
	DEPLOYMENT_STATE_DRAINING,
	PULSE_DEPLOYMENT_ID,
	PULSE_DEPLOYMENT_STATE,
	PULSE_DRAIN_STARTED_AT,
	PULSE_INTERNAL_TOKEN,
	PULSE_RAILWAY_REDIS_URL,
	RAILWAY_API_TOKEN,
	RAILWAY_TOKEN,
)
from pulse_railway.errors import DeploymentError
from pulse_railway.images import (
	build_and_push_image,
	build_router_image,
	image_ref,
)
from pulse_railway.railway import (
	RailwayGraphQLClient,
	normalize_service_prefix,
	service_name_for_deployment,
	validate_deployment_id,
)
from pulse_railway.session import RailwayRedisSessionStore
from pulse_railway.stack import (
	JANITOR_START_COMMAND,
	ROUTER_START_COMMAND,
	ResolvedRedis,
	_deploy_service_and_wait,
	default_env_service_name,
	default_janitor_service_name,
	default_redis_service_name,
	require_ready_stack,
	resolve_or_create_internal_token,
	resolve_or_create_redis,
	resolve_project_internals,
	shared_variable_reference,
	upsert_service_variables,
)


@dataclass(slots=True)
class DeployResult:
	deployment_id: str
	backend_service_id: str
	backend_service_name: str
	backend_image: str | None
	router_service_id: str
	router_service_name: str
	router_image: str | None
	router_domain: str
	server_address: str
	backend_deployment_id: str
	backend_status: str
	router_deployment_id: str | None = None
	router_status: str | None = None
	janitor_service_id: str | None = None
	janitor_service_name: str | None = None
	janitor_image: str | None = None
	janitor_deployment_id: str | None = None
	janitor_status: str | None = None
	source_context: str | None = None
	dockerfile_path: str | None = None


@dataclass(slots=True)
class RedeployResult:
	deployment_id: str
	backend_service_id: str
	backend_service_name: str
	backend_deployment_id: str
	backend_status: str


@dataclass(slots=True)
class DeploymentServiceRecord:
	service_id: str
	service_name: str
	deployment_id: str
	state: str | None = None
	drain_started_at: float | None = None


RESERVED_BACKEND_ENV_VARS: frozenset[str] = frozenset(
	{
		PULSE_DEPLOYMENT_ID,
		PULSE_DEPLOYMENT_STATE,
		PULSE_DRAIN_STARTED_AT,
		PULSE_INTERNAL_TOKEN,
		PULSE_RAILWAY_REDIS_URL,
		"PULSE_APP_FILE",
		"PULSE_SERVER_ADDRESS",
		"PORT",
	}
)
RESERVED_ENV_REFERENCE_VARS: frozenset[str] = RESERVED_BACKEND_ENV_VARS.union(
	{"APP_FILE", "WEB_ROOT", "RAILWAY_DOCKERFILE_PATH"}
)


def _is_user_managed_env_var(name: str) -> bool:
	return not name.startswith("RAILWAY_") and name not in RESERVED_ENV_REFERENCE_VARS


def validate_backend_env_vars(
	env_vars: dict[str, str],
) -> None:
	reserved = sorted(key for key in env_vars if key in RESERVED_BACKEND_ENV_VARS)
	if reserved:
		raise DeploymentError(
			"backend env vars cannot override pulse-railway managed variables: "
			+ ", ".join(reserved)
		)


def check_reserved_source_build_args(
	build_args: dict[str, str],
) -> None:
	reserved = sorted(key for key in build_args if key in RESERVED_BACKEND_ENV_VARS)
	if reserved:
		raise DeploymentError(
			"source build args cannot override pulse-railway managed variables: "
			+ ", ".join(reserved)
		)


def pulse_start_command() -> str:
	return (
		'sh -c \'pulse run "$PULSE_APP_FILE" --prod --address 0.0.0.0 '
		'--port "${PORT:-8000}"\''
	)


def deployment_name_slug(deployment_name: str) -> str:
	base = "".join(
		char if char.isalnum() else "-" for char in deployment_name.strip().lower()
	)
	return "-".join(segment for segment in base.split("-") if segment) or "prod"


def generate_deployment_id(deployment_name: str) -> str:
	base = deployment_name_slug(deployment_name)
	suffix = datetime.now(UTC).strftime("%y%m%d-%H%M%S")
	prefix_limit = 24 - len(suffix) - 1
	base = base[:prefix_limit].rstrip("-") or "prod"
	return validate_deployment_id(f"{base}-{suffix}")


def default_service_prefix(service_name: str) -> str:
	name = service_name.strip().lower()
	if name.endswith("-router"):
		name = name[:-7]
	name = "".join(char if char.isalnum() else "-" for char in name)
	name = "-".join(segment for segment in name.split("-") if segment) or "pulse"
	return normalize_service_prefix(f"{name[:7]}-")


def _app_session_store(app_file: str, context_path: Path) -> object:
	app_path = Path(app_file)
	if not app_path.is_absolute():
		app_path = (context_path / app_path).resolve()
	if not app_path.exists():
		raise DeploymentError(f"app file not found: {app_file}")
	try:
		app_ctx = load_app_from_target(str(app_path))
	except (Exception, SystemExit) as exc:
		raise DeploymentError(
			f"failed to load app session store config from {app_file}"
		) from exc
	return app_ctx.app.session_store


def _uses_railway_session_store_from_app(
	app_file: str,
	context_path: Path,
) -> bool:
	session_store = _app_session_store(app_file, context_path)
	return isinstance(session_store, RailwayRedisSessionStore)


def _resolve_uses_railway_session_store(
	uses_railway_session_store: bool | None,
	*,
	app_file: str,
	context_path: Path,
) -> bool:
	if uses_railway_session_store is not None:
		return uses_railway_session_store
	return _uses_railway_session_store_from_app(app_file, context_path)


def _backend_session_env(
	uses_railway_session_store: bool,
	*,
	redis_url: str | None,
) -> dict[str, str]:
	if not uses_railway_session_store:
		return {}
	if redis_url is None:
		raise DeploymentError("redis_url is required for Railway session store wiring")
	return {PULSE_RAILWAY_REDIS_URL: redis_url}


def _backend_service_variables(
	*,
	deployment_id: str,
	app_file: str,
	server_address: str,
	backend_port: int,
	backend_session_env: dict[str, str],
	project_env_vars: dict[str, str],
) -> dict[str, str]:
	return {
		PULSE_DEPLOYMENT_ID: deployment_id,
		PULSE_INTERNAL_TOKEN: shared_variable_reference(PULSE_INTERNAL_TOKEN),
		"PULSE_APP_FILE": app_file,
		"PULSE_SERVER_ADDRESS": server_address,
		"PORT": str(backend_port),
		**backend_session_env,
		**project_env_vars,
	}


def _backend_build_variables(
	*,
	build_args: dict[str, str],
	app_file: str,
	web_root: str,
	server_address: str,
	dockerfile_path: Path,
	context_path: Path,
) -> dict[str, str]:
	railway_build_vars = dict(build_args)
	railway_build_vars.setdefault("APP_FILE", app_file)
	railway_build_vars.setdefault("WEB_ROOT", web_root)
	railway_build_vars.setdefault("PULSE_SERVER_ADDRESS", server_address)
	try:
		dockerfile_relative = dockerfile_path.relative_to(context_path)
	except ValueError as exc:
		raise DeploymentError(
			"dockerfile must be inside the build context for railway up"
		) from exc
	if dockerfile_relative.as_posix() != "Dockerfile":
		railway_build_vars["RAILWAY_DOCKERFILE_PATH"] = dockerfile_relative.as_posix()
	return railway_build_vars


async def _pulse_env_reference_variables(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	env_service_id: str | None = None,
) -> dict[str, str]:
	env_service_name = default_env_service_name(project.service_name)
	if env_service_id is None:
		env_service = await client.find_service_by_name(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=env_service_name,
		)
		if env_service is None:
			raise DeploymentError(
				f"env service {env_service_name} not found; "
				+ "run `pulse-railway ensure`"
			)
		env_service_id = env_service.id
	variables = await client.get_project_variables(
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=env_service_id,
		unrendered=True,
	)
	return {
		name: "${{" + f"{env_service_name}.{name}" + "}}"
		for name in variables
		if _is_user_managed_env_var(name)
	}


async def _run_command(
	*args: str,
	cwd: Path | None = None,
	env_vars: dict[str, str] | None = None,
) -> None:
	process_env = os.environ.copy()
	if env_vars is not None:
		process_env.pop(RAILWAY_TOKEN, None)
		process_env.pop(RAILWAY_API_TOKEN, None)
		process_env.update(env_vars)
	process = await asyncio.create_subprocess_exec(
		*args,
		cwd=str(cwd) if cwd is not None else None,
		env=process_env,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
	)
	stdout, stderr = await process.communicate()
	if process.returncode != 0:
		raise DeploymentError(
			f"command failed ({' '.join(args)}):\n{stdout.decode()}{stderr.decode()}"
		)


async def _promote_deployment(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	backend_service_id: str,
	deployment_id: str,
) -> None:
	project_variables = await client.get_project_variables(
		project_id=project.project_id,
		environment_id=project.environment_id,
	)
	previous_active_deployment_id = project_variables.get(ACTIVE_DEPLOYMENT_VARIABLE)
	deployment_services = await _list_deployment_service_records(
		client,
		project=project,
	)
	drain_started_at = datetime.now(UTC).timestamp()
	await _set_deployment_service_state(
		client,
		project=project,
		service_id=backend_service_id,
		state=DEPLOYMENT_STATE_ACTIVE,
		drain_started_at=None,
	)
	await asyncio.gather(
		*[
			_set_deployment_service_state(
				client,
				project=project,
				service_id=service.service_id,
				state=DEPLOYMENT_STATE_DRAINING,
				drain_started_at=(
					service.drain_started_at
					if service.state == DEPLOYMENT_STATE_DRAINING
					and service.deployment_id != previous_active_deployment_id
					and service.drain_started_at is not None
					else drain_started_at
				),
			)
			for service in deployment_services
			if service.deployment_id != deployment_id
		]
	)
	await client.upsert_variable(
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=ACTIVE_DEPLOYMENT_VARIABLE,
		value=deployment_id,
		skip_deploys=True,
	)


def railway_up_command(
	*,
	project_id: str,
	environment_id: str,
	service_name: str,
	context_path: Path,
	no_gitignore: bool = False,
) -> list[str]:
	command = [
		"railway",
		"up",
		str(context_path),
		"--project",
		project_id,
		"--environment",
		environment_id,
		"--service",
		service_name,
		"--ci",
	]
	command.append("--path-as-root")
	if no_gitignore:
		command.append("--no-gitignore")
	return command


async def _wait_for_latest_service_deployment(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service_id: str,
	timeout: float = 900.0,
	poll_interval: float = 2.0,
) -> dict[str, Any]:
	deadline = asyncio.get_running_loop().time() + timeout
	last_seen: dict[str, Any] | None = None
	while asyncio.get_running_loop().time() < deadline:
		last_seen = await client.get_service_latest_deployment(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=service_id,
		)
		if last_seen is None:
			await asyncio.sleep(poll_interval)
			continue
		if last_seen["status"] in {"SUCCESS", "FAILED", "CRASHED", "REMOVED"}:
			return last_seen
		await asyncio.sleep(poll_interval)
	raise TimeoutError(
		f"service {service_id} did not produce a terminal deployment in {timeout:.0f}s"
	)


async def _place_backend_in_router_group(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_service_id: str,
	backend_service_id: str,
) -> None:
	config = await client.get_environment_config(
		project_id=project.project_id,
		environment_id=project.environment_id,
	)
	router_config = (config.get("services") or {}).get(router_service_id) or {}
	group_id = router_config.get("groupId")
	if not isinstance(group_id, str) or not group_id:
		return
	await client.set_service_group_id(
		environment_id=project.environment_id,
		service_id=backend_service_id,
		group_id=group_id,
	)


def _parse_optional_float(value: str | None) -> float | None:
	if value is None or not value:
		return None
	return float(value)


async def _list_deployment_service_records(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> list[DeploymentServiceRecord]:
	services = await client.list_services(
		project_id=project.project_id,
		environment_id=project.environment_id,
	)
	variable_sets = await asyncio.gather(
		*[
			client.get_service_variables_for_deployment(
				project_id=project.project_id,
				environment_id=project.environment_id,
				service_id=service.id,
			)
			for service in services
		]
	)
	deployments: list[DeploymentServiceRecord] = []
	for service, variables in zip(services, variable_sets, strict=True):
		deployment_id = variables.get(PULSE_DEPLOYMENT_ID)
		if deployment_id:
			deployments.append(
				DeploymentServiceRecord(
					service_id=service.id,
					service_name=service.name,
					deployment_id=deployment_id,
					state=variables.get(PULSE_DEPLOYMENT_STATE),
					drain_started_at=_parse_optional_float(
						variables.get(PULSE_DRAIN_STARTED_AT)
					),
				)
			)
	return deployments


async def _set_deployment_service_state(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service_id: str,
	state: str,
	drain_started_at: float | None,
) -> None:
	await client.upsert_variable(
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=service_id,
		name=PULSE_DEPLOYMENT_STATE,
		value=state,
		skip_deploys=True,
	)
	await client.upsert_variable(
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=service_id,
		name=PULSE_DRAIN_STARTED_AT,
		value="" if drain_started_at is None else str(drain_started_at),
		skip_deploys=True,
	)


list_deployment_service_records = _list_deployment_service_records
set_deployment_service_state = _set_deployment_service_state


async def _list_deployment_services(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> list[tuple[str, str]]:
	services = await _list_deployment_service_records(client, project=project)
	return [(service.deployment_id, service.service_name) for service in services]


async def resolve_deployment_id_by_name(
	*,
	project: RailwayProject,
	deployment_name: str,
) -> str:
	target = deployment_name.strip().lower()
	if not target:
		raise DeploymentError("deployment name is required")
	async with RailwayGraphQLClient(token=project.token) as client:
		deployments = await _list_deployment_services(client, project=project)
	exact_matches = [
		deployment_id
		for deployment_id, _service_name in deployments
		if deployment_id == target
	]
	if len(exact_matches) == 1:
		return exact_matches[0]
	prefix = f"{deployment_name_slug(target)}-"
	prefix_matches = [
		deployment_id
		for deployment_id, _service_name in deployments
		if deployment_id.startswith(prefix)
	]
	if len(prefix_matches) == 1:
		return prefix_matches[0]
	if not prefix_matches:
		raise DeploymentError(f"deployment '{deployment_name}' not found")
	matches = ", ".join(sorted(prefix_matches))
	raise DeploymentError(
		f"deployment name '{deployment_name}' is ambiguous; matches: {matches}"
	)


async def redeploy_deployment(
	*,
	project: RailwayProject,
	deployment_id: str | None = None,
) -> RedeployResult:
	async with RailwayGraphQLClient(token=project.token) as client:
		resolved_deployment_id = deployment_id
		if resolved_deployment_id is None:
			variables = await client.get_project_variables(
				project_id=project.project_id,
				environment_id=project.environment_id,
			)
			resolved_deployment_id = variables.get(ACTIVE_DEPLOYMENT_VARIABLE)
		if resolved_deployment_id is None:
			raise DeploymentError("no active deployment found")
		resolved_deployment_id = validate_deployment_id(resolved_deployment_id)
		backend_service_name = service_name_for_deployment(
			project.service_prefix,
			resolved_deployment_id,
		)
		backend_service = await client.find_service_by_name(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=backend_service_name,
		)
		if backend_service is None:
			raise DeploymentError(f"service {backend_service_name} not found")
		backend_deployment_id, backend_status = await _deploy_service_and_wait(
			client,
			service_id=backend_service.id,
			environment_id=project.environment_id,
			error_message="backend redeployment failed",
		)
		return RedeployResult(
			deployment_id=resolved_deployment_id,
			backend_service_id=backend_service.id,
			backend_service_name=backend_service_name,
			backend_deployment_id=backend_deployment_id,
			backend_status=backend_status,
		)


async def deploy(
	*,
	project: RailwayProject,
	docker: DockerBuild,
	deployment_name: str = "prod",
	deployment_id: str | None = None,
	app_file: str = "main.py",
	web_root: str = "web",
	uses_railway_session_store: bool | None = None,
	backend_instance: ServiceInstanceConfig = DEFAULT_BACKEND_INSTANCE,
	cli_token_env_name: str | None = None,
	no_gitignore: bool = False,
) -> DeployResult:
	validate_backend_env_vars(project.env_vars)
	if docker.image_repository is None:
		return await _deploy_source(
			project=project,
			docker=docker,
			deployment_name=deployment_name,
			deployment_id=deployment_id,
			app_file=app_file,
			web_root=web_root,
			uses_railway_session_store=uses_railway_session_store,
			backend_instance=backend_instance,
			cli_token_env_name=cli_token_env_name,
			no_gitignore=no_gitignore,
		)
	if no_gitignore:
		raise DeploymentError("--no-gitignore cannot be used with image deployments")
	docker = replace(docker, build_args=dict(docker.build_args))
	build_args = dict(docker.build_args)
	resolved_uses_railway_session_store = _resolve_uses_railway_session_store(
		uses_railway_session_store,
		app_file=app_file,
		context_path=docker.context_path,
	)
	deployment_id = (
		validate_deployment_id(deployment_id)
		if deployment_id is not None
		else generate_deployment_id(deployment_name)
	)
	backend_service_name = service_name_for_deployment(
		project.service_prefix,
		deployment_id,
	)
	backend_image = image_ref(
		image_repository=docker.image_repository,
		prefix=deployment_id,
	)

	async with RailwayGraphQLClient(token=project.token) as client:
		existing_backend = await client.find_service_by_name(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=backend_service_name,
		)
		if existing_backend is not None:
			raise DeploymentError(
				f"service already exists for deployment {deployment_id}"
			)
		stack_state = await require_ready_stack(project=project)
		server_address = project.server_address or stack_state.server_address
		reference_env_vars = await _pulse_env_reference_variables(
			client,
			project=project,
			env_service_id=(
				stack_state.env.service_id if stack_state.env is not None else None
			),
		)
		build_args.setdefault("APP_FILE", app_file)
		build_args.setdefault("WEB_ROOT", web_root)
		build_args.setdefault("PULSE_SERVER_ADDRESS", server_address)
		backend_session_env = _backend_session_env(
			resolved_uses_railway_session_store,
			redis_url=stack_state.redis_url,
		)
		backend_image = await build_and_push_image(
			docker=replace(docker, build_args=build_args),
			image_ref=backend_image,
		)

		backend_service_id = await client.create_service(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=backend_service_name,
			image=backend_image,
		)
		await _place_backend_in_router_group(
			client,
			project=project,
			router_service_id=stack_state.router.service_id,
			backend_service_id=backend_service_id,
		)
		await upsert_service_variables(
			client,
			project=project,
			service_id=backend_service_id,
			variables=_backend_service_variables(
				deployment_id=deployment_id,
				app_file=app_file,
				server_address=server_address,
				backend_port=project.backend_port,
				backend_session_env=backend_session_env,
				project_env_vars={**reference_env_vars, **project.env_vars},
			),
		)
		await client.update_service_instance(
			service_id=backend_service_id,
			environment_id=project.environment_id,
			source_image=backend_image,
			num_replicas=project.backend_replicas,
			healthcheck_path=backend_instance.healthcheck_path,
			healthcheck_timeout=backend_instance.healthcheck_timeout,
			overlap_seconds=backend_instance.overlap_seconds,
			start_command=pulse_start_command(),
		)
		backend_deployment_id = await client.deploy_service(
			service_id=backend_service_id,
			environment_id=project.environment_id,
		)
		backend_deployment = await client.wait_for_deployment(
			deployment_id=backend_deployment_id
		)
		if backend_deployment["status"] != "SUCCESS":
			raise DeploymentError("backend deployment failed")
		await _promote_deployment(
			client,
			project=project,
			backend_service_id=backend_service_id,
			deployment_id=deployment_id,
		)
		return DeployResult(
			deployment_id=deployment_id,
			backend_service_id=backend_service_id,
			backend_service_name=backend_service_name,
			backend_image=backend_image,
			router_service_id=stack_state.router.service_id,
			router_service_name=stack_state.router.service_name,
			router_image=stack_state.router.image,
			router_domain=stack_state.router.domain or "",
			server_address=server_address,
			backend_deployment_id=backend_deployment_id,
			backend_status=backend_deployment["status"],
			janitor_service_id=stack_state.janitor.service_id,
			janitor_service_name=stack_state.janitor.service_name,
			janitor_image=stack_state.janitor.image,
		)


async def _deploy_source(
	*,
	project: RailwayProject,
	docker: DockerBuild,
	deployment_name: str = "prod",
	deployment_id: str | None = None,
	app_file: str = "main.py",
	web_root: str = "web",
	uses_railway_session_store: bool | None = None,
	backend_instance: ServiceInstanceConfig = DEFAULT_BACKEND_INSTANCE,
	cli_token_env_name: str | None = None,
	no_gitignore: bool = False,
) -> DeployResult:
	validate_backend_env_vars(project.env_vars)
	check_reserved_source_build_args(docker.build_args)
	resolved_uses_railway_session_store = _resolve_uses_railway_session_store(
		uses_railway_session_store,
		app_file=app_file,
		context_path=docker.context_path,
	)
	deployment_id = (
		validate_deployment_id(deployment_id)
		if deployment_id is not None
		else generate_deployment_id(deployment_name)
	)
	backend_service_name = service_name_for_deployment(
		project.service_prefix,
		deployment_id,
	)
	backend_service_id: str | None = None
	resolved_cli_token_env_name = cli_token_env_name
	build_started = False
	promoted = False

	try:
		async with RailwayGraphQLClient(token=project.token) as client:
			existing_backend = await client.find_service_by_name(
				project_id=project.project_id,
				environment_id=project.environment_id,
				name=backend_service_name,
			)
			if existing_backend is not None:
				raise DeploymentError(
					f"service already exists for deployment {deployment_id}"
				)
			stack_state = await require_ready_stack(project=project)
			server_address = project.server_address or stack_state.server_address
			backend_session_env = _backend_session_env(
				resolved_uses_railway_session_store,
				redis_url=stack_state.redis_url,
			)
			reference_env_vars = await _pulse_env_reference_variables(
				client,
				project=project,
				env_service_id=(
					stack_state.env.service_id if stack_state.env is not None else None
				),
			)
			runtime_vars = _backend_service_variables(
				deployment_id=deployment_id,
				app_file=app_file,
				server_address=server_address,
				backend_port=project.backend_port,
				backend_session_env=backend_session_env,
				project_env_vars={**reference_env_vars, **project.env_vars},
			)
			build_vars = _backend_build_variables(
				build_args=dict(docker.build_args),
				app_file=app_file,
				web_root=web_root,
				server_address=server_address,
				dockerfile_path=docker.dockerfile_path,
				context_path=docker.context_path,
			)
			backend_service_id = await client.create_service(
				project_id=project.project_id,
				environment_id=project.environment_id,
				name=backend_service_name,
			)
			await _place_backend_in_router_group(
				client,
				project=project,
				router_service_id=stack_state.router.service_id,
				backend_service_id=backend_service_id,
			)
			await upsert_service_variables(
				client,
				project=project,
				service_id=backend_service_id,
				variables={**runtime_vars, **build_vars},
			)
			await client.update_service_instance(
				service_id=backend_service_id,
				environment_id=project.environment_id,
				num_replicas=project.backend_replicas,
				healthcheck_path=backend_instance.healthcheck_path,
				healthcheck_timeout=backend_instance.healthcheck_timeout,
				overlap_seconds=backend_instance.overlap_seconds,
				start_command=pulse_start_command(),
			)
			if resolved_cli_token_env_name is None:
				resolved_cli_token_env_name = railway_cli_token_env_name_for_auth_mode(
					await client.resolve_auth_mode()
				)

		up_command = railway_up_command(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_name=backend_service_name,
			context_path=docker.context_path,
			no_gitignore=no_gitignore,
		)
		await _run_command(
			*up_command,
			cwd=docker.context_path,
			env_vars=railway_cli_token_env(
				project.token,
				env_name=resolved_cli_token_env_name,
			),
		)
		build_started = True

		async with RailwayGraphQLClient(token=project.token) as client:
			build_deployment = await _wait_for_latest_service_deployment(
				client,
				project=project,
				service_id=backend_service_id,
			)
			if build_deployment["status"] != "SUCCESS":
				raise DeploymentError(
					"backend source build failed after railway up: "
					+ build_deployment["status"].lower()
				)
			await _promote_deployment(
				client,
				project=project,
				backend_service_id=backend_service_id,
				deployment_id=deployment_id,
			)
			promoted = True
			return DeployResult(
				deployment_id=deployment_id,
				backend_service_id=backend_service_id,
				backend_service_name=backend_service_name,
				backend_image=None,
				router_service_id=stack_state.router.service_id,
				router_service_name=stack_state.router.service_name,
				router_image=stack_state.router.image,
				router_domain=stack_state.router.domain or "",
				server_address=server_address,
				backend_status=build_deployment["status"],
				source_context=str(docker.context_path),
				dockerfile_path=str(docker.dockerfile_path),
				backend_deployment_id=build_deployment["id"],
				janitor_service_id=stack_state.janitor.service_id,
				janitor_service_name=stack_state.janitor.service_name,
				janitor_image=stack_state.janitor.image,
			)
	except Exception:
		if backend_service_id is not None and not build_started and not promoted:
			try:
				async with RailwayGraphQLClient(token=project.token) as client:
					await client.delete_service(
						service_id=backend_service_id,
						environment_id=project.environment_id,
					)
			except Exception as cleanup_exc:
				raise DeploymentError(
					f"source deployment failed for {backend_service_name}; "
					+ f"cleanup also failed: {cleanup_exc}"
				) from cleanup_exc
		raise


async def delete_deployment(
	*,
	project: RailwayProject,
	deployment_id: str,
	clear_active: bool = True,
) -> None:
	service_name = service_name_for_deployment(
		project.service_prefix,
		deployment_id,
	)
	async with RailwayGraphQLClient(token=project.token) as client:
		service = await client.find_service_by_name(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=service_name,
		)
		if service is None:
			raise DeploymentError(f"service {service_name} not found")
		await client.delete_service(
			service_id=service.id,
			environment_id=project.environment_id,
		)
		if not clear_active:
			return
		variables = await client.get_project_variables(
			project_id=project.project_id,
			environment_id=project.environment_id,
		)
		if variables.get(ACTIVE_DEPLOYMENT_VARIABLE) == deployment_id:
			await client.delete_variable(
				project_id=project.project_id,
				environment_id=project.environment_id,
				name=ACTIVE_DEPLOYMENT_VARIABLE,
			)


__all__ = [
	"DeployResult",
	"DeploymentError",
	"JANITOR_START_COMMAND",
	"RedeployResult",
	"ROUTER_START_COMMAND",
	"build_and_push_image",
	"build_router_image",
	"deployment_name_slug",
	"default_janitor_service_name",
	"default_redis_service_name",
	"default_service_prefix",
	"delete_deployment",
	"deploy",
	"DeploymentServiceRecord",
	"generate_deployment_id",
	"list_deployment_service_records",
	"railway_up_command",
	"redeploy_deployment",
	"ResolvedRedis",
	"resolve_deployment_id_by_name",
	"resolve_or_create_redis",
	"resolve_or_create_internal_token",
	"resolve_project_internals",
	"set_deployment_service_state",
]
