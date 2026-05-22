from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
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
	default_janitor_service_name,
	default_redis_service_name,
)
from pulse_railway.constants import (
	DEPLOYMENT_META_PATH,
	DEPLOYMENT_STATE_DRAINING,
	RAILWAY_API_TOKEN,
	RAILWAY_TOKEN,
)
from pulse_railway.env import (
	backend_build_env,
	backend_env,
	backend_session_env,
	check_reserved_source_build_args,
	validate_backend_env_vars,
)
from pulse_railway.errors import DeploymentError
from pulse_railway.images import (
	build_and_push_image,
	image_ref,
)
from pulse_railway.railway.client import (
	RailwayGraphQLClient,
	normalize_service_prefix,
	service_name_for_deployment,
	validate_deployment_id,
)
from pulse_railway.railway.ops import (
	DeploymentServiceRecord,
	configure_service,
	configure_service_and_deploy,
	create_service_in_router_group,
	deploy_service_and_wait,
	list_deployment_service_records,
	pulse_env_reference_variables,
	raise_if_service_exists,
	require_service_by_name,
	wait_for_latest_service_deployment,
)
from pulse_railway.session import RailwayRedisSessionStore
from pulse_railway.stack import (
	JANITOR_START_COMMAND,
	ROUTER_START_COMMAND,
	inspect_stack,
)

ROUTED_DEPLOYMENT_TIMEOUT_SECONDS = 180.0
ROUTED_DEPLOYMENT_POLL_SECONDS = 2.0


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


def validate_deployment_service_records(
	services: list[DeploymentServiceRecord],
	active_deployment_id: str | None,
) -> tuple[DeploymentServiceRecord | None, list[DeploymentServiceRecord]]:
	seen: dict[str, DeploymentServiceRecord] = {}
	for service in services:
		existing = seen.get(service.deployment_id)
		if existing is not None:
			raise DeploymentError(
				f"duplicate PULSE_DEPLOYMENT_ID {service.deployment_id!r} "
				+ f"on services {existing.service_name!r} and {service.service_name!r}"
			)
		seen[service.deployment_id] = service

	if not services:
		return None, []
	if active_deployment_id is None:
		raise DeploymentError(
			"active deployment id is missing while backend services exist"
		)
	active = seen.get(active_deployment_id)
	if active is None:
		raise DeploymentError(
			f"active deployment id {active_deployment_id!r} "
			+ "does not match any backend service"
		)
	return active, [
		service for service in services if service.deployment_id != active_deployment_id
	]


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


async def _run_command_output(
	*args: str,
	cwd: Path | None = None,
	env_vars: dict[str, str] | None = None,
) -> str:
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
	return stdout.decode()


async def _resolve_cli_token_env_name(
	project: RailwayProject,
	cli_token_env_name: str | None,
) -> str:
	if cli_token_env_name is not None:
		return cli_token_env_name
	async with RailwayGraphQLClient(token=project.token) as client:
		return railway_cli_token_env_name_for_auth_mode(
			await client.resolve_auth_mode()
		)


async def _run_router_control_command(
	*,
	project: RailwayProject,
	router_service_name: str,
	cli_token_env_name: str | None,
	control_args: list[str],
) -> dict[str, object]:
	resolved_cli_token_env_name = await _resolve_cli_token_env_name(
		project,
		cli_token_env_name,
	)
	stdout = await _run_command_output(
		"railway",
		"ssh",
		"--project",
		project.project_id,
		"--environment",
		project.environment_id,
		"--service",
		router_service_name,
		"--",
		shlex.join(["pulse-railway", "control", *control_args]),
		env_vars=railway_cli_token_env(
			project.token,
			env_name=resolved_cli_token_env_name,
		),
	)
	try:
		stdout_lines = [line for line in stdout.splitlines() if line.strip()]
		payload = json.loads(stdout_lines[-1] if stdout_lines else "")
	except ValueError as exc:
		raise DeploymentError(
			f"router control command returned invalid JSON: {stdout}"
		) from exc
	if not isinstance(payload, dict):
		raise DeploymentError("router control command returned invalid JSON")
	return payload


