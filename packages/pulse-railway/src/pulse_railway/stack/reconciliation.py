from __future__ import annotations

from pulse_railway.config import (
	DEFAULT_ROUTER_INSTANCE,
	RailwayProject,
	ServiceInstanceConfig,
)
from pulse_railway.images import official_janitor_image_ref, official_router_image_ref
from pulse_railway.railway.client import RailwayGraphQLClient
from pulse_railway.railway.ops import (
	list_deployment_service_records,
	place_services_in_router_group,
)
from pulse_railway.stack.common import (
	StackChange,
	StackServiceChange,
	list_baseline_services,
	reconcile_runtime,
	stack_internals,
)
from pulse_railway.stack.creation import _create_stack_with_client
from pulse_railway.stack.inspection import _inspect_stack_with_client


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
	assert stack.env is not None
	deployments = await list_deployment_service_records(client, project=project)
	group_service_ids = [
		stack.janitor.id,
		stack.env.id,
		*[deployment.service_id for deployment in deployments],
	]
	if stack.redis is not None:
		group_service_ids.append(stack.redis.id)
	await place_services_in_router_group(
		client,
		project=project,
		router_service_id=stack.router.id,
		service_ids=group_service_ids,
	)
	internals = stack_internals(
		project,
		internal_token=stack.internal_token,
		redis_url=stack.redis_url,
	)
	router_deployment_id, janitor_deployment_id = await reconcile_runtime(
		client,
		project=project,
		router=stack.router,
		janitor=stack.janitor,
		internals=internals,
		router_instance=router_instance,
		router_variables=stack.router_variables,
		janitor_variables=stack.janitor_variables,
	)
	return StackChange(
		router=StackServiceChange(
			service_id=stack.router.service_id,
			service_name=stack.router.service_name,
			image=official_router_image_ref(),
			domain=stack.router.domain,
			deployed=router_deployment_id is not None,
			deployment_id=router_deployment_id,
			status="SUCCESS" if router_deployment_id is not None else None,
		),
		janitor=StackServiceChange(
			service_id=stack.janitor.service_id,
			service_name=stack.janitor.service_name,
			image=official_janitor_image_ref(),
			deployed=janitor_deployment_id is not None,
			deployment_id=janitor_deployment_id,
			status="SUCCESS" if janitor_deployment_id is not None else None,
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
		services = await list_baseline_services(client, project=project)
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
