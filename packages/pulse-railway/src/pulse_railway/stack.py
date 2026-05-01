from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import Literal

from pulse_railway.config import (
	DEFAULT_ROUTER_INSTANCE,
	RailwayInternals,
	RailwayProject,
	ServiceInstanceConfig,
	default_env_service_name,
	default_janitor_service_name,
	default_redis_service_name,
)
from pulse_railway.constants import (
	DEFAULT_PULSE_BASELINE_TEMPLATE_CODE,
	PULSE_DRAIN_TTL_SECONDS,
	PULSE_INTERNAL_TOKEN,
	PULSE_REDIS_PREFIX,
	RAILWAY_TOKEN,
	REDIS_URL,
)
from pulse_railway.env import PORT, janitor_env, router_env
from pulse_railway.errors import DeploymentError
from pulse_railway.images import official_janitor_image_ref, official_router_image_ref
from pulse_railway.railway.client import RailwayGraphQLClient, ServiceRecord
from pulse_railway.railway.ops import (
	deploy_service_and_wait,
	place_service_in_router_group,
	upsert_service_variables,
)

ROUTER_START_COMMAND = (
	"sh -c 'uvicorn pulse_railway.router:build_app_from_env --factory "
	'--host 0.0.0.0 --port "${PORT:-8000}"\''
)
JANITOR_START_COMMAND = "sh -c 'pulse-railway janitor run'"


@dataclass(slots=True)
class StackInspection:
	router: ServiceRecord
	janitor: ServiceRecord
	redis: ServiceRecord | None
	internal_token: str
	redis_url: str
	server_address: str
	env: ServiceRecord | None = None
	redis_mode: Literal["managed", "external"] = "managed"


@dataclass(slots=True)
class StackServiceChange:
	service_id: str | None
	service_name: str | None
	image: str | None = None
	domain: str | None = None
	created: bool = False
	deployed: bool = False
	deployment_id: str | None = None
	status: str | None = None


@dataclass(slots=True)
class StackChange:
	router: StackServiceChange
	janitor: StackServiceChange
	redis: StackServiceChange | None
	internal_token_created: bool
	redis_url: str
	server_address: str


@dataclass(slots=True)
class _BaselineServices:
	router: ServiceRecord | None = None
	janitor: ServiceRecord | None = None
	env: ServiceRecord | None = None
	redis: ServiceRecord | None = None

	@property
	def found(self) -> list[ServiceRecord]:
		return [
			service
			for service in (self.router, self.janitor, self.env, self.redis)
			if service is not None
		]


def _change_for_service(
	service: ServiceRecord,
	*,
	image: str | None = None,
	domain: str | None = None,
	created: bool,
	deployment_id: str | None = None,
) -> StackServiceChange:
	return StackServiceChange(
		service_id=service.id,
		service_name=service.name,
		image=image or service.image,
		domain=domain,
		created=created,
		deployed=deployment_id is not None,
		deployment_id=deployment_id,
		status="SUCCESS" if deployment_id is not None else None,
	)


async def _list_baseline_services(
	client: RailwayGraphQLClient, *, project: RailwayProject
) -> _BaselineServices:
	service_by_name = {
		service.name: service
		for service in await client.list_services(
			project_id=project.project_id,
			environment_id=project.environment_id,
		)
	}
	return _BaselineServices(
		router=service_by_name.get(project.service_name),
		janitor=service_by_name.get(project.janitor_service_name),
		env=service_by_name.get(project.env_service_name),
		redis=(
			service_by_name.get(project.redis_service_name)
			if project.redis_service_name is not None
			else None
		),
	)


def _raise_for_existing_baseline(services: list[ServiceRecord]) -> None:
	found_text = ", ".join(sorted({service.name for service in services}))
	raise DeploymentError(
		"baseline stack already exists: "
		+ found_text
		+ ". `pulse-railway scaffold` only creates a fresh baseline. "
		+ "Delete the existing baseline services and rerun `pulse-railway scaffold`."
	)


def _raise_missing_service(name: str, *, command: str) -> None:
	raise DeploymentError(
		f"baseline service {name} not found; run `pulse-railway {command}`"
	)


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