async def _promote_deployment(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_service_name: str,
	cli_token_env_name: str | None,
	backend_service_name: str,
	deployment_id: str,
) -> None:
	deployment_services = await list_deployment_service_records(
		client,
		project=project,
	)
	drain_started_at = datetime.now(UTC).timestamp()
	await _run_router_control_command(
		project=project,
		router_service_name=router_service_name,
		cli_token_env_name=cli_token_env_name,
		control_args=[
			"promote",
			"--active-deployment-id",
			deployment_id,
			"--active-service-name",
			backend_service_name,
			"--draining-json",
			json.dumps(
				[
					{
						"deployment_id": service.deployment_id,
						"service_name": service.service_name,
						"drain_started_at": (
							service.drain_started_at
							if service.state == DEPLOYMENT_STATE_DRAINING
							and service.drain_started_at is not None
							else drain_started_at
						),
					}
					for service in deployment_services
					if service.deployment_id != deployment_id
				],
				separators=(",", ":"),
			),
		],
	)


async def _register_deployment(
	*,
	project: RailwayProject,
	router_service_name: str,
	cli_token_env_name: str | None,
	backend_service_name: str,
	deployment_id: str,
) -> None:
	await _run_router_control_command(
		project=project,
		router_service_name=router_service_name,
		cli_token_env_name=cli_token_env_name,
		control_args=[
			"register",
			"--deployment-id",
			deployment_id,
			"--service-name",
			backend_service_name,
		],
	)


async def _fetch_deployment_meta(
	session: aiohttp.ClientSession,
	*,
	server_address: str,
	deployment_id: str | None,
) -> tuple[int | None, dict[str, object] | None]:
	url = f"{server_address.rstrip('/')}{DEPLOYMENT_META_PATH}"
	if deployment_id is not None:
		url += "?" + urlencode({"pulse_deployment": deployment_id})
	try:
		async with session.get(url) as response:
			payload = await response.json(content_type=None)
			return response.status, payload if isinstance(payload, dict) else None
	except Exception:
		return None, None


async def _wait_for_routed_deployment(
	*,
	server_address: str,
	deployment_id: str,
	use_affinity: bool,
	timeout: float = ROUTED_DEPLOYMENT_TIMEOUT_SECONDS,
	poll_interval: float = ROUTED_DEPLOYMENT_POLL_SECONDS,
) -> None:
	deadline = asyncio.get_running_loop().time() + timeout
	last_status: int | None = None
	last_payload: dict[str, object] | None = None
	async with aiohttp.ClientSession(
		timeout=aiohttp.ClientTimeout(total=10, sock_connect=5)
	) as session:
		while True:
			last_status, last_payload = await _fetch_deployment_meta(
				session,
				server_address=server_address,
				deployment_id=deployment_id if use_affinity else None,
			)
			if (
				last_status == 200
				and last_payload is not None
				and last_payload.get("deployment_id") == deployment_id
			):
				return
			if asyncio.get_running_loop().time() >= deadline:
				break
			await asyncio.sleep(poll_interval)
	mode = "affinity" if use_affinity else "active"
	raise DeploymentError(
		f"deployment {deployment_id} did not become healthy through router "
		+ f"({mode}); last_status={last_status!r}, last_payload={last_payload!r}"
	)


async def _get_active_deployment_from_control(
	*,
	project: RailwayProject,
	router_service_name: str,
	cli_token_env_name: str | None,
) -> str | None:
	payload = await _run_router_control_command(
		project=project,
		router_service_name=router_service_name,
		cli_token_env_name=cli_token_env_name,
		control_args=["active"],
	)
	deployment_id = payload.get("deployment_id")
	if deployment_id is None:
		return None
	if not isinstance(deployment_id, str):
		raise DeploymentError("router control returned invalid active deployment")
	return deployment_id


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


