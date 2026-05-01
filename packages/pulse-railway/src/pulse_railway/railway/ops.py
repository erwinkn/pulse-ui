from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypeVar

from pulse_railway.config import RailwayProject
from pulse_railway.constants import (
	PULSE_DEPLOYMENT_ID,
	PULSE_DEPLOYMENT_STATE,
	PULSE_DRAIN_STARTED_AT,
)
from pulse_railway.env import pulse_env_user_references
from pulse_railway.errors import DeploymentError
from pulse_railway.railway.client import (
	EnvironmentRecord,
	ProjectRecord,
	ProjectTokenRecord,
	RailwayGraphQLClient,
	ServiceRecord,
	WorkspaceRecord,
)

DEFAULT_RAILWAY_ENVIRONMENT_NAME = "production"
TERMINAL_DEPLOYMENT_STATUSES = {"SUCCESS", "FAILED", "CRASHED", "REMOVED"}
RailwayNameRecord = TypeVar(
	"RailwayNameRecord",
	ProjectRecord,
	EnvironmentRecord,
	WorkspaceRecord,
)


@dataclass(slots=True)
class DeploymentServiceRecord:
	service_id: str
	service_name: str
	deployment_id: str
	state: str | None = None
	drain_started_at: float | None = None


def _match_record_by_name(
	records: list[RailwayNameRecord],
	*,
	name: str,
	label: str,
) -> RailwayNameRecord:
	matches = [record for record in records if record.name == name]
	if len(matches) == 1:
		return matches[0]
	if not matches:
		available = ", ".join(record.name for record in records) or "none"
		raise ValueError(
			f"Railway {label} not found by name: {name}. Available: {available}"
		)
	raise ValueError(f"multiple Railway {label}s named {name}")


def _reject_name_and_id(
	*,
	name: str | None,
	record_id: str | None,
	label: str,
) -> None:
	if name is not None and record_id is not None:
		raise ValueError(f"use either Railway {label} name or {label} id, not both")


def _parse_optional_float(value: str | None) -> float | None:
	if value is None or not value:
		return None
	return float(value)


async def _resolve_workspace_id(
	client: RailwayGraphQLClient,
	*,
	workspace_name: str | None,
	workspace_id: str | None,
) -> str | None:
	_reject_name_and_id(name=workspace_name, record_id=workspace_id, label="workspace")
	if workspace_id is not None:
		return workspace_id
	if workspace_name is None:
		return None
	workspaces = await client.list_workspaces()
	return _match_record_by_name(
		workspaces,
		name=workspace_name,
		label="workspace",
	).id


async def _resolve_project_id(
	client: RailwayGraphQLClient,
	*,
	project_name: str | None,
	project_id: str | None,
	project_token: ProjectTokenRecord | None,
	workspace_id: str | None,
) -> str:
	_reject_name_and_id(name=project_name, record_id=project_id, label="project")
	if project_id is not None:
		if project_token is not None and project_token.project_id != project_id:
			project = await client.get_project(project_id=project_token.project_id)
			raise ValueError(
				f"project token is scoped to Railway project {project.name}, not {project_id}"
			)
		return project_id
	if project_name is None:
		if project_token is None:
			raise ValueError(
				"Railway project is required unless token is a project token"
			)
		return project_token.project_id
	if project_token is not None:
		project = await client.get_project(project_id=project_token.project_id)
		if project.name != project_name:
			raise ValueError(
				f"project token is scoped to Railway project {project.name}, not {project_name}"
			)
		return project.id
	projects = await client.list_projects(workspace_id=workspace_id)
	return _match_record_by_name(
		projects,
		name=project_name,
		label="project",
	).id


