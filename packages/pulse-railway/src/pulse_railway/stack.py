from __future__ import annotations

import asyncio
import secrets
from copy import deepcopy
from dataclasses import dataclass

from pulse_railway.config import (
	DEFAULT_ROUTER_INSTANCE,
	RailwayInternals,
	RailwayProject,
	ServiceInstanceConfig,
)
from pulse_railway.constants import (
	DEFAULT_PULSE_BASELINE_TEMPLATE_CODE,
	DEFAULT_REDIS_TEMPLATE_CODE,
	PULSE_INTERNAL_TOKEN,
	PULSE_JANITOR_DRAIN_GRACE_SECONDS,
	PULSE_JANITOR_MAX_DRAIN_AGE_SECONDS,
	PULSE_REDIS_PREFIX,
	PULSE_SERVICE_PREFIX,
	PULSE_WEBSOCKET_HEARTBEAT_SECONDS,
	PULSE_WEBSOCKET_TTL_SECONDS,
	RAILWAY_ENVIRONMENT_ID,
	RAILWAY_PROJECT_ID,
	RAILWAY_TOKEN,
	REDIS_URL,
)
from pulse_railway.errors import DeploymentError
from pulse_railway.images import official_janitor_image_ref, official_router_image_ref
from pulse_railway.railway import (
	RailwayGraphQLClient,
	ServiceRecord,
	normalize_service_name,
	normalize_service_prefix,
)

ROUTER_START_COMMAND = (
	"sh -c 'uvicorn pulse_railway.router:build_app_from_env --factory "
	'--host 0.0.0.0 --port "${PORT:-8000}"\''
)
JANITOR_START_COMMAND = "sh -c 'pulse-railway janitor run'"


@dataclass(slots=True)
class StackServiceState:
	service_id: str
	service_name: str
	image: str | None = None
	domain: str | None = None


@dataclass(slots=True)
class StackServiceResult:
	service_id: str | None
	service_name: str | None
	image: str | None = None
	domain: str | None = None
	created: bool = False
	deployed: bool = False
	deployment_id: str | None = None
	status: str | None = None


@dataclass(slots=True)
class StackState:
	router: StackServiceState
	janitor: StackServiceState
	redis: StackServiceState | None
	internal_token: str
	redis_url: str
	server_address: str
	env: StackServiceState | None = None


@dataclass(slots=True)
class InitResult:
	router: StackServiceResult
	janitor: StackServiceResult
	redis: StackServiceResult | None
	internal_token_created: bool
	redis_url: str
	server_address: str


@dataclass(slots=True)
class ResolvedRedis:
	internal_url: str
	service: ServiceRecord
	created: bool


def _baseline_service_names(project: RailwayProject) -> dict[str, str]:
	names = {
		"router": project.service_name,
		"janitor": project.janitor_service_name
		or default_janitor_service_name(project.service_name),
		"env": default_env_service_name(project.service_name),
	}
	if project.redis_url is None:
		names["redis"] = project.redis_service_name or default_redis_service_name(
			project.service_name
		)
	return names


def _baseline_leftover_service_names(project: RailwayProject) -> dict[str, str]:
	names = dict(_baseline_service_names(project))
	names["redis"] = project.redis_service_name or default_redis_service_name(
		project.service_name
	)
	if names["redis"] != "pulse-redis":
		names["template_redis"] = "pulse-redis"
	return names


def _raise_for_existing_baseline(found_names: list[str]) -> None:
	found_text = ", ".join(sorted(found_names))
	raise DeploymentError(
		"baseline stack already exists: "
		+ found_text
		+ ". `pulse-railway init` only creates a fresh baseline. "
		+ "Delete these baseline services and rerun `pulse-railway init`; "
		+ "use `pulse-railway update` once stack reconciliation is implemented."
	)


