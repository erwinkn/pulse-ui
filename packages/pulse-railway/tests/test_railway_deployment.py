from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pulse_railway import RailwayRedisSessionStore
from pulse_railway.config import DockerBuild, RailwayProject
from pulse_railway.constants import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	DEFAULT_JANITOR_CRON_SCHEDULE,
	DEPLOYMENT_STATE_ACTIVE,
	DEPLOYMENT_STATE_DRAINING,
	PULSE_DEPLOYMENT_ID,
	PULSE_DEPLOYMENT_STATE,
	PULSE_DRAIN_STARTED_AT,
	PULSE_INTERNAL_TOKEN,
	PULSE_REDIS_PREFIX,
	PULSE_REDIS_URL,
)
from pulse_railway.deployment import (
	JANITOR_START_COMMAND,
	DeploymentError,
	_list_deployment_services,
	_railway_session_store_from_app,
	default_service_prefix,
	deploy,
	generate_deployment_id,
	resolve_deployment_id_by_name,
)
from pulse_railway.railway import ServiceDomain, ServiceRecord, TemplateRecord


def _write_app_fixture(
	root,
	*,
	relative_path: str = "main.py",
	session_store_expr: str = "None",
) -> None:
	app_path = root / relative_path
	app_path.parent.mkdir(parents=True, exist_ok=True)
	if session_store_expr == "None":
		app_path.write_text("import pulse as ps\napp = ps.App()\n")
		return
	app_path.write_text(
		"import pulse as ps\n"
		"from pulse_railway import redis_session_store\n"
		f"app = ps.App(session_store={session_store_expr})\n"
	)


def test_generate_deployment_id_and_prefix() -> None:
	deployment_id = generate_deployment_id("Production Main")
	assert deployment_id.startswith("production-")
	assert len(deployment_id) <= 24
	assert default_service_prefix("pulse-router") == "pulse-"


def test_railway_session_store_from_app_uses_declared_helper(tmp_path) -> None:
	app_file = tmp_path / "main.py"
	app_file.write_text(
		"import pulse as ps\n"
		"from pulse_railway import redis_session_store\n"
		"app = ps.App(\n"
		"    session_store=redis_session_store()\n"
		")\n"
	)

	spec = _railway_session_store_from_app("main.py", tmp_path)

	assert isinstance(spec, RailwayRedisSessionStore)


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
			return {PULSE_DEPLOYMENT_ID: f"dep-{service_id}"}

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
async def test_resolve_deployment_id_by_name_matches_single_prefix(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

	async def fake_list(
		client: object, *, project: RailwayProject
	) -> list[tuple[str, str]]:
		assert isinstance(client, _FakeClient)
		assert project.project_id == "project"
		return [
			("redis-smoke-260405-120000", "pulse-redis-smoke-260405-120000"),
			("prod-260405-120001", "pulse-prod-260405-120001"),
		]

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)
	monkeypatch.setattr(
		"pulse_railway.deployment._list_deployment_services",
		fake_list,
	)

	deployment_id = await resolve_deployment_id_by_name(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
		),
		deployment_name="redis smoke",
	)

	assert deployment_id == "redis-smoke-260405-120000"


@pytest.mark.asyncio
async def test_resolve_deployment_id_by_name_requires_unique_match(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

	async def fake_list(
		client: object, *, project: RailwayProject
	) -> list[tuple[str, str]]:
		assert isinstance(client, _FakeClient)
		assert project.project_id == "project"
		return [
			("redis-smoke-260405-120000", "pulse-redis-smoke-260405-120000"),
			("redis-smoke-260405-130000", "pulse-redis-smoke-260405-130000"),
		]

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)
	monkeypatch.setattr(
		"pulse_railway.deployment._list_deployment_services",
		fake_list,
	)

	with pytest.raises(DeploymentError, match="is ambiguous"):
		await resolve_deployment_id_by_name(
			project=RailwayProject(
				project_id="project",
				environment_id="env",
				token="token",
				service_name="pulse-router",
			),
			deployment_name="redis-smoke",
		)


