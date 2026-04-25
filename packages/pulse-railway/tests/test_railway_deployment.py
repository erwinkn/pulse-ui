from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pulse_railway.config import DockerBuild, RailwayProject
from pulse_railway.constants import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	DEPLOYMENT_STATE_ACTIVE,
	DEPLOYMENT_STATE_DRAINING,
	PULSE_DEPLOYMENT_ID,
	PULSE_DEPLOYMENT_STATE,
	PULSE_DRAIN_STARTED_AT,
	PULSE_INTERNAL_TOKEN,
	PULSE_RAILWAY_REDIS_URL,
	REDIS_URL,
)
from pulse_railway.deployment import (
	DeploymentError,
	_list_deployment_services,
	_pulse_env_reference_variables,
	_run_command,
	_uses_railway_session_store_from_app,
	check_reserved_source_build_args,
	default_service_prefix,
	deploy,
	generate_deployment_id,
	railway_up_command,
	redeploy_deployment,
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
		"from pulse_railway import RailwaySessionStore\n"
		f"app = ps.App(session_store={session_store_expr})\n"
	)


@pytest.fixture(autouse=True)
def _stub_pulse_env_reference_variables(monkeypatch: pytest.MonkeyPatch) -> None:
	async def fake_pulse_env_reference_variables(
		*_args: object, **_kwargs: object
	) -> dict[str, str]:
		return {}

	monkeypatch.setattr(
		"pulse_railway.deployment._pulse_env_reference_variables",
		fake_pulse_env_reference_variables,
	)


def test_generate_deployment_id_and_prefix() -> None:
	deployment_id = generate_deployment_id("Production Main")
	assert deployment_id.startswith("production-")
	assert len(deployment_id) <= 24
	assert default_service_prefix("pulse-router") == "pulse-"


def test_railway_up_command_targets_service_context() -> None:
	assert railway_up_command(
		project_id="project",
		environment_id="env",
		service_name="backend",
		context_path=Path("/tmp/project"),
	) == [
		"railway",
		"up",
		"/tmp/project",
		"--project",
		"project",
		"--environment",
		"env",
		"--service",
		"backend",
		"--ci",
		"--path-as-root",
	]


@pytest.mark.asyncio
async def test_run_command_replaces_railway_token_env(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	captured_env: dict[str, str] = {}
	monkeypatch.setenv("RAILWAY_TOKEN", "ambient-project-token")
	monkeypatch.setenv("RAILWAY_API_TOKEN", "ambient-api-token")

	class _FakeProcess:
		returncode = 0

		async def communicate(self) -> tuple[bytes, bytes]:
			return b"", b""

	async def fake_create_subprocess_exec(
		*args: str,
		cwd: str | None = None,
		env: dict[str, str] | None = None,
		stdout: object = None,
		stderr: object = None,
	) -> _FakeProcess:
		_ = args, cwd, stdout, stderr
		assert env is not None
		captured_env.update(env)
		return _FakeProcess()

	monkeypatch.setattr(
		"pulse_railway.deployment.asyncio.create_subprocess_exec",
		fake_create_subprocess_exec,
	)

	await _run_command("railway", "up", env_vars={"RAILWAY_API_TOKEN": "api-token"})

	assert captured_env["RAILWAY_API_TOKEN"] == "api-token"
	assert "RAILWAY_TOKEN" not in captured_env


@pytest.mark.asyncio
async def test_pulse_env_reference_variables_only_uses_unrendered_user_vars() -> None:
	requests: list[dict[str, object]] = []

	class _FakeClient:
		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			assert project_id == "project"
			assert environment_id == "env"
			assert name == "pulse-env"
			return ServiceRecord(id="svc-env", name="pulse-env")

		async def get_project_variables(self, **kwargs: object) -> dict[str, str]:
			requests.append(dict(kwargs))
			return {
				"SANDBOX_THEME": "amber",
				"SANDBOX_MESSAGE": "from-pulse-env",
				"RAILWAY_PRIVATE_DOMAIN": "pulse-env.railway.internal",
				"PORT": "8000",
			}

	result = await _pulse_env_reference_variables(
		_FakeClient(),  # pyright: ignore[reportArgumentType]
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
		),
	)

	assert result == {
		"SANDBOX_THEME": "${{pulse-env.SANDBOX_THEME}}",
		"SANDBOX_MESSAGE": "${{pulse-env.SANDBOX_MESSAGE}}",
	}
	assert requests == [
		{
			"project_id": "project",
			"environment_id": "env",
			"service_id": "svc-env",
			"unrendered": True,
		}
	]


