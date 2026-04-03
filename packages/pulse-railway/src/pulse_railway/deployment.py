from __future__ import annotations

import asyncio
import secrets
import tempfile
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from pulse_railway.config import (
	DEFAULT_BACKEND_INSTANCE,
	DEFAULT_ROUTER_INSTANCE,
	DockerBuild,
	RailwayInternals,
	RailwayProject,
	ServiceInstanceConfig,
)
from pulse_railway.constants import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	DEFAULT_REDIS_TEMPLATE_CODE,
	DEFAULT_ROUTER_PORT,
	RAILWAY_DEPLOYMENT_ID_ENV,
	RAILWAY_ENVIRONMENT_ID_ENV,
	RAILWAY_INTERNAL_TOKEN_ENV,
	RAILWAY_JANITOR_DRAIN_GRACE_SECONDS_ENV,
	RAILWAY_JANITOR_MAX_DRAIN_AGE_SECONDS_ENV,
	RAILWAY_PROJECT_ID_ENV,
	RAILWAY_REDIS_PREFIX_ENV,
	RAILWAY_REDIS_URL_ENV,
	RAILWAY_SERVICE_PREFIX_ENV,
	RAILWAY_TOKEN_ENV,
	RAILWAY_WEBSOCKET_HEARTBEAT_SECONDS_ENV,
	RAILWAY_WEBSOCKET_TTL_SECONDS_ENV,
)
from pulse_railway.railway import (
	RailwayGraphQLClient,
	ServiceRecord,
	normalize_service_prefix,
	service_name_for_deployment,
	validate_deployment_id,
)
from pulse_railway.tracker import RedisDeploymentTracker


class DeploymentError(RuntimeError):
	pass


@dataclass(slots=True)
class DeployResult:
	deployment_id: str
	backend_service_id: str
	backend_service_name: str
	backend_image: str
	router_service_id: str
	router_service_name: str
	router_image: str
	router_domain: str
	server_address: str
	backend_deployment_id: str
	router_deployment_id: str
	backend_status: str
	router_status: str
	janitor_service_id: str | None = None
	janitor_service_name: str | None = None
	janitor_image: str | None = None
	janitor_deployment_id: str | None = None
	janitor_status: str | None = None


@dataclass(slots=True)
class ResolvedRedis:
	internal_url: str
	public_url: str | None
	service: ServiceRecord


ROUTER_START_COMMAND = (
	"sh -c 'uvicorn pulse_railway.router:build_app_from_env --factory "
	'--host 0.0.0.0 --port "${PORT:-8000}"\''
)
JANITOR_START_COMMAND = "sh -c 'pulse-railway janitor run'"


def pulse_start_command() -> str:
	return (
		'sh -c \'pulse run "$PULSE_APP_FILE" --prod --address 0.0.0.0 '
		'--port "${PORT:-8000}"\''
	)


def generate_deployment_id(deployment_name: str) -> str:
	base = "".join(
		char if char.isalnum() else "-" for char in deployment_name.strip().lower()
	)
	base = "-".join(segment for segment in base.split("-") if segment) or "prod"
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


def default_janitor_service_name(service_name: str) -> str:
	candidate = f"{service_name.strip().lower()}-janitor"
	candidate = "".join(
		char if char.isalnum() or char == "-" else "-" for char in candidate
	)
	candidate = "-".join(segment for segment in candidate.split("-") if segment)
	if len(candidate) > 32:
		raise ValueError("janitor service name must be <= 32 chars")
	return candidate


def default_redis_service_name(service_name: str) -> str:
	candidate = f"{service_name.strip().lower()}-redis"
	candidate = "".join(
		char if char.isalnum() or char == "-" else "-" for char in candidate
	)
	candidate = "-".join(segment for segment in candidate.split("-") if segment)
	if len(candidate) > 32:
		raise ValueError("redis service name must be <= 32 chars")
	return candidate


def default_image_ref(*, image_repository: str | None, prefix: str) -> str:
	if image_repository:
		return f"{image_repository}:{prefix}"
	return f"ttl.sh/pulse-railway-{prefix}-{secrets.token_hex(4)}:24h"


