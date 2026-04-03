from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pulse_railway.config import DockerBuild, RailwayProject
from pulse_railway.constants import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	DEFAULT_JANITOR_CRON_SCHEDULE,
	RAILWAY_DEPLOYMENT_ID_ENV,
	RAILWAY_INTERNAL_TOKEN_ENV,
	RAILWAY_REDIS_PREFIX_ENV,
	RAILWAY_REDIS_URL_ENV,
)
from pulse_railway.deployment import (
	JANITOR_START_COMMAND,
	DeploymentError,
	_list_deployment_services,
	default_service_prefix,
	deploy,
	generate_deployment_id,
)
from pulse_railway.railway import ServiceDomain, ServiceRecord, TemplateRecord
from pulse_railway.tracker import MemoryDeploymentTracker


def test_generate_deployment_id_and_prefix() -> None:
	deployment_id = generate_deployment_id("Production Main")
	assert deployment_id.startswith("production-")
	assert len(deployment_id) <= 24
	assert default_service_prefix("pulse-router") == "pulse-"


@pytest.mark.asyncio
async def test_list_deployment_services_fetches_variables_concurrently() -> None:
	services = [
		ServiceRecord(id="svc-1", name="pulse-prod-1"),
		ServiceRecord(id="svc-2", name="pulse-prod-2"),
		ServiceRecord(id="svc-3", name="pulse-prod-3"),
	]
	in_flight = 0
	max_in_flight = 0

	class _FakeClient:
		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			assert project_id == "project"
			assert environment_id == "env"
			return services

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			nonlocal in_flight, max_in_flight
			assert project_id == "project"
			assert environment_id == "env"
			in_flight += 1
			max_in_flight = max(max_in_flight, in_flight)
			await asyncio.sleep(0)
			in_flight -= 1
			if service_id == "svc-2":
				return {}
			return {RAILWAY_DEPLOYMENT_ID_ENV: f"dep-{service_id}"}

	deployments = await _list_deployment_services(
		_FakeClient(),
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
		),
	)

	assert deployments == [
		("dep-svc-1", "pulse-prod-1"),
		("dep-svc-3", "pulse-prod-3"),
	]
	assert max_in_flight > 1


@pytest.mark.asyncio
async def test_deploy_happy_path(monkeypatch, tmp_path) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")

	service_state: dict[str, ServiceRecord] = {
		"pulse-prod-prev": ServiceRecord(id="svc-old-1", name="pulse-prod-prev"),
		"pulse-prod-old": ServiceRecord(id="svc-old-2", name="pulse-prod-old"),
	}
	service_variables: dict[str, dict[str, str]] = {
		"svc-old-1": {RAILWAY_DEPLOYMENT_ID_ENV: "prod-prev"},
		"svc-old-2": {RAILWAY_DEPLOYMENT_ID_ENV: "prod-old"},
	}
	variables: list[tuple[str | None, str, str]] = []
	service_instance_updates: list[dict[str, Any]] = []
	memory_tracker = MemoryDeploymentTracker()

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

		async def get_project_variables(
			self, *, project_id: str, environment_id: str, service_id: str | None = None
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			assert service_id is None
			return {
				ACTIVE_DEPLOYMENT_VARIABLE: "prod-prev",
				RAILWAY_INTERNAL_TOKEN_ENV: "secret-token",
			}

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
			return dict(service_variables.get(service_id, {}))

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
			variables.append((service_id, name, value))
			if service_id is not None:
				service_variables.setdefault(service_id, {})[name] = value

		async def update_service_instance(self, **kwargs: Any) -> None:
			service_instance_updates.append(kwargs)

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
			assert target_port == 8000
			for service in service_state.values():
				if service.id != service_id:
					continue
				domain = "pulse-router-production.up.railway.app"
				service.domains = [
					ServiceDomain(id="domain-1", domain=domain, target_port=target_port)
				]
				return domain
			raise AssertionError(service_id)

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)
	monkeypatch.setattr(
		"pulse_railway.deployment.RedisDeploymentTracker.from_url",
		lambda **_: memory_tracker,
	)

	async def fake_build_router_image(*, image_ref: str) -> str:
		return image_ref

	async def fake_build_and_push_image(*, docker: DockerBuild, image_ref: str) -> str:
		assert docker.build_args["APP_FILE"] == "examples/aws-ecs/main.py"
		assert docker.build_args["WEB_ROOT"] == "examples/aws-ecs/web"
		assert docker.build_args["PULSE_SERVER_ADDRESS"].startswith(
			"https://pulse-router"
		)
		return image_ref

	monkeypatch.setattr(
		"pulse_railway.deployment.build_router_image",
		fake_build_router_image,
	)
	monkeypatch.setattr(
		"pulse_railway.deployment.build_and_push_image",
		fake_build_and_push_image,
	)

	result = await deploy(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			redis_url="redis://test",
		),
		docker=DockerBuild(
			dockerfile_path=dockerfile,
			context_path=tmp_path,
		),
		deployment_id="prod-260402-120000",
		app_file="examples/aws-ecs/main.py",
		web_root="examples/aws-ecs/web",
	)

	assert result.backend_service_name == "pulse-prod-260402-120000"
	assert result.router_service_name == "pulse-router"
	assert result.janitor_service_name == "pulse-router-janitor"
	assert result.server_address == "https://pulse-router-production.up.railway.app"
	assert (None, ACTIVE_DEPLOYMENT_VARIABLE, "prod-260402-120000") in variables
	assert (
		result.router_service_id,
		RAILWAY_REDIS_URL_ENV,
		"redis://test",
	) in variables
	assert (
		result.router_service_id,
		RAILWAY_REDIS_PREFIX_ENV,
		"pulse:railway",
	) in variables
	assert (
		result.janitor_service_id,
		RAILWAY_INTERNAL_TOKEN_ENV,
		"secret-token",
	) in variables
	janitor_update = next(
		update
		for update in service_instance_updates
		if update["service_id"] == result.janitor_service_id
	)
	assert janitor_update["cron_schedule"] == DEFAULT_JANITOR_CRON_SCHEDULE
	assert janitor_update["restart_policy_type"] == "NEVER"
	assert janitor_update["start_command"] == JANITOR_START_COMMAND
	draining = await memory_tracker.list_draining_deployments()
	assert {deployment.deployment_id for deployment in draining} == {
		"prod-prev",
		"prod-old",
	}