def test_validate_backend_env_vars_rejects_managed_names() -> None:
	with pytest.raises(DeploymentError, match="PORT"):
		validate_backend_env_vars({"PORT": "9000", "FEATURE_FLAG": "enabled"})


def test_validate_backend_env_vars_rejects_managed_railway_redis_url() -> None:
	with pytest.raises(DeploymentError, match=PULSE_RAILWAY_REDIS_URL):
		validate_backend_env_vars({PULSE_RAILWAY_REDIS_URL: "redis://managed:6379/0"})


def test_validate_backend_env_vars_allows_unmanaged_redis_url() -> None:
	validate_backend_env_vars({REDIS_URL: "redis://app-cache:6379/0"})


def test_check_reserved_source_build_args_rejects_managed_runtime_names() -> None:
	with pytest.raises(DeploymentError, match="PORT"):
		check_reserved_source_build_args({"PORT": "3000", "FEATURE_BUILD": "enabled"})


def test_check_reserved_source_build_args_allows_source_build_names() -> None:
	check_reserved_source_build_args(
		{
			"APP_FILE": "examples/railway/main.py",
			"WEB_ROOT": "examples/railway/web",
			"RAILWAY_DOCKERFILE_PATH": "examples/Dockerfile",
		}
	)


@pytest.mark.asyncio
async def test_deploy_source_rejects_managed_source_build_args_before_app_load(
	tmp_path,
) -> None:
	with pytest.raises(DeploymentError, match="PORT"):
		await deploy(
			project=RailwayProject(
				project_id="project",
				environment_id="env",
				token="token",
				service_name="pulse-router",
			),
			docker=DockerBuild(
				dockerfile_path=tmp_path / "Dockerfile",
				context_path=tmp_path,
				build_args={"PORT": "3000"},
			),
			app_file="missing.py",
		)


@pytest.mark.asyncio
async def test_deploy_rejects_no_gitignore_with_image_repository(tmp_path) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path)

	with pytest.raises(DeploymentError, match="--no-gitignore"):
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
				image_repository="ghcr.io/acme/app",
			),
			deployment_id="prod-260402-120000",
			no_gitignore=True,
		)


def test_uses_railway_session_store_from_app_detects_declared_constructor(
	tmp_path,
) -> None:
	app_file = tmp_path / "main.py"
	app_file.write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwaySessionStore\n"
		"app = ps.App(\n"
		"    session_store=RailwaySessionStore()\n"
		")\n"
	)

	uses_railway_session_store = _uses_railway_session_store_from_app(
		"main.py", tmp_path
	)

	assert uses_railway_session_store is True


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
async def test_redeploy_deployment_defaults_to_active_deployment(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	calls: list[tuple[str, str]] = []

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
			return {ACTIVE_DEPLOYMENT_VARIABLE: "prod-260402-120000"}

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			assert project_id == "project"
			assert environment_id == "env"
			assert name == "prod-260402-120000"
			return ServiceRecord(id="svc-backend", name=name)

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
			calls.append((service_id, environment_id))
			return "deploy-backend"

		async def wait_for_deployment(self, *, deployment_id: str) -> dict[str, str]:
			assert deployment_id == "deploy-backend"
			return {"id": deployment_id, "status": "SUCCESS"}

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	result = await redeploy_deployment(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
		)
	)

	assert result.deployment_id == "prod-260402-120000"
	assert result.backend_service_id == "svc-backend"
	assert result.backend_deployment_id == "deploy-backend"
	assert calls == [("svc-backend", "env")]


