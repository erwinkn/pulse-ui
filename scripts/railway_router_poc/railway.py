from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

AFFINITY_QUERY_PARAM = "pulse_deployment"
AFFINITY_HEADER = "x-pulse-deployment"
ACTIVE_DEPLOYMENT_VARIABLE = "PULSE_ACTIVE_DEPLOYMENT"
DEPLOYMENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")


class RailwayGraphQLError(RuntimeError):
	pass


def validate_deployment_id(deployment_id: str) -> str:
	candidate = deployment_id.strip().lower()
	if not DEPLOYMENT_ID_PATTERN.fullmatch(candidate):
		raise ValueError("deployment id must match ^[a-z0-9][a-z0-9-]{0,23}$")
	return candidate


def service_name_for_deployment(prefix: str, deployment_id: str) -> str:
	deployment_id = validate_deployment_id(deployment_id)
	name = f"{prefix}{deployment_id}"
	if len(name) > 32:
		raise ValueError("service name must be <= 32 chars")
	return name


@dataclass(slots=True)
class RouteTarget:
	deployment_id: str
	base_url: str


class RailwayGraphQLClient:
	def __init__(
		self,
		*,
		token: str,
		endpoint: str = "https://backboard.railway.com/graphql/v2",
		timeout: float = 30.0,
	) -> None:
		self.endpoint = endpoint
		self._client = httpx.AsyncClient(
			base_url=endpoint,
			headers={
				"Content-Type": "application/json",
				"Project-Access-Token": token,
			},
			timeout=timeout,
		)

	async def aclose(self) -> None:
		await self._client.aclose()

	async def __aenter__(self) -> RailwayGraphQLClient:
		return self

	async def __aexit__(self, *_: object) -> None:
		await self.aclose()

	async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> Any:
		response = await self._client.post(
			"",
			json={"query": query, "variables": variables or {}},
		)
		response.raise_for_status()
		payload = response.json()
		errors = payload.get("errors") or []
		if errors:
			message = "; ".join(error["message"] for error in errors)
			raise RailwayGraphQLError(message)
		return payload["data"]

	async def get_project_variables(
		self, *, project_id: str, environment_id: str
	) -> dict[str, str]:
		data = await self.graphql(
			"""
			query($projectId: String!, $environmentId: String!) {
				variables(projectId: $projectId, environmentId: $environmentId)
			}
			""",
			{"projectId": project_id, "environmentId": environment_id},
		)
		return dict(data["variables"])

	async def upsert_variable(
		self,
		*,
		project_id: str,
		environment_id: str,
		name: str,
		value: str,
		service_id: str | None = None,
		skip_deploys: bool = True,
	) -> None:
		await self.graphql(
			"""
			mutation($input: VariableUpsertInput!) {
				variableUpsert(input: $input)
			}
			""",
			{
				"input": {
					"projectId": project_id,
					"environmentId": environment_id,
					"serviceId": service_id,
					"name": name,
					"value": value,
					"skipDeploys": skip_deploys,
				}
			},
		)

	async def list_services(self, *, project_id: str) -> list[dict[str, str]]:
		data = await self.graphql(
			"""
			query($id: String!) {
				project(id: $id) {
					services {
						edges {
							node {
								id
								name
							}
						}
					}
				}
			}
			""",
			{"id": project_id},
		)
		edges = data["project"]["services"]["edges"]
		return [edge["node"] for edge in edges]

	async def create_service(
		self,
		*,
		project_id: str,
		environment_id: str,
		name: str,
		image: str,
	) -> str:
		data = await self.graphql(
			"""
			mutation($input: ServiceCreateInput!) {
				serviceCreate(input: $input) {
					id
				}
			}
			""",
			{
				"input": {
					"projectId": project_id,
					"environmentId": environment_id,
					"name": name,
					"source": {"image": image},
				}
			},
		)
		return data["serviceCreate"]["id"]

	async def update_service_instance(
		self,
		*,
		service_id: str,
		environment_id: str,
		num_replicas: int | None = None,
	) -> None:
		input_payload: dict[str, Any] = {}
		if num_replicas is not None:
			input_payload["numReplicas"] = num_replicas
		if not input_payload:
			return
		await self.graphql(
			"""
			mutation(
				$serviceId: String!,
				$environmentId: String!,
				$input: ServiceInstanceUpdateInput!
			) {
				serviceInstanceUpdate(
					serviceId: $serviceId,
					environmentId: $environmentId,
					input: $input
				)
			}
			""",
			{
				"serviceId": service_id,
				"environmentId": environment_id,
				"input": input_payload,
			},
		)

	async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
		data = await self.graphql(
			"""
			mutation($serviceId: String!, $environmentId: String!) {
				serviceInstanceDeployV2(
					serviceId: $serviceId,
					environmentId: $environmentId
				)
			}
			""",
			{"serviceId": service_id, "environmentId": environment_id},
		)
		return data["serviceInstanceDeployV2"]

	async def get_deployment(self, *, deployment_id: str) -> dict[str, Any]:
		data = await self.graphql(
			"""
			query($id: String!) {
				deployment(id: $id) {
					id
					status
					createdAt
					staticUrl
				}
			}
			""",
			{"id": deployment_id},
		)
		return data["deployment"]

	async def wait_for_deployment(
		self,
		*,
		deployment_id: str,
		timeout: float = 300.0,
		poll_interval: float = 2.0,
	) -> dict[str, Any]:
		deadline = time.monotonic() + timeout
		last_seen: dict[str, Any] | None = None
		while time.monotonic() < deadline:
			last_seen = await self.get_deployment(deployment_id=deployment_id)
			status = last_seen["status"]
			if status in {"SUCCESS", "FAILED", "CRASHED", "REMOVED"}:
				return last_seen
			await asyncio.sleep(poll_interval)
		raise TimeoutError(
			f"deployment {deployment_id} did not complete in {timeout:.0f}s"
		)

	async def create_service_domain(
		self,
		*,
		service_id: str,
		environment_id: str,
		target_port: int,
	) -> str:
		data = await self.graphql(
			"""
			mutation(
				$serviceId: String!,
				$environmentId: String!,
				$targetPort: Int!
			) {
				serviceDomainCreate(
					input: {
						serviceId: $serviceId,
						environmentId: $environmentId,
						targetPort: $targetPort
					}
				) {
					domain
				}
			}
			""",
			{
				"serviceId": service_id,
				"environmentId": environment_id,
				"targetPort": target_port,
			},
		)
		return data["serviceDomainCreate"]["domain"]

	async def delete_service(self, *, service_id: str, environment_id: str) -> None:
		await self.graphql(
			"""
			mutation($id: String!, $environmentId: String!) {
				serviceDelete(id: $id, environmentId: $environmentId)
			}
			""",
			{"id": service_id, "environmentId": environment_id},
		)