async def _run_command(*args: str, cwd: Path | None = None) -> None:
	process = await asyncio.create_subprocess_exec(
		*args,
		cwd=str(cwd) if cwd is not None else None,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
	)
	stdout, stderr = await process.communicate()
	if process.returncode != 0:
		raise DeploymentError(
			f"command failed ({' '.join(args)}):\n{stdout.decode()}{stderr.decode()}"
		)


async def build_and_push_image(
	*,
	docker: DockerBuild,
	image_ref: str,
) -> str:
	command = [
		"docker",
		"buildx",
		"build",
		"--push",
		"--platform",
		docker.platform,
		"-t",
		image_ref,
		"-f",
		str(docker.dockerfile_path),
	]
	for key, value in sorted(docker.build_args.items()):
		command.extend(["--build-arg", f"{key}={value}"])
	command.append(str(docker.context_path))
	await _run_command(*command)
	return image_ref


def _workspace_root() -> Path | None:
	for parent in Path(__file__).resolve().parents:
		if (parent / "packages" / "pulse-railway" / "pyproject.toml").exists():
			return parent
	return None


def _router_dockerfile() -> str:
	workspace_root = _workspace_root()
	if workspace_root is None:
		return "\n".join(
			[
				"FROM python:3.12-slim",
				"COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv",
				"RUN uv pip install --system pulse-railway",
				f"EXPOSE {DEFAULT_ROUTER_PORT}",
				'CMD ["uvicorn", "pulse_railway.router:build_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]',
			]
		)
	return "\n".join(
		[
			"FROM python:3.12-slim",
			"COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv",
			"WORKDIR /src",
			"COPY packages/pulse/python /src/packages/pulse/python",
			"COPY packages/pulse-railway /src/packages/pulse-railway",
			"RUN uv pip install --system /src/packages/pulse/python /src/packages/pulse-railway",
			f"EXPOSE {DEFAULT_ROUTER_PORT}",
			'CMD ["uvicorn", "pulse_railway.router:build_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]',
		]
	)


async def build_router_image(*, image_ref: str) -> str:
	workspace_root = _workspace_root()
	context = workspace_root if workspace_root is not None else Path(tempfile.mkdtemp())
	with tempfile.NamedTemporaryFile("w", suffix=".Dockerfile", delete=False) as handle:
		handle.write(_router_dockerfile())
		dockerfile_path = Path(handle.name)
	try:
		command = [
			"docker",
			"buildx",
			"build",
			"--push",
			"--platform",
			"linux/amd64",
			"-t",
			image_ref,
			"-f",
			str(dockerfile_path),
			str(context),
		]
		await _run_command(*command)
		return image_ref
	finally:
		dockerfile_path.unlink(missing_ok=True)


async def _ensure_service(
	client: RailwayGraphQLClient,
	*,
	project_id: str,
	environment_id: str,
	name: str,
	image: str | None = None,
) -> ServiceRecord:
	service = await client.find_service_by_name(
		project_id=project_id,
		environment_id=environment_id,
		name=name,
	)
	if service is not None:
		return service
	service_id = await client.create_service(
		project_id=project_id,
		environment_id=environment_id,
		name=name,
		image=image,
	)
	return ServiceRecord(id=service_id, name=name)