@pytest.mark.asyncio
async def test_deploy_rejects_duplicate_deployment(monkeypatch, tmp_path) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def get_project_variables(
			self, *, project_id: str, environment_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			return {}

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			return ServiceRecord(id="svc-1", name=name)

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	with pytest.raises(DeploymentError, match="already exists"):
		await deploy(
			project=RailwayProject(
				project_id="project",
				environment_id="env",
				token="token",
				service_name="pulse-router",
				redis_url="redis://test",
			),
			docker=DockerBuild(
				dockerfile_path=dockerfile,
				context_path=tmp_path,
			),
			deployment_id="prod-260402-120000",
		)


@pytest.mark.asyncio
async def test_deploy_provisions_redis_when_missing(monkeypatch, tmp_path) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")

	service_state: dict[str, ServiceRecord] = {}
	service_variables: dict[str, dict[str, str]] = {}
	memory_tracker = MemoryDeploymentTracker()
	template_deploys: list[str] = []
	tracker_urls: list[str] = []
	service_instance_updates: list[dict[str, Any]] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			self.service_counter = 0

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def get_project_variables(
			self, *, project_id: str, environment_id: str, service_id: str | None = None
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			assert service_id is None
			return {}

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			service = next(
				record for record in service_state.values() if record.id == service_id
			)
			if service.name == "pulse-router-redis":
				return {
					"REDIS_URL": "redis://pulse-router-redis.railway.internal:6379",
					"REDIS_PUBLIC_URL": "redis://public-host:6379",
				}
			return dict(service_variables.get(service_id, {}))

		async def get_template_by_code(self, *, code: str) -> TemplateRecord:
			assert code == "redis"
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
			assert project_id == "project"
			assert environment_id == "env"
			assert template_id == "template-1"
			service_name = serialized_config["services"]["template-service"]["name"]
			self.service_counter += 1
			service_state[service_name] = ServiceRecord(
				id=f"svc-{self.service_counter}",
				name=service_name,
			)
			template_deploys.append(service_name)
			return "workflow-1"

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

		async def upsert_variable(self, **kwargs: Any) -> None:
			service_id = kwargs.get("service_id")
			if service_id is not None:
				service_variables.setdefault(service_id, {})[kwargs["name"]] = kwargs[
					"value"
				]

		async def update_service_instance(self, **kwargs: Any) -> None:
			service_instance_updates.append(kwargs)

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
			assert target_port == 8000
			for service in service_state.values():
				if service.id != service_id:
					continue
				domain = "pulse-router-production.up.railway.app"
				service.domains = [
					ServiceDomain(id="domain-1", domain=domain, target_port=target_port)
				]
				return domain
			raise AssertionError(service_id)

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)
	monkeypatch.setattr(
		"pulse_railway.deployment.RedisDeploymentTracker.from_url",
		lambda **kwargs: tracker_urls.append(kwargs["url"]) or memory_tracker,
	)

	async def fake_build_router_image(*, image_ref: str) -> str:
		return image_ref

	async def fake_build_and_push_image(*, docker: DockerBuild, image_ref: str) -> str:
		assert docker.build_args["PULSE_SERVER_ADDRESS"].startswith(
			"https://pulse-router"
		)
		return image_ref

	monkeypatch.setattr(
		"pulse_railway.deployment.build_router_image",
		fake_build_router_image,
	)
	monkeypatch.setattr(
		"pulse_railway.deployment.build_and_push_image",
		fake_build_and_push_image,
	)

	project = RailwayProject(
		project_id="project",
		environment_id="env",
		token="token",
		service_name="pulse-router",
		service_prefix="Pulse",
	)
	docker = DockerBuild(
		dockerfile_path=dockerfile,
		context_path=tmp_path,
		build_args={"KEEP": "1"},
	)

	result = await deploy(
		project=project,
		docker=docker,
		deployment_id="prod-260402-120000",
	)

	assert result.janitor_service_name == "pulse-router-janitor"
	assert "pulse-router-redis" in template_deploys
	assert tracker_urls == ["redis://public-host:6379"]
	assert project.service_prefix == "Pulse"
	assert project.redis_url is None
	assert docker.build_args == {"KEEP": "1"}
	janitor_update = next(
		update
		for update in service_instance_updates
		if update["service_id"] == result.janitor_service_id
	)
	assert janitor_update["cron_schedule"] == DEFAULT_JANITOR_CRON_SCHEDULE
	assert janitor_update["restart_policy_type"] == "NEVER"
	assert janitor_update["start_command"] == JANITOR_START_COMMAND
