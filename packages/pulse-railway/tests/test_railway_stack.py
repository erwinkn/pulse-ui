from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from pulse_railway.config import RailwayProject
from pulse_railway.constants import (
	DEFAULT_PULSE_BASELINE_TEMPLATE_CODE,
	PULSE_DEPLOYMENT_ID,
	PULSE_DRAIN_TTL_SECONDS,
	PULSE_INTERNAL_TOKEN,
	PULSE_RAILWAY_JANITOR_SERVICE,
	PULSE_RAILWAY_REDIS_SERVICE,
	PULSE_RAILWAY_SERVICE,
	PULSE_REDIS_PREFIX,
	RAILWAY_TOKEN,
	REDIS_URL,
)
from pulse_railway.errors import DeploymentError
from pulse_railway.images import official_janitor_image_ref, official_router_image_ref
from pulse_railway.railway import ServiceDomain, ServiceRecord, TemplateRecord
from pulse_railway.railway.ops import upsert_service_variables
from pulse_railway.stack import (
	JANITOR_START_COMMAND,
	ROUTER_START_COMMAND,
	create_or_reconcile_stack,
	create_stack,
	inspect_stack,
	reconcile_stack,
)


@dataclass
class RailwayHarness:
	services: dict[str, ServiceRecord] = field(default_factory=dict)
	variables: dict[str, dict[str, str]] = field(default_factory=dict)
	unrendered_variables: dict[str, dict[str, str]] = field(default_factory=dict)
	updates: list[dict[str, Any]] = field(default_factory=list)
	deployed_templates: list[str] = field(default_factory=list)
	deleted_services: list[str] = field(default_factory=list)
	deleted_variables: list[tuple[str, str]] = field(default_factory=list)
	variable_collections: list[tuple[str, dict[str, str]]] = field(default_factory=list)
	created_services: list[str] = field(default_factory=list)
	deployed_services: list[str] = field(default_factory=list)
	group_assignments: list[tuple[str, str]] = field(default_factory=list)
	service_groups: dict[str, str] = field(default_factory=dict)
	domain_creations: list[str] = field(default_factory=list)
	environment_config_reads: int = 0
	router_group_available_after_config_reads: int = 0
	router_group_id: str | None = "group-baseline"
	service_counter: int = 0
	public_domain: str = "test.pulse.sc"

	def add_service(
		self,
		name: str,
		*,
		service_id: str | None = None,
		image: str | None = None,
		domain: str | None = None,
		group_id: str | None = None,
		variables: dict[str, str] | None = None,
		unrendered_variables: dict[str, str] | None = None,
		num_replicas: int | None = None,
		healthcheck_path: str | None = None,
		healthcheck_timeout: int | None = None,
		overlap_seconds: int | None = None,
		start_command: str | None = None,
		cron_schedule: str | None = None,
		restart_policy_type: str | None = None,
	) -> ServiceRecord:
		if service_id is None:
			self.service_counter += 1
			service_id = f"svc-{self.service_counter}"
		service = ServiceRecord(
			id=service_id,
			name=name,
			image=image,
			num_replicas=num_replicas,
			healthcheck_path=healthcheck_path,
			healthcheck_timeout=healthcheck_timeout,
			overlap_seconds=overlap_seconds,
			start_command=start_command,
			cron_schedule=cron_schedule,
			restart_policy_type=restart_policy_type,
		)
		if domain is not None:
			service.domains = [
				ServiceDomain(
					id=f"domain-{service_id}", domain=domain, target_port=8000
				)
			]
		self.services[name] = service
		self.variables[service_id] = dict(variables or {})
		self.unrendered_variables[service_id] = dict(unrendered_variables or {})
		if group_id is not None:
			self.service_groups[service_id] = group_id
		return service


