from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pulse_railway import RailwayRedisSessionStore
from pulse_railway.config import DockerBuild, RailwayProject
from pulse_railway.constants import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	DEPLOYMENT_STATE_ACTIVE,
	DEPLOYMENT_STATE_DRAINING,
	PULSE_DEPLOYMENT_ID,
	PULSE_DEPLOYMENT_STATE,
	PULSE_DRAIN_STARTED_AT,
	REDIS_URL,
)
from pulse_railway.deployment import (
	DeploymentError,
	_list_deployment_services,
	_railway_session_store_from_app,
	default_service_prefix,
	deploy,
	generate_deployment_id,
	resolve_deployment_id_by_name,
	validate_backend_env_vars,
)
from pulse_railway.railway import ServiceRecord
from pulse_railway.stack import StackServiceState, StackState


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


def test_validate_backend_env_vars_rejects_managed_names() -> None:
	with pytest.raises(DeploymentError, match="PORT"):
		validate_backend_env_vars({"PORT": "9000", "FEATURE_FLAG": "enabled"})


def test_validate_backend_env_vars_allows_unmanaged_redis_url() -> None:
	validate_backend_env_vars({REDIS_URL: "redis://app-cache:6379/0"})


def test_validate_backend_env_vars_rejects_managed_redis_url() -> None:
	with pytest.raises(DeploymentError, match="REDIS_URL"):
		validate_backend_env_vars(
			{REDIS_URL: "redis://app-cache:6379/0"},
			managed_env_vars={REDIS_URL},
		)


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
async def test_deploy_happy_path_on_ready_stack(monkeypatch, tmp_path) -> None:
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
	project_variables = {ACTIVE_DEPLOYMENT_VARIABLE: "prod-old"}
	variables: list[tuple[str | None, str, str]] = []
	group_updates: list[tuple[str, str, str]] = []

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
			if service_id is None:
				project_variables[name] = value
				return
			service_variables.setdefault(service_id, {})[name] = value

		async def update_service_instance(self, **kwargs: Any) -> None:
			assert kwargs["start_command"]

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
			assert environment_id == "env"
			return f"deploy-{service_id}"

		async def wait_for_deployment(self, *, deployment_id: str) -> dict[str, str]:
			return {"id": deployment_id, "status": "SUCCESS"}

		async def get_project_variables(
			self, *, project_id: str, environment_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			return dict(project_variables)

		async def get_environment_config(
			self, *, project_id: str, environment_id: str
		) -> dict[str, Any]:
			assert project_id == "project"
			assert environment_id == "env"
			return {"services": {"svc-router": {"groupId": "group-baseline"}}}

		async def set_service_group_id(
			self, *, environment_id: str, service_id: str, group_id: str
		) -> None:
			assert environment_id == "env"
			group_updates.append((environment_id, service_id, group_id))

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

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(**_: Any) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				image="ttl.sh/router:24h",
				domain="pulse-router-production.up.railway.app",
			),
			janitor=StackServiceState(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				image="ttl.sh/router:24h",
			),
			redis=StackServiceState(
				service_id="svc-redis",
				service_name="pulse-redis",
			),
			internal_token="secret-token",
			redis_url="redis://pulse-router-redis.railway.internal:6379",
			server_address="https://test.pulse.sc",
		)

	monkeypatch.setattr(
		"pulse_railway.deployment.require_ready_stack",
		fake_require_ready_stack,
	)

	async def fake_build_and_push_image(*, docker: DockerBuild, image_ref: str) -> str:
		assert docker.build_args["APP_FILE"] == "examples/aws-ecs/main.py"
		assert docker.build_args["WEB_ROOT"] == "examples/aws-ecs/web"
		assert docker.build_args["PULSE_SERVER_ADDRESS"] == "https://test.pulse.sc"
		return image_ref

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
			redis_service_name="pulse-redis",
			janitor_service_name="pulse-janitor",
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
	assert result.janitor_service_name == "pulse-janitor"
	assert result.router_deployment_id is None
	assert result.router_status is None
	assert result.janitor_deployment_id is None
	assert result.server_address == "https://test.pulse.sc"
	assert group_updates == [("env", result.backend_service_id, "group-baseline")]
	assert (None, ACTIVE_DEPLOYMENT_VARIABLE, "prod-260402-120000") in variables
	assert not any(
		service_id == result.backend_service_id and key == REDIS_URL
		for service_id, key, _value in variables
	)
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
	assert service_variables["svc-old-1"][PULSE_DRAIN_STARTED_AT] == "123.0"
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

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			return ServiceRecord(id="svc-1", name=name)

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)
	monkeypatch.setattr(
		"pulse_railway.deployment.require_ready_stack",
		lambda **_: StackState(
			router=StackServiceState("svc-router", "pulse-router"),
			janitor=StackServiceState("svc-janitor", "pulse-janitor"),
			redis=StackServiceState("svc-redis", "pulse-redis"),
			internal_token="secret-token",
			redis_url="redis://pulse-router-redis.railway.internal:6379",
			server_address="https://test.pulse.sc",
		),
	)

	with pytest.raises(DeploymentError, match="already exists"):
		await deploy(
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
			deployment_id="prod-260402-120000",
		)


@pytest.mark.asyncio
async def test_deploy_fails_when_stack_not_ready(monkeypatch, tmp_path) -> None:
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

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			return None

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(**_: Any) -> StackState:
		raise DeploymentError("router service pulse-router not found")

	monkeypatch.setattr(
		"pulse_railway.deployment.require_ready_stack",
		fake_require_ready_stack,
	)

	with pytest.raises(DeploymentError, match="router service pulse-router not found"):
		await deploy(
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

	service_state: dict[str, ServiceRecord] = {}
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
			return service_state.get(name)

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

		async def get_project_variables(
			self, *, project_id: str, environment_id: str
		) -> dict[str, str]:
			return {}

		async def get_environment_config(
			self, *, project_id: str, environment_id: str
		) -> dict[str, Any]:
			return {"services": {}}

		async def set_service_group_id(
			self, *, environment_id: str, service_id: str, group_id: str
		) -> None:
			raise AssertionError("backend should not be grouped without router group")

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			return list(service_state.values())

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			return dict(service_variables.get(service_id, {}))

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(**_: Any) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				domain="pulse-router-production.up.railway.app",
			),
			janitor=StackServiceState("svc-janitor", "pulse-janitor"),
			redis=StackServiceState("svc-redis", "pulse-redis"),
			internal_token="secret-token",
			redis_url="redis://project-public:6379",
			server_address="https://test.pulse.sc",
		)

	monkeypatch.setattr(
		"pulse_railway.deployment.require_ready_stack",
		fake_require_ready_stack,
	)

	async def fake_build_and_push_image(*, docker: DockerBuild, image_ref: str) -> str:
		assert docker.build_args["PULSE_SERVER_ADDRESS"] == "https://test.pulse.sc"
		return image_ref

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
		service_variables[backend_service.id][REDIS_URL]
		== "redis://pulse-router-redis.railway.internal:6379"
	)
	assert (
		service_variables[backend_service.id][PULSE_DEPLOYMENT_STATE]
		== DEPLOYMENT_STATE_ACTIVE
	)
	assert service_variables[backend_service.id][PULSE_DRAIN_STARTED_AT] == ""
