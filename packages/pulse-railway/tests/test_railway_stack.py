from __future__ import annotations

from typing import Any

import pytest
from pulse_railway.config import RailwayProject
from pulse_railway.constants import (
	DEFAULT_PULSE_BASELINE_TEMPLATE_CODE,
	PULSE_INTERNAL_TOKEN,
	PULSE_JANITOR_DRAIN_GRACE_SECONDS,
	PULSE_JANITOR_MAX_DRAIN_AGE_SECONDS,
	PULSE_REDIS_PREFIX,
	PULSE_WEBSOCKET_HEARTBEAT_SECONDS,
	PULSE_WEBSOCKET_TTL_SECONDS,
	REDIS_URL,
)
from pulse_railway.errors import DeploymentError
from pulse_railway.images import (
	official_janitor_image_ref,
	official_router_image_ref,
)
from pulse_railway.railway import ServiceDomain, ServiceRecord, TemplateRecord
from pulse_railway.stack import (
	JANITOR_START_COMMAND,
	ROUTER_START_COMMAND,
	bootstrap_stack,
	ensure_stack,
	require_ready_stack,
)


@pytest.mark.asyncio
async def test_bootstrap_stack_creates_baseline_from_empty_project(monkeypatch) -> None:
	service_state: dict[str, ServiceRecord] = {}
	service_variables: dict[str, dict[str, str]] = {}
	project_variables: dict[str, str] = {}
	service_updates: list[dict[str, Any]] = []
	domain_targets: list[str] = []
	deployed_templates: list[str] = []
	group_assignments: list[tuple[str, str]] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			self.service_counter = 0

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			assert project_id == "project"
			assert environment_id == "env"
			return service_state.get(name)

		async def get_template_by_code(self, *, code: str) -> TemplateRecord:
			assert code == DEFAULT_PULSE_BASELINE_TEMPLATE_CODE
			return TemplateRecord(
				id="template-1",
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
			assert template_id == "template-1"
			deployed_templates.append(template_id)
			for service_config in serialized_config["services"].values():
				service_name = service_config["name"]
				self.service_counter += 1
				service_state[service_name] = ServiceRecord(
					id=f"svc-{self.service_counter}",
					name=service_name,
				)
			return "workflow-1"

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			service = next(
				record for record in service_state.values() if record.id == service_id
			)
			if service.name == "pulse-redis":
				return {"REDIS_URL": "redis://pulse-redis.railway.internal:6379"}
			variables = dict(service_variables.get(service_id, {}))
			if service.name == "pulse-router":
				variables["RAILWAY_PUBLIC_DOMAIN"] = "test.pulse.sc"
			return variables

		async def get_project_variables(
			self, *, project_id: str, environment_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			return dict(project_variables)

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
			assert project_id == "project"
			assert environment_id == "env"
			assert skip_deploys is True
			if service_id is None:
				project_variables[name] = value
				return
			service_variables.setdefault(service_id, {})[name] = value

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
			self.service_counter += 1
			service_id = f"svc-{self.service_counter}"
			service_state[name] = ServiceRecord(id=service_id, name=name, image=image)
			service_variables[service_id] = {}
			return service_id

		async def get_environment_config(
			self, *, project_id: str, environment_id: str
		) -> dict[str, Any]:
			assert project_id == "project"
			assert environment_id == "env"
			return {"services": {"svc-1": {"groupId": "group-baseline"}}}

		async def set_service_group_id(
			self, *, environment_id: str, service_id: str, group_id: str
		) -> None:
			assert environment_id == "env"
			group_assignments.append((service_id, group_id))

		async def update_service_instance(self, **kwargs: Any) -> None:
			service_updates.append(kwargs)

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
			assert environment_id == "env"
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
			domain_targets.append(service_id)
			for service in service_state.values():
				if service.id != service_id:
					continue
				domain = "pulse-router-production.up.railway.app"
				service.domains = [
					ServiceDomain(id="domain-1", domain=domain, target_port=target_port)
				]
				return domain
			raise AssertionError(service_id)

	monkeypatch.setattr("pulse_railway.stack.RailwayGraphQLClient", _FakeClient)

	result = await bootstrap_stack(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			redis_service_name="pulse-redis",
			janitor_service_name="pulse-janitor",
		)
	)

	assert result.router.created is True
	assert result.router.deployed is True
	assert result.router.image == official_router_image_ref()
	assert result.janitor.created is True
	assert result.janitor.deployed is True
	assert result.janitor.image == official_janitor_image_ref()
	assert result.redis is not None
	assert result.redis.created is True
	assert result.internal_token_created is True
	assert result.redis_url == "redis://pulse-redis.railway.internal:6379"
	assert result.server_address == "https://test.pulse.sc"
	assert "pulse-env" in service_state
	assert group_assignments == [("svc-4", "group-baseline")]
	assert PULSE_INTERNAL_TOKEN in project_variables
	assert domain_targets
	assert deployed_templates == ["template-1"]
	router_update = next(
		update
		for update in service_updates
		if update["start_command"] == ROUTER_START_COMMAND
	)
	assert router_update["num_replicas"] == 1
	janitor_update = next(
		update
		for update in service_updates
		if update["start_command"] == JANITOR_START_COMMAND
	)
	assert janitor_update["restart_policy_type"] == "NEVER"
	assert REDIS_URL in service_variables[result.router.service_id]
	assert PULSE_REDIS_PREFIX in service_variables[result.router.service_id]
	assert (
		PULSE_JANITOR_DRAIN_GRACE_SECONDS
		in service_variables[result.janitor.service_id]
	)
	assert (
		PULSE_JANITOR_MAX_DRAIN_AGE_SECONDS
		in service_variables[result.janitor.service_id]
	)


@pytest.mark.asyncio
async def test_ensure_stack_reconciles_existing_baseline(monkeypatch) -> None:
	service_state: dict[str, ServiceRecord] = {
		"pulse-router": ServiceRecord(
			id="svc-router",
			name="pulse-router",
			domains=[
				ServiceDomain(
					id="domain-1",
					domain="pulse-router-production.up.railway.app",
					target_port=8000,
				)
			],
		),
		"pulse-redis": ServiceRecord(id="svc-redis", name="pulse-redis"),
		"pulse-janitor": ServiceRecord(id="svc-janitor", name="pulse-janitor"),
		"pulse-env": ServiceRecord(id="svc-env", name="pulse-env"),
	}
	service_variables: dict[str, dict[str, str]] = {}
	project_variables: dict[str, str] = {PULSE_INTERNAL_TOKEN: "internal-token"}
	service_updates: list[dict[str, Any]] = []
	deployed_services: list[str] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			assert project_id == "project"
			assert environment_id == "env"
			return service_state.get(name)

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			assert project_id == "project"
			assert environment_id == "env"
			return list(service_state.values())

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			service = next(
				record for record in service_state.values() if record.id == service_id
			)
			if service.name == "pulse-redis":
				return {"REDIS_URL": "redis://pulse-redis.railway.internal:6379"}
			variables = dict(service_variables.get(service_id, {}))
			if service.name == "pulse-router":
				variables["RAILWAY_PUBLIC_DOMAIN"] = "test.pulse.sc"
			return variables

		async def get_project_variables(
			self, *, project_id: str, environment_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			return dict(project_variables)

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
			assert project_id == "project"
			assert environment_id == "env"
			assert skip_deploys is True
			if service_id is None:
				project_variables[name] = value
				return
			service_variables.setdefault(service_id, {})[name] = value

		async def create_service(self, **_: object) -> str:
			raise AssertionError("existing baseline should not create services")

		async def update_service_instance(self, **kwargs: Any) -> None:
			service_updates.append(kwargs)

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
			assert environment_id == "env"
			deployed_services.append(service_id)
			return f"deploy-{service_id}"

		async def wait_for_deployment(self, *, deployment_id: str) -> dict[str, str]:
			return {"id": deployment_id, "status": "SUCCESS"}

		async def create_service_domain(self, **_: object) -> str:
			raise AssertionError("existing router domain should be reused")

	monkeypatch.setattr("pulse_railway.stack.RailwayGraphQLClient", _FakeClient)

	result = await ensure_stack(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			redis_service_name="pulse-redis",
			janitor_service_name="pulse-janitor",
		)
	)

	assert result.router.created is False
	assert result.router.deployed is True
	assert result.janitor.created is False
	assert result.redis is not None
	assert result.redis.created is False
	assert result.internal_token_created is False
	assert result.redis_url == "redis://pulse-redis.railway.internal:6379"
	assert result.server_address == "https://test.pulse.sc"
	assert deployed_services == ["svc-router", "svc-janitor"]
	assert service_variables["svc-router"][REDIS_URL] == (
		"redis://pulse-redis.railway.internal:6379"
	)
	assert service_variables["svc-janitor"][PULSE_INTERNAL_TOKEN] == (
		"${{ shared.PULSE_RAILWAY_INTERNAL_TOKEN }}"
	)
	assert len(service_updates) == 2


@pytest.mark.asyncio
async def test_bootstrap_stack_fails_for_existing_stack(monkeypatch) -> None:
	service_state: dict[str, ServiceRecord] = {
		"pulse-router": ServiceRecord(
			id="svc-router",
			name="pulse-router",
			image="ghcr.io/acme/router:old",
			domains=[
				ServiceDomain(
					id="domain-1",
					domain="pulse-router-production.up.railway.app",
					target_port=8000,
				)
			],
		),
		"pulse-redis": ServiceRecord(id="svc-redis", name="pulse-redis"),
		"pulse-janitor": ServiceRecord(id="svc-janitor", name="pulse-janitor"),
		"pulse-env": ServiceRecord(id="svc-env", name="pulse-env"),
	}
	service_variables = {
		"svc-router": {
			"RAILWAY_TOKEN": "token",
			"RAILWAY_PROJECT_ID": "project",
			"RAILWAY_ENVIRONMENT_ID": "env",
			"PULSE_BACKEND_PORT": "8000",
			"PORT": "8000",
			REDIS_URL: "redis://pulse-redis.railway.internal:6379",
			PULSE_REDIS_PREFIX: "pulse:railway",
			PULSE_WEBSOCKET_HEARTBEAT_SECONDS: "15",
			PULSE_WEBSOCKET_TTL_SECONDS: "45",
			"RAILWAY_PUBLIC_DOMAIN": "test.pulse.sc",
		},
		"svc-redis": {"REDIS_URL": "redis://pulse-redis.railway.internal:6379"},
		"svc-janitor": {
			"RAILWAY_TOKEN": "token",
			"RAILWAY_PROJECT_ID": "project",
			"RAILWAY_ENVIRONMENT_ID": "env",
			PULSE_INTERNAL_TOKEN: "secret-token",
			REDIS_URL: "redis://pulse-redis.railway.internal:6379",
			PULSE_REDIS_PREFIX: "pulse:railway",
			PULSE_JANITOR_DRAIN_GRACE_SECONDS: "60",
			PULSE_JANITOR_MAX_DRAIN_AGE_SECONDS: "86400",
			PULSE_WEBSOCKET_HEARTBEAT_SECONDS: "15",
			PULSE_WEBSOCKET_TTL_SECONDS: "45",
		},
	}
	create_calls: list[str] = []
	deploy_calls: list[str] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			return service_state.get(name)

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			return dict(service_variables[service_id])

		async def get_project_variables(
			self, *, project_id: str, environment_id: str
		) -> dict[str, str]:
			return {PULSE_INTERNAL_TOKEN: "secret-token"}

		async def create_service(self, **kwargs: Any) -> str:
			create_calls.append(kwargs["name"])
			raise AssertionError("bootstrap should not create services")

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
			deploy_calls.append(service_id)
			raise AssertionError("bootstrap should not deploy existing services")

		async def create_service_domain(self, **kwargs: Any) -> str:
			raise AssertionError(
				"bootstrap should not create domains for a ready stack"
			)

	monkeypatch.setattr("pulse_railway.stack.RailwayGraphQLClient", _FakeClient)

	with pytest.raises(DeploymentError, match="baseline stack already exists"):
		await bootstrap_stack(
			project=RailwayProject(
				project_id="project",
				environment_id="env",
				token="token",
				service_name="pulse-router",
				redis_service_name="pulse-redis",
				janitor_service_name="pulse-janitor",
			)
		)

	assert create_calls == []
	assert deploy_calls == []


@pytest.mark.asyncio
async def test_bootstrap_stack_fails_for_partial_baseline(monkeypatch) -> None:
	service_state: dict[str, ServiceRecord] = {
		"pulse-router": ServiceRecord(id="svc-router", name="pulse-router")
	}
	service_variables: dict[str, dict[str, str]] = {"svc-router": {}}
	project_variables: dict[str, str] = {}
	service_updates: list[dict[str, Any]] = []
	deployed_templates: list[str] = []
	group_assignments: list[tuple[str, str]] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			self.service_counter = 1

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			return service_state.get(name)

		async def get_template_by_code(self, *, code: str) -> TemplateRecord:
			return TemplateRecord(
				id="template-redis",
				code=code,
				serialized_config={"services": {"template-service": {"name": "Redis"}}},
			)

		async def deploy_template(
			self,
			*,
			project_id: str,
			environment_id: str,
			template_id: str,
			serialized_config: dict[str, Any],
		) -> str:
			deployed_templates.append(template_id)
			service_name = serialized_config["services"]["template-service"]["name"]
			self.service_counter += 1
			service_id = f"svc-{self.service_counter}"
			service_state[service_name] = ServiceRecord(
				id=service_id,
				name=service_name,
			)
			service_variables[service_id] = {
				"REDIS_URL": "redis://pulse-redis.railway.internal:6379"
			}
			return "workflow-redis"

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			service = next(
				record for record in service_state.values() if record.id == service_id
			)
			variables = dict(service_variables.get(service_id, {}))
			if service.name == "pulse-router":
				variables["RAILWAY_PUBLIC_DOMAIN"] = "test.pulse.sc"
			return variables

		async def get_project_variables(
			self, *, project_id: str, environment_id: str
		) -> dict[str, str]:
			return dict(project_variables)

		async def upsert_variable(self, **kwargs: Any) -> None:
			service_id = kwargs.get("service_id")
			if service_id is None:
				project_variables[kwargs["name"]] = kwargs["value"]
				return
			service_variables.setdefault(service_id, {})[kwargs["name"]] = kwargs[
				"value"
			]

		async def create_service(
			self,
			*,
			project_id: str,
			environment_id: str,
			name: str,
			image: str | None = None,
		) -> str:
			self.service_counter += 1
			service_id = f"svc-{self.service_counter}"
			service_state[name] = ServiceRecord(id=service_id, name=name, image=image)
			service_variables[service_id] = {}
			return service_id

		async def get_environment_config(
			self, *, project_id: str, environment_id: str
		) -> dict[str, Any]:
			return {"services": {"svc-router": {"groupId": "group-baseline"}}}

		async def set_service_group_id(
			self, *, environment_id: str, service_id: str, group_id: str
		) -> None:
			group_assignments.append((service_id, group_id))

		async def update_service_instance(self, **kwargs: Any) -> None:
			service_updates.append(kwargs)

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
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
			for service in service_state.values():
				if service.id != service_id:
					continue
				domain = "pulse-router-production.up.railway.app"
				service.domains = [
					ServiceDomain(id="domain-1", domain=domain, target_port=target_port)
				]
				return domain
			raise AssertionError(service_id)

	monkeypatch.setattr("pulse_railway.stack.RailwayGraphQLClient", _FakeClient)

	with pytest.raises(DeploymentError, match="baseline stack already exists"):
		await bootstrap_stack(
			project=RailwayProject(
				project_id="project",
				environment_id="env",
				token="token",
				service_name="pulse-router",
				redis_service_name="pulse-redis",
				janitor_service_name="pulse-janitor",
			)
		)

	assert "pulse-janitor" not in service_state
	assert deployed_templates == []
	assert group_assignments == []
	assert service_updates == []


@pytest.mark.asyncio
async def test_bootstrap_stack_removes_managed_redis_for_external_redis(
	monkeypatch,
) -> None:
	service_state: dict[str, ServiceRecord] = {}
	service_variables: dict[str, dict[str, str]] = {}
	project_variables: dict[str, str] = {}
	template_codes: list[str] = []
	deleted_variables: list[tuple[str | None, str]] = []
	deleted_services: list[str] = []
	group_assignments: list[tuple[str, str]] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			self.service_counter = 0

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			return service_state.get(name)

		async def get_template_by_code(self, *, code: str) -> TemplateRecord:
			template_codes.append(code)
			assert code == DEFAULT_PULSE_BASELINE_TEMPLATE_CODE
			return TemplateRecord(
				id="template-baseline",
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
			for service_config in serialized_config["services"].values():
				self.service_counter += 1
				service_name = service_config["name"]
				service_state[service_name] = ServiceRecord(
					id=f"svc-{self.service_counter}",
					name=service_name,
				)
			return "workflow-1"

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			service = next(
				record for record in service_state.values() if record.id == service_id
			)
			variables = dict(service_variables.get(service_id, {}))
			if service.name == "pulse-router":
				variables["RAILWAY_PUBLIC_DOMAIN"] = "test.pulse.sc"
			return variables

		async def get_project_variables(
			self,
			*,
			project_id: str,
			environment_id: str,
			service_id: str | None = None,
			unrendered: bool = False,
		) -> dict[str, str]:
			if not unrendered:
				return dict(project_variables)
			if service_id is None:
				return dict(project_variables)
			service = next(
				record for record in service_state.values() if record.id == service_id
			)
			if service.name == "pulse-router":
				return {"REDIS_URL": "${{pulse-redis.REDIS_URL}}"}
			if service.name == "pulse-janitor":
				return {"REDIS_URL": "${{ pulse-redis.REDIS_URL }}"}
			return dict(project_variables)

		async def upsert_variable(self, **kwargs: Any) -> None:
			service_id = kwargs.get("service_id")
			if service_id is None:
				project_variables[kwargs["name"]] = kwargs["value"]
				return
			service_variables.setdefault(service_id, {})[kwargs["name"]] = kwargs[
				"value"
			]

		async def create_service(
			self,
			*,
			project_id: str,
			environment_id: str,
			name: str,
			image: str | None = None,
		) -> str:
			self.service_counter += 1
			service_id = f"svc-{self.service_counter}"
			service_state[name] = ServiceRecord(id=service_id, name=name, image=image)
			service_variables[service_id] = {}
			return service_id

		async def get_environment_config(
			self, *, project_id: str, environment_id: str
		) -> dict[str, Any]:
			return {"services": {"svc-1": {"groupId": "group-baseline"}}}

		async def set_service_group_id(
			self, *, environment_id: str, service_id: str, group_id: str
		) -> None:
			group_assignments.append((service_id, group_id))

		async def update_service_instance(self, **kwargs: Any) -> None:
			return None

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
			return f"deploy-{service_id}"

		async def wait_for_deployment(self, *, deployment_id: str) -> dict[str, str]:
			return {"id": deployment_id, "status": "SUCCESS"}

		async def delete_variable(
			self,
			*,
			project_id: str,
			environment_id: str,
			name: str,
			service_id: str | None = None,
		) -> None:
			deleted_variables.append((service_id, name))

		async def delete_service(self, *, service_id: str, environment_id: str) -> None:
			deleted_services.append(service_id)
			service = next(
				record_name
				for record_name, record in service_state.items()
				if record.id == service_id
			)
			del service_state[service]

		async def create_service_domain(
			self,
			*,
			service_id: str,
			environment_id: str,
			target_port: int,
		) -> str:
			for service in service_state.values():
				if service.id != service_id:
					continue
				domain = "pulse-router-production.up.railway.app"
				service.domains = [
					ServiceDomain(id="domain-1", domain=domain, target_port=target_port)
				]
				return domain
			raise AssertionError(service_id)

	monkeypatch.setattr("pulse_railway.stack.RailwayGraphQLClient", _FakeClient)

	result = await bootstrap_stack(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			janitor_service_name="pulse-janitor",
			redis_url="redis://external.example:6379",
		)
	)

	assert template_codes == [DEFAULT_PULSE_BASELINE_TEMPLATE_CODE]
	assert result.router.image == official_router_image_ref()
	assert result.janitor.image == official_janitor_image_ref()
	assert result.redis is None
	assert result.redis_url == "redis://external.example:6379"
	assert group_assignments == [("svc-4", "group-baseline")]
	assert deleted_services == ["svc-3"]
	assert deleted_variables == [("svc-1", "REDIS_URL"), ("svc-2", "REDIS_URL")]
	assert service_variables["svc-1"][REDIS_URL] == "redis://external.example:6379"
	assert service_variables["svc-2"][REDIS_URL] == "redis://external.example:6379"


@pytest.mark.asyncio
async def test_require_ready_stack_accepts_external_redis_baseline(
	monkeypatch,
) -> None:
	service_state: dict[str, ServiceRecord] = {
		"pulse-router": ServiceRecord(
			id="svc-router",
			name="pulse-router",
			domains=[
				ServiceDomain(
					id="domain-1",
					domain="pulse-router-production.up.railway.app",
					target_port=8000,
				)
			],
		),
		"pulse-janitor": ServiceRecord(id="svc-janitor", name="pulse-janitor"),
		"pulse-env": ServiceRecord(id="svc-env", name="pulse-env"),
	}
	redis_url = "redis://external.example:6379"
	service_variables = {
		"svc-router": {
			"RAILWAY_TOKEN": "token",
			"RAILWAY_PROJECT_ID": "project",
			"RAILWAY_ENVIRONMENT_ID": "env",
			"PULSE_BACKEND_PORT": "8000",
			"PORT": "8000",
			REDIS_URL: redis_url,
			PULSE_REDIS_PREFIX: "pulse:railway",
			PULSE_WEBSOCKET_HEARTBEAT_SECONDS: "15",
			PULSE_WEBSOCKET_TTL_SECONDS: "45",
			"RAILWAY_PUBLIC_DOMAIN": "test.pulse.sc",
		},
		"svc-janitor": {
			"RAILWAY_TOKEN": "token",
			"RAILWAY_PROJECT_ID": "project",
			"RAILWAY_ENVIRONMENT_ID": "env",
			PULSE_INTERNAL_TOKEN: "secret-token",
			REDIS_URL: redis_url,
			PULSE_REDIS_PREFIX: "pulse:railway",
			PULSE_JANITOR_DRAIN_GRACE_SECONDS: "60",
			PULSE_JANITOR_MAX_DRAIN_AGE_SECONDS: "86400",
			PULSE_WEBSOCKET_HEARTBEAT_SECONDS: "15",
			PULSE_WEBSOCKET_TTL_SECONDS: "45",
		},
	}

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			assert project_id == "project"
			assert environment_id == "env"
			return service_state.get(name)

		async def get_project_variables(
			self, *, project_id: str, environment_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			return {PULSE_INTERNAL_TOKEN: "secret-token"}

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			return dict(service_variables[service_id])

		async def create_service_domain(self, **_: object) -> str:
			raise AssertionError("ready external stack should already have a domain")

	monkeypatch.setattr("pulse_railway.stack.RailwayGraphQLClient", _FakeClient)

	result = await require_ready_stack(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			redis_service_name="pulse-redis",
			janitor_service_name="pulse-janitor",
		)
	)

	assert result.redis is None
	assert result.redis_url == redis_url
	assert result.server_address == "https://test.pulse.sc"