def _project(**overrides: Any) -> RailwayProject:
	values = {
		"project_id": "project",
		"environment_id": "env",
		"token": "token",
		"service_name": "pulse-router",
		"janitor_service_name": "pulse-janitor",
		"redis_service_name": "pulse-redis",
	}
	if overrides.get("redis_url") is not None and "redis_service_name" not in overrides:
		values["redis_service_name"] = None
	values.update(overrides)
	return RailwayProject(**values)


def _runtime_variables(
	*, redis_url: str = "redis://pulse-redis:6379"
) -> tuple[
	dict[str, str],
	dict[str, str],
]:
	router = {
		RAILWAY_TOKEN: "token",
		"PORT": "8000",
		PULSE_INTERNAL_TOKEN: "secret-token",
		REDIS_URL: redis_url,
		PULSE_REDIS_PREFIX: "pulse:railway",
		"RAILWAY_PUBLIC_DOMAIN": "test.pulse.sc",
	}
	janitor = {
		RAILWAY_TOKEN: "token",
		PULSE_INTERNAL_TOKEN: "secret-token",
		REDIS_URL: redis_url,
		PULSE_REDIS_PREFIX: "pulse:railway",
		PULSE_DRAIN_TTL_SECONDS: "86400",
		PULSE_RAILWAY_SERVICE: "pulse-router",
		PULSE_RAILWAY_JANITOR_SERVICE: "pulse-janitor",
		PULSE_RAILWAY_REDIS_SERVICE: "pulse-redis",
	}
	return router, janitor