async def _deploy_baseline_template(
	client: RailwayGraphQLClient, *, project: RailwayProject
) -> _BaselineServices:
	template = await client.get_template_by_code(
		code=DEFAULT_PULSE_BASELINE_TEMPLATE_CODE
	)
	config = template.serialized_config
	services = {
		"pulse-router": project.service_name,
		"pulse-janitor": project.janitor_service_name,
	}
	if project.redis_service_name is not None:
		services["pulse-redis"] = project.redis_service_name
	for key, service_config in list(config["services"].items()):
		template_name = service_config.get("name")
		if template_name in services:
			service_config["name"] = services[template_name]
		elif template_name == "pulse-redis":
			del config["services"][key]
	await client.deploy_template(
		project_id=project.project_id,
		environment_id=project.environment_id,
		template_id=template.id,
		serialized_config=config,
	)
	router_wait = _wait_for_service_by_name(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=project.service_name,
	)
	janitor_wait = _wait_for_service_by_name(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=project.janitor_service_name,
	)
	if project.redis_service_name is None:
		router, janitor = await asyncio.gather(router_wait, janitor_wait)
		redis = None
	else:
		router, janitor, redis = await asyncio.gather(
			router_wait,
			janitor_wait,
			_wait_for_service_by_name(
				client,
				project_id=project.project_id,
				environment_id=project.environment_id,
				name=project.redis_service_name,
			),
		)
	return _BaselineServices(
		router=router,
		janitor=janitor,
		redis=redis,
	)


async def _create_env_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router: ServiceRecord,
) -> ServiceRecord:
	await client.create_service(
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=project.env_service_name,
	)
	service = await _wait_for_service_by_name(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=project.env_service_name,
	)
	await place_service_in_router_group(
		client,
		project=project,
		router_service_id=router.id,
		service_id=service.id,
	)
	return service


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


def _stack_internals(
	project: RailwayProject,
	*,
	internal_token: str,
	redis_url: str,
) -> RailwayInternals:
	return RailwayInternals(
		service_prefix=project.service_prefix,
		internal_token=internal_token,
		redis_url=redis_url,
	)


async def _configure_router_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	internals: RailwayInternals,
	service: ServiceRecord,
	router_instance: ServiceInstanceConfig,
) -> str:
	await upsert_service_variables(
		client,
		project=project,
		service_id=service.id,
		variables={
			PULSE_INTERNAL_TOKEN: internals.internal_token,
			**router_env(
				token=project.token,
				router_port=project.router_port,
				service_prefix=internals.service_prefix,
				redis_url=internals.redis_url,
				redis_prefix=project.redis_prefix,
			),
		},
	)
	await client.update_service_instance(
		service_id=service.id,
		environment_id=project.environment_id,
		source_image=official_router_image_ref(),
		num_replicas=project.router_replicas,
		healthcheck_path=router_instance.healthcheck_path,
		healthcheck_timeout=router_instance.healthcheck_timeout,
		overlap_seconds=router_instance.overlap_seconds,
		start_command=ROUTER_START_COMMAND,
	)
	deployment_id, _status = await deploy_service_and_wait(
		client,
		service_id=service.id,
		environment_id=project.environment_id,
		error_message="router deployment failed",
	)
	return deployment_id


async def _configure_janitor_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	internals: RailwayInternals,
	service: ServiceRecord,
) -> str:
	if internals.redis_url is None:
		raise DeploymentError("redis_url is required for janitor service creation")
	await upsert_service_variables(
		client,
		project=project,
		service_id=service.id,
		variables=janitor_env(
			token=project.token,
			internal_token=internals.internal_token,
			redis_url=internals.redis_url,
			redis_prefix=project.redis_prefix,
			service_prefix=internals.service_prefix,
			drain_ttl_seconds=project.drain_ttl_seconds,
		),
	)
	await client.update_service_instance(
		service_id=service.id,
		environment_id=project.environment_id,
		source_image=official_janitor_image_ref(),
		num_replicas=project.janitor_replicas,
		start_command=JANITOR_START_COMMAND,
		cron_schedule=project.janitor_cron_schedule,
		restart_policy_type="NEVER",
	)
	deployment_id, _status = await deploy_service_and_wait(
		client,
		service_id=service.id,
		environment_id=project.environment_id,
		error_message="janitor deployment failed",
	)
	return deployment_id