@pytest.mark.asyncio
async def test_redeploy_deployment_uses_explicit_deployment_id(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	looked_up_names: list[str] = []

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
			raise AssertionError("explicit deployment id should skip active lookup")

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			looked_up_names.append(name)
			return ServiceRecord(id="svc-explicit", name=name)

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
			return "deploy-explicit"

		async def wait_for_deployment(self, *, deployment_id: str) -> dict[str, str]:
			return {"id": deployment_id, "status": "SUCCESS"}

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	result = await redeploy_deployment(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			service_prefix="app-",
		),
		deployment_id="prod-260402-120000",
	)

	assert result.backend_service_name == "app-prod-260402-120000"
	assert looked_up_names == ["app-prod-260402-120000"]


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
	deleted_variables: list[tuple[str, str, str]] = []
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
			assert service_id == "svc-1"
			deleted_variables.append((service_id, name, environment_id))
			service_variables[service_id].pop(name, None)

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

		async def get_service_latest_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str] | None:
			assert project_id == "project"
			assert environment_id == "env"
			assert service_id == "svc-1"
			return {"id": "dep-svc-1", "status": "SUCCESS", "createdAt": "now"}

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(**_: Any) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				image="ghcr.io/acme/router:24h",
				domain="pulse-router-production.up.railway.app",
			),
			janitor=StackServiceState(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				image="ghcr.io/acme/router:24h",
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

	async def fake_pulse_env_reference_variables(
		*_args: object, **_kwargs: object
	) -> dict[str, str]:
		return {"EXTERNAL_KEY": "${{pulse-env.EXTERNAL_KEY}}"}

	monkeypatch.setattr(
		"pulse_railway.deployment._pulse_env_reference_variables",
		fake_pulse_env_reference_variables,
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
			image_repository="ghcr.io/acme/app",
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
	assert service_variables[result.backend_service_id]["EXTERNAL_KEY"] == (
		"${{pulse-env.EXTERNAL_KEY}}"
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
async def test_deploy_source_happy_path_on_ready_stack(monkeypatch, tmp_path) -> None:
	dockerfile = tmp_path / "examples" / "Dockerfile"
	dockerfile.parent.mkdir(parents=True, exist_ok=True)
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(
		tmp_path,
		relative_path="examples/aws-ecs/main.py",
		session_store_expr='RailwaySessionStore(prefix="test")',
	)
	(tmp_path / "examples" / "aws-ecs" / "web").mkdir(parents=True)

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
	build_time_service_variables: list[dict[str, str]] = []
	run_command_calls: list[
		tuple[tuple[str, ...], str | None, dict[str, str] | None]
	] = []

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
			assert image is None
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
			assert kwargs.get("source_image") is None

		async def resolve_auth_mode(self) -> str:
			return "project-token"

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

		async def get_service_latest_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str] | None:
			assert project_id == "project"
			assert environment_id == "env"
			assert service_id == "svc-1"
			return {"id": "dep-svc-1", "status": "SUCCESS", "createdAt": "now"}

		async def deploy_service(self, *, service_id: str, environment_id: str) -> str:
			assert service_id == "svc-1"
			assert environment_id == "env"
			return "dep-runtime-1"

		async def wait_for_deployment(self, *, deployment_id: str) -> dict[str, str]:
			assert deployment_id == "dep-runtime-1"
			return {"id": deployment_id, "status": "SUCCESS"}

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(**_: Any) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				image="ghcr.io/acme/router:24h",
				domain="pulse-router-production.up.railway.app",
			),
			janitor=StackServiceState(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				image="ghcr.io/acme/router:24h",
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

	async def fake_pulse_env_reference_variables(
		*_args: object, **_kwargs: object
	) -> dict[str, str]:
		return {"EXTERNAL_KEY": "${{pulse-env.EXTERNAL_KEY}}"}

	monkeypatch.setattr(
		"pulse_railway.deployment._pulse_env_reference_variables",
		fake_pulse_env_reference_variables,
	)

	async def fake_run_command(
		*args: str, cwd: Path | None = None, env_vars: dict[str, str] | None = None
	) -> None:
		run_command_calls.append((args, None if cwd is None else str(cwd), env_vars))
		build_time_service_variables.append(dict(service_variables["svc-1"]))

	monkeypatch.setattr("pulse_railway.deployment._run_command", fake_run_command)

	result = await deploy(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			redis_service_name="pulse-redis",
			janitor_service_name="pulse-janitor",
			env_vars={"FEATURE_FLAG": "enabled"},
		),
		docker=DockerBuild(
			dockerfile_path=dockerfile,
			context_path=tmp_path,
			build_args={"FEATURE_BUILD": "on"},
		),
		deployment_id="prod-260402-120000",
		app_file="examples/aws-ecs/main.py",
		web_root="examples/aws-ecs/web",
	)

	assert result.backend_service_name == "prod-260402-120000"
	assert result.router_service_name == "pulse-router"
	assert result.janitor_service_name == "pulse-janitor"
	assert result.server_address == "https://test.pulse.sc"
	assert result.backend_deployment_id == "dep-svc-1"
	assert group_updates == [("env", result.backend_service_id, "group-baseline")]
	assert run_command_calls == [
		(
			(
				"railway",
				"up",
				str(tmp_path),
				"--project",
				"project",
				"--environment",
				"env",
				"--service",
				"prod-260402-120000",
				"--ci",
				"--path-as-root",
			),
			str(tmp_path),
			{"RAILWAY_TOKEN": "token"},
		)
	]
	assert build_time_service_variables == [
		{
			"PULSE_DEPLOYMENT_ID": "prod-260402-120000",
			PULSE_INTERNAL_TOKEN: "${{ shared.PULSE_RAILWAY_INTERNAL_TOKEN }}",
			"PULSE_APP_FILE": "examples/aws-ecs/main.py",
			"PULSE_SERVER_ADDRESS": "https://test.pulse.sc",
			"PORT": "8000",
			"PULSE_RAILWAY_REDIS_URL": (
				"redis://pulse-router-redis.railway.internal:6379"
			),
			"EXTERNAL_KEY": "${{pulse-env.EXTERNAL_KEY}}",
			"FEATURE_FLAG": "enabled",
			"APP_FILE": "examples/aws-ecs/main.py",
			"WEB_ROOT": "examples/aws-ecs/web",
			"FEATURE_BUILD": "on",
			"RAILWAY_DOCKERFILE_PATH": "examples/Dockerfile",
		}
	]
	assert (None, ACTIVE_DEPLOYMENT_VARIABLE, "prod-260402-120000") in variables
	assert service_variables[result.backend_service_id]["RAILWAY_DOCKERFILE_PATH"] == (
		"examples/Dockerfile"
	)
	assert service_variables[result.backend_service_id]["APP_FILE"] == (
		"examples/aws-ecs/main.py"
	)
	assert service_variables[result.backend_service_id]["WEB_ROOT"] == (
		"examples/aws-ecs/web"
	)
	assert service_variables[result.backend_service_id]["FEATURE_BUILD"] == "on"
	assert service_variables[result.backend_service_id]["EXTERNAL_KEY"] == (
		"${{pulse-env.EXTERNAL_KEY}}"
	)
	assert service_variables[result.backend_service_id]["FEATURE_FLAG"] == "enabled"
	assert service_variables[result.backend_service_id]["PULSE_SERVER_ADDRESS"] == (
		"https://test.pulse.sc"
	)
	assert service_variables[result.backend_service_id][PULSE_RAILWAY_REDIS_URL] == (
		"redis://pulse-router-redis.railway.internal:6379"
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
async def test_deploy_source_uses_railway_api_token_for_cli_when_present(
	monkeypatch,
	tmp_path,
) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path, relative_path="examples/aws-ecs/main.py")
	run_command_calls: list[dict[str, str] | None] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(self, **_: object) -> None:
			return None

		async def create_service(self, **_: object) -> str:
			return "svc-1"

		async def get_environment_config(self, **_: object) -> dict[str, object]:
			return {"services": {"svc-router": {"groupId": "group-baseline"}}}

		async def set_service_group_id(self, **_: object) -> None:
			return None

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			return [ServiceRecord(id="svc-1", name="prod-260402-120000")]

		async def get_service_variables_for_deployment(
			self, **_: object
		) -> dict[str, str]:
			return {PULSE_DEPLOYMENT_ID: "prod-260402-120000"}

		async def get_project_variables(self, **_: object) -> dict[str, str]:
			return {}

		async def upsert_variable(self, **_: object) -> None:
			return None

		async def update_service_instance(self, **_: object) -> None:
			return None

		async def resolve_auth_mode(self) -> str:
			return "project-token"

		async def delete_variable(self, **_: object) -> None:
			return None

		async def get_service_latest_deployment(self, **_: object) -> dict[str, object]:
			return {"id": "dep-svc-1", "status": "SUCCESS", "deploymentStopped": False}

		async def deploy_service(self, **_: object) -> str:
			return "dep-runtime-1"

		async def wait_for_deployment(self, **_: object) -> dict[str, object]:
			return {"id": "dep-runtime-1", "status": "SUCCESS"}

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(*, project: RailwayProject) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				domain="pulse-router-production.up.railway.app",
				image="ghcr.io/acme/router:24h",
			),
			janitor=StackServiceState(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				image="ghcr.io/acme/router:24h",
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
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")

	async def fake_run_command(
		*args: str, cwd: Path | None = None, env_vars: dict[str, str] | None = None
	) -> None:
		run_command_calls.append(env_vars)

	monkeypatch.setattr("pulse_railway.deployment._run_command", fake_run_command)

	await deploy(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="api-token",
			service_name="pulse-router",
			redis_service_name="pulse-redis",
			janitor_service_name="pulse-janitor",
		),
		docker=DockerBuild(
			dockerfile_path=dockerfile,
			context_path=tmp_path,
			build_args={},
		),
		deployment_id="prod-260402-120000",
		app_file="examples/aws-ecs/main.py",
		web_root="examples/aws-ecs/web",
		cli_token_env_name="RAILWAY_API_TOKEN",
	)

	assert run_command_calls == [{"RAILWAY_API_TOKEN": "api-token"}]