@pytest.mark.asyncio
async def test_deploy_happy_path(monkeypatch, tmp_path) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path, relative_path="examples/aws-ecs/main.py")

	service_state: dict[str, ServiceRecord] = {
		"pulse-prod-prev": ServiceRecord(id="svc-old-1", name="pulse-prod-prev"),
		"pulse-prod-old": ServiceRecord(id="svc-old-2", name="pulse-prod-old"),
	}
	service_variables: dict[str, dict[str, str]] = {
		"svc-old-1": {
			PULSE_DEPLOYMENT_ID: "prod-prev",
			PULSE_DEPLOYMENT_STATE: DEPLOYMENT_STATE_DRAINING,
			PULSE_DRAIN_STARTED_AT: "123.0",
		},
		"svc-old-2": {
			PULSE_DEPLOYMENT_ID: "prod-old",
			PULSE_DEPLOYMENT_STATE: DEPLOYMENT_STATE_ACTIVE,
		},
	}
	variables: list[tuple[str | None, str, str]] = []
	service_instance_updates: list[dict[str, Any]] = []

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
				PULSE_INTERNAL_TOKEN: "secret-token",
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
			variables = dict(service_variables.get(service_id, {}))
			service = next(
				(
					record
					for record in service_state.values()
					if record.id == service_id
				),
				None,
			)
			if service is not None and service.name == "pulse-router":
				variables["RAILWAY_PUBLIC_DOMAIN"] = "test.pulse.sc"
			return variables

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

	async def fake_build_router_image(*, image_ref: str) -> str:
		return image_ref

	async def fake_build_and_push_image(*, docker: DockerBuild, image_ref: str) -> str:
		assert docker.build_args["APP_FILE"] == "examples/aws-ecs/main.py"
		assert docker.build_args["WEB_ROOT"] == "examples/aws-ecs/web"
		assert docker.build_args["PULSE_SERVER_ADDRESS"] == "https://test.pulse.sc"
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

	assert result.backend_service_name == "prod-260402-120000"
	assert result.router_service_name == "pulse-router"
	assert result.janitor_service_name == "pulse-router-janitor"
	assert result.server_address == "https://test.pulse.sc"
	assert (None, ACTIVE_DEPLOYMENT_VARIABLE, "prod-260402-120000") in variables
	assert (
		result.router_service_id,
		PULSE_REDIS_URL,
		"redis://test",
	) in variables
	assert not any(
		service_id == result.backend_service_id and key == PULSE_REDIS_URL
		for service_id, key, _value in variables
	)
	assert (
		result.router_service_id,
		PULSE_REDIS_PREFIX,
		"pulse:railway",
	) in variables
	assert (
		result.janitor_service_id,
		PULSE_INTERNAL_TOKEN,
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
	assert (
		service_variables[result.backend_service_id][PULSE_DEPLOYMENT_STATE]
		== DEPLOYMENT_STATE_ACTIVE
	)
	assert service_variables[result.backend_service_id][PULSE_DRAIN_STARTED_AT] == ""
	assert service_variables["svc-old-1"][PULSE_DEPLOYMENT_STATE] == (
		DEPLOYMENT_STATE_DRAINING
	)
	assert service_variables["svc-old-2"][PULSE_DEPLOYMENT_STATE] == (
		DEPLOYMENT_STATE_DRAINING
	)
	assert service_variables["svc-old-1"][PULSE_DRAIN_STARTED_AT] != "123.0"
	assert (
		service_variables["svc-old-1"][PULSE_DRAIN_STARTED_AT]
		== service_variables["svc-old-2"][PULSE_DRAIN_STARTED_AT]
	)
	assert service_variables["svc-old-2"][PULSE_DRAIN_STARTED_AT]


@pytest.mark.asyncio
async def test_deploy_rejects_duplicate_deployment(monkeypatch, tmp_path) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path)

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
	_write_app_fixture(
		tmp_path,
		session_store_expr="redis_session_store()",
	)

	service_state: dict[str, ServiceRecord] = {}
	service_variables: dict[str, dict[str, str]] = {}
	template_deploys: list[str] = []
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
			if service.name == "pulse-router":
				return {"RAILWAY_PUBLIC_DOMAIN": "test.pulse.sc"}
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

	async def fake_build_router_image(*, image_ref: str) -> str:
		return image_ref

	async def fake_build_and_push_image(*, docker: DockerBuild, image_ref: str) -> str:
		assert docker.build_args["PULSE_SERVER_ADDRESS"] == "https://test.pulse.sc"
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
	assert (
		service_variables[result.backend_service_id][PULSE_REDIS_URL]
		== "redis://pulse-router-redis.railway.internal:6379"
	)
	assert (
		service_variables[result.backend_service_id][PULSE_DEPLOYMENT_STATE]
		== DEPLOYMENT_STATE_ACTIVE
	)
	assert service_variables[result.backend_service_id][PULSE_DRAIN_STARTED_AT] == ""
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