async def _deploy_baseline_template(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> dict[str, ServiceRecord]:
	template = await client.get_template_by_code(
		code=DEFAULT_PULSE_BASELINE_TEMPLATE_CODE
	)
	config = deepcopy(template.serialized_config)
	service_name_map = {
		"pulse-router": project.service_name,
		"pulse-janitor": project.janitor_service_name
		or default_janitor_service_name(project.service_name),
	}
	if project.redis_url is None:
		service_name_map["pulse-redis"] = project.redis_service_name or (
			default_redis_service_name(project.service_name)
		)
	else:
		service_name_map["pulse-redis"] = "pulse-redis"
	renamed_services: set[str] = set()
	for service_config in config["services"].values():
		template_name = service_config.get("name")
		if template_name not in service_name_map:
			continue
		service_config["name"] = service_name_map[template_name]
		renamed_services.add(template_name)
	missing = [name for name in service_name_map if name not in renamed_services]
	if missing:
		missing_text = ", ".join(missing)
		raise DeploymentError(
			f"template {template.code} is missing expected services: {missing_text}"
		)
	await client.deploy_template(
		project_id=project.project_id,
		environment_id=project.environment_id,
		template_id=template.id,
		serialized_config=config,
	)
	created_services = await asyncio.gather(
		*[
			_wait_for_service_by_name(
				client,
				project_id=project.project_id,
				environment_id=project.environment_id,
				name=service_name,
			)
			for service_name in service_name_map.values()
		]
	)
	return dict(zip(service_name_map, created_services, strict=True))


async def _place_service_in_router_group(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_service_id: str,
	service_id: str,
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
		service_id=service_id,
		group_id=group_id,
	)


def _variable_references_service(value: str, service_name: str) -> bool:
	return f"${{{{{service_name}." in value.replace(" ", "")


def _variable_names_referencing_services(
	variables: dict[str, str],
	service_names: list[str],
) -> list[str]:
	return [
		name
		for name, value in variables.items()
		if any(
			_variable_references_service(value, service_name)
			for service_name in service_names
		)
	]


async def _remove_managed_redis_from_baseline(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_service: ServiceRecord | None,
	janitor_service: ServiceRecord | None,
	env_service: ServiceRecord | None,
) -> bool:
	redis_names = list(
		dict.fromkeys(
			[
				project.redis_service_name
				or default_redis_service_name(project.service_name),
				"pulse-redis",
			]
		)
	)
	redis_services = await asyncio.gather(
		*[
			client.find_service_by_name(
				project_id=project.project_id,
				environment_id=project.environment_id,
				name=redis_name,
			)
			for redis_name in redis_names
		]
	)
	variable_service_ids = [
		None,
		*[
			service.id
			for service in (router_service, janitor_service, env_service)
			if service is not None
		],
	]
	variable_sets = await asyncio.gather(
		*[
			client.get_project_variables(
				project_id=project.project_id,
				environment_id=project.environment_id,
				service_id=service_id,
				unrendered=True,
			)
			for service_id in variable_service_ids
		]
	)
	variables_to_delete = [
		(service_id, name)
		for service_id, variables in zip(
			variable_service_ids, variable_sets, strict=True
		)
		for name in _variable_names_referencing_services(variables, redis_names)
	]
	removed_variables = bool(variables_to_delete)
	await asyncio.gather(
		*[
			client.delete_variable(
				project_id=project.project_id,
				environment_id=project.environment_id,
				service_id=service_id,
				name=name,
			)
			for service_id, name in variables_to_delete
		]
	)
	services_to_delete = [service for service in redis_services if service is not None]
	if not services_to_delete:
		return removed_variables
	await asyncio.gather(
		*[
			client.delete_service(
				service_id=service.id,
				environment_id=project.environment_id,
			)
			for service in services_to_delete
		]
	)
	return True


def default_janitor_service_name(service_name: str) -> str:
	return normalize_service_name(f"{service_name}-janitor")


def default_redis_service_name(service_name: str) -> str:
	return normalize_service_name(f"{service_name}-redis")


def default_env_service_name(service_name: str) -> str:
	candidate = service_name.strip().lower()
	if candidate.endswith("-router"):
		candidate = candidate[:-7]
	return normalize_service_name(f"{candidate}-env")


async def _ensure_service(
	client: RailwayGraphQLClient,
	*,
	project_id: str,
	environment_id: str,
	name: str,
	image: str | None = None,
) -> tuple[ServiceRecord, bool]:
	service = await client.find_service_by_name(
		project_id=project_id,
		environment_id=environment_id,
		name=name,
	)
	if service is not None:
		return service, False
	await client.create_service(
		project_id=project_id,
		environment_id=environment_id,
		name=name,
		image=image,
	)
	service = await _wait_for_service_by_name(
		client,
		project_id=project_id,
		environment_id=environment_id,
		name=name,
	)
	service.image = service.image or image
	return service, True


async def _ensure_env_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_service: ServiceRecord | None = None,
) -> ServiceRecord:
	service_name = default_env_service_name(project.service_name)
	service, created = await _ensure_service(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=service_name,
	)
	if created and router_service is not None:
		await _place_service_in_router_group(
			client,
			project=project,
			router_service_id=router_service.id,
			service_id=service.id,
		)
	return service


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