class RailwayResolver:
	def __init__(
		self,
		*,
		client: RailwayGraphQLClient,
		project_id: str,
		environment_id: str,
		service_prefix: str,
		backend_port: int,
		cache_ttl_seconds: float = 5.0,
	) -> None:
		self.client = client
		self.project_id = project_id
		self.environment_id = environment_id
		self.service_prefix = service_prefix
		self.backend_port = backend_port
		self.cache_ttl_seconds = cache_ttl_seconds
		self._cached_service_names: set[str] = set()
		self._cached_at = 0.0

	async def _refresh_services(self) -> None:
		if time.monotonic() - self._cached_at < self.cache_ttl_seconds:
			return
		services = await self.client.list_services(project_id=self.project_id)
		self._cached_service_names = {service["name"] for service in services}
		self._cached_at = time.monotonic()

	async def resolve(self, deployment_id: str) -> RouteTarget | None:
		service_name = service_name_for_deployment(self.service_prefix, deployment_id)
		await self._refresh_services()
		if service_name not in self._cached_service_names:
			return None
		return RouteTarget(
			deployment_id=deployment_id,
			base_url=f"http://{service_name}.railway.internal:{self.backend_port}",
		)

	async def resolve_active(self) -> RouteTarget | None:
		variables = await self.client.get_project_variables(
			project_id=self.project_id,
			environment_id=self.environment_id,
		)
		deployment_id = variables.get(ACTIVE_DEPLOYMENT_VARIABLE)
		if not deployment_id:
			return None
		return await self.resolve(deployment_id)
