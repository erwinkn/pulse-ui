from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pytest
from pulse_railway.cli import (
	JANITOR_RUN_RUNTIME_ERROR,
	_add_deploy_args,
	_add_init_args,
	_add_janitor_run_args,
	_add_upgrade_args,
	_run_delete,
	_run_deploy,
	_run_init,
	_run_janitor_run,
	_run_remove,
	_run_upgrade,
	main,
)
from pulse_railway.deployment import DeploymentError, DeployResult
from pulse_railway.janitor import JanitorResult
from pulse_railway.stack import InitResult, StackServiceResult, UpgradeResult


def _make_init_args(**overrides: Any) -> argparse.Namespace:
	values: dict[str, Any] = {
		"app_file": "main.py",
		"project_id": "project",
		"environment_id": "env",
		"workspace_id": None,
		"project_name": None,
		"token": "token",
		"service_prefix": None,
		"redis_url": None,
		"redis_prefix": "pulse:railway",
		"router_image": None,
		"janitor_image": None,
		"janitor_cron_schedule": "*/5 * * * *",
		"drain_grace_seconds": 60,
		"max_drain_age_seconds": 86400,
		"backend_port": 8000,
		"router_replicas": 1,
	}
	values.update(overrides)
	return argparse.Namespace(**values)


def _make_upgrade_args(**overrides: Any) -> argparse.Namespace:
	return _make_init_args(**overrides)


def _make_deploy_args(**overrides: Any) -> argparse.Namespace:
	values: dict[str, Any] = {
		"deployment_name": None,
		"deployment_id": None,
		"project_id": "project",
		"environment_id": "env",
		"token": "token",
		"service_prefix": None,
		"server_address": None,
		"app_file": "main.py",
		"web_root": "web",
		"dockerfile": "Dockerfile",
		"context": ".",
		"image_repository": None,
		"build_arg": [],
		"env": [],
		"backend_port": 8000,
		"backend_replicas": 1,
	}
	values.update(overrides)
	return argparse.Namespace(**values)