async def _configure_runtime(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router: ServiceRecord,
	janitor: ServiceRecord,
	internals: RailwayInternals,
	router_instance: ServiceInstanceConfig,
) -> tuple[str, str]:
	router_task = asyncio.create_task(
		_configure_router_service(
			client,
			project=project,
			internals=internals,
			service=router,
			router_instance=router_instance,
		)
	)
	janitor_task = asyncio.create_task(
		_configure_janitor_service(
			client,
			project=project,
			internals=internals,
			service=janitor,
		)
	)
	try:
		return await asyncio.gather(router_task, janitor_task)
	except Exception:
		for task in (router_task, janitor_task):
			if not task.done():
				task.cancel()
		await asyncio.gather(router_task, janitor_task, return_exceptions=True)
		raise


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


async def _inspect_stack_with_client(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	command: str = "ensure",
) -> StackInspection:
	services = await _list_baseline_services(client, project=project)
	if services.router is None:
		_raise_missing_service(project.service_name, command=command)
	if services.janitor is None:
		_raise_missing_service(project.janitor_service_name, command=command)
	if services.env is None:
		_raise_missing_service(project.env_service_name, command=command)
	if project.redis_service_name is not None and services.redis is None:
		_raise_missing_service(project.redis_service_name, command=command)

	assert services.router is not None
	assert services.janitor is not None
	assert services.env is not None
	router_variables, janitor_variables = await asyncio.gather(
		client.get_service_variables_for_deployment(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=services.router.id,
		),
		client.get_service_variables_for_deployment(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=services.janitor.id,
		),
	)
	_require_variables(
		service_name=services.router.name,
		variables=router_variables,
		names=(
			RAILWAY_TOKEN,
			PORT,
			PULSE_INTERNAL_TOKEN,
			REDIS_URL,
			PULSE_REDIS_PREFIX,
		),
		command=command,
	)
	_require_variables(
		service_name=services.janitor.name,
		variables=janitor_variables,
		names=(
			RAILWAY_TOKEN,
			PULSE_INTERNAL_TOKEN,
			REDIS_URL,
			PULSE_REDIS_PREFIX,
			PULSE_DRAIN_TTL_SECONDS,
		),
		command=command,
	)
	internal_token = router_variables[PULSE_INTERNAL_TOKEN]
	if janitor_variables[PULSE_INTERNAL_TOKEN] != internal_token:
		raise DeploymentError(
			"router and janitor PULSE_RAILWAY_INTERNAL_TOKEN values differ; "
			+ f"run `pulse-railway {command}`"
		)
	redis_url = router_variables[REDIS_URL]
	if janitor_variables[REDIS_URL] != redis_url:
		raise DeploymentError(
			"router and janitor REDIS_URL values differ; "
			+ f"run `pulse-railway {command}`"
		)
	if project.redis_url is not None and project.redis_url != redis_url:
		raise DeploymentError(
			"baseline REDIS_URL differs from --redis-url; delete the baseline and "
			+ "rerun `pulse-railway scaffold` to change Redis mode"
		)
	domain = services.router.domains[0].domain if services.router.domains else None
	server_address = _server_address_from_runtime(
		domain=domain,
		variables=router_variables,
	)
	if server_address is None:
		raise DeploymentError(
			f"could not resolve a public address for {services.router.name}; "
			+ f"run `pulse-railway {command}`"
		)
	redis_service = services.redis
	redis_mode: Literal["managed", "external"] = (
		"managed" if redis_service is not None else "external"
	)
	return StackInspection(
		router=services.router,
		janitor=services.janitor,
		env=services.env,
		redis=redis_service,
		redis_mode=redis_mode,
		internal_token=internal_token,
		redis_url=redis_url,
		server_address=server_address,
	)


async def inspect_stack(*, project: RailwayProject) -> StackInspection:
	async with RailwayGraphQLClient(token=project.token) as client:
		return await _inspect_stack_with_client(
			client,
			project=project,
			command="scaffold",
		)