def _install_client(monkeypatch: pytest.MonkeyPatch, harness: RailwayHarness) -> None:
	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			assert project_id == "project"
			assert environment_id == "env"
			return list(harness.services.values())

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			assert project_id == "project"
			assert environment_id == "env"
			return harness.services.get(name)

		async def get_template_by_code(self, *, code: str) -> TemplateRecord:
			assert code == DEFAULT_PULSE_BASELINE_TEMPLATE_CODE
			return TemplateRecord(
				id="baseline-template",
				code=code,
				serialized_config={
					"services": {
						"template-router": {"name": "pulse-router"},
						"template-janitor": {"name": "pulse-janitor"},
						"template-redis": {"name": "pulse-redis"},
					}
				},
			)

		async def deploy_template(
			self,
			*,
			project_id: str,
			environment_id: str,
			template_id: str,
			serialized_config: dict[str, Any],
		) -> str:
			assert project_id == "project"
			assert environment_id == "env"
			harness.deployed_templates.append(template_id)
			for service_config in serialized_config["services"].values():
				name = service_config["name"]
				unrendered = (
					{REDIS_URL: "${{ pulse-redis.REDIS_URL }}"}
					if name in {"pulse-router", "pulse-janitor"}
					else {}
				)
				variables = (
					{REDIS_URL: "redis://pulse-redis.railway.internal:6379"}
					if name == "pulse-redis"
					else {}
				)
				harness.add_service(
					name,
					variables=variables,
					unrendered_variables=unrendered,
				)
			return "workflow-1"

		async def create_service(
			self,
			*,
			project_id: str,
			environment_id: str,
			name: str,
			image: str | None = None,
		) -> str:
			assert project_id == "project"
			assert environment_id == "env"
			harness.created_services.append(name)
			return harness.add_service(name, image=image).id

		async def get_environment_config(
			self, *, project_id: str, environment_id: str
		) -> dict[str, Any]:
			assert project_id == "project"
			assert environment_id == "env"
			router = harness.services.get("pulse-router")
			harness.environment_config_reads += 1
			if (
				router is None
				or harness.router_group_id is None
				or harness.environment_config_reads
				<= harness.router_group_available_after_config_reads
			):
				return {
					"services": {
						service_id: {"groupId": group_id}
						for service_id, group_id in harness.service_groups.items()
					}
				}
			services = {
				service_id: {"groupId": group_id}
				for service_id, group_id in harness.service_groups.items()
			}
			services[router.id] = {"groupId": harness.router_group_id}
			return {"services": services}

		async def set_service_group_id(
			self, *, environment_id: str, service_id: str, group_id: str
		) -> None:
			assert environment_id == "env"
			harness.group_assignments.append((service_id, group_id))
			harness.service_groups[service_id] = group_id

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			service = next(
				service
				for service in harness.services.values()
				if service.id == service_id
			)
			variables = dict(harness.variables.get(service_id, {}))
			if service.name == "pulse-router" and harness.public_domain:
				variables.setdefault("RAILWAY_PUBLIC_DOMAIN", harness.public_domain)
			return variables

		async def get_project_variables(
			self,
			*,
			project_id: str,
			environment_id: str,
			service_id: str | None = None,
			unrendered: bool = False,
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			if service_id is None:
				return {}
			if unrendered:
				return dict(harness.unrendered_variables.get(service_id, {}))
			return dict(harness.variables.get(service_id, {}))

		async def upsert_variable_collection(
			self,
			*,
			project_id: str,
			environment_id: str,
			variables: dict[str, str],
			service_id: str | None = None,
			skip_deploys: bool = True,
			replace: bool = False,
		) -> None:
			assert project_id == "project"
			assert environment_id == "env"
			assert service_id is not None
			assert skip_deploys is True
			assert replace is False
			harness.variable_collections.append((service_id, dict(variables)))
			harness.variables.setdefault(service_id, {}).update(variables)

		async def update_service_instance(self, **kwargs: Any) -> None:
			harness.updates.append(kwargs)
			service = next(
				service
				for service in harness.services.values()
				if service.id == kwargs["service_id"]
			)
			if kwargs.get("source_image") is not None:
				service.image = kwargs["source_image"]
			if kwargs.get("num_replicas") is not None:
				service.num_replicas = kwargs["num_replicas"]
			if kwargs.get("healthcheck_path") is not None:
				service.healthcheck_path = kwargs["healthcheck_path"]
			if kwargs.get("healthcheck_timeout") is not None:
				service.healthcheck_timeout = kwargs["healthcheck_timeout"]
			if kwargs.get("overlap_seconds") is not None:
				service.overlap_seconds = kwargs["overlap_seconds"]
			if kwargs.get("start_command") is not None:
				service.start_command = kwargs["start_command"]
			if kwargs.get("cron_schedule") is not None:
				service.cron_schedule = kwargs["cron_schedule"]
			if kwargs.get("restart_policy_type") is not None:
				service.restart_policy_type = kwargs["restart_policy_type"]

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
			assert environment_id == "env"
			harness.deployed_services.append(service_id)
			return f"deploy-{service_id}"

		async def wait_for_deployment(self, *, deployment_id: str) -> dict[str, str]:
			return {"id": deployment_id, "status": "SUCCESS"}

		async def create_service_domain(
			self,
			*,
			service_id: str,
			environment_id: str,
			target_port: int,
		) -> str:
			assert environment_id == "env"
			harness.domain_creations.append(service_id)
			service = next(
				service
				for service in harness.services.values()
				if service.id == service_id
			)
			domain = "pulse-router-production.up.railway.app"
			service.domains = [
				ServiceDomain(id="domain-1", domain=domain, target_port=target_port)
			]
			return domain

		async def delete_variable(
			self,
			*,
			project_id: str,
			environment_id: str,
			name: str,
			service_id: str | None = None,
		) -> None:
			assert project_id == "project"
			assert environment_id == "env"
			assert service_id is not None
			harness.deleted_variables.append((service_id, name))
			harness.variables.get(service_id, {}).pop(name, None)
			harness.unrendered_variables.get(service_id, {}).pop(name, None)

		async def delete_service(self, *, service_id: str, environment_id: str) -> None:
			assert environment_id == "env"
			harness.deleted_services.append(service_id)
			name = next(
				name
				for name, service in harness.services.items()
				if service.id == service_id
			)
			del harness.services[name]

	monkeypatch.setattr(
		"pulse_railway.stack.creation.RailwayGraphQLClient", _FakeClient
	)
	monkeypatch.setattr(
		"pulse_railway.stack.inspection.RailwayGraphQLClient", _FakeClient
	)
	monkeypatch.setattr(
		"pulse_railway.stack.reconciliation.RailwayGraphQLClient", _FakeClient
	)


@pytest.mark.asyncio
async def test_upsert_service_variables_requires_service_id() -> None:
	class _FakeClient:
		async def upsert_variable_collection(self, **_: object) -> None:
			raise AssertionError("should not write project-level variables")

	with pytest.raises(DeploymentError, match="service_id is required"):
		await upsert_service_variables(
			_FakeClient(),  # type: ignore[arg-type]
			project=_project(),
			service_id="",
			variables={REDIS_URL: "redis://example"},
		)


@pytest.mark.asyncio
async def test_upsert_service_variables_writes_collection_once() -> None:
	class _FakeClient:
		def __init__(self) -> None:
			self.calls: list[dict[str, object]] = []

		async def upsert_variable_collection(self, **kwargs: object) -> None:
			self.calls.append(kwargs)

	client = _FakeClient()

	await upsert_service_variables(
		client,  # type: ignore[arg-type]
		project=_project(),
		service_id="svc-router",
		variables={"A": "1", "B": "2"},
	)

	assert client.calls == [
		{
			"project_id": "project",
			"environment_id": "env",
			"service_id": "svc-router",
			"variables": {"A": "1", "B": "2"},
			"skip_deploys": True,
			"replace": False,
		}
	]


@pytest.mark.asyncio
async def test_create_stack_creates_fresh_managed_baseline(monkeypatch) -> None:
	harness = RailwayHarness()
	_install_client(monkeypatch, harness)

	result = await create_stack(project=_project())

	assert result.router.created is True
	assert result.router.deployed is True
	assert result.router.image == official_router_image_ref()
	assert result.janitor.created is True
	assert result.janitor.image == official_janitor_image_ref()
	assert result.redis is not None
	assert result.redis.created is True
	assert result.internal_token_created is True
	assert result.redis_url == "redis://pulse-redis.railway.internal:6379"
	assert result.server_address == "https://test.pulse.sc"
	assert set(harness.services) == {
		"pulse-router",
		"pulse-janitor",
		"pulse-redis",
		"pulse-env",
	}
	assert harness.deployed_templates == ["baseline-template"]
	assert harness.group_assignments == [("svc-4", "group-baseline")]
	assert harness.domain_creations == ["svc-1"]
	assert PULSE_INTERNAL_TOKEN in harness.variables["svc-1"]
	assert PULSE_INTERNAL_TOKEN in harness.variables["svc-2"]
	assert REDIS_URL in harness.variables["svc-1"]
	assert REDIS_URL in harness.variables["svc-2"]
	router_update = next(
		update
		for update in harness.updates
		if update["start_command"] == ROUTER_START_COMMAND
	)
	assert router_update["num_replicas"] == 1
	janitor_update = next(
		update
		for update in harness.updates
		if update["start_command"] == JANITOR_START_COMMAND
	)
	assert janitor_update["restart_policy_type"] == "NEVER"


@pytest.mark.asyncio
async def test_create_stack_waits_for_router_group_before_creating_env(
	monkeypatch,
) -> None:
	harness = RailwayHarness(router_group_available_after_config_reads=1)
	sleep_delays: list[float] = []
	_install_client(monkeypatch, harness)

	async def fast_sleep(delay: float) -> None:
		sleep_delays.append(delay)

	monkeypatch.setattr("pulse_railway.railway.ops.asyncio.sleep", fast_sleep)

	await create_stack(project=_project())

	assert harness.environment_config_reads == 2
	assert sleep_delays == [2.0]
	assert harness.group_assignments == [("svc-4", "group-baseline")]


@pytest.mark.asyncio
async def test_create_stack_omits_redis_for_external_url(
	monkeypatch,
) -> None:
	harness = RailwayHarness()
	_install_client(monkeypatch, harness)

	result = await create_stack(
		project=_project(redis_url="redis://external.example:6379")
	)

	assert result.redis is None
	assert result.redis_url == "redis://external.example:6379"
	assert "pulse-redis" not in harness.services
	assert harness.deleted_services == []
	assert harness.deleted_variables == []
	assert harness.variables["svc-1"][REDIS_URL] == "redis://external.example:6379"
	assert harness.variables["svc-2"][REDIS_URL] == "redis://external.example:6379"


@pytest.mark.asyncio
async def test_create_stack_fails_if_any_baseline_service_exists(monkeypatch) -> None:
	harness = RailwayHarness()
	harness.add_service("pulse-router", service_id="svc-router")
	_install_client(monkeypatch, harness)

	with pytest.raises(DeploymentError, match="baseline stack already exists"):
		await create_stack(project=_project())

	assert harness.deployed_templates == []
	assert harness.created_services == []
	assert harness.updates == []


@pytest.mark.asyncio
async def test_inspect_stack_returns_complete_managed_baseline_without_mutating(
	monkeypatch,
) -> None:
	harness = RailwayHarness()
	router_vars, janitor_vars = _runtime_variables()
	harness.add_service(
		"pulse-router",
		service_id="svc-router",
		image="router-image",
		domain="pulse-router-production.up.railway.app",
		variables=router_vars,
	)
	harness.add_service(
		"pulse-janitor",
		service_id="svc-janitor",
		image="janitor-image",
		variables=janitor_vars,
	)
	harness.add_service("pulse-env", service_id="svc-env")
	harness.add_service("pulse-redis", service_id="svc-redis")
	_install_client(monkeypatch, harness)

	stack = await inspect_stack(project=_project())

	assert stack.router.service_id == "svc-router"
	assert stack.janitor.service_id == "svc-janitor"
	assert stack.env is not None
	assert stack.env.service_id == "svc-env"
	assert stack.redis is not None
	assert stack.redis.service_id == "svc-redis"
	assert stack.redis_mode == "managed"
	assert stack.internal_token == "secret-token"
	assert stack.redis_url == "redis://pulse-redis:6379"
	assert stack.server_address == "https://test.pulse.sc"
	assert harness.created_services == []
	assert harness.domain_creations == []
	assert harness.updates == []


@pytest.mark.asyncio
async def test_inspect_stack_accepts_external_redis_baseline(monkeypatch) -> None:
	harness = RailwayHarness()
	redis_url = "redis://external.example:6379"
	router_vars, janitor_vars = _runtime_variables(redis_url=redis_url)
	harness.add_service(
		"pulse-router",
		service_id="svc-router",
		domain="pulse-router-production.up.railway.app",
		variables=router_vars,
	)
	harness.add_service(
		"pulse-janitor", service_id="svc-janitor", variables=janitor_vars
	)
	harness.add_service("pulse-env", service_id="svc-env")
	_install_client(monkeypatch, harness)

	stack = await inspect_stack(project=_project(redis_service_name=None))

	assert stack.redis is None
	assert stack.redis_mode == "external"
	assert stack.redis_url == redis_url


@pytest.mark.asyncio
async def test_inspect_stack_fails_for_partial_baseline(monkeypatch) -> None:
	harness = RailwayHarness()
	router_vars, _janitor_vars = _runtime_variables()
	harness.add_service("pulse-router", service_id="svc-router", variables=router_vars)
	_install_client(monkeypatch, harness)

	with pytest.raises(
		DeploymentError, match="baseline service pulse-janitor not found"
	):
		await inspect_stack(project=_project())

	assert harness.created_services == []
	assert harness.updates == []


@pytest.mark.asyncio
async def test_reconcile_stack_updates_runtime_config_without_creating_services(
	monkeypatch,
) -> None:
	harness = RailwayHarness()
	router_vars, janitor_vars = _runtime_variables()
	harness.add_service(
		"pulse-router",
		service_id="svc-router",
		domain="pulse-router-production.up.railway.app",
		variables=router_vars,
	)
	harness.add_service(
		"pulse-janitor", service_id="svc-janitor", variables=janitor_vars
	)
	harness.add_service("pulse-env", service_id="svc-env")
	harness.add_service("pulse-redis", service_id="svc-redis")
	harness.add_service(
		"pulse-prod-260501-120000",
		service_id="svc-backend",
		variables={PULSE_DEPLOYMENT_ID: "prod-260501-120000"},
	)
	harness.add_service(
		"pulse-prod-260501-121000",
		service_id="svc-grouped-backend",
		group_id="group-baseline",
		variables={PULSE_DEPLOYMENT_ID: "prod-260501-121000"},
	)
	_install_client(monkeypatch, harness)

	result = await reconcile_stack(
		project=_project(router_replicas=3, drain_ttl_seconds=120),
	)

	assert result.router.created is False
	assert result.router.deployed is True
	assert result.janitor.created is False
	assert result.janitor.deployed is True
	assert result.internal_token_created is False
	assert harness.created_services == []
	assert harness.deployed_templates == []
	assert harness.group_assignments == [
		("svc-janitor", "group-baseline"),
		("svc-env", "group-baseline"),
		("svc-backend", "group-baseline"),
		("svc-redis", "group-baseline"),
	]
	router_update = next(
		update for update in harness.updates if update["service_id"] == "svc-router"
	)
	janitor_update = next(
		update for update in harness.updates if update["service_id"] == "svc-janitor"
	)
	assert router_update["source_image"] == official_router_image_ref()
	assert router_update["num_replicas"] == 3
	assert janitor_update["source_image"] == official_janitor_image_ref()
	assert harness.variables["svc-janitor"][PULSE_DRAIN_TTL_SECONDS] == "120"
	assert harness.deployed_services == ["svc-router", "svc-janitor"]


@pytest.mark.asyncio
async def test_reconcile_stack_skips_runtime_deploy_when_config_is_current(
	monkeypatch,
) -> None:
	project = _project()
	harness = RailwayHarness()
	router_vars, janitor_vars = _runtime_variables()
	harness.add_service(
		"pulse-router",
		service_id="svc-router",
		domain="pulse-router-production.up.railway.app",
		variables=router_vars,
		image=official_router_image_ref(),
		num_replicas=project.router_replicas,
		healthcheck_path="/healthz",
		healthcheck_timeout=60,
		overlap_seconds=30,
		start_command=ROUTER_START_COMMAND,
	)
	harness.add_service(
		"pulse-janitor",
		service_id="svc-janitor",
		variables=janitor_vars,
		image=official_janitor_image_ref(),
		num_replicas=project.janitor_replicas,
		start_command=JANITOR_START_COMMAND,
		cron_schedule=project.janitor_cron_schedule,
		restart_policy_type="NEVER",
	)
	harness.add_service("pulse-env", service_id="svc-env", group_id="group-baseline")
	harness.add_service(
		"pulse-redis", service_id="svc-redis", group_id="group-baseline"
	)
	_install_client(monkeypatch, harness)

	result = await reconcile_stack(project=project)

	assert result.router.deployed is False
	assert result.router.deployment_id is None
	assert result.janitor.deployed is False
	assert result.janitor.deployment_id is None
	assert harness.updates == []
	assert harness.variable_collections == []
	assert harness.deployed_services == []


@pytest.mark.asyncio
async def test_reconcile_stack_deploys_only_changed_runtime_service(
	monkeypatch,
) -> None:
	project = _project(drain_ttl_seconds=120)
	harness = RailwayHarness()
	router_vars, janitor_vars = _runtime_variables()
	janitor_vars[PULSE_DRAIN_TTL_SECONDS] = "86400"
	harness.add_service(
		"pulse-router",
		service_id="svc-router",
		domain="pulse-router-production.up.railway.app",
		variables=router_vars,
		image=official_router_image_ref(),
		num_replicas=project.router_replicas,
		healthcheck_path="/healthz",
		healthcheck_timeout=60,
		overlap_seconds=30,
		start_command=ROUTER_START_COMMAND,
	)
	harness.add_service(
		"pulse-janitor",
		service_id="svc-janitor",
		variables=janitor_vars,
		image=official_janitor_image_ref(),
		num_replicas=project.janitor_replicas,
		start_command=JANITOR_START_COMMAND,
		cron_schedule=project.janitor_cron_schedule,
		restart_policy_type="NEVER",
	)
	harness.add_service("pulse-env", service_id="svc-env", group_id="group-baseline")
	harness.add_service(
		"pulse-redis", service_id="svc-redis", group_id="group-baseline"
	)
	_install_client(monkeypatch, harness)

	result = await reconcile_stack(project=project)

	assert result.router.deployed is False
	assert result.janitor.deployed is True
	assert result.janitor.deployment_id == "deploy-svc-janitor"
	assert harness.updates == []
	assert harness.variable_collections == [
		(
			"svc-janitor",
			{
				RAILWAY_TOKEN: "token",
				PULSE_INTERNAL_TOKEN: "secret-token",
				REDIS_URL: "redis://pulse-redis:6379",
				PULSE_REDIS_PREFIX: "pulse:railway",
				PULSE_DRAIN_TTL_SECONDS: "120",
				PULSE_RAILWAY_SERVICE: "pulse-router",
				PULSE_RAILWAY_JANITOR_SERVICE: "pulse-janitor",
				PULSE_RAILWAY_REDIS_SERVICE: "pulse-redis",
			},
		)
	]
	assert harness.deployed_services == ["svc-janitor"]


@pytest.mark.asyncio
async def test_reconcile_stack_ignores_grouping_when_router_has_no_group(
	monkeypatch,
) -> None:
	harness = RailwayHarness(router_group_id=None)
	router_vars, janitor_vars = _runtime_variables()
	harness.add_service(
		"pulse-router",
		service_id="svc-router",
		domain="pulse-router-production.up.railway.app",
		variables=router_vars,
	)
	harness.add_service(
		"pulse-janitor", service_id="svc-janitor", variables=janitor_vars
	)
	harness.add_service("pulse-env", service_id="svc-env")
	harness.add_service("pulse-redis", service_id="svc-redis")
	harness.add_service(
		"pulse-prod-260501-120000",
		service_id="svc-backend",
		variables={PULSE_DEPLOYMENT_ID: "prod-260501-120000"},
	)
	_install_client(monkeypatch, harness)

	await reconcile_stack(project=_project())

	assert harness.group_assignments == []


@pytest.mark.asyncio
async def test_create_or_reconcile_creates_only_when_no_baseline_exists(
	monkeypatch,
) -> None:
	harness = RailwayHarness()
	_install_client(monkeypatch, harness)

	result = await create_or_reconcile_stack(project=_project())

	assert result.router.created is True
	assert harness.deployed_templates == ["baseline-template"]


@pytest.mark.asyncio
async def test_create_or_reconcile_fails_instead_of_repairing_partial_baseline(
	monkeypatch,
) -> None:
	harness = RailwayHarness()
	harness.add_service("pulse-env", service_id="svc-env")
	_install_client(monkeypatch, harness)

	with pytest.raises(
		DeploymentError, match="baseline service pulse-router not found"
	):
		await create_or_reconcile_stack(project=_project())

	assert harness.created_services == []
	assert harness.deployed_templates == []