@pytest.mark.asyncio
async def test_deploy_source_uses_bearer_env_for_unmatched_explicit_account_token(
	monkeypatch,
	tmp_path,
) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path, relative_path="examples/aws-ecs/main.py")
	run_command_calls: list[dict[str, str] | None] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(self, **_: object) -> None:
			return None

		async def create_service(self, **_: object) -> str:
			return "svc-1"

		async def get_environment_config(self, **_: object) -> dict[str, object]:
			return {"services": {"svc-router": {"groupId": "group-baseline"}}}

		async def set_service_group_id(self, **_: object) -> None:
			return None

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			return [ServiceRecord(id="svc-1", name="prod-260402-120000")]

		async def get_service_variables_for_deployment(
			self, **_: object
		) -> dict[str, str]:
			return {PULSE_DEPLOYMENT_ID: "prod-260402-120000"}

		async def get_project_variables(self, **_: object) -> dict[str, str]:
			return {}

		async def upsert_variable(self, **_: object) -> None:
			return None

		async def delete_variable(self, **_: object) -> None:
			return None

		async def update_service_instance(self, **_: object) -> None:
			return None

		async def resolve_auth_mode(self) -> str:
			return "bearer"

		async def get_service_latest_deployment(self, **_: object) -> dict[str, object]:
			return {"id": "dep-svc-1", "status": "SUCCESS", "deploymentStopped": False}

		async def deploy_service(self, **_: object) -> str:
			return "dep-runtime-1"

		async def wait_for_deployment(self, **_: object) -> dict[str, object]:
			return {"id": "dep-runtime-1", "status": "SUCCESS"}

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(*, project: RailwayProject) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				domain="pulse-router-production.up.railway.app",
				image="ghcr.io/acme/router:24h",
			),
			janitor=StackServiceState(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				image="ghcr.io/acme/router:24h",
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

	async def fake_run_command(
		*args: str, cwd: Path | None = None, env_vars: dict[str, str] | None = None
	) -> None:
		run_command_calls.append(env_vars)

	monkeypatch.setattr("pulse_railway.deployment._run_command", fake_run_command)

	await deploy(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="explicit-account-token",
			service_name="pulse-router",
			redis_service_name="pulse-redis",
			janitor_service_name="pulse-janitor",
		),
		docker=DockerBuild(
			dockerfile_path=dockerfile,
			context_path=tmp_path,
			build_args={},
		),
		deployment_id="prod-260402-120000",
		app_file="examples/aws-ecs/main.py",
		web_root="examples/aws-ecs/web",
		cli_token_env_name=None,
	)

	assert run_command_calls == [{"RAILWAY_API_TOKEN": "explicit-account-token"}]


