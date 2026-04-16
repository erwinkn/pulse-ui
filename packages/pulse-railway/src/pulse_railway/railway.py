from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from pulse_railway.constants import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	DEFAULT_BACKEND_PORT,
	PULSE_DEPLOYMENT_ID,
	RAILWAY_API_ENDPOINT,
)

DEPLOYMENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")
DEFAULT_RAILWAY_GRAPHQL_TIMEOUT = 120.0
DEFAULT_RAILWAY_GRAPHQL_CONNECT_TIMEOUT = 30.0


class RailwayGraphQLError(RuntimeError):
	pass


def validate_deployment_id(deployment_id: str) -> str:
	candidate = deployment_id.strip().lower()
	if not DEPLOYMENT_ID_PATTERN.fullmatch(candidate):
		raise ValueError("deployment id must match ^[a-z0-9][a-z0-9-]{0,23}$")
	return candidate


def normalize_service_prefix(prefix: str) -> str:
	candidate = re.sub(r"[^a-z0-9-]+", "-", prefix.strip().lower())
	candidate = candidate.strip("-")
	if not candidate:
		raise ValueError(
			"service prefix must contain at least one alphanumeric character"
		)
	if not candidate.endswith("-"):
		candidate += "-"
	if len(candidate) > 8:
		raise ValueError(
			"service prefix must be <= 8 characters including trailing '-'"
		)
	return candidate


def normalize_service_name(name: str) -> str:
	candidate = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower())
	candidate = candidate.strip("-")
	if not candidate:
		raise ValueError(
			"service name must contain at least one alphanumeric character"
		)
	if len(candidate) > 32:
		raise ValueError("service name must be <= 32 chars")
	return candidate


def prefixed_service_name(prefix: str, name: str) -> str:
	full_name = f"{normalize_service_prefix(prefix)}{normalize_service_name(name)}"
	if len(full_name) > 32:
		raise ValueError("service name must be <= 32 chars")
	return full_name


def service_name_for_deployment(prefix: str | None, deployment_id: str) -> str:
	deployment_id = validate_deployment_id(deployment_id)
	service_prefix = (
		normalize_service_prefix(prefix)
		if prefix is not None and prefix.strip()
		else ""
	)
	name = f"{service_prefix}{deployment_id}"
	if len(name) > 32:
		raise ValueError("service name must be <= 32 chars")
	return name


@dataclass(slots=True)
class RouteTarget:
	deployment_id: str
	base_url: str


@dataclass(slots=True)
class ServiceDomain:
	id: str
	domain: str
	target_port: int


@dataclass(slots=True)
class ServiceRecord:
	id: str
	name: str
	instance_id: str | None = None
	environment_id: str | None = None
	image: str | None = None
	repo: str | None = None
	domains: list[ServiceDomain] = field(default_factory=list)


@dataclass(slots=True)
class TemplateRecord:
	id: str
	code: str
	serialized_config: dict[str, Any]


@dataclass(slots=True)
class EnvironmentRecord:
	id: str
	name: str