async def _list_deployment_services(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> list[tuple[str, str]]:
	services = await list_deployment_service_records(client, project=project)
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
	cli_token_env_name: str | None = None,
) -> RedeployResult:
	resolved_deployment_id = deployment_id
	if resolved_deployment_id is None:
		stack_state = await inspect_stack(project=project)
		resolved_deployment_id = await _get_active_deployment_from_control(
			project=project,
			router_service_name=stack_state.router.service_name,
			cli_token_env_name=cli_token_env_name,
		)
	async with RailwayGraphQLClient(token=project.token) as client:
		if resolved_deployment_id is None:
			raise DeploymentError("no active deployment found")
		resolved_deployment_id = validate_deployment_id(resolved_deployment_id)
		backend_service_name = service_name_for_deployment(
			project.service_prefix,
			resolved_deployment_id,
		)
		backend_service = await require_service_by_name(
			client,
			project=project,
			name=backend_service_name,
		)
		backend_deployment_id, backend_status = await deploy_service_and_wait(
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
		await raise_if_service_exists(
			client,
			project=project,
			name=backend_service_name,
			error_message=f"service already exists for deployment {deployment_id}",
		)
		stack_state = await inspect_stack(project=project)
		server_address = project.server_address or stack_state.server_address
		reference_env_vars = await pulse_env_reference_variables(
			client,
			project=project,
			env_service_id=(
				stack_state.env.service_id if stack_state.env is not None else None
			),
		)
		build_args = backend_build_env(
			build_args=build_args,
			app_file=app_file,
			web_root=web_root,
			server_address=server_address,
			dockerfile_path=docker.dockerfile_path,
			context_path=docker.context_path,
		)
		session_env = backend_session_env(
			resolved_uses_railway_session_store,
			redis_url=stack_state.redis_url,
		)
		backend_image = await build_and_push_image(
			docker=replace(docker, build_args=build_args),
			image_ref=backend_image,
		)

		backend_service = await create_service_in_router_group(
			client,
			project=project,
			router_service_id=stack_state.router.service_id,
			name=backend_service_name,
			image=backend_image,
		)
		backend_service_id = backend_service.id
		backend_deployment_id, backend_status = await configure_service_and_deploy(
			client,
			project=project,
			service_id=backend_service_id,
			variables=backend_env(
				deployment_id=deployment_id,
				internal_token=stack_state.internal_token,
				app_file=app_file,
				server_address=server_address,
				session_env=session_env,
				user_env={**reference_env_vars, **project.env_vars},
			),
			error_message="backend deployment failed",
			source_image=backend_image,
			num_replicas=project.backend_replicas,
			healthcheck_path=backend_instance.healthcheck_path,
			healthcheck_timeout=backend_instance.healthcheck_timeout,
			overlap_seconds=backend_instance.overlap_seconds,
			start_command=pulse_start_command(),
		)
		await _register_deployment(
			project=project,
			router_service_name=stack_state.router.service_name,
			cli_token_env_name=cli_token_env_name,
			backend_service_name=backend_service_name,
			deployment_id=deployment_id,
		)
		await _wait_for_routed_deployment(
			server_address=stack_state.server_address,
			deployment_id=deployment_id,
			use_affinity=True,
		)
		await _promote_deployment(
			client,
			project=project,
			router_service_name=stack_state.router.service_name,
			cli_token_env_name=cli_token_env_name,
			backend_service_name=backend_service_name,
			deployment_id=deployment_id,
		)
		await _wait_for_routed_deployment(
			server_address=stack_state.server_address,
			deployment_id=deployment_id,
			use_affinity=False,
		)
		if server_address != stack_state.server_address:
			await _wait_for_routed_deployment(
				server_address=server_address,
				deployment_id=deployment_id,
				use_affinity=False,
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
			backend_status=backend_status,
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
			await raise_if_service_exists(
				client,
				project=project,
				name=backend_service_name,
				error_message=f"service already exists for deployment {deployment_id}",
			)
			stack_state = await inspect_stack(project=project)
			server_address = project.server_address or stack_state.server_address
			session_env = backend_session_env(
				resolved_uses_railway_session_store,
				redis_url=stack_state.redis_url,
			)
			reference_env_vars = await pulse_env_reference_variables(
				client,
				project=project,
				env_service_id=(
					stack_state.env.service_id if stack_state.env is not None else None
				),
			)
			runtime_vars = backend_env(
				deployment_id=deployment_id,
				internal_token=stack_state.internal_token,
				app_file=app_file,
				server_address=server_address,
				session_env=session_env,
				user_env={**reference_env_vars, **project.env_vars},
			)
			build_vars = backend_build_env(
				build_args=dict(docker.build_args),
				app_file=app_file,
				web_root=web_root,
				server_address=server_address,
				dockerfile_path=docker.dockerfile_path,
				context_path=docker.context_path,
			)
			backend_service = await create_service_in_router_group(
				client,
				project=project,
				router_service_id=stack_state.router.service_id,
				name=backend_service_name,
			)
			backend_service_id = backend_service.id
			await configure_service(
				client,
				project=project,
				service_id=backend_service_id,
				variables={**runtime_vars, **build_vars},
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
			build_deployment = await wait_for_latest_service_deployment(
				client,
				project=project,
				service_id=backend_service_id,
			)
			if build_deployment["status"] != "SUCCESS":
				raise DeploymentError(
					"backend source build failed after railway up: "
					+ build_deployment["status"].lower()
				)
			await _register_deployment(
				project=project,
				router_service_name=stack_state.router.service_name,
				cli_token_env_name=resolved_cli_token_env_name,
				backend_service_name=backend_service_name,
				deployment_id=deployment_id,
			)
			await _wait_for_routed_deployment(
				server_address=stack_state.server_address,
				deployment_id=deployment_id,
				use_affinity=True,
			)
			await _promote_deployment(
				client,
				project=project,
				router_service_name=stack_state.router.service_name,
				cli_token_env_name=resolved_cli_token_env_name,
				backend_service_name=backend_service_name,
				deployment_id=deployment_id,
			)
			promoted = True
			await _wait_for_routed_deployment(
				server_address=stack_state.server_address,
				deployment_id=deployment_id,
				use_affinity=False,
			)
			if server_address != stack_state.server_address:
				await _wait_for_routed_deployment(
					server_address=server_address,
					deployment_id=deployment_id,
					use_affinity=False,
				)
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
	cli_token_env_name: str | None = None,
) -> None:
	service_name = service_name_for_deployment(
		project.service_prefix,
		deployment_id,
	)
	async with RailwayGraphQLClient(token=project.token) as client:
		service = await require_service_by_name(
			client,
			project=project,
			name=service_name,
		)
		stack_state = await inspect_stack(project=project)
		active_deployment_id = await _get_active_deployment_from_control(
			project=project,
			router_service_name=stack_state.router.service_name,
			cli_token_env_name=cli_token_env_name,
		)
		if active_deployment_id is None:
			raise DeploymentError(
				"no active deployment found; refusing to delete backend service"
			)
		if active_deployment_id == deployment_id:
			raise DeploymentError(
				"cannot delete active deployment; deploy or promote another deployment first"
			)
		await _run_router_control_command(
			project=project,
			router_service_name=stack_state.router.service_name,
			cli_token_env_name=cli_token_env_name,
			control_args=["delete", "--deployment-id", deployment_id],
		)
		await client.delete_service(
			service_id=service.id,
			environment_id=project.environment_id,
		)


__all__ = [
	"DeployResult",
	"DeploymentError",
	"JANITOR_START_COMMAND",
	"RedeployResult",
	"ROUTER_START_COMMAND",
	"build_and_push_image",
	"deployment_name_slug",
	"default_janitor_service_name",
	"default_redis_service_name",
	"default_service_prefix",
	"delete_deployment",
	"deploy",
	"generate_deployment_id",
	"railway_up_command",
	"redeploy_deployment",
	"resolve_deployment_id_by_name",
	"validate_deployment_service_records",
]