@pytest.mark.asyncio
async def test_deploy_source_uses_project_token_env_for_explicit_token_override(
	monkeypatch,
	tmp_path,
) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path, relative_path="examples/aws-ecs/main.py")
	run_command_calls: list[dict[str, str] | None] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(self, **_: object) -> None:
			return None

		async def create_service(self, **_: object) -> str:
			return "svc-1"

		async def get_environment_config(self, **_: object) -> dict[str, object]:
			return {"services": {"svc-router": {"groupId": "group-baseline"}}}

		async def set_service_group_id(self, **_: object) -> None:
			return None

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			return [ServiceRecord(id="svc-1", name="prod-260402-120000")]

		async def get_service_variables_for_deployment(
			self, **_: object
		) -> dict[str, str]:
			return {PULSE_DEPLOYMENT_ID: "prod-260402-120000"}

		async def get_project_variables(self, **_: object) -> dict[str, str]:
			return {}

		async def upsert_variable(self, **_: object) -> None:
			return None

		async def update_service_instance(self, **_: object) -> None:
			return None

		async def resolve_auth_mode(self) -> str:
			return "project-token"

		async def delete_variable(self, **_: object) -> None:
			return None

		async def get_service_latest_deployment(self, **_: object) -> dict[str, object]:
			return {"id": "dep-svc-1", "status": "SUCCESS", "deploymentStopped": False}

		async def deploy_service(self, **_: object) -> str:
			return "dep-runtime-1"

		async def wait_for_deployment(self, **_: object) -> dict[str, object]:
			return {"id": "dep-runtime-1", "status": "SUCCESS"}

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(*, project: RailwayProject) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				domain="pulse-router-production.up.railway.app",
				image="ghcr.io/acme/router:24h",
			),
			janitor=StackServiceState(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				image="ghcr.io/acme/router:24h",
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
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")

	async def fake_run_command(
		*args: str, cwd: Path | None = None, env_vars: dict[str, str] | None = None
	) -> None:
		run_command_calls.append(env_vars)

	monkeypatch.setattr("pulse_railway.deployment._run_command", fake_run_command)

	await deploy(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="project-token",
			service_name="pulse-router",
			redis_service_name="pulse-redis",
			janitor_service_name="pulse-janitor",
		),
		docker=DockerBuild(
			dockerfile_path=dockerfile,
			context_path=tmp_path,
			build_args={},
		),
		deployment_id="prod-260402-120000",
		app_file="examples/aws-ecs/main.py",
		web_root="examples/aws-ecs/web",
		cli_token_env_name="RAILWAY_TOKEN",
	)

	assert run_command_calls == [{"RAILWAY_TOKEN": "project-token"}]