async def _ensure_router_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	internals: RailwayInternals,
	router_image: str,
	router_instance: ServiceInstanceConfig,
) -> tuple[ServiceRecord, str, str]:
	service = await _ensure_service(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=project.service_name,
		image=router_image,
	)
	router_variables = {
		RAILWAY_TOKEN_ENV: project.token,
		RAILWAY_PROJECT_ID_ENV: project.project_id,
		RAILWAY_ENVIRONMENT_ID_ENV: project.environment_id,
		RAILWAY_SERVICE_PREFIX_ENV: internals.service_prefix,
		"PULSE_RAILWAY_BACKEND_PORT": str(project.backend_port),
		"PORT": str(project.router_port),
	}
	if internals.redis_url:
		router_variables[RAILWAY_REDIS_URL_ENV] = internals.redis_url
		router_variables[RAILWAY_REDIS_PREFIX_ENV] = project.redis_prefix
		router_variables[RAILWAY_WEBSOCKET_HEARTBEAT_SECONDS_ENV] = str(
			project.websocket_heartbeat_seconds
		)
		router_variables[RAILWAY_WEBSOCKET_TTL_SECONDS_ENV] = str(
			project.websocket_ttl_seconds
		)
	for key, value in router_variables.items():
		await client.upsert_variable(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=service.id,
			name=key,
			value=value,
			skip_deploys=True,
		)
	await client.update_service_instance(
		service_id=service.id,
		environment_id=project.environment_id,
		source_image=router_image,
		num_replicas=project.router_replicas,
		healthcheck_path=router_instance.healthcheck_path,
		healthcheck_timeout=router_instance.healthcheck_timeout,
		overlap_seconds=router_instance.overlap_seconds,
		start_command=ROUTER_START_COMMAND,
	)
	router_deployment_id = await client.deploy_service(
		service_id=service.id,
		environment_id=project.environment_id,
	)
	router_deployment = await client.wait_for_deployment(
		deployment_id=router_deployment_id
	)
	if router_deployment["status"] != "SUCCESS":
		raise DeploymentError("router deployment failed")

	service = await _ensure_service(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=project.service_name,
	)
	domain = service.domains[0].domain if service.domains else None
	if domain is None:
		domain = await client.create_service_domain(
			service_id=service.id,
			environment_id=project.environment_id,
			target_port=project.router_port,
		)
	return service, domain, router_deployment_id


async def _ensure_janitor_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	internals: RailwayInternals,
	janitor_image: str,
) -> tuple[ServiceRecord, str]:
	service_name = project.janitor_service_name or default_janitor_service_name(
		project.service_name
	)
	service = await _ensure_service(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=service_name,
		image=janitor_image,
	)
	if not internals.redis_url:
		raise DeploymentError("redis_url is required for janitor service creation")
	for key, value in {
		RAILWAY_TOKEN_ENV: project.token,
		RAILWAY_PROJECT_ID_ENV: project.project_id,
		RAILWAY_ENVIRONMENT_ID_ENV: project.environment_id,
		RAILWAY_SERVICE_PREFIX_ENV: internals.service_prefix,
		RAILWAY_INTERNAL_TOKEN_ENV: internals.internal_token,
		RAILWAY_REDIS_URL_ENV: internals.redis_url,
		RAILWAY_REDIS_PREFIX_ENV: project.redis_prefix,
		RAILWAY_JANITOR_DRAIN_GRACE_SECONDS_ENV: str(project.drain_grace_seconds),
		RAILWAY_JANITOR_MAX_DRAIN_AGE_SECONDS_ENV: str(project.max_drain_age_seconds),
		RAILWAY_WEBSOCKET_HEARTBEAT_SECONDS_ENV: str(
			project.websocket_heartbeat_seconds
		),
		RAILWAY_WEBSOCKET_TTL_SECONDS_ENV: str(project.websocket_ttl_seconds),
	}.items():
		await client.upsert_variable(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=service.id,
			name=key,
			value=value,
			skip_deploys=True,
		)
	await client.update_service_instance(
		service_id=service.id,
		environment_id=project.environment_id,
		source_image=janitor_image,
		num_replicas=project.janitor_replicas,
		start_command=JANITOR_START_COMMAND,
		cron_schedule=project.janitor_cron_schedule,
		restart_policy_type="NEVER",
	)
	deployment_id = await client.deploy_service(
		service_id=service.id,
		environment_id=project.environment_id,
	)
	deployment = await client.wait_for_deployment(deployment_id=deployment_id)
	if deployment["status"] != "SUCCESS":
		raise DeploymentError("janitor deployment failed")
	return service, deployment_id


async def _wait_for_service_by_name(
	client: RailwayGraphQLClient,
	*,
	project_id: str,
	environment_id: str,
	name: str,
	timeout: float = 120.0,
	poll_interval: float = 2.0,
) -> ServiceRecord:
	loop = asyncio.get_running_loop()
	deadline = loop.time() + timeout
	while True:
		service = await client.find_service_by_name(
			project_id=project_id,
			environment_id=environment_id,
			name=name,
		)
		if service is not None:
			return service
		if loop.time() >= deadline:
			raise TimeoutError(f"service {name} was not created within {timeout:.0f}s")
		await asyncio.sleep(poll_interval)


