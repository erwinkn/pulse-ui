from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from pulse_railway.config import (
	RailwayInternals,
	RailwayProject,
	ServiceInstanceConfig,
)
from pulse_railway.constants import PULSE_INTERNAL_TOKEN
from pulse_railway.env import janitor_env, router_env
from pulse_railway.errors import DeploymentError
from pulse_railway.images import official_janitor_image_ref, official_router_image_ref
from pulse_railway.railway.client import RailwayGraphQLClient, ServiceRecord
from pulse_railway.railway.ops import (
	configure_service_and_deploy,
	deploy_service_and_wait,
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
	router_variables: dict[str, str] = field(default_factory=dict)
	janitor_variables: dict[str, str] = field(default_factory=dict)
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
class BaselineServices:
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


def change_for_service(
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


async def list_baseline_services(
	client: RailwayGraphQLClient, *, project: RailwayProject
) -> BaselineServices:
	service_by_name = {
		service.name: service
		for service in await client.list_services(
			project_id=project.project_id,
			environment_id=project.environment_id,
		)
	}
	return BaselineServices(
		router=service_by_name.get(project.service_name),
		janitor=service_by_name.get(project.janitor_service_name),
		env=service_by_name.get(project.env_service_name),
		redis=(
			service_by_name.get(project.redis_service_name)
			if project.redis_service_name is not None
			else None
		),
	)


def raise_for_existing_baseline(services: list[ServiceRecord]) -> None:
	found_text = ", ".join(sorted({service.name for service in services}))
	raise DeploymentError(
		"baseline stack already exists: "
		+ found_text
		+ ". `pulse-railway scaffold` only creates a fresh baseline. "
		+ "Delete the existing baseline services and rerun `pulse-railway scaffold`."
	)


def raise_missing_service(name: str, *, command: str) -> None:
	raise DeploymentError(
		f"baseline service {name} not found; run `pulse-railway {command}`"
	)


async def ensure_router_domain(
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


def server_address_from_runtime(
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


async def resolve_router_server_address(
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
		server_address = server_address_from_runtime(
			domain=fallback_domain,
			variables=variables,
		)
		if server_address is not None:
			return server_address
		if loop.time() >= deadline:
			return f"https://{fallback_domain}"
		await asyncio.sleep(poll_interval)


def stack_internals(
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


async def configure_router_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	internals: RailwayInternals,
	service: ServiceRecord,
	router_instance: ServiceInstanceConfig,
) -> str:
	deployment_id, _status = await configure_service_and_deploy(
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
		error_message="router deployment failed",
		source_image=official_router_image_ref(),
		num_replicas=project.router_replicas,
		healthcheck_path=router_instance.healthcheck_path,
		healthcheck_timeout=router_instance.healthcheck_timeout,
		overlap_seconds=router_instance.overlap_seconds,
		start_command=ROUTER_START_COMMAND,
	)
	return deployment_id


def _service_variables_changed(
	current_variables: dict[str, str],
	desired_variables: dict[str, str],
) -> bool:
	return any(
		current_variables.get(name) != value
		for name, value in desired_variables.items()
	)


def _service_instance_changed(
	service: ServiceRecord,
	*,
	source_image: str | None = None,
	num_replicas: int | None = None,
	healthcheck_path: str | None = None,
	healthcheck_timeout: int | None = None,
	overlap_seconds: int | None = None,
	start_command: str | None = None,
	cron_schedule: str | None = None,
	restart_policy_type: str | None = None,
	restart_policy_max_retries: int | None = None,
) -> bool:
	expected = {
		"image": source_image,
		"num_replicas": num_replicas,
		"healthcheck_path": healthcheck_path,
		"healthcheck_timeout": healthcheck_timeout,
		"overlap_seconds": overlap_seconds,
		"start_command": start_command,
		"cron_schedule": cron_schedule,
		"restart_policy_type": restart_policy_type,
		"restart_policy_max_retries": restart_policy_max_retries,
	}
	return any(
		value is not None and getattr(service, name) != value
		for name, value in expected.items()
	)


async def configure_service_if_changed(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service: ServiceRecord,
	current_variables: dict[str, str],
	desired_variables: dict[str, str],
	error_message: str,
	**instance_config: Any,
) -> str | None:
	variables_changed = _service_variables_changed(
		current_variables,
		desired_variables,
	)
	instance_changed = _service_instance_changed(service, **instance_config)
	if not variables_changed and not instance_changed:
		return None
	if variables_changed:
		await client.upsert_variable_collection(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=service.id,
			variables=desired_variables,
			skip_deploys=True,
			replace=False,
		)
	if instance_changed:
		await client.update_service_instance(
			service_id=service.id,
			environment_id=project.environment_id,
			**instance_config,
		)
	deployment_id, _status = await deploy_service_and_wait(
		client,
		service_id=service.id,
		environment_id=project.environment_id,
		error_message=error_message,
	)
	return deployment_id


async def configure_janitor_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	internals: RailwayInternals,
	service: ServiceRecord,
) -> str:
	if internals.redis_url is None:
		raise DeploymentError("redis_url is required for janitor service creation")
	deployment_id, _status = await configure_service_and_deploy(
		client,
		project=project,
		service_id=service.id,
		variables=janitor_env(
			token=project.token,
			internal_token=internals.internal_token,
			redis_url=internals.redis_url,
			redis_prefix=project.redis_prefix,
			router_service_name=project.service_name,
			janitor_service_name=project.janitor_service_name,
			redis_service_name=project.redis_service_name,
			service_prefix=internals.service_prefix,
			drain_ttl_seconds=project.drain_ttl_seconds,
		),
		error_message="janitor deployment failed",
		source_image=official_janitor_image_ref(),
		num_replicas=project.janitor_replicas,
		start_command=JANITOR_START_COMMAND,
		cron_schedule=project.janitor_cron_schedule,
		restart_policy_type="NEVER",
	)
	return deployment_id


async def configure_runtime(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router: ServiceRecord,
	janitor: ServiceRecord,
	internals: RailwayInternals,
	router_instance: ServiceInstanceConfig,
) -> tuple[str, str]:
	router_task = asyncio.create_task(
		configure_router_service(
			client,
			project=project,
			internals=internals,
			service=router,
			router_instance=router_instance,
		)
	)
	janitor_task = asyncio.create_task(
		configure_janitor_service(
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


async def reconcile_runtime(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router: ServiceRecord,
	janitor: ServiceRecord,
	internals: RailwayInternals,
	router_instance: ServiceInstanceConfig,
	router_variables: dict[str, str],
	janitor_variables: dict[str, str],
) -> tuple[str | None, str | None]:
	if internals.redis_url is None:
		raise DeploymentError("redis_url is required for janitor service creation")
	router_task = asyncio.create_task(
		configure_service_if_changed(
			client,
			project=project,
			service=router,
			current_variables=router_variables,
			desired_variables={
				PULSE_INTERNAL_TOKEN: internals.internal_token,
				**router_env(
					token=project.token,
					router_port=project.router_port,
					service_prefix=internals.service_prefix,
					redis_url=internals.redis_url,
					redis_prefix=project.redis_prefix,
				),
			},
			error_message="router deployment failed",
			source_image=official_router_image_ref(),
			num_replicas=project.router_replicas,
			healthcheck_path=router_instance.healthcheck_path,
			healthcheck_timeout=router_instance.healthcheck_timeout,
			overlap_seconds=router_instance.overlap_seconds,
			start_command=ROUTER_START_COMMAND,
		)
	)
	janitor_task = asyncio.create_task(
		configure_service_if_changed(
			client,
			project=project,
			service=janitor,
			current_variables=janitor_variables,
			desired_variables=janitor_env(
				token=project.token,
				internal_token=internals.internal_token,
				redis_url=internals.redis_url,
				redis_prefix=project.redis_prefix,
				router_service_name=project.service_name,
				janitor_service_name=project.janitor_service_name,
				redis_service_name=project.redis_service_name,
				service_prefix=internals.service_prefix,
				drain_ttl_seconds=project.drain_ttl_seconds,
			),
			error_message="janitor deployment failed",
			source_image=official_janitor_image_ref(),
			num_replicas=project.janitor_replicas,
			start_command=JANITOR_START_COMMAND,
			cron_schedule=project.janitor_cron_schedule,
			restart_policy_type="NEVER",
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