class RailwayGraphQLClient:
	def __init__(
		self,
		*,
		token: str,
		endpoint: str = RAILWAY_API_ENDPOINT,
		timeout: float = DEFAULT_RAILWAY_GRAPHQL_TIMEOUT,
		auth_mode: str = "auto",
	) -> None:
		self.token: str = token
		self.endpoint: str = endpoint
		self.auth_mode: str = auth_mode
		self._resolved_auth_mode: str | None = (
			None if auth_mode == "auto" else auth_mode
		)
		self._client: httpx.AsyncClient = httpx.AsyncClient(
			base_url=endpoint,
			headers={"Content-Type": "application/json"},
			timeout=httpx.Timeout(
				timeout,
				connect=min(timeout, DEFAULT_RAILWAY_GRAPHQL_CONNECT_TIMEOUT),
			),
		)

	async def aclose(self) -> None:
		await self._client.aclose()

	async def __aenter__(self) -> RailwayGraphQLClient:
		return self

	async def __aexit__(self, *_: object) -> None:
		await self.aclose()

	def _headers_for_auth_mode(self, auth_mode: str) -> dict[str, str]:
		if auth_mode == "project-token":
			return {"Project-Access-Token": self.token}
		if auth_mode == "bearer":
			return {"Authorization": f"Bearer {self.token}"}
		raise ValueError(f"unsupported Railway auth mode: {auth_mode}")

	async def _post_graphql(
		self,
		*,
		query: str,
		variables: dict[str, Any] | None = None,
		auth_mode: str,
	) -> dict[str, Any]:
		response = await self._client.post(
			"",
			json={"query": query, "variables": variables or {}},
			headers=self._headers_for_auth_mode(auth_mode),
		)
		response.raise_for_status()
		return response.json()

	async def _ensure_auth_mode(self) -> str:
		if self._resolved_auth_mode is not None:
			return self._resolved_auth_mode
		try:
			payload = await self._post_graphql(
				query="""
				query {
					projectToken {
						projectId
					}
				}
				""",
				auth_mode="project-token",
			)
		except (httpx.HTTPError, ValueError):
			payload = {}
		project_token = (payload.get("data") or {}).get("projectToken")
		self._resolved_auth_mode = (
			"project-token" if isinstance(project_token, dict) else "bearer"
		)
		return self._resolved_auth_mode

	async def graphql(
		self,
		query: str,
		variables: dict[str, Any] | None = None,
		*,
		auth_mode: str | None = None,
	) -> Any:
		selected_auth_mode = auth_mode or await self._ensure_auth_mode()
		payload = await self._post_graphql(
			query=query,
			variables=variables,
			auth_mode=selected_auth_mode,
		)
		errors = payload.get("errors")
		if errors:
			messages: list[str] = []
			error_items = errors if isinstance(errors, list) else [errors]
			for error in error_items:
				if isinstance(error, dict):
					error_fields = cast(dict[str, object], error)
					error_message = error_fields.get("message")
					messages.append(
						error_message
						if isinstance(error_message, str)
						else str(error_fields)
					)
				else:
					messages.append(str(cast(object, error)))
			message = "; ".join(messages)
			raise RailwayGraphQLError(message)
		return payload["data"]

	async def create_project(
		self,
		*,
		name: str,
		workspace_id: str,
		default_environment_name: str | None = None,
	) -> str:
		input_payload: dict[str, Any] = {
			"name": name,
			"workspaceId": workspace_id,
		}
		if default_environment_name is not None:
			input_payload["defaultEnvironmentName"] = default_environment_name
		data = await self.graphql(
			"""
			mutation($input: ProjectCreateInput!) {
				projectCreate(input: $input) {
					id
				}
			}
			""",
			{"input": input_payload},
			auth_mode="bearer",
		)
		return data["projectCreate"]["id"]

	async def list_environments(self, *, project_id: str) -> list[EnvironmentRecord]:
		data = await self.graphql(
			"""
			query($projectId: String!) {
				environments(projectId: $projectId) {
					edges {
						node {
							id
							name
						}
					}
				}
			}
			""",
			{"projectId": project_id},
		)
		return [
			EnvironmentRecord(id=edge["node"]["id"], name=edge["node"]["name"])
			for edge in data["environments"]["edges"]
		]

	async def get_environment_config(
		self, *, project_id: str, environment_id: str
	) -> dict[str, Any]:
		data = await self.graphql(
			"""
			query($projectId: String!, $environmentId: String!) {
				environment(id: $environmentId, projectId: $projectId) {
					config
				}
			}
			""",
			{"projectId": project_id, "environmentId": environment_id},
		)
		return dict(data["environment"]["config"])

	async def set_service_group_id(
		self, *, environment_id: str, service_id: str, group_id: str
	) -> None:
		await self.graphql(
			"""
			mutation($environmentId: String!, $patch: EnvironmentConfig) {
				environmentPatchCommit(
					environmentId: $environmentId,
					patch: $patch,
					commitMessage: "Place service in Railway canvas group"
				)
			}
			""",
			{
				"environmentId": environment_id,
				"patch": {"services": {service_id: {"groupId": group_id}}},
			},
		)

	async def get_project_variables(
		self,
		*,
		project_id: str,
		environment_id: str,
		service_id: str | None = None,
	) -> dict[str, str]:
		data = await self.graphql(
			"""
			query($projectId: String!, $environmentId: String!, $serviceId: String) {
				variables(
					projectId: $projectId,
					environmentId: $environmentId,
					serviceId: $serviceId
				)
			}
			""",
			{
				"projectId": project_id,
				"environmentId": environment_id,
				"serviceId": service_id,
			},
		)
		return dict(data["variables"])

	async def get_service_variables_for_deployment(
		self, *, project_id: str, environment_id: str, service_id: str
	) -> dict[str, str]:
		data = await self.graphql(
			"""
			query($projectId: String!, $environmentId: String!, $serviceId: String!) {
				variablesForServiceDeployment(
					projectId: $projectId,
					environmentId: $environmentId,
					serviceId: $serviceId
				)
			}
			""",
			{
				"projectId": project_id,
				"environmentId": environment_id,
				"serviceId": service_id,
			},
		)
		return dict(data["variablesForServiceDeployment"])

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

	async def delete_variable(
		self,
		*,
		project_id: str,
		environment_id: str,
		name: str,
		service_id: str | None = None,
	) -> None:
		input_payload: dict[str, Any] = {
			"projectId": project_id,
			"environmentId": environment_id,
			"name": name,
		}
		if service_id is not None:
			input_payload["serviceId"] = service_id
		await self.graphql(
			"""
			mutation($input: VariableDeleteInput!) {
				variableDelete(input: $input)
			}
			""",
			{"input": input_payload},
		)

	async def list_services(
		self, *, project_id: str, environment_id: str
	) -> list[ServiceRecord]:
		data = await self.graphql(
			"""
			query($projectId: String!) {
				project(id: $projectId) {
					services {
						edges {
							node {
								id
								name
								serviceInstances {
									edges {
										node {
											id
											environmentId
											source {
												image
												repo
											}
											domains {
												serviceDomains {
													id
													domain
													targetPort
												}
											}
										}
									}
								}
							}
						}
					}
				}
			}
			""",
			{"projectId": project_id},
		)
		services: list[ServiceRecord] = []
		for edge in data["project"]["services"]["edges"]:
			node = edge["node"]
			record = ServiceRecord(id=node["id"], name=node["name"])
			for instance_edge in node["serviceInstances"]["edges"]:
				instance = instance_edge["node"]
				if instance["environmentId"] != environment_id:
					continue
				record.instance_id = instance["id"]
				record.environment_id = instance["environmentId"]
				record.image = (instance.get("source") or {}).get("image")
				record.repo = (instance.get("source") or {}).get("repo")
				record.domains = [
					ServiceDomain(
						id=domain["id"],
						domain=domain["domain"],
						target_port=domain["targetPort"],
					)
					for domain in instance["domains"]["serviceDomains"]
				]
				break
			services.append(record)
		return services

	async def find_service_by_name(
		self, *, project_id: str, environment_id: str, name: str
	) -> ServiceRecord | None:
		for service in await self.list_services(
			project_id=project_id, environment_id=environment_id
		):
			if service.name == name:
				return service
		return None

	async def create_service(
		self,
		*,
		project_id: str,
		environment_id: str,
		name: str,
		image: str | None = None,
	) -> str:
		input_payload: dict[str, Any] = {
			"projectId": project_id,
			"environmentId": environment_id,
			"name": name,
		}
		if image is not None:
			input_payload["source"] = {"image": image}
		data = await self.graphql(
			"""
			mutation($input: ServiceCreateInput!) {
				serviceCreate(input: $input) {
					id
				}
			}
			""",
			{"input": input_payload},
		)
		return data["serviceCreate"]["id"]

	async def get_template_by_code(self, *, code: str) -> TemplateRecord:
		data = await self.graphql(
			"""
			query($code: String!) {
				template(code: $code) {
					id
					code
					serializedConfig
				}
			}
			""",
			{"code": code},
		)
		template = data["template"]
		return TemplateRecord(
			id=template["id"],
			code=template["code"],
			serialized_config=dict(template["serializedConfig"]),
		)

	async def deploy_template(
		self,
		*,
		project_id: str,
		environment_id: str,
		template_id: str,
		serialized_config: dict[str, Any],
	) -> str | None:
		data = await self.graphql(
			"""
			mutation($input: TemplateDeployV2Input!) {
				templateDeployV2(input: $input) {
					workflowId
				}
			}
			""",
			{
				"input": {
					"projectId": project_id,
					"environmentId": environment_id,
					"templateId": template_id,
					"serializedConfig": serialized_config,
				}
			},
		)
		return data["templateDeployV2"]["workflowId"]

	async def update_service_instance(
		self,
		*,
		service_id: str,
		environment_id: str,
		source_image: str | None = None,
		num_replicas: int | None = None,
		healthcheck_path: str | None = None,
		healthcheck_timeout: int | None = None,
		overlap_seconds: int | None = None,
		start_command: str | None = None,
		cron_schedule: str | None = None,
		restart_policy_type: str | None = None,
		restart_policy_max_retries: int | None = None,
	) -> None:
		input_payload: dict[str, Any] = {}
		if source_image is not None:
			input_payload["source"] = {"image": source_image}
		if num_replicas is not None:
			input_payload["numReplicas"] = num_replicas
		if healthcheck_path is not None:
			input_payload["healthcheckPath"] = healthcheck_path
		if healthcheck_timeout is not None:
			input_payload["healthcheckTimeout"] = healthcheck_timeout
		if overlap_seconds is not None:
			input_payload["overlapSeconds"] = overlap_seconds
		if start_command is not None:
			input_payload["startCommand"] = start_command
		if cron_schedule is not None:
			input_payload["cronSchedule"] = cron_schedule
		if restart_policy_type is not None:
			input_payload["restartPolicyType"] = restart_policy_type
		if restart_policy_max_retries is not None:
			input_payload["restartPolicyMaxRetries"] = restart_policy_max_retries
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
					url
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
		timeout: float = 900.0,
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
		service_prefix: str | None,
		backend_port: int = DEFAULT_BACKEND_PORT,
		cache_ttl_seconds: float = 5.0,
	) -> None:
		self.client: RailwayGraphQLClient = client
		self.project_id: str = project_id
		self.environment_id: str = environment_id
		self.service_prefix: str | None = (
			normalize_service_prefix(service_prefix)
			if service_prefix is not None and service_prefix.strip()
			else None
		)
		self.backend_port: int = backend_port
		self.cache_ttl_seconds: float = cache_ttl_seconds
		self._cached_active_deployment_id: str | None = None
		self._active_cached_at: float = 0.0
		self._resolved_active_deployment_id: str | None = None
		self._cached_active_target: RouteTarget | None = None
		self._cached_deployment_service_names: dict[str, str] = {}
		self._cached_at: float = 0.0

	async def _refresh_active_deployment(self) -> str | None:
		if time.monotonic() - self._active_cached_at < self.cache_ttl_seconds:
			return self._cached_active_deployment_id
		variables = await self.client.get_project_variables(
			project_id=self.project_id,
			environment_id=self.environment_id,
		)
		self._cached_active_deployment_id = variables.get(ACTIVE_DEPLOYMENT_VARIABLE)
		self._active_cached_at = time.monotonic()
		return self._cached_active_deployment_id

	async def _refresh_services(self) -> None:
		if time.monotonic() - self._cached_at < self.cache_ttl_seconds:
			return
		services = await self.client.list_services(
			project_id=self.project_id,
			environment_id=self.environment_id,
		)
		variable_sets = await asyncio.gather(
			*[
				self.client.get_service_variables_for_deployment(
					project_id=self.project_id,
					environment_id=self.environment_id,
					service_id=service.id,
				)
				for service in services
			]
		)
		self._cached_deployment_service_names = {
			deployment_id: service.name
			for service, variables in zip(services, variable_sets, strict=True)
			for deployment_id in [variables.get(PULSE_DEPLOYMENT_ID)]
			if deployment_id
		}
		self._cached_at = time.monotonic()

	async def resolve(self, deployment_id: str) -> RouteTarget | None:
		service_name = service_name_for_deployment(self.service_prefix, deployment_id)
		await self._refresh_services()
		if self._cached_deployment_service_names.get(deployment_id) != service_name:
			return None
		return RouteTarget(
			deployment_id=deployment_id,
			base_url=f"http://{service_name}.railway.internal:{self.backend_port}",
		)

	async def resolve_active(self) -> RouteTarget | None:
		deployment_id = await self._refresh_active_deployment()
		if not deployment_id:
			self._resolved_active_deployment_id = None
			self._cached_active_target = None
			return None
		if (
			deployment_id == self._resolved_active_deployment_id
			and self._cached_active_target is not None
		):
			return self._cached_active_target
		target = await self.resolve(deployment_id)
		self._resolved_active_deployment_id = deployment_id
		self._cached_active_target = target
		return target


__all__ = [
	"ACTIVE_DEPLOYMENT_VARIABLE",
	"EnvironmentRecord",
	"RailwayGraphQLClient",
	"RailwayGraphQLError",
	"RailwayResolver",
	"RouteTarget",
	"ServiceRecord",
	"TemplateRecord",
	"normalize_service_prefix",
	"service_name_for_deployment",
	"validate_deployment_id",
]