async def _wait_for_service_variable(
	client: RailwayGraphQLClient,
	*,
	project_id: str,
	environment_id: str,
	service_id: str,
	name: str,
	timeout: float = 180.0,
	poll_interval: float = 2.0,
) -> str:
	loop = asyncio.get_running_loop()
	deadline = loop.time() + timeout
	while True:
		variables = await client.get_service_variables_for_deployment(
			project_id=project_id,
			environment_id=environment_id,
			service_id=service_id,
		)
		value = variables.get(name)
		if value:
			return value
		if loop.time() >= deadline:
			raise TimeoutError(
				f"service variable {name} not available within {timeout:.0f}s"
			)
		await asyncio.sleep(poll_interval)


async def resolve_or_create_redis(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> ResolvedRedis:
	service_name = project.redis_service_name or default_redis_service_name(
		project.service_name
	)
	service = await client.find_service_by_name(
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=service_name,
	)
	if service is None:
		template = await client.get_template_by_code(
			code=project.redis_template_code or DEFAULT_REDIS_TEMPLATE_CODE
		)
		config = deepcopy(template.serialized_config)
		template_service_id = next(iter(config["services"]))
		config["services"][template_service_id]["name"] = service_name
		await client.deploy_template(
			project_id=project.project_id,
			environment_id=project.environment_id,
			template_id=template.id,
			serialized_config=config,
		)
		service = await _wait_for_service_by_name(
			client,
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=service_name,
		)
	internal_url = await _wait_for_service_variable(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=service.id,
		name="REDIS_URL",
	)
	service_variables = await client.get_service_variables_for_deployment(
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=service.id,
	)
	return ResolvedRedis(
		internal_url=internal_url,
		public_url=service_variables.get("REDIS_PUBLIC_URL"),
		service=service,
	)


async def resolve_or_create_internal_token(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> str:
	variables = await client.get_project_variables(
		project_id=project.project_id,
		environment_id=project.environment_id,
	)
	internal_token = variables.get(RAILWAY_INTERNAL_TOKEN_ENV)
	if internal_token:
		return internal_token
	internal_token = secrets.token_urlsafe(32)
	await client.upsert_variable(
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=RAILWAY_INTERNAL_TOKEN_ENV,
		value=internal_token,
		skip_deploys=True,
	)
	return internal_token


async def resolve_project_internals(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> RailwayInternals:
	redis_url = project.redis_url
	redis_public_url: str | None = None
	if redis_url is None:
		resolved_redis = await resolve_or_create_redis(client, project=project)
		redis_url = resolved_redis.internal_url
		redis_public_url = resolved_redis.public_url
	return RailwayInternals(
		service_prefix=normalize_service_prefix(project.service_prefix),
		internal_token=await resolve_or_create_internal_token(
			client,
			project=project,
		),
		redis_url=redis_url,
		redis_public_url=redis_public_url,
	)


async def _list_deployment_services(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> list[tuple[str, str]]:
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
	deployments: list[tuple[str, str]] = []
	for service, variables in zip(services, variable_sets, strict=True):
		deployment_id = variables.get(RAILWAY_DEPLOYMENT_ID_ENV)
		if deployment_id:
			deployments.append((deployment_id, service.name))
	return deployments


async def deploy(
	*,
	project: RailwayProject,
	docker: DockerBuild,
	deployment_name: str = "prod",
	deployment_id: str | None = None,
	app_file: str = "main.py",
	web_root: str = "web",
	backend_instance: ServiceInstanceConfig = DEFAULT_BACKEND_INSTANCE,
	router_instance: ServiceInstanceConfig = DEFAULT_ROUTER_INSTANCE,
) -> DeployResult:
	docker = replace(docker, build_args=dict(docker.build_args))
	build_args = dict(docker.build_args)
	deployment_id = (
		validate_deployment_id(deployment_id)
		if deployment_id is not None
		else generate_deployment_id(deployment_name)
	)
	backend_service_name = service_name_for_deployment(
		normalize_service_prefix(project.service_prefix), deployment_id
	)
	router_image = project.router_image or default_image_ref(
		image_repository=docker.image_repository,
		prefix="router",
	)
	backend_image = default_image_ref(
		image_repository=docker.image_repository,
		prefix=deployment_id,
	)
	janitor_image = project.janitor_image or router_image
	tracker = None

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
			internals = await resolve_project_internals(client, project=project)
			if internals.tracker_url is None:
				raise DeploymentError("redis_url is required for deployment tracking")
			tracker = RedisDeploymentTracker.from_url(
				url=internals.tracker_url,
				prefix=project.redis_prefix,
				websocket_ttl_seconds=project.websocket_ttl_seconds,
			)

			if project.router_image is None:
				router_image = await build_router_image(image_ref=router_image)
				janitor_image = project.janitor_image or router_image
			(
				router_service,
				router_domain,
				router_deployment_id,
			) = await _ensure_router_service(
				client,
				project=project,
				internals=internals,
				router_image=router_image,
				router_instance=router_instance,
			)
			janitor_service, janitor_deployment_id = await _ensure_janitor_service(
				client,
				project=project,
				internals=internals,
				janitor_image=janitor_image,
			)

			server_address = project.server_address or f"https://{router_domain}"
			build_args.setdefault("APP_FILE", app_file)
			build_args.setdefault("WEB_ROOT", web_root)
			build_args.setdefault("PULSE_SERVER_ADDRESS", server_address)
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
			for key, value in {
				RAILWAY_DEPLOYMENT_ID_ENV: deployment_id,
				RAILWAY_INTERNAL_TOKEN_ENV: internals.internal_token,
				"PULSE_APP_FILE": app_file,
				"PULSE_SERVER_ADDRESS": server_address,
				"PORT": str(project.backend_port),
				**project.env_vars,
			}.items():
				await client.upsert_variable(
					project_id=project.project_id,
					environment_id=project.environment_id,
					service_id=backend_service_id,
					name=key,
					value=value,
					skip_deploys=True,
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

			await client.upsert_variable(
				project_id=project.project_id,
				environment_id=project.environment_id,
				name=ACTIVE_DEPLOYMENT_VARIABLE,
				value=deployment_id,
				skip_deploys=True,
			)
			await tracker.mark_active(
				deployment_id=deployment_id,
				service_name=backend_service_name,
			)
			draining_deployments = [
				(tracked_deployment_id, tracked_service_name)
				for tracked_deployment_id, tracked_service_name in await _list_deployment_services(
					client, project=project
				)
				if tracked_deployment_id != deployment_id
			]
			await asyncio.gather(
				*[
					tracker.mark_draining(
						deployment_id=tracked_deployment_id,
						service_name=tracked_service_name,
					)
					for tracked_deployment_id, tracked_service_name in draining_deployments
				]
			)
			return DeployResult(
				deployment_id=deployment_id,
				backend_service_id=backend_service_id,
				backend_service_name=backend_service_name,
				backend_image=backend_image,
				router_service_id=router_service.id,
				router_service_name=project.service_name,
				router_image=router_image,
				router_domain=router_domain,
				server_address=server_address,
				backend_deployment_id=backend_deployment_id,
				router_deployment_id=router_deployment_id,
				backend_status=backend_deployment["status"],
				router_status="SUCCESS",
				janitor_service_id=janitor_service.id,
				janitor_service_name=janitor_service.name,
				janitor_image=janitor_image,
				janitor_deployment_id=janitor_deployment_id,
				janitor_status="SUCCESS",
			)
	finally:
		if tracker is not None:
			await tracker.close()


async def delete_deployment(
	*,
	project: RailwayProject,
	deployment_id: str,
	clear_active: bool = True,
) -> None:
	service_name = service_name_for_deployment(
		normalize_service_prefix(project.service_prefix),
		deployment_id,
	)
	tracker = (
		RedisDeploymentTracker.from_url(
			url=project.redis_url,
			prefix=project.redis_prefix,
			websocket_ttl_seconds=project.websocket_ttl_seconds,
		)
		if project.redis_url
		else None
	)
	try:
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
			if tracker is not None:
				await tracker.clear_deployment(deployment_id=deployment_id)
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
	finally:
		if tracker is not None:
			await tracker.close()


__all__ = [
	"DeployResult",
	"DeploymentError",
	"build_and_push_image",
	"build_router_image",
	"default_redis_service_name",
	"default_service_prefix",
	"delete_deployment",
	"deploy",
	"generate_deployment_id",
	"ResolvedRedis",
	"resolve_or_create_redis",
	"resolve_project_internals",
]