def _install_fake_init(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
	init_call: dict[str, Any] = {}

	async def fake_bootstrap_stack(**kwargs: Any) -> InitResult:
		init_call.update(kwargs)
		return InitResult(
			router=StackServiceResult(
				service_id="svc-router",
				service_name="pulse-router",
				domain="pulse-router-production.up.railway.app",
				created=True,
				deployed=True,
				deployment_id="deploy-router",
				status="SUCCESS",
			),
			janitor=StackServiceResult(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				created=True,
				deployed=True,
				deployment_id="deploy-janitor",
				status="SUCCESS",
			),
			redis=StackServiceResult(
				service_id="svc-redis",
				service_name="pulse-redis",
				created=True,
			),
			internal_token_created=True,
			redis_url="redis://pulse-router-redis.railway.internal:6379",
			server_address="https://pulse-router-production.up.railway.app",
		)

	monkeypatch.setattr(
		"pulse_railway.commands.init.bootstrap_stack", fake_bootstrap_stack
	)
	return init_call


def _install_fake_upgrade(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
	upgrade_call: dict[str, Any] = {}

	async def fake_upgrade_stack(**kwargs: Any) -> UpgradeResult:
		upgrade_call.update(kwargs)
		return UpgradeResult(
			router=StackServiceResult(
				service_id="svc-router",
				service_name="pulse-router",
				domain="pulse-router-production.up.railway.app",
				deployed=True,
				deployment_id="deploy-router",
				status="SUCCESS",
			),
			janitor=StackServiceResult(
				service_id="svc-janitor",
				service_name="pulse-janitor",
				deployed=True,
				deployment_id="deploy-janitor",
				status="SUCCESS",
			),
			redis=StackServiceResult(
				service_id="svc-redis",
				service_name="pulse-redis",
			),
			internal_token_created=False,
			redis_url="redis://pulse-router-redis.railway.internal:6379",
			server_address="https://pulse-router-production.up.railway.app",
		)

	monkeypatch.setattr(
		"pulse_railway.commands.upgrade.upgrade_stack",
		fake_upgrade_stack,
	)
	return upgrade_call


def _install_fake_deploy(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
	deploy_call: dict[str, Any] = {}

	async def fake_deploy(**kwargs: Any) -> DeployResult:
		deploy_call.update(kwargs)
		return DeployResult(
			deployment_id="prod-260402-120000",
			backend_service_id="svc-2",
			backend_service_name="prod-260402-120000",
			backend_image="ttl.sh/backend:24h",
			router_service_id="svc-1",
			router_service_name="pulse-router",
			router_image="ttl.sh/router:24h",
			router_domain="pulse-router-production.up.railway.app",
			server_address="https://pulse-router-production.up.railway.app",
			backend_deployment_id="deploy-svc-2",
			backend_status="SUCCESS",
			janitor_service_id="svc-3",
			janitor_service_name="pulse-janitor",
		)

	monkeypatch.setattr("pulse_railway.commands.deploy.deploy", fake_deploy)
	return deploy_call


def _write_deploy_fixture(root: Path) -> None:
	(root / "web").mkdir(parents=True)
	(root / "Dockerfile").write_text("FROM scratch\n")
	(root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		"app = ps.App(routes=[], plugins=[RailwayPlugin()])\n"
	)


def test_init_parser_reads_env_overrides(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_RAILWAY_APP_FILE", "examples/aws-ecs/main.py")
	monkeypatch.setenv("PULSE_RAILWAY_JANITOR_CRON_SCHEDULE", "0 */6 * * *")
	parser = argparse.ArgumentParser()

	_add_init_args(parser)
	args = parser.parse_args([])

	assert args.app_file == "examples/aws-ecs/main.py"
	assert args.janitor_cron_schedule == "0 */6 * * *"
	assert args.redis_url is None


def test_init_parser_reads_workspace_env_override(monkeypatch) -> None:
	monkeypatch.setenv("RAILWAY_WORKSPACE_ID", "workspace")
	parser = argparse.ArgumentParser()

	_add_init_args(parser)
	args = parser.parse_args([])

	assert args.workspace_id == "workspace"


def test_upgrade_parser_reads_env_overrides(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_RAILWAY_ROUTER_IMAGE", "ghcr.io/pulse/router:1")
	parser = argparse.ArgumentParser()

	_add_upgrade_args(parser)
	args = parser.parse_args([])

	assert args.router_image == "ghcr.io/pulse/router:1"


def test_deploy_parser_drops_stable_stack_flags(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_RAILWAY_APP_FILE", "examples/aws-ecs/main.py")
	parser = argparse.ArgumentParser()

	_add_deploy_args(parser)
	args = parser.parse_args([])

	assert args.app_file == "examples/aws-ecs/main.py"
	assert not hasattr(args, "redis_url")
	assert not hasattr(args, "janitor_cron_schedule")
	assert not hasattr(args, "router_image")


def test_janitor_parser_reads_service_env_defaults(monkeypatch) -> None:
	monkeypatch.setenv("RAILWAY_PROJECT_ID", "project")
	monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env")
	monkeypatch.setenv("RAILWAY_TOKEN", "token")
	parser = argparse.ArgumentParser()

	_add_janitor_run_args(parser)
	args = parser.parse_args([])

	assert args.project_id == "project"
	assert args.environment_id == "env"
	assert args.token == "token"


@pytest.mark.asyncio
async def test_run_init_reads_target_from_railway_plugin(monkeypatch, tmp_path) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		"app = ps.App(\n"
		"    routes=[],\n"
		"    plugins=[\n"
		'        RailwayPlugin(project_id="project", environment_id="env")\n'
		"    ],\n"
		")\n"
	)
	init_call = _install_fake_init(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_init(
		_make_init_args(
			project_id=None,
			environment_id=None,
			token="token",
		)
	)

	assert result == 0
	assert init_call["project"].project_id == "project"
	assert init_call["project"].environment_id == "env"
	assert init_call["project"].service_name == "pulse-router"
	assert init_call["project"].redis_service_name == "pulse-redis"
	assert init_call["project"].janitor_service_name == "pulse-janitor"


@pytest.mark.asyncio
async def test_run_init_creates_project_when_project_id_missing(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	init_call = _install_fake_init(monkeypatch)
	client_calls: dict[str, Any] = {}

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def create_project(
			self,
			*,
			name: str,
			workspace_id: str,
			default_environment_name: str | None = None,
		) -> str:
			client_calls["name"] = name
			client_calls["workspace_id"] = workspace_id
			client_calls["default_environment_name"] = default_environment_name
			return "project-created"

		async def list_environments(self, *, project_id: str) -> list[Any]:
			client_calls["project_id"] = project_id
			return [type("Env", (), {"id": "env-created", "name": "production"})()]

	monkeypatch.setattr("pulse_railway.commands.init.RailwayGraphQLClient", _FakeClient)
	monkeypatch.chdir(project_root)

	result = await _run_init(
		_make_init_args(
			project_id=None,
			environment_id=None,
			workspace_id="workspace",
			project_name=None,
			token="token",
		)
	)

	assert result == 0
	assert client_calls["name"] == "main"
	assert client_calls["workspace_id"] == "workspace"
	assert client_calls["project_id"] == "project-created"
	assert init_call["project"].project_id == "project-created"
	assert init_call["project"].environment_id == "env-created"


@pytest.mark.asyncio
async def test_run_init_resolves_project_token_when_project_id_missing(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	init_call = _install_fake_init(monkeypatch)

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def graphql(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
			assert kwargs["auth_mode"] == "project-token"
			return {
				"projectToken": {
					"projectId": "project-from-token",
					"environmentId": "env-from-token",
				}
			}

		async def create_project(self, **kwargs: Any) -> str:
			raise AssertionError("project token should not create a new project")

	monkeypatch.setattr("pulse_railway.commands.init.RailwayGraphQLClient", _FakeClient)
	monkeypatch.chdir(project_root)

	result = await _run_init(
		_make_init_args(
			project_id=None,
			environment_id=None,
			workspace_id=None,
			project_name=None,
			token="token",
		)
	)

	assert result == 0
	assert init_call["project"].project_id == "project-from-token"
	assert init_call["project"].environment_id == "env-from-token"


@pytest.mark.asyncio
async def test_run_init_prefers_explicit_project_name_for_created_project(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	_install_fake_init(monkeypatch)
	client_calls: dict[str, Any] = {}

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def create_project(
			self,
			*,
			name: str,
			workspace_id: str,
			default_environment_name: str | None = None,
		) -> str:
			client_calls["name"] = name
			return "project-created"

		async def list_environments(self, *, project_id: str) -> list[Any]:
			return [type("Env", (), {"id": "env-created", "name": "production"})()]

	monkeypatch.setattr("pulse_railway.commands.init.RailwayGraphQLClient", _FakeClient)
	monkeypatch.chdir(project_root)

	await _run_init(
		_make_init_args(
			project_id=None,
			environment_id=None,
			workspace_id="workspace",
			project_name="custom-project",
			token="token",
		)
	)

	assert client_calls["name"] == "custom-project"


@pytest.mark.asyncio
async def test_run_upgrade_reads_target_from_railway_plugin(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	upgrade_call = _install_fake_upgrade(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_upgrade(_make_upgrade_args())

	assert result == 0
	assert upgrade_call["project"].service_name == "pulse-router"
	assert upgrade_call["project"].redis_service_name == "pulse-redis"
	assert upgrade_call["project"].janitor_service_name == "pulse-janitor"


@pytest.mark.asyncio
async def test_run_deploy_resolves_paths_and_defaults(monkeypatch, tmp_path) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args())

	assert result == 0
	assert deploy_call["project"].service_prefix is None
	assert deploy_call["project"].service_name == "pulse-router"
	assert deploy_call["project"].redis_service_name == "pulse-redis"
	assert deploy_call["project"].janitor_service_name == "pulse-janitor"
	assert deploy_call["docker"].dockerfile_path == (project_root / "Dockerfile")
	assert deploy_call["docker"].context_path == project_root


@pytest.mark.asyncio
async def test_run_deploy_passes_env_vars_to_backend(monkeypatch, tmp_path) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(
		_make_deploy_args(
			env=[
				"FEATURE_FLAG=enabled",
				"EMPTY_ALLOWED=",
				"REDIS_URL=redis://app-cache:6379/0",
			]
		)
	)

	assert result == 0
	assert deploy_call["project"].env_vars == {
		"FEATURE_FLAG": "enabled",
		"EMPTY_ALLOWED": "",
		"REDIS_URL": "redis://app-cache:6379/0",
	}


@pytest.mark.asyncio
async def test_run_deploy_rejects_reserved_backend_env_vars(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	_install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	with pytest.raises(DeploymentError, match="PULSE_DEPLOYMENT_ID"):
		await _run_deploy(_make_deploy_args(env=["PULSE_DEPLOYMENT_ID=wrong"]))


@pytest.mark.asyncio
async def test_run_deploy_reads_target_from_railway_plugin(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		"app = ps.App(\n"
		"    routes=[],\n"
		"    plugins=[\n"
		'        RailwayPlugin(project_id="project", environment_id="env", deployment_name="staging")\n'
		"    ],\n"
		")\n"
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(
		_make_deploy_args(
			project_id=None,
			environment_id=None,
			token="token",
			service_prefix=None,
		)
	)

	assert result == 0
	assert deploy_call["project"].project_id == "project"
	assert deploy_call["project"].environment_id == "env"
	assert deploy_call["deployment_name"] == "staging"
	assert deploy_call["project"].service_name == "pulse-router"
	assert deploy_call["project"].service_prefix is None
	assert deploy_call["project"].redis_service_name == "pulse-redis"
	assert deploy_call["project"].janitor_service_name == "pulse-janitor"


@pytest.mark.asyncio
async def test_run_deploy_env_overrides_plugin_deployment_name(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		'app = ps.App(routes=[], plugins=[RailwayPlugin(deployment_name="staging")])\n'
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)
	monkeypatch.setenv("PULSE_RAILWAY_DEPLOYMENT_NAME", "preview")

	result = await _run_deploy(_make_deploy_args(deployment_name=None))

	assert result == 0
	assert deploy_call["deployment_name"] == "preview"


@pytest.mark.asyncio
async def test_run_deploy_uses_literal_stable_service_names_without_prefix(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		"app = ps.App(routes=[], plugins=[RailwayPlugin(router_service='api')])\n"
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args())

	assert result == 0
	assert deploy_call["project"].service_name == "api"
	assert deploy_call["project"].service_prefix is None
	assert deploy_call["project"].redis_service_name == "pulse-redis"
	assert deploy_call["project"].janitor_service_name == "pulse-janitor"


@pytest.mark.asyncio
async def test_run_deploy_requires_railway_plugin(monkeypatch, tmp_path) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	(project_root / "web").mkdir(parents=True)
	(project_root / "Dockerfile").write_text("FROM scratch\n")
	(project_root / "main.py").write_text(
		"import pulse as ps\napp = ps.App(routes=[])\n"
	)
	_install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	with pytest.raises(ValueError, match="RailwayPlugin not found on app"):
		await _run_deploy(_make_deploy_args())


@pytest.mark.asyncio
async def test_run_deploy_requires_context_relative_app_paths(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	_install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	with pytest.raises(ValueError, match="app-file must be relative"):
		await _run_deploy(_make_deploy_args(app_file=str(project_root / "main.py")))


@pytest.mark.asyncio
async def test_run_delete_builds_shared_project_defaults(monkeypatch) -> None:
	delete_call: dict[str, Any] = {}

	async def fake_delete_deployment(**kwargs: Any) -> None:
		delete_call.update(kwargs)

	monkeypatch.setattr("pulse_railway.cli.delete_deployment", fake_delete_deployment)

	result = await _run_delete(
		argparse.Namespace(
			service="pulse-router",
			deployment_id="prod-260402-120000",
			project_id="project",
			environment_id="env",
			token="token",
			service_prefix="Custom",
			keep_active_variable=False,
			redis_url=None,
			redis_service=None,
			redis_prefix="pulse:railway",
		)
	)

	assert result == 0
	assert delete_call["project"].service_prefix == "custom-"
	assert delete_call["project"].redis_service_name == "pulse-router-redis"
	assert delete_call["clear_active"] is True


@pytest.mark.asyncio
async def test_run_remove_resolves_name_then_deletes(
	monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
	delete_call: dict[str, Any] = {}
	resolve_call: dict[str, Any] = {}

	async def fake_resolve_deployment_id_by_name(**kwargs: Any) -> str:
		resolve_call.update(kwargs)
		return "redis-smoke-260405-120000"

	async def fake_delete_deployment(**kwargs: Any) -> None:
		delete_call.update(kwargs)

	monkeypatch.setattr(
		"pulse_railway.cli.resolve_deployment_id_by_name",
		fake_resolve_deployment_id_by_name,
	)
	monkeypatch.setattr("pulse_railway.cli.delete_deployment", fake_delete_deployment)

	result = await _run_remove(
		argparse.Namespace(
			service="pulse-router",
			deployment_name="redis-smoke",
			project_id="project",
			environment_id="env",
			token="token",
			service_prefix=None,
			keep_active_variable=False,
			redis_url=None,
			redis_service=None,
			redis_prefix="pulse:railway",
		)
	)

	assert result == 0
	assert resolve_call["deployment_name"] == "redis-smoke"
	assert delete_call["deployment_id"] == "redis-smoke-260405-120000"
	assert delete_call["project"].redis_service_name == "pulse-router-redis"
	assert capsys.readouterr().out == "redis-smoke-260405-120000\n"


@pytest.mark.asyncio
async def test_run_janitor_run_invokes_janitor(monkeypatch) -> None:
	janitor_call: dict[str, Any] = {}

	async def fake_run_janitor(**kwargs: Any) -> JanitorResult:
		janitor_call.update(kwargs)
		return JanitorResult(lock_acquired=True, scanned_count=1)

	monkeypatch.setattr("pulse_railway.cli.run_janitor", fake_run_janitor)
	monkeypatch.setenv("RAILWAY_SERVICE_ID", "svc-janitor")

	result = await _run_janitor_run(
		argparse.Namespace(
			service="pulse-router",
			project_id="project",
			environment_id="env",
			token="token",
			service_prefix=None,
			redis_url=None,
			redis_service=None,
			redis_prefix="pulse:railway",
			drain_grace_seconds=60,
			max_drain_age_seconds=86400,
		)
	)

	assert result == 0
	assert janitor_call["project"].redis_service_name == "pulse-router-redis"


@pytest.mark.asyncio
async def test_run_janitor_run_fails_outside_railway(monkeypatch) -> None:
	for name in ("RAILWAY_SERVICE_ID", "RAILWAY_REPLICA_ID", "RAILWAY_PRIVATE_DOMAIN"):
		monkeypatch.delenv(name, raising=False)

	with pytest.raises(SystemExit, match="must execute inside Railway"):
		await _run_janitor_run(
			argparse.Namespace(
				service="pulse-router",
				project_id="project",
				environment_id="env",
				token="token",
				service_prefix=None,
				redis_url=None,
				redis_service=None,
				redis_prefix="pulse:railway",
				drain_grace_seconds=60,
				max_drain_age_seconds=86400,
			)
		)


def test_main_janitor_help_mentions_railway_runtime(
	monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
	monkeypatch.setattr(
		sys,
		"argv",
		["pulse-railway", "janitor", "run", "--help"],
	)

	with pytest.raises(SystemExit) as excinfo:
		main()
	assert excinfo.value.code == 0

	help_text = capsys.readouterr().out
	assert "Run janitor cleanup inside a Railway service runtime." in help_text
	assert "fails immediately outside Railway." in help_text


def test_janitor_runtime_error_message_is_actionable() -> None:
	assert "not a local shell" in JANITOR_RUN_RUNTIME_ERROR


def test_print_janitor_result_lock_not_acquired(
	capsys: pytest.CaptureFixture[str],
) -> None:
	from pulse_railway.cli import _print_janitor_result

	_print_janitor_result(JanitorResult(lock_acquired=False))

	assert capsys.readouterr().out == "skipped; lock already held\n"


def test_print_janitor_result_timeline(capsys: pytest.CaptureFixture[str]) -> None:
	from pulse_railway.cli import _print_janitor_result

	_print_janitor_result(
		JanitorResult(
			lock_acquired=True,
			scanned_count=3,
			deleted_deployments=["deploy9", "deploy8"],
			force_deleted_deployments=["deploy8"],
			skipped_deployments=["deploy7"],
		)
	)

	assert capsys.readouterr().out == (
		"scan start; draining=3\n"
		"delete deploy9; reason=drainable\n"
		"delete deploy8; reason=max_drain_age\n"
		"keep deploy7; reason=still_active\n"
		"scan complete; deleted=2 skipped=1\n"
	)
