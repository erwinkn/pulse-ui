from __future__ import annotations

import asyncio
from typing import Literal

from pulse_railway.config import RailwayProject
from pulse_railway.constants import (
	PULSE_DRAIN_TTL_SECONDS,
	PULSE_INTERNAL_TOKEN,
	PULSE_REDIS_PREFIX,
	RAILWAY_TOKEN,
	REDIS_URL,
)
from pulse_railway.env import PORT
from pulse_railway.errors import DeploymentError
from pulse_railway.railway.client import RailwayGraphQLClient
from pulse_railway.stack.common import (
	CLI_RUNTIME_TOKEN_ERROR,
	StackInspection,
	list_baseline_services,
	public_origin_from_runtime,
	raise_missing_service,
)


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


async def inspect_stack_with_client(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	command: str = "ensure",
) -> StackInspection:
	services = await list_baseline_services(client, project=project)
	if services.router is None:
		raise_missing_service(project.service_name, command=command)
	if services.janitor is None:
		raise_missing_service(project.janitor_service_name, command=command)
	if services.env is None:
		raise_missing_service(project.env_service_name, command=command)
	if project.redis_service_name is not None and services.redis is None:
		raise_missing_service(project.redis_service_name, command=command)

	assert services.router is not None
	assert services.janitor is not None
	assert services.env is not None
	(
		router_variables,
		janitor_variables,
		router_config_variables,
		janitor_config_variables,
	) = await asyncio.gather(
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
		client.get_project_variables(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=services.router.id,
			unrendered=True,
		),
		client.get_project_variables(
			project_id=project.project_id,
			environment_id=project.environment_id,
			service_id=services.janitor.id,
			unrendered=True,
		),
	)
	if project.token_source == "cli" and (
		not router_variables.get(RAILWAY_TOKEN)
		or not janitor_variables.get(RAILWAY_TOKEN)
	):
		raise DeploymentError(CLI_RUNTIME_TOKEN_ERROR)
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
	public_origin = public_origin_from_runtime(
		domain=domain,
		variables=router_variables,
	)
	if public_origin is None:
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
		public_origin=public_origin,
		router_variables=router_variables,
		janitor_variables=janitor_variables,
		router_config_variables=router_config_variables or router_variables,
		janitor_config_variables=janitor_config_variables or janitor_variables,
	)


async def inspect_stack(*, project: RailwayProject) -> StackInspection:
	async with RailwayGraphQLClient(token=project.token) as client:
		return await inspect_stack_with_client(
			client,
			project=project,
			command="scaffold",
		)