@pytest.mark.asyncio
async def test_deploy_source_cleans_up_failed_source_service(
	monkeypatch,
	tmp_path,
) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path, relative_path="examples/aws-ecs/main.py")
	deleted_services: list[tuple[str, str]] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(self, **_: object) -> None:
			return None

		async def create_service(self, **_: object) -> str:
			return "svc-1"

		async def get_environment_config(self, **_: object) -> dict[str, object]:
			return {"services": {"svc-router": {"groupId": "group-baseline"}}}

		async def set_service_group_id(self, **_: object) -> None:
			return None

		async def upsert_variable(self, **_: object) -> None:
			return None

		async def update_service_instance(self, **_: object) -> None:
			return None

		async def resolve_auth_mode(self) -> str:
			return "project-token"

		async def delete_service(self, *, service_id: str, environment_id: str) -> None:
			deleted_services.append((service_id, environment_id))

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(*, project: RailwayProject) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				domain="pulse-router-production.up.railway.app",
				image="ghcr.io/acme/router:24h",
			),
			janitor=StackServiceState(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				image="ghcr.io/acme/router:24h",
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

	async def fake_run_command(
		*args: str, cwd: Path | None = None, env_vars: dict[str, str] | None = None
	) -> None:
		raise DeploymentError("railway up failed")

	monkeypatch.setattr("pulse_railway.deployment._run_command", fake_run_command)

	with pytest.raises(DeploymentError, match="railway up failed"):
		await deploy(
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
				build_args={},
			),
			deployment_id="prod-260402-120000",
			app_file="examples/aws-ecs/main.py",
			web_root="examples/aws-ecs/web",
		)

	assert deleted_services == [("svc-1", "env")]