async def _resolve_environment_id(
	client: RailwayGraphQLClient,
	*,
	project_id: str,
	environment_name: str | None,
	environment_id: str | None,
	project_token_environment_id: str | None,
) -> str:
	_reject_name_and_id(
		name=environment_name,
		record_id=environment_id,
		label="environment",
	)
	if environment_id is not None:
		if (
			project_token_environment_id is not None
			and project_token_environment_id != environment_id
		):
			environment = await client.get_environment(
				environment_id=project_token_environment_id
			)
			raise ValueError(
				"project token is scoped to Railway environment "
				+ f"{environment.name}, not {environment_id}"
			)
		return environment_id
	if project_token_environment_id is not None:
		if environment_name is None:
			return project_token_environment_id
		environment = await client.get_environment(
			environment_id=project_token_environment_id
		)
		if environment.name == environment_name:
			return environment.id
		raise ValueError(
			"project token is scoped to Railway environment "
			+ f"{environment.name}, not {environment_name}"
		)
	resolved_environment_name = environment_name or DEFAULT_RAILWAY_ENVIRONMENT_NAME
	environments = await client.list_environments(project_id=project_id)
	return _match_record_by_name(
		environments,
		name=resolved_environment_name,
		label="environment",
	).id


async def resolve_railway_target_ids_with_client(
	client: RailwayGraphQLClient,
	*,
	project_name: str | None = None,
	project_id: str | None = None,
	environment_name: str | None = None,
	environment_id: str | None = None,
	workspace_name: str | None = None,
	workspace_id: str | None = None,
) -> tuple[str, str]:
	project_token = await client.get_project_token()
	resolved_workspace_id = await _resolve_workspace_id(
		client,
		workspace_name=workspace_name,
		workspace_id=workspace_id,
	)
	project_id = await _resolve_project_id(
		client,
		project_name=project_name,
		project_id=project_id,
		project_token=project_token,
		workspace_id=resolved_workspace_id,
	)
	project_token_environment_id = (
		project_token.environment_id
		if project_token is not None and project_token.project_id == project_id
		else None
	)
	environment_id = await _resolve_environment_id(
		client,
		project_id=project_id,
		environment_name=environment_name,
		environment_id=environment_id,
		project_token_environment_id=project_token_environment_id,
	)
	return project_id, environment_id


async def resolve_railway_target_ids(
	*,
	token: str,
	project_name: str | None = None,
	project_id: str | None = None,
	environment_name: str | None = None,
	environment_id: str | None = None,
	workspace_name: str | None = None,
	workspace_id: str | None = None,
) -> tuple[str, str]:
	async with RailwayGraphQLClient(token=token) as client:
		return await resolve_railway_target_ids_with_client(
			client,
			project_name=project_name,
			project_id=project_id,
			environment_name=environment_name,
			environment_id=environment_id,
			workspace_name=workspace_name,
			workspace_id=workspace_id,
		)