def _require_variables(
	*,
	service_name: str,
	variables: dict[str, str],
	names: tuple[str, ...],
	command: str,
) -> None:
	missing = [name for name in names if not variables.get(name)]
	if missing:
		missing_text = ", ".join(missing)
		raise DeploymentError(
			f"{service_name} is missing required runtime variables ({missing_text}); "
			+ f"run `pulse-railway {command}`"
		)


def _effective_redis_url(
	*,
	router_variables: dict[str, str],
	janitor_variables: dict[str, str],
) -> str:
	router_redis_url = router_variables.get(REDIS_URL)
	janitor_redis_url = janitor_variables.get(REDIS_URL)
	if not router_redis_url or not janitor_redis_url:
		raise DeploymentError(
			"baseline stack is missing REDIS_URL; run `pulse-railway init`"
		)
	if router_redis_url != janitor_redis_url:
		raise DeploymentError(
			"router and janitor REDIS_URL values differ; run `pulse-railway init`"
		)
	return router_redis_url


async def _deploy_service_and_wait(
	client: RailwayGraphQLClient,
	*,
	service_id: str,
	environment_id: str,
	error_message: str,
) -> tuple[str, str]:
	deployment_id = await client.deploy_service(
		service_id=service_id,
		environment_id=environment_id,
	)
	deployment = await client.wait_for_deployment(deployment_id=deployment_id)
	if deployment["status"] != "SUCCESS":
		raise DeploymentError(error_message)
	return deployment_id, deployment["status"]


async def _ensure_router_domain(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service: ServiceRecord,
) -> str:
	if service.domains:
		return service.domains[0].domain
	return await client.create_service_domain(
		service_id=service.id,
		environment_id=project.environment_id,
		target_port=project.router_port,
	)


def _server_address_from_runtime(
	*,
	domain: str | None,
	variables: dict[str, str],
) -> str | None:
	public_domain = variables.get("RAILWAY_PUBLIC_DOMAIN") or variables.get(
		"RAILWAY_STATIC_URL"
	)
	if public_domain:
		return f"https://{public_domain}"
	if domain:
		return f"https://{domain}"
	return None