@pytest.mark.asyncio
async def test_deploy_source_keeps_service_when_post_build_polling_fails(
	monkeypatch,
	tmp_path,
) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path, relative_path="examples/aws-ecs/main.py")
	deleted_services: list[tuple[str, str]] = []

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(self, **_: object) -> None:
			return None

		async def create_service(self, **_: object) -> str:
			return "svc-1"

		async def get_environment_config(self, **_: object) -> dict[str, object]:
			return {"services": {"svc-router": {"groupId": "group-baseline"}}}

		async def set_service_group_id(self, **_: object) -> None:
			return None

		async def upsert_variable(self, **_: object) -> None:
			return None

		async def update_service_instance(self, **_: object) -> None:
			return None

		async def resolve_auth_mode(self) -> str:
			return "project-token"

		async def delete_service(self, *, service_id: str, environment_id: str) -> None:
			deleted_services.append((service_id, environment_id))

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(*, project: RailwayProject) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				domain="pulse-router-production.up.railway.app",
				image="ghcr.io/acme/router:24h",
			),
			janitor=StackServiceState(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				image="ghcr.io/acme/router:24h",
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

	async def fake_run_command(
		*args: str, cwd: Path | None = None, env_vars: dict[str, str] | None = None
	) -> None:
		return None

	async def fake_wait_for_latest_service_deployment(
		_client: object,
		**_: object,
	) -> dict[str, object]:
		raise TimeoutError("build polling timed out")

	monkeypatch.setattr("pulse_railway.deployment._run_command", fake_run_command)
	monkeypatch.setattr(
		"pulse_railway.deployment._wait_for_latest_service_deployment",
		fake_wait_for_latest_service_deployment,
	)

	with pytest.raises(TimeoutError, match="build polling timed out"):
		await deploy(
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
				build_args={},
			),
			deployment_id="prod-260402-120000",
			app_file="examples/aws-ecs/main.py",
			web_root="examples/aws-ecs/web",
		)

	assert deleted_services == []


