from __future__ import annotations

from typing import Any

from pulse_railway.config import RailwayProject
from pulse_railway.errors import DeploymentError
from pulse_railway.railway.client import RailwayGraphQLClient


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


__all__ = [
	"deploy_service_and_wait",
	"place_service_in_router_group",
	"upsert_service_variables",
]