async def _resolve_router_server_address(
	client: RailwayGraphQLClient,
	*,
	project_id: str,
	environment_id: str,
	service_id: str,
	fallback_domain: str,
	timeout: float = 30.0,
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
		server_address = _server_address_from_runtime(
			domain=fallback_domain,
			variables=variables,
		)
		if server_address is not None:
			return server_address
		if loop.time() >= deadline:
			return f"https://{fallback_domain}"
		await asyncio.sleep(poll_interval)


async def _ensure_router_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	internals: RailwayInternals,
	router_image: str,
	router_instance: ServiceInstanceConfig,
) -> tuple[ServiceRecord, str, str]:
	service, _created = await _ensure_service(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=project.service_name,
		image=router_image,
	)
	router_variables = {
		RAILWAY_TOKEN: project.token,
		RAILWAY_PROJECT_ID: project.project_id,
		RAILWAY_ENVIRONMENT_ID: project.environment_id,
		"PULSE_BACKEND_PORT": str(project.backend_port),
		"PORT": str(project.router_port),
	}
	if internals.service_prefix is not None:
		router_variables[PULSE_SERVICE_PREFIX] = internals.service_prefix
	if internals.redis_url:
		router_variables[REDIS_URL] = internals.redis_url
		router_variables[PULSE_REDIS_PREFIX] = project.redis_prefix
		router_variables[PULSE_WEBSOCKET_HEARTBEAT_SECONDS] = str(
			project.websocket_heartbeat_seconds
		)
		router_variables[PULSE_WEBSOCKET_TTL_SECONDS] = str(
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
	router_deployment_id, _status = await _deploy_service_and_wait(
		client,
		service_id=service.id,
		environment_id=project.environment_id,
		error_message="router deployment failed",
	)
	service = await _wait_for_service_by_name(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=project.service_name,
	)
	domain = await _ensure_router_domain(client, project=project, service=service)
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
	service, _created = await _ensure_service(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=service_name,
		image=janitor_image,
	)
	if not internals.redis_url:
		raise DeploymentError("redis_url is required for janitor service creation")
	janitor_variables = {
		RAILWAY_TOKEN: project.token,
		RAILWAY_PROJECT_ID: project.project_id,
		RAILWAY_ENVIRONMENT_ID: project.environment_id,
		PULSE_INTERNAL_TOKEN: internals.internal_token,
		REDIS_URL: internals.redis_url,
		PULSE_REDIS_PREFIX: project.redis_prefix,
		PULSE_JANITOR_DRAIN_GRACE_SECONDS: str(project.drain_grace_seconds),
		PULSE_JANITOR_MAX_DRAIN_AGE_SECONDS: str(project.max_drain_age_seconds),
		PULSE_WEBSOCKET_HEARTBEAT_SECONDS: str(project.websocket_heartbeat_seconds),
		PULSE_WEBSOCKET_TTL_SECONDS: str(project.websocket_ttl_seconds),
	}
	if internals.service_prefix is not None:
		janitor_variables[PULSE_SERVICE_PREFIX] = internals.service_prefix
	for key, value in janitor_variables.items():
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
	deployment_id, _status = await _deploy_service_and_wait(
		client,
		service_id=service.id,
		environment_id=project.environment_id,
		error_message="janitor deployment failed",
	)
	return service, deployment_id


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
	created = False
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
		created = True
	internal_url = await _wait_for_service_variable(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=service.id,
		name="REDIS_URL",
	)
	return ResolvedRedis(
		internal_url=internal_url,
		service=service,
		created=created,
	)


async def resolve_or_create_internal_token(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> tuple[str, bool]:
	variables = await client.get_project_variables(
		project_id=project.project_id,
		environment_id=project.environment_id,
	)
	internal_token = variables.get(PULSE_INTERNAL_TOKEN)
	if internal_token:
		return internal_token, False
	internal_token = secrets.token_urlsafe(32)
	await client.upsert_variable(
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=PULSE_INTERNAL_TOKEN,
		value=internal_token,
		skip_deploys=True,
	)
	return internal_token, True


async def resolve_project_internals(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	redis_url: str | None = None,
) -> RailwayInternals:
	redis_url = redis_url or project.redis_url
	if redis_url is None:
		resolved_redis = await resolve_or_create_redis(client, project=project)
		redis_url = resolved_redis.internal_url
	return RailwayInternals(
		service_prefix=(
			normalize_service_prefix(project.service_prefix)
			if project.service_prefix is not None and project.service_prefix.strip()
			else None
		),
		internal_token=(
			await resolve_or_create_internal_token(client, project=project)
		)[0],
		redis_url=redis_url,
	)


async def _validate_router_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service: ServiceRecord,
	require_redis: bool,
	command: str,
	variables: dict[str, str] | None = None,
) -> str:
	domain = await _ensure_router_domain(client, project=project, service=service)
	if variables is None:
		variables = await client.get_service_variables_for_deployment(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=service.id,
		)
	names = (
		RAILWAY_TOKEN,
		RAILWAY_PROJECT_ID,
		RAILWAY_ENVIRONMENT_ID,
		"PULSE_BACKEND_PORT",
		"PORT",
	)
	if require_redis:
		names = names + (
			REDIS_URL,
			PULSE_REDIS_PREFIX,
			PULSE_WEBSOCKET_HEARTBEAT_SECONDS,
			PULSE_WEBSOCKET_TTL_SECONDS,
		)
	_require_variables(
		service_name=service.name,
		variables=variables,
		names=names,
		command=command,
	)
	server_address = _server_address_from_runtime(domain=domain, variables=variables)
	if server_address is None:
		raise DeploymentError(
			f"could not resolve a public address for {service.name}; "
			+ f"run `pulse-railway {command}`"
		)
	return server_address


async def _validate_janitor_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service: ServiceRecord,
	command: str,
	variables: dict[str, str] | None = None,
) -> None:
	if variables is None:
		variables = await client.get_service_variables_for_deployment(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=service.id,
		)
	_require_variables(
		service_name=service.name,
		variables=variables,
		names=(
			RAILWAY_TOKEN,
			RAILWAY_PROJECT_ID,
			RAILWAY_ENVIRONMENT_ID,
			PULSE_INTERNAL_TOKEN,
			REDIS_URL,
			PULSE_REDIS_PREFIX,
			PULSE_JANITOR_DRAIN_GRACE_SECONDS,
			PULSE_JANITOR_MAX_DRAIN_AGE_SECONDS,
			PULSE_WEBSOCKET_HEARTBEAT_SECONDS,
			PULSE_WEBSOCKET_TTL_SECONDS,
		),
		command=command,
	)