async def deploy_service_and_wait(
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


async def wait_for_service_by_name(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	name: str,
	timeout: float = 120.0,
	poll_interval: float = 2.0,
) -> ServiceRecord:
	loop = asyncio.get_running_loop()
	deadline = loop.time() + timeout
	while True:
		service = await client.find_service_by_name(
			project_id=project.project_id,
			environment_id=project.environment_id,
			name=name,
		)
		if service is not None:
			return service
		if loop.time() >= deadline:
			raise TimeoutError(f"service {name} was not created within {timeout:.0f}s")
		await asyncio.sleep(poll_interval)


async def wait_for_service_variable(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service_id: str,
	name: str,
	timeout: float = 180.0,
	poll_interval: float = 2.0,
) -> str:
	loop = asyncio.get_running_loop()
	deadline = loop.time() + timeout
	while True:
		variables = await client.get_service_variables_for_deployment(
			project_id=project.project_id,
			environment_id=project.environment_id,
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


async def wait_for_latest_service_deployment(
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
		if last_seen["status"] in TERMINAL_DEPLOYMENT_STATUSES:
			return last_seen
		await asyncio.sleep(poll_interval)
	raise TimeoutError(
		f"service {service_id} did not produce a terminal deployment in {timeout:.0f}s"
	)


async def require_service_by_name(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	name: str,
	error_message: str | None = None,
) -> ServiceRecord:
	service = await client.find_service_by_name(
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=name,
	)
	if service is None:
		raise DeploymentError(error_message or f"service {name} not found")
	return service


async def raise_if_service_exists(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	name: str,
	error_message: str,
) -> None:
	service = await client.find_service_by_name(
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=name,
	)
	if service is not None:
		raise DeploymentError(error_message)


async def upsert_service_variables(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service_id: str,
	variables: dict[str, str],
) -> None:
	if not service_id:
		raise DeploymentError("service_id is required for Pulse-managed variables")
	await client.upsert_variable_collection(
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=service_id,
		variables=variables,
		skip_deploys=True,
		replace=False,
	)


async def configure_service(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service_id: str,
	variables: dict[str, str],
	**instance_config: Any,
) -> None:
	await upsert_service_variables(
		client,
		project=project,
		service_id=service_id,
		variables=variables,
	)
	await client.update_service_instance(
		service_id=service_id,
		environment_id=project.environment_id,
		**instance_config,
	)


async def configure_service_and_deploy(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	service_id: str,
	variables: dict[str, str],
	error_message: str,
	**instance_config: Any,
) -> tuple[str, str]:
	await configure_service(
		client,
		project=project,
		service_id=service_id,
		variables=variables,
		**instance_config,
	)
	return await deploy_service_and_wait(
		client,
		service_id=service_id,
		environment_id=project.environment_id,
		error_message=error_message,
	)


async def place_service_in_router_group(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_service_id: str,
	service_id: str,
) -> None:
	config: dict[str, Any] = await client.get_environment_config(
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


async def create_service_in_router_group(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	router_service_id: str,
	name: str,
	image: str | None = None,
) -> ServiceRecord:
	service_id = await client.create_service(
		project_id=project.project_id,
		environment_id=project.environment_id,
		name=name,
		image=image,
	)
	await place_service_in_router_group(
		client,
		project=project,
		router_service_id=router_service_id,
		service_id=service_id,
	)
	return ServiceRecord(id=service_id, name=name, image=image)


async def list_services_with_variables(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> list[tuple[ServiceRecord, dict[str, str]]]:
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
	return list(zip(services, variable_sets, strict=True))


async def list_deployment_service_records(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
) -> list[DeploymentServiceRecord]:
	services_with_variables = await list_services_with_variables(
		client,
		project=project,
	)
	deployments: list[DeploymentServiceRecord] = []
	for service, variables in services_with_variables:
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


async def pulse_env_reference_variables(
	client: RailwayGraphQLClient,
	*,
	project: RailwayProject,
	env_service_id: str | None = None,
) -> dict[str, str]:
	env_service_name = project.env_service_name
	if env_service_id is None:
		env_service = await require_service_by_name(
			client,
			project=project,
			name=env_service_name,
			error_message=(
				f"env service {env_service_name} not found; "
				+ "run `pulse-railway scaffold`"
			),
		)
		env_service_id = env_service.id
	variables = await client.get_project_variables(
		project_id=project.project_id,
		environment_id=project.environment_id,
		service_id=env_service_id,
		unrendered=True,
	)
	return pulse_env_user_references(
		env_service_name=env_service_name,
		env_vars=variables,
	)


__all__ = [
	"DEFAULT_RAILWAY_ENVIRONMENT_NAME",
	"DeploymentServiceRecord",
	"configure_service",
	"configure_service_and_deploy",
	"create_service_in_router_group",
	"deploy_service_and_wait",
	"list_deployment_service_records",
	"list_services_with_variables",
	"place_service_in_router_group",
	"pulse_env_reference_variables",
	"raise_if_service_exists",
	"require_service_by_name",
	"resolve_railway_target_ids",
	"resolve_railway_target_ids_with_client",
	"upsert_service_variables",
	"wait_for_latest_service_deployment",
	"wait_for_service_by_name",
	"wait_for_service_variable",
]
