from __future__ import annotations

import asyncio
from collections.abc import Container
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from pulse.cli.helpers import load_app_from_target

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
	REDIS_URL,
)
from pulse_railway.errors import DeploymentError
from pulse_railway.images import (
	build_and_push_image,
	build_router_image,
	default_image_ref,
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
	default_janitor_service_name,
	default_redis_service_name,
	require_ready_stack,
	resolve_or_create_internal_token,
	resolve_or_create_redis,
	resolve_project_internals,
)


@dataclass(slots=True)
class DeployResult:
	deployment_id: str
	backend_service_id: str
	backend_service_name: str
	backend_image: str
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
		"PULSE_APP_FILE",
		"PULSE_SERVER_ADDRESS",
		"PORT",
	}
)


def validate_backend_env_vars(
	env_vars: dict[str, str],
	*,
	managed_env_vars: Container[str] | None = None,
) -> None:
	managed = () if managed_env_vars is None else managed_env_vars
	reserved = sorted(
		key for key in env_vars if key in RESERVED_BACKEND_ENV_VARS or key in managed
	)
	if reserved:
		raise DeploymentError(
			"backend env vars cannot override pulse-railway managed variables: "
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


def _railway_session_store_from_app(
	app_file: str,
	context_path: Path,
) -> RailwayRedisSessionStore | None:
	session_store = _app_session_store(app_file, context_path)
	if isinstance(session_store, RailwayRedisSessionStore):
		return session_store
	return None


def _backend_session_env(
	store: RailwayRedisSessionStore | None,
	*,
	redis_url: str | None,
) -> dict[str, str]:
	if store is None:
		return {}
	configured_url = store.configured_url()
	if configured_url is not None:
		return {REDIS_URL: configured_url}
	if redis_url is None:
		raise DeploymentError("redis_url is required for Railway session store wiring")
	return {REDIS_URL: redis_url}


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


async def deploy(
	*,
	project: RailwayProject,
	docker: DockerBuild,
	deployment_name: str = "prod",
	deployment_id: str | None = None,
	app_file: str = "main.py",
	web_root: str = "web",
	backend_instance: ServiceInstanceConfig = DEFAULT_BACKEND_INSTANCE,
) -> DeployResult:
	validate_backend_env_vars(project.env_vars)
	docker = replace(docker, build_args=dict(docker.build_args))
	build_args = dict(docker.build_args)
	session_store = _railway_session_store_from_app(app_file, docker.context_path)
	deployment_id = (
		validate_deployment_id(deployment_id)
		if deployment_id is not None
		else generate_deployment_id(deployment_name)
	)
	backend_service_name = service_name_for_deployment(
		project.service_prefix,
		deployment_id,
	)
	backend_image = default_image_ref(
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
		build_args.setdefault("APP_FILE", app_file)
		build_args.setdefault("WEB_ROOT", web_root)
		build_args.setdefault("PULSE_SERVER_ADDRESS", server_address)
		backend_session_env = _backend_session_env(
			session_store,
			redis_url=stack_state.redis_url,
		)
		validate_backend_env_vars(
			project.env_vars,
			managed_env_vars=backend_session_env,
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
		for key, value in {
			PULSE_DEPLOYMENT_ID: deployment_id,
			PULSE_INTERNAL_TOKEN: stack_state.internal_token,
			"PULSE_APP_FILE": app_file,
			"PULSE_SERVER_ADDRESS": server_address,
			"PORT": str(project.backend_port),
			**backend_session_env,
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

		project_variables = await client.get_project_variables(
			project_id=project.project_id,
			environment_id=project.environment_id,
		)
		previous_active_deployment_id = project_variables.get(
			ACTIVE_DEPLOYMENT_VARIABLE
		)
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
	"ResolvedRedis",
	"resolve_deployment_id_by_name",
	"resolve_or_create_redis",
	"resolve_or_create_internal_token",
	"resolve_project_internals",
	"set_deployment_service_state",
]