def _stack_service_state(
	service: ServiceRecord, *, domain: str | None = None
) -> StackServiceState:
	return StackServiceState(
		service_id=service.id,
		service_name=service.name,
		image=service.image,
		domain=domain,
	)


async def bootstrap_stack(
	*,
	project: RailwayProject,
	router_instance: ServiceInstanceConfig = DEFAULT_ROUTER_INSTANCE,
) -> InitResult:
	async with RailwayGraphQLClient(token=project.token) as client:
		leftover_service_names = _baseline_leftover_service_names(project)
		leftover_services = await asyncio.gather(
			*[
				client.find_service_by_name(
					project_id=project.project_id,
					environment_id=project.environment_id,
					name=name,
				)
				for name in leftover_service_names.values()
			]
		)
		found_leftovers = [
			service.name for service in leftover_services if service is not None
		]
		if found_leftovers:
			_raise_for_existing_baseline(found_leftovers)

		template_services = await _deploy_baseline_template(client, project=project)
		router_service = template_services["pulse-router"]
		janitor_service = template_services["pulse-janitor"]
		env_service = await _ensure_env_service(
			client,
			project=project,
			router_service=router_service,
		)
		if project.redis_url is not None:
			await _remove_managed_redis_from_baseline(
				client,
				project=project,
				router_service=router_service,
				janitor_service=janitor_service,
				env_service=env_service,
			)
		resolved_redis: ResolvedRedis | None = None
		if project.redis_url is None:
			resolved_redis = await resolve_or_create_redis(client, project=project)
		internal_token, token_created = await resolve_or_create_internal_token(
			client, project=project
		)
		internals = RailwayInternals(
			service_prefix=(
				normalize_service_prefix(project.service_prefix)
				if project.service_prefix is not None and project.service_prefix.strip()
				else None
			),
			internal_token=internal_token,
			redis_url=project.redis_url
			or (resolved_redis.internal_url if resolved_redis is not None else None),
		)

		redis_result = (
			StackServiceResult(
				service_id=resolved_redis.service.id,
				service_name=resolved_redis.service.name,
				image=resolved_redis.service.image,
				created=True,
			)
			if resolved_redis is not None
			else None
		)

		router_image = project.router_image or official_router_image_ref()
		janitor_image = project.janitor_image or official_janitor_image_ref()
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
		router_result = StackServiceResult(
			service_id=router_service.id,
			service_name=router_service.name,
			image=router_image,
			domain=router_domain,
			created=True,
			deployed=True,
			deployment_id=router_deployment_id,
			status="SUCCESS",
		)
		server_address = await _resolve_router_server_address(
			client,
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=router_service.id,
			fallback_domain=router_domain,
		)
		janitor_service, janitor_deployment_id = await _ensure_janitor_service(
			client,
			project=project,
			internals=internals,
			janitor_image=janitor_image,
		)
		janitor_result = StackServiceResult(
			service_id=janitor_service.id,
			service_name=janitor_service.name,
			image=janitor_image,
			created=True,
			deployed=True,
			deployment_id=janitor_deployment_id,
			status="SUCCESS",
		)

		return InitResult(
			router=router_result,
			janitor=janitor_result,
			redis=redis_result,
			internal_token_created=token_created,
			redis_url=internals.redis_url or "",
			server_address=server_address,
		)


