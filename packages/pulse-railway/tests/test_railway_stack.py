from __future__ import annotations

from typing import Any

import pytest
from pulse_railway.config import RailwayProject
from pulse_railway.constants import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	DEFAULT_PULSE_BASELINE_NO_REDIS_TEMPLATE_CODE,
	DEFAULT_PULSE_BASELINE_TEMPLATE_CODE,
	PULSE_INTERNAL_TOKEN,
	PULSE_JANITOR_DRAIN_GRACE_SECONDS,
	PULSE_JANITOR_MAX_DRAIN_AGE_SECONDS,
	PULSE_REDIS_PREFIX,
	PULSE_REDIS_URL,
	PULSE_WEBSOCKET_HEARTBEAT_SECONDS,
	PULSE_WEBSOCKET_TTL_SECONDS,
)
from pulse_railway.errors import DeploymentError
from pulse_railway.railway import ServiceDomain, ServiceRecord, TemplateRecord
from pulse_railway.stack import (
	JANITOR_START_COMMAND,
	ROUTER_START_COMMAND,
	bootstrap_stack,
	require_ready_stack,
	upgrade_stack,
)


@pytest.mark.asyncio
async def test_bootstrap_stack_creates_baseline_from_empty_project(monkeypatch) -> None:
	service_state: dict[str, ServiceRecord] = {}
	service_variables: dict[str, dict[str, str]] = {}
	project_variables: dict[str, str] = {}
	service_updates: list[dict[str, Any]] = []
	domain_targets: list[str] = []
	deployed_templates: list[str] = []

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

	async def fake_build_router_image(*, image_ref: str) -> str:
		return image_ref

	monkeypatch.setattr(
		"pulse_railway.stack.build_router_image", fake_build_router_image
	)

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
	assert result.janitor.created is True
	assert result.janitor.deployed is True
	assert result.redis is not None
	assert result.redis.created is True
	assert result.internal_token_created is True
	assert result.redis_url == "redis://pulse-redis.railway.internal:6379"
	assert result.server_address == "https://test.pulse.sc"
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
	assert PULSE_REDIS_URL in service_variables[result.router.service_id]
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
async def test_bootstrap_stack_is_idempotent_for_existing_stack(monkeypatch) -> None:
	service_state: dict[str, ServiceRecord] = {
		"pulse-router": ServiceRecord(
			id="svc-router",
			name="pulse-router",
			image="ttl.sh/router:old",
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
	}
	service_variables = {
		"svc-router": {
			"RAILWAY_TOKEN": "token",
			"RAILWAY_PROJECT_ID": "project",
			"RAILWAY_ENVIRONMENT_ID": "env",
			"PULSE_BACKEND_PORT": "8000",
			"PORT": "8000",
			PULSE_REDIS_URL: "redis://pulse-redis.railway.internal:6379",
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
			PULSE_REDIS_URL: "redis://pulse-redis.railway.internal:6379",
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

	assert result.router.created is False
	assert result.router.deployed is False
	assert result.janitor.created is False
	assert result.janitor.deployed is False
	assert result.redis is not None
	assert result.redis.created is False
	assert result.internal_token_created is False
	assert result.server_address == "https://test.pulse.sc"
	assert create_calls == []
	assert deploy_calls == []


@pytest.mark.asyncio
async def test_bootstrap_stack_fails_for_partial_baseline(monkeypatch) -> None:
	service_state: dict[str, ServiceRecord] = {
		"pulse-router": ServiceRecord(id="svc-router", name="pulse-router")
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
			return service_state.get(name)

	monkeypatch.setattr("pulse_railway.stack.RailwayGraphQLClient", _FakeClient)

	with pytest.raises(DeploymentError, match="pulse-railway upgrade"):
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


@pytest.mark.asyncio
async def test_bootstrap_stack_uses_no_redis_template_for_external_redis(
	monkeypatch,
) -> None:
	service_state: dict[str, ServiceRecord] = {}
	service_variables: dict[str, dict[str, str]] = {}
	project_variables: dict[str, str] = {}
	template_codes: list[str] = []

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
			assert code == DEFAULT_PULSE_BASELINE_NO_REDIS_TEMPLATE_CODE
			return TemplateRecord(
				id="template-no-redis",
				code=code,
				serialized_config={
					"services": {
						"template-router": {"name": "pulse-router"},
						"template-janitor": {"name": "pulse-janitor"},
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

		async def update_service_instance(self, **kwargs: Any) -> None:
			return None

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

	async def fake_build_router_image(*, image_ref: str) -> str:
		return image_ref

	monkeypatch.setattr(
		"pulse_railway.stack.build_router_image", fake_build_router_image
	)

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

	assert template_codes == [DEFAULT_PULSE_BASELINE_NO_REDIS_TEMPLATE_CODE]
	assert result.redis is None
	assert result.redis_url == "redis://external.example:6379"


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
	}
	redis_url = "redis://external.example:6379"
	service_variables = {
		"svc-router": {
			"RAILWAY_TOKEN": "token",
			"RAILWAY_PROJECT_ID": "project",
			"RAILWAY_ENVIRONMENT_ID": "env",
			"PULSE_BACKEND_PORT": "8000",
			"PORT": "8000",
			PULSE_REDIS_URL: redis_url,
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
			PULSE_REDIS_URL: redis_url,
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


@pytest.mark.asyncio
async def test_upgrade_stack_reconciles_and_creates_missing_services(
	monkeypatch,
) -> None:
	service_state: dict[str, ServiceRecord] = {
		"pulse-router": ServiceRecord(id="svc-router", name="pulse-router"),
	}
	service_variables: dict[str, dict[str, str]] = {}
	project_variables: dict[str, str] = {
		PULSE_INTERNAL_TOKEN: "secret-token",
		ACTIVE_DEPLOYMENT_VARIABLE: "prod-1",
	}
	service_updates: list[dict[str, Any]] = []
	project_upserts: list[str] = []

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
				id="template-1",
				code="redis",
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
			service_name = serialized_config["services"]["template-service"]["name"]
			self.service_counter += 1
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
			if service.name == "pulse-redis":
				return {"REDIS_URL": "redis://pulse-redis.railway.internal:6379"}
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
				project_upserts.append(kwargs["name"])
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

	async def fake_build_router_image(*, image_ref: str) -> str:
		return image_ref

	monkeypatch.setattr(
		"pulse_railway.stack.build_router_image", fake_build_router_image
	)

	result = await upgrade_stack(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			redis_service_name="pulse-redis",
			janitor_service_name="pulse-janitor",
		)
	)

	assert result.router.deployed is True
	assert result.janitor.deployed is True
	assert result.janitor.created is True
	assert result.redis is not None
	assert result.redis.created is True
	assert result.internal_token_created is False
	assert result.server_address == "https://test.pulse.sc"
	assert ACTIVE_DEPLOYMENT_VARIABLE not in project_upserts
	assert any(
		update["start_command"] == ROUTER_START_COMMAND for update in service_updates
	)
	assert any(
		update["start_command"] == JANITOR_START_COMMAND for update in service_updates
	)