@pytest.mark.asyncio
async def test_deploy_keeps_shared_app_redis_canonical(monkeypatch, tmp_path) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(
		tmp_path,
		session_store_expr=(
			"redis_session_store("
			"url='redis://pulse-router-redis.railway.internal:6379'"
			")"
		),
	)

	service_state: dict[str, ServiceRecord] = {
		"pulse-router-redis": ServiceRecord(id="svc-redis", name="pulse-router-redis")
	}
	service_variables: dict[str, dict[str, str]] = {}

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
			return {PULSE_INTERNAL_TOKEN: "secret-token"}

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
				(
					record
					for record in service_state.values()
					if record.id == service_id
				),
				None,
			)
			if service is not None and service.name == "pulse-router":
				return {"RAILWAY_PUBLIC_DOMAIN": "test.pulse.sc"}
			if service_id == "svc-redis":
				return {
					"REDIS_URL": "redis://pulse-router-redis.railway.internal:6379",
					"REDIS_PUBLIC_URL": "redis://public-host:6379",
				}
			return dict(service_variables.get(service_id, {}))

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
			return None

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

	async def fake_build_router_image(*, image_ref: str) -> str:
		return image_ref

	async def fake_build_and_push_image(*, docker: DockerBuild, image_ref: str) -> str:
		assert docker.build_args["PULSE_SERVER_ADDRESS"] == "https://test.pulse.sc"
		return image_ref

	monkeypatch.setattr(
		"pulse_railway.deployment.build_router_image",
		fake_build_router_image,
	)
	monkeypatch.setattr(
		"pulse_railway.deployment.build_and_push_image",
		fake_build_and_push_image,
	)

	await deploy(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			redis_url="redis://project-public:6379",
		),
		docker=DockerBuild(
			dockerfile_path=dockerfile,
			context_path=tmp_path,
		),
		deployment_id="next",
	)

	backend_service = next(
		service for service in service_state.values() if service.name == "next"
	)
	assert (
		service_variables[backend_service.id][PULSE_REDIS_URL]
		== "redis://pulse-router-redis.railway.internal:6379"
	)
	assert (
		service_variables[backend_service.id][PULSE_DEPLOYMENT_STATE]
		== DEPLOYMENT_STATE_ACTIVE
	)
	assert service_variables[backend_service.id][PULSE_DRAIN_STARTED_AT] == ""


@pytest.mark.asyncio
async def test_deploy_marks_non_active_services_draining_with_service_variables(
	monkeypatch, tmp_path
) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path)

	service_state: dict[str, ServiceRecord] = {
		"pulse-prev": ServiceRecord(id="svc-old", name="pulse-prev"),
	}
	service_variables: dict[str, dict[str, str]] = {
		"svc-old": {PULSE_DEPLOYMENT_ID: "prev"},
	}

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
			return {PULSE_INTERNAL_TOKEN: "secret-token"}

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
				(
					record
					for record in service_state.values()
					if record.id == service_id
				),
				None,
			)
			if service is not None and service.name == "pulse-router":
				return {"RAILWAY_PUBLIC_DOMAIN": "test.pulse.sc"}
			if service_id == "svc-redis":
				return {"REDIS_URL": "redis://pulse-router-redis.railway.internal:6379"}
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
			service_state[service_name] = ServiceRecord(
				id="svc-redis", name=service_name
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
			return None

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

	async def fake_build_router_image(*, image_ref: str) -> str:
		return image_ref

	async def fake_build_and_push_image(*, docker: DockerBuild, image_ref: str) -> str:
		assert docker.build_args["PULSE_SERVER_ADDRESS"] == "https://test.pulse.sc"
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
		),
		docker=DockerBuild(
			dockerfile_path=dockerfile,
			context_path=tmp_path,
		),
		deployment_id="next",
	)

	assert result.server_address == "https://test.pulse.sc"
	assert service_variables["svc-old"][PULSE_DEPLOYMENT_STATE] == (
		DEPLOYMENT_STATE_DRAINING
	)
	assert service_variables["svc-old"][PULSE_DRAIN_STARTED_AT]
	assert (
		service_variables[result.backend_service_id][PULSE_DEPLOYMENT_STATE]
		== DEPLOYMENT_STATE_ACTIVE
	)
	assert service_variables[result.backend_service_id][PULSE_DRAIN_STARTED_AT] == ""