async def _create_stack_with_client(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_instance: ServiceInstanceConfig = DEFAULT_ROUTER_INSTANCE,
) -> StackChange:
	existing = await _list_baseline_services(client, project=project)
	if existing.found:
		_raise_for_existing_baseline(existing.found)

	services = await _deploy_baseline_template(client, project=project)
	if services.router is None or services.janitor is None:
		raise DeploymentError("baseline template did not create router and janitor")
	services.env = await _create_env_service(
		client,
		project=project,
		router=services.router,
	)

	redis_url = project.redis_url
	if redis_url is None:
		if services.redis is None:
			raise DeploymentError("baseline template did not create managed Redis")
		redis_url = await _wait_for_service_variable(
			client,
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=services.redis.id,
			name=REDIS_URL,
		)
	internal_token = secrets.token_urlsafe(32)
	internals = _stack_internals(
		project,
		internal_token=internal_token,
		redis_url=redis_url,
	)
	router_deployment_id, janitor_deployment_id = await _configure_runtime(
		client,
		project=project,
		router=services.router,
		janitor=services.janitor,
		internals=internals,
		router_instance=router_instance,
	)
	router = await _wait_for_service_by_name(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=project.service_name,
	)
	router_domain = await _ensure_router_domain(client, project=project, service=router)
	server_address = await _resolve_router_server_address(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=router.id,
		fallback_domain=router_domain,
	)
	return StackChange(
		router=_change_for_service(
			router,
			image=official_router_image_ref(),
			domain=router_domain,
			created=True,
			deployment_id=router_deployment_id,
		),
		janitor=_change_for_service(
			services.janitor,
			image=official_janitor_image_ref(),
			created=True,
			deployment_id=janitor_deployment_id,
		),
		redis=(
			_change_for_service(services.redis, created=True)
			if services.redis is not None
			else None
		),
		internal_token_created=True,
		redis_url=redis_url,
		server_address=server_address,
	)


async def create_stack(
	*,
	project: RailwayProject,
	router_instance: ServiceInstanceConfig = DEFAULT_ROUTER_INSTANCE,
) -> StackChange:
	async with RailwayGraphQLClient(token=project.token) as client:
		return await _create_stack_with_client(
			client,
			project=project,
			router_instance=router_instance,
		)


async def _reconcile_stack_with_client(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_instance: ServiceInstanceConfig = DEFAULT_ROUTER_INSTANCE,
) -> StackChange:
	stack = await _inspect_stack_with_client(
		client,
		project=project,
		command="ensure",
	)
	internals = _stack_internals(
		project,
		internal_token=stack.internal_token,
		redis_url=stack.redis_url,
	)
	router_deployment_id, janitor_deployment_id = await _configure_runtime(
		client,
		project=project,
		router=stack.router,
		janitor=stack.janitor,
		internals=internals,
		router_instance=router_instance,
	)
	return StackChange(
		router=StackServiceChange(
			service_id=stack.router.service_id,
			service_name=stack.router.service_name,
			image=official_router_image_ref(),
			domain=stack.router.domain,
			deployed=True,
			deployment_id=router_deployment_id,
			status="SUCCESS",
		),
		janitor=StackServiceChange(
			service_id=stack.janitor.service_id,
			service_name=stack.janitor.service_name,
			image=official_janitor_image_ref(),
			deployed=True,
			deployment_id=janitor_deployment_id,
			status="SUCCESS",
		),
		redis=(
			StackServiceChange(
				service_id=stack.redis.service_id,
				service_name=stack.redis.service_name,
				image=stack.redis.image,
			)
			if stack.redis is not None
			else None
		),
		internal_token_created=False,
		redis_url=stack.redis_url,
		server_address=stack.server_address,
	)


async def reconcile_stack(
	*,
	project: RailwayProject,
	router_instance: ServiceInstanceConfig = DEFAULT_ROUTER_INSTANCE,
) -> StackChange:
	async with RailwayGraphQLClient(token=project.token) as client:
		return await _reconcile_stack_with_client(
			client,
			project=project,
			router_instance=router_instance,
		)


async def create_or_reconcile_stack(
	*,
	project: RailwayProject,
	router_instance: ServiceInstanceConfig = DEFAULT_ROUTER_INSTANCE,
) -> StackChange:
	async with RailwayGraphQLClient(token=project.token) as client:
		services = await _list_baseline_services(client, project=project)
		if not services.found:
			return await _create_stack_with_client(
				client,
				project=project,
				router_instance=router_instance,
			)
		return await _reconcile_stack_with_client(
			client,
			project=project,
			router_instance=router_instance,
		)


__all__ = [
	"JANITOR_START_COMMAND",
	"ROUTER_START_COMMAND",
	"StackChange",
	"StackInspection",
	"StackServiceChange",
	"create_or_reconcile_stack",
	"create_stack",
	"default_env_service_name",
	"default_janitor_service_name",
	"default_redis_service_name",
	"inspect_stack",
	"reconcile_stack",
]