@pytest.mark.asyncio
async def test_deploy_source_waits_through_transient_stopped_build_state(
	monkeypatch,
	tmp_path,
) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(tmp_path, relative_path="examples/aws-ecs/main.py")
	latest_states = [
		{"id": "dep-svc-1", "status": "BUILDING", "deploymentStopped": True},
		{"id": "dep-svc-1", "status": "INITIALIZING", "deploymentStopped": True},
		{"id": "dep-svc-1", "status": "SUCCESS", "deploymentStopped": False},
	]

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def find_service_by_name(self, **_: object) -> None:
			return None

		async def create_service(self, **_: object) -> str:
			return "svc-1"

		async def get_environment_config(self, **_: object) -> dict[str, object]:
			return {"services": {"svc-router": {"groupId": "group-baseline"}}}

		async def set_service_group_id(self, **_: object) -> None:
			return None

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			return [ServiceRecord(id="svc-1", name="prod-260402-120000")]

		async def get_service_variables_for_deployment(
			self, **_: object
		) -> dict[str, str]:
			return {PULSE_DEPLOYMENT_ID: "prod-260402-120000"}

		async def get_project_variables(self, **_: object) -> dict[str, str]:
			return {}

		async def upsert_variable(self, **_: object) -> None:
			return None

		async def update_service_instance(self, **_: object) -> None:
			return None

		async def resolve_auth_mode(self) -> str:
			return "project-token"

		async def delete_variable(self, **_: object) -> None:
			return None

		async def get_service_latest_deployment(self, **_: object) -> dict[str, object]:
			return latest_states.pop(0)

		async def deploy_service(self, **_: object) -> str:
			return "dep-runtime-1"

		async def wait_for_deployment(self, **_: object) -> dict[str, object]:
			return {"id": "dep-runtime-1", "status": "SUCCESS"}

	monkeypatch.setattr("pulse_railway.deployment.RailwayGraphQLClient", _FakeClient)

	async def fake_require_ready_stack(*, project: RailwayProject) -> StackState:
		return StackState(
			router=StackServiceState(
				service_id="svc-router",
				service_name="pulse-router",
				domain="pulse-router-production.up.railway.app",
				image="ghcr.io/acme/router:24h",
			),
			janitor=StackServiceState(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				image="ghcr.io/acme/router:24h",
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

	async def fake_run_command(
		*args: str, cwd: Path | None = None, env_vars: dict[str, str] | None = None
	) -> None:
		return None

	async def fast_sleep(_seconds: float) -> None:
		return None

	monkeypatch.setattr("pulse_railway.deployment._run_command", fake_run_command)
	monkeypatch.setattr("pulse_railway.deployment.asyncio.sleep", fast_sleep)

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
			build_args={},
		),
		deployment_id="prod-260402-120000",
		app_file="examples/aws-ecs/main.py",
		web_root="examples/aws-ecs/web",
	)

	assert result.backend_status == "SUCCESS"


@pytest.mark.asyncio
async def test_deploy_ignores_ambient_redis_url_for_managed_session_store(
	monkeypatch,
	tmp_path,
) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	(tmp_path / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwaySessionStore\n"
		"app = ps.App(\n"
		"    session_store=RailwaySessionStore()\n"
		")\n"
	)
	monkeypatch.setenv(REDIS_URL, "redis://local-dev:6379/0")

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
			redis_url="redis://railway-internal:6379/0",
			server_address="https://test.pulse.sc",
		)

	monkeypatch.setattr(
		"pulse_railway.deployment.require_ready_stack",
		fake_require_ready_stack,
	)

	async def fake_build_and_push_image(*, docker: DockerBuild, image_ref: str) -> str:
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
			image_repository="ghcr.io/acme/app",
		),
		deployment_id="next",
	)

	backend_service = next(
		service for service in service_state.values() if service.name == "next"
	)
	assert service_variables[backend_service.id][PULSE_RAILWAY_REDIS_URL] == (
		"redis://railway-internal:6379/0"
	)
	assert REDIS_URL not in service_variables[backend_service.id]


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
				image_repository="ghcr.io/acme/app",
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
				image_repository="ghcr.io/acme/app",
			),
			deployment_id="next",
		)


@pytest.mark.asyncio
async def test_deploy_always_injects_managed_railway_redis_url(
	monkeypatch, tmp_path
) -> None:
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")
	_write_app_fixture(
		tmp_path,
		session_store_expr="RailwaySessionStore(url='redis://custom:6379/0')",
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
			image_repository="ghcr.io/acme/app",
		),
		deployment_id="next",
	)

	backend_service = next(
		service for service in service_state.values() if service.name == "next"
	)
	assert (
		service_variables[backend_service.id][PULSE_RAILWAY_REDIS_URL]
		== "redis://project-public:6379"
	)
	assert (
		service_variables[backend_service.id][PULSE_DEPLOYMENT_STATE]
		== DEPLOYMENT_STATE_ACTIVE
	)
	assert service_variables[backend_service.id][PULSE_DRAIN_STARTED_AT] == ""