async def require_ready_stack(*, project: RailwayProject) -> StackState:
	if project.redis_url is not None:
		raise DeploymentError(
			"`pulse-railway deploy` does not accept an explicit redis url; "
			+ "run `pulse-railway init` to manage baseline infra"
		)
	async with RailwayGraphQLClient(token=project.token) as client:
		router_service = await client.find_service_by_name(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=project.service_name,
		)
		if router_service is None:
			raise DeploymentError(
				f"router service {project.service_name} not found; "
				+ "run `pulse-railway init`"
			)
		janitor_name = project.janitor_service_name or default_janitor_service_name(
			project.service_name
		)
		janitor_service = await client.find_service_by_name(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=janitor_name,
		)
		if janitor_service is None:
			raise DeploymentError(
				f"janitor service {janitor_name} not found; "
				+ "run `pulse-railway init`"
			)
		env_name = default_env_service_name(project.service_name)
		env_service = await client.find_service_by_name(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=env_name,
		)
		if env_service is None:
			raise DeploymentError(
				f"env service {env_name} not found; " + "run `pulse-railway init`"
			)
		project_variables = await client.get_project_variables(
			project_id=project.project_id,
			environment_id=project.environment_id,
		)
		internal_token = project_variables.get(PULSE_INTERNAL_TOKEN)
		if not internal_token:
			raise DeploymentError(
				"project is missing PULSE_RAILWAY_INTERNAL_TOKEN; "
				+ "run `pulse-railway init`"
			)
		router_variables = await client.get_service_variables_for_deployment(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=router_service.id,
		)
		janitor_variables = await client.get_service_variables_for_deployment(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=janitor_service.id,
		)
		server_address = await _validate_router_service(
			client,
			project=project,
			service=router_service,
			require_redis=True,
			command="init",
			variables=router_variables,
		)
		await _validate_janitor_service(
			client,
			project=project,
			service=janitor_service,
			command="init",
			variables=janitor_variables,
		)
		redis_url = _effective_redis_url(
			router_variables=router_variables,
			janitor_variables=janitor_variables,
		)
		redis_name = project.redis_service_name or default_redis_service_name(
			project.service_name
		)
		redis_service = await client.find_service_by_name(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=redis_name,
		)
		return StackState(
			router=_stack_service_state(
				router_service,
				domain=router_service.domains[0].domain
				if router_service.domains
				else None,
			),
			janitor=_stack_service_state(janitor_service),
			redis=(
				_stack_service_state(redis_service)
				if redis_service is not None
				else None
			),
			internal_token=internal_token,
			redis_url=redis_url,
			server_address=server_address,
			env=_stack_service_state(env_service),
		)


__all__ = [
	"JANITOR_START_COMMAND",
	"InitResult",
	"ResolvedRedis",
	"ROUTER_START_COMMAND",
	"StackServiceResult",
	"StackServiceState",
	"StackState",
	"bootstrap_stack",
	"default_env_service_name",
	"default_janitor_service_name",
	"default_redis_service_name",
	"require_ready_stack",
	"resolve_or_create_redis",
	"resolve_project_internals",
]
