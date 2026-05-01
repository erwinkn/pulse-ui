from __future__ import annotations

import asyncio
import secrets

from pulse_railway.config import (
	DEFAULT_ROUTER_INSTANCE,
	RailwayProject,
	ServiceInstanceConfig,
)
from pulse_railway.constants import DEFAULT_PULSE_BASELINE_TEMPLATE_CODE, REDIS_URL
from pulse_railway.errors import DeploymentError
from pulse_railway.images import official_janitor_image_ref, official_router_image_ref
from pulse_railway.railway.client import RailwayGraphQLClient, ServiceRecord
from pulse_railway.railway.ops import (
	create_service_in_router_group,
	wait_for_service_by_name,
	wait_for_service_variable,
)
from pulse_railway.stack.common import (
	BaselineServices,
	StackChange,
	change_for_service,
	configure_runtime,
	ensure_router_domain,
	list_baseline_services,
	raise_for_existing_baseline,
	resolve_router_server_address,
	stack_internals,
)


async def _deploy_baseline_template(
	client: RailwayGraphQLClient, *, project: RailwayProject
) -> BaselineServices:
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
	router_wait = wait_for_service_by_name(
		client,
		project=project,
		name=project.service_name,
	)
	janitor_wait = wait_for_service_by_name(
		client,
		project=project,
		name=project.janitor_service_name,
	)
	if project.redis_service_name is None:
		router, janitor = await asyncio.gather(router_wait, janitor_wait)
		redis = None
	else:
		router, janitor, redis = await asyncio.gather(
			router_wait,
			janitor_wait,
			wait_for_service_by_name(
				client,
				project=project,
				name=project.redis_service_name,
			),
		)
	return BaselineServices(
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
	return await create_service_in_router_group(
		client,
		project=project,
		router_service_id=router.id,
		name=project.env_service_name,
	)


async def _create_stack_with_client(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_instance: ServiceInstanceConfig = DEFAULT_ROUTER_INSTANCE,
) -> StackChange:
	existing = await list_baseline_services(client, project=project)
	if existing.found:
		raise_for_existing_baseline(existing.found)

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
		redis_url = await wait_for_service_variable(
			client,
			project=project,
			service_id=services.redis.id,
			name=REDIS_URL,
		)
	internal_token = secrets.token_urlsafe(32)
	internals = stack_internals(
		project,
		internal_token=internal_token,
		redis_url=redis_url,
	)
	router_deployment_id, janitor_deployment_id = await configure_runtime(
		client,
		project=project,
		router=services.router,
		janitor=services.janitor,
		internals=internals,
		router_instance=router_instance,
	)
	router = await wait_for_service_by_name(
		client,
		project=project,
		name=project.service_name,
	)
	router_domain = await ensure_router_domain(client, project=project, service=router)
	server_address = await resolve_router_server_address(
		client,
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=router.id,
		fallback_domain=router_domain,
	)
	return StackChange(
		router=change_for_service(
			router,
			image=official_router_image_ref(),
			domain=router_domain,
			created=True,
			deployment_id=router_deployment_id,
		),
		janitor=change_for_service(
			services.janitor,
			image=official_janitor_image_ref(),
			created=True,
			deployment_id=janitor_deployment_id,
		),
		redis=(
			change_for_service(services.redis, created=True)
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
