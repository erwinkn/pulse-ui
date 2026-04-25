from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from pulse_railway.cli import (
	JANITOR_RUN_RUNTIME_ERROR,
	_add_deploy_args,
	_add_ensure_args,
	_add_janitor_run_args,
	_add_redeploy_args,
	_add_scaffold_args,
	_add_upgrade_args,
	_run_delete,
	_run_deploy,
	_run_ensure,
	_run_janitor_run,
	_run_redeploy,
	_run_remove,
	_run_scaffold,
	_run_upgrade,
	main,
)
from pulse_railway.deployment import (
	DeploymentError,
	DeployResult,
	RedeployResult,
)
from pulse_railway.janitor import JanitorResult
from pulse_railway.railway import EnvironmentRecord, ProjectRecord, ProjectTokenRecord
from pulse_railway.stack import InitResult, StackServiceResult


def _make_scaffold_args(**overrides: Any) -> argparse.Namespace:
	values: dict[str, Any] = {
		"app_file": "main.py",
		"workspace_id": None,
		"token": "token",
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


def _make_deploy_args(**overrides: Any) -> argparse.Namespace:
	values: dict[str, Any] = {
		"deployment_name": None,
		"deployment_id": None,
		"project": "project",
		"environment": "env",
		"token": "token",
		"service_prefix": None,
		"server_address": None,
		"app_file": "main.py",
		"web_root": None,
		"dockerfile": None,
		"context": ".",
		"image_repository": "ghcr.io/acme/app",
		"build_arg": [],
		"no_gitignore": False,
		"env": [],
		"backend_port": 8000,
		"backend_replicas": 1,
	}
	values.update(overrides)
	return argparse.Namespace(**values)


def _baseline_result(*, created: bool) -> InitResult:
	return InitResult(
		router=StackServiceResult(
			service_id="svc-router",
			service_name="pulse-router",
			domain="pulse-router-production.up.railway.app",
			created=created,
			deployed=True,
			deployment_id="deploy-router",
			status="SUCCESS",
		),
		janitor=StackServiceResult(
			service_id="svc-janitor",
			service_name="pulse-janitor",
			created=created,
			deployed=True,
			deployment_id="deploy-janitor",
			status="SUCCESS",
		),
		redis=StackServiceResult(
			service_id="svc-redis",
			service_name="pulse-redis",
			created=created,
		),
		internal_token_created=created,
		redis_url=(
			"redis://pulse-router-redis.railway.internal:6379"
			if created
			else "redis://pulse-redis.railway.internal:6379"
		),
		server_address="https://pulse-router-production.up.railway.app",
	)


def _install_fake_baseline(
	monkeypatch: pytest.MonkeyPatch,
	*,
	stack_function: str,
	created: bool,
) -> dict[str, Any]:
	baseline_call: dict[str, Any] = {}

	async def fake_resolve_railway_target_ids(**kwargs: Any) -> tuple[str, str]:
		baseline_call["target"] = kwargs
		return kwargs["project_name"] or "project-from-token", kwargs[
			"environment_name"
		] or "env-from-token"

	monkeypatch.setattr(
		"pulse_railway.commands.scaffold.resolve_railway_target_ids",
		fake_resolve_railway_target_ids,
	)

	async def fake_stack(**kwargs: Any) -> InitResult:
		baseline_call.update(kwargs)
		return _baseline_result(created=created)

	monkeypatch.setattr(f"pulse_railway.commands.scaffold.{stack_function}", fake_stack)
	return baseline_call


def _install_fake_scaffold(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
	return _install_fake_baseline(
		monkeypatch,
		stack_function="bootstrap_stack",
		created=True,
	)


def _install_fake_ensure(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
	return _install_fake_baseline(
		monkeypatch,
		stack_function="ensure_stack",
		created=False,
	)


def _install_fake_deploy(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
	deploy_call: dict[str, Any] = {}

	async def fake_resolve_railway_target_ids(**kwargs: Any) -> tuple[str, str]:
		deploy_call["target"] = kwargs
		return kwargs["project_name"] or "project-from-token", kwargs[
			"environment_name"
		] or "env-from-token"

	monkeypatch.setattr(
		"pulse_railway.commands.deploy.common.resolve_railway_target_ids",
		fake_resolve_railway_target_ids,
	)

	async def fake_deploy(**kwargs: Any) -> DeployResult:
		deploy_call.update(kwargs)
		return DeployResult(
			deployment_id="prod-260402-120000",
			backend_service_id="svc-2",
			backend_service_name="prod-260402-120000",
			backend_image="ghcr.io/acme/backend:24h",
			router_service_id="svc-1",
			router_service_name="pulse-router",
			router_image="ghcr.io/acme/router:24h",
			router_domain="pulse-router-production.up.railway.app",
			server_address="https://pulse-router-production.up.railway.app",
			backend_deployment_id="deploy-svc-2",
			backend_status="SUCCESS",
			janitor_service_id="svc-3",
			janitor_service_name="pulse-janitor",
		)

	monkeypatch.setattr("pulse_railway.commands.deploy.image.deploy", fake_deploy)
	return deploy_call


def _install_fake_deploy_source(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
	deploy_call: dict[str, Any] = {}

	async def fake_resolve_railway_target_ids(**kwargs: Any) -> tuple[str, str]:
		deploy_call["target"] = kwargs
		return kwargs["project_name"] or "project-from-token", kwargs[
			"environment_name"
		] or "env-from-token"

	monkeypatch.setattr(
		"pulse_railway.commands.deploy.common.resolve_railway_target_ids",
		fake_resolve_railway_target_ids,
	)

	async def fake_deploy_source(**kwargs: Any) -> DeployResult:
		deploy_call.update(kwargs)
		return DeployResult(
			deployment_id="prod-260402-120000",
			backend_service_id="svc-2",
			backend_service_name="prod-260402-120000",
			backend_image=None,
			backend_deployment_id="deploy-source",
			router_service_id="svc-1",
			router_service_name="pulse-router",
			router_image="ghcr.io/acme/router:24h",
			router_domain="pulse-router-production.up.railway.app",
			server_address="https://pulse-router-production.up.railway.app",
			backend_status="SUCCESS",
			source_context="/tmp/project",
			dockerfile_path="/tmp/project/Dockerfile",
			janitor_service_id="svc-3",
			janitor_service_name="pulse-janitor",
		)

	monkeypatch.setattr(
		"pulse_railway.commands.deploy.source.deploy", fake_deploy_source
	)
	return deploy_call


def _write_deploy_fixture(root: Path) -> None:
	(root / "web").mkdir(parents=True)
	(root / "Dockerfile").write_text("FROM scratch\n")
	(root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		'app = ps.App(routes=[], plugins=[RailwayPlugin(dockerfile="Dockerfile")])\n'
	)


def test_scaffold_parser_uses_static_defaults(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_RAILWAY_APP_FILE", "examples/aws-ecs/main.py")
	monkeypatch.setenv("PULSE_RAILWAY_JANITOR_CRON_SCHEDULE", "0 */6 * * *")
	parser = argparse.ArgumentParser()

	_add_scaffold_args(parser)
	args = parser.parse_args(["main.py"])

	assert args.app_file == "main.py"
	assert args.janitor_cron_schedule == "*/5 * * * *"
	assert args.redis_url is None
	assert not hasattr(args, "project")
	assert not hasattr(args, "environment")
	assert not hasattr(args, "service_prefix")


def test_scaffold_parser_ignores_workspace_env_default(monkeypatch) -> None:
	monkeypatch.setenv("RAILWAY_WORKSPACE_ID", "workspace")
	parser = argparse.ArgumentParser()

	_add_scaffold_args(parser)
	args = parser.parse_args(["main.py"])

	assert args.workspace_id is None


def test_scaffold_parser_rejects_project_and_environment_flags() -> None:
	parser = argparse.ArgumentParser()

	_add_scaffold_args(parser)

	with pytest.raises(SystemExit):
		parser.parse_args(["main.py", "--project", "project"])

	with pytest.raises(SystemExit):
		parser.parse_args(["main.py", "--environment", "env"])


def test_ensure_parser_rejects_project_and_environment_flags() -> None:
	parser = argparse.ArgumentParser()

	_add_ensure_args(parser)

	with pytest.raises(SystemExit):
		parser.parse_args(["main.py", "--project", "project"])

	with pytest.raises(SystemExit):
		parser.parse_args(["main.py", "--environment", "env"])


def test_upgrade_parser_is_noop_placeholder() -> None:
	parser = argparse.ArgumentParser()

	_add_upgrade_args(parser)
	args = parser.parse_args([])

	assert vars(args) == {}


def test_deploy_parser_drops_stable_stack_flags(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_RAILWAY_APP_FILE", "examples/aws-ecs/main.py")
	parser = argparse.ArgumentParser()

	_add_deploy_args(parser)
	args = parser.parse_args(["main.py"])

	assert args.app_file == "main.py"
	assert not hasattr(args, "mode")
	assert not hasattr(args, "redis_url")
	assert not hasattr(args, "janitor_cron_schedule")
	assert not hasattr(args, "router_image")


def test_deploy_parser_prefers_railway_token(monkeypatch) -> None:
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")
	monkeypatch.setenv("RAILWAY_TOKEN", "project-token")
	parser = argparse.ArgumentParser()

	_add_deploy_args(parser)
	args = parser.parse_args(["main.py"])

	assert args.token == "project-token"


def test_deploy_parser_uses_project_token_env_for_explicit_token(monkeypatch) -> None:
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")
	parser = argparse.ArgumentParser()

	_add_deploy_args(parser)
	args = parser.parse_args(["main.py", "--token", "project-token"])

	assert args.token == "project-token"


def test_deploy_parser_reads_source_mode_flags(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_RAILWAY_APP_FILE", "examples/aws-ecs/main.py")
	parser = argparse.ArgumentParser()

	_add_deploy_args(parser)
	args = parser.parse_args(["main.py", "--no-gitignore"])

	assert not hasattr(args, "mode")
	assert args.no_gitignore is True
	assert args.app_file == "main.py"
	assert not hasattr(args, "redis_url")
	assert not hasattr(args, "janitor_cron_schedule")
	assert not hasattr(args, "router_image")


def test_deploy_parser_removes_mode_flag() -> None:
	parser = argparse.ArgumentParser()

	_add_deploy_args(parser)

	with pytest.raises(SystemExit):
		parser.parse_args(["main.py", "--mode", "source"])


def test_deploy_parser_requires_app_file() -> None:
	parser = argparse.ArgumentParser()

	_add_deploy_args(parser)

	with pytest.raises(SystemExit):
		parser.parse_args([])


def test_redeploy_parser_rejects_dead_redis_flags() -> None:
	parser = argparse.ArgumentParser()

	_add_redeploy_args(parser)

	with pytest.raises(SystemExit):
		parser.parse_args(["--redis-url", "redis://example"])


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


def test_janitor_parser_prefers_railway_token(monkeypatch) -> None:
	monkeypatch.setenv("RAILWAY_PROJECT_ID", "project")
	monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env")
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")
	monkeypatch.setenv("RAILWAY_TOKEN", "project-token")
	parser = argparse.ArgumentParser()

	_add_janitor_run_args(parser)
	args = parser.parse_args([])

	assert args.token == "project-token"


@pytest.mark.asyncio
async def test_run_scaffold_reads_target_from_railway_plugin(
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
		'        RailwayPlugin(dockerfile="Dockerfile", project="stoneware", environment="staging", router_service="api", service_prefix="foo-")\n'
		"    ],\n"
		")\n"
	)
	init_call = _install_fake_scaffold(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_scaffold(
		_make_scaffold_args(
			token="token",
		)
	)

	assert result == 0
	assert init_call["target"]["project_name"] == "stoneware"
	assert init_call["target"]["environment_name"] == "staging"
	assert init_call["project"].project_id == "stoneware"
	assert init_call["project"].environment_id == "staging"
	assert init_call["project"].service_name == "foo-api"
	assert init_call["project"].service_prefix == "foo-"
	assert init_call["project"].redis_service_name == "foo-redis"
	assert init_call["project"].janitor_service_name == "foo-janitor"


@pytest.mark.asyncio
async def test_run_scaffold_passes_omitted_environment_to_resolver(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		'app = ps.App(routes=[], plugins=[RailwayPlugin(dockerfile="Dockerfile", project="stoneware")])\n'
	)
	init_call = _install_fake_scaffold(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_scaffold(
		_make_scaffold_args(
			token="token",
		)
	)

	assert result == 0
	assert init_call["target"]["project_name"] == "stoneware"
	assert init_call["target"]["environment_name"] is None


@pytest.mark.asyncio
async def test_run_scaffold_allows_project_token_inference(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	init_call = _install_fake_scaffold(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_scaffold(
		_make_scaffold_args(
			token="token",
		)
	)

	assert result == 0
	assert init_call["target"]["project_name"] is None
	assert init_call["target"]["environment_name"] is None
	assert init_call["project"].project_id == "project-from-token"
	assert init_call["project"].environment_id == "env-from-token"


@pytest.mark.asyncio
async def test_run_ensure_reads_target_from_railway_plugin(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		'app = ps.App(routes=[], plugins=[RailwayPlugin(dockerfile="Dockerfile", project="stoneware", environment="staging")])\n'
	)
	ensure_call = _install_fake_ensure(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_ensure(
		_make_scaffold_args(
			token="token",
		)
	)

	assert result == 0
	assert ensure_call["target"]["project_name"] == "stoneware"
	assert ensure_call["target"]["environment_name"] == "staging"
	assert ensure_call["project"].project_id == "stoneware"
	assert ensure_call["project"].environment_id == "staging"
	assert ensure_call["project"].service_name == "pulse-router"


@pytest.mark.asyncio
async def test_resolve_railway_target_ids_resolves_names(monkeypatch) -> None:
	from pulse_railway.commands.common import resolve_railway_target_ids

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def get_project_token(self) -> None:
			return None

		async def list_projects(
			self, *, workspace_id: str | None = None
		) -> list[ProjectRecord]:
			assert workspace_id == "workspace"
			return [ProjectRecord(id="project-id", name="stoneware")]

		async def list_environments(
			self, *, project_id: str
		) -> list[EnvironmentRecord]:
			assert project_id == "project-id"
			return [
				EnvironmentRecord(id="env-prod", name="production"),
				EnvironmentRecord(id="env-staging", name="staging"),
			]

	monkeypatch.setattr(
		"pulse_railway.commands.common.RailwayGraphQLClient", _FakeClient
	)

	project_id, environment_id = await resolve_railway_target_ids(
		project_name="stoneware",
		environment_name="staging",
		token="token",
		workspace_id="workspace",
	)

	assert project_id == "project-id"
	assert environment_id == "env-staging"


@pytest.mark.asyncio
async def test_resolve_railway_target_ids_defaults_environment_without_project_token(
	monkeypatch,
) -> None:
	from pulse_railway.commands.common import resolve_railway_target_ids

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def get_project_token(self) -> None:
			return None

		async def list_projects(
			self, *, workspace_id: str | None = None
		) -> list[ProjectRecord]:
			assert workspace_id is None
			return [ProjectRecord(id="project-id", name="stoneware")]

		async def list_environments(
			self, *, project_id: str
		) -> list[EnvironmentRecord]:
			assert project_id == "project-id"
			return [
				EnvironmentRecord(id="env-prod", name="production"),
				EnvironmentRecord(id="env-staging", name="staging"),
			]

	monkeypatch.setattr(
		"pulse_railway.commands.common.RailwayGraphQLClient", _FakeClient
	)

	project_id, environment_id = await resolve_railway_target_ids(
		project_name="stoneware",
		environment_name=None,
		token="token",
	)

	assert project_id == "project-id"
	assert environment_id == "env-prod"


@pytest.mark.asyncio
async def test_resolve_railway_target_ids_infers_project_from_token(
	monkeypatch,
) -> None:
	from pulse_railway.commands.common import resolve_railway_target_ids

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def get_project_token(self) -> ProjectTokenRecord:
			return ProjectTokenRecord(
				project_id="project-from-token",
				environment_id="env-from-token",
			)

		async def get_environment(self, *, environment_id: str) -> EnvironmentRecord:
			assert environment_id == "env-from-token"
			return EnvironmentRecord(id="env-from-token", name="production")

	monkeypatch.setattr(
		"pulse_railway.commands.common.RailwayGraphQLClient", _FakeClient
	)

	project_id, environment_id = await resolve_railway_target_ids(
		project_name=None,
		environment_name="production",
		token="token",
	)

	assert project_id == "project-from-token"
	assert environment_id == "env-from-token"


@pytest.mark.asyncio
async def test_resolve_railway_target_ids_infers_environment_from_token(
	monkeypatch,
) -> None:
	from pulse_railway.commands.common import resolve_railway_target_ids

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def get_project_token(self) -> ProjectTokenRecord:
			return ProjectTokenRecord(
				project_id="project-from-token",
				environment_id="env-staging",
			)

		async def get_environment(self, *, environment_id: str) -> EnvironmentRecord:
			raise AssertionError("omitted environment should use the token scope")

		async def list_environments(
			self, *, project_id: str
		) -> list[EnvironmentRecord]:
			raise AssertionError("omitted environment should use the token scope")

	monkeypatch.setattr(
		"pulse_railway.commands.common.RailwayGraphQLClient", _FakeClient
	)

	project_id, environment_id = await resolve_railway_target_ids(
		project_name=None,
		environment_name=None,
		token="token",
	)

	assert project_id == "project-from-token"
	assert environment_id == "env-staging"


@pytest.mark.asyncio
async def test_resolve_railway_target_ids_rejects_mismatched_project_token_environment(
	monkeypatch,
) -> None:
	from pulse_railway.commands.common import resolve_railway_target_ids

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def get_project_token(self) -> ProjectTokenRecord:
			return ProjectTokenRecord(
				project_id="project-from-token",
				environment_id="env-staging",
			)

		async def get_environment(self, *, environment_id: str) -> EnvironmentRecord:
			assert environment_id == "env-staging"
			return EnvironmentRecord(id="env-staging", name="staging")

		async def list_environments(
			self, *, project_id: str
		) -> list[EnvironmentRecord]:
			raise AssertionError("project token should not resolve other environments")

	monkeypatch.setattr(
		"pulse_railway.commands.common.RailwayGraphQLClient", _FakeClient
	)

	with pytest.raises(ValueError, match="scoped to Railway environment staging"):
		await resolve_railway_target_ids(
			project_name=None,
			environment_name="production",
			token="token",
		)


@pytest.mark.asyncio
async def test_resolve_railway_target_ids_fails_without_project_or_project_token(
	monkeypatch,
) -> None:
	from pulse_railway.commands.common import resolve_railway_target_ids

	class _FakeClient:
		def __init__(self, **_: object) -> None:
			return None

		async def __aenter__(self) -> "_FakeClient":
			return self

		async def __aexit__(self, *_: object) -> None:
			return None

		async def get_project_token(self) -> None:
			return None

	monkeypatch.setattr(
		"pulse_railway.commands.common.RailwayGraphQLClient", _FakeClient
	)

	with pytest.raises(ValueError, match="project is required"):
		await resolve_railway_target_ids(
			project_name=None,
			environment_name="production",
			token="token",
		)


@pytest.mark.asyncio
async def test_run_upgrade_is_noop() -> None:
	result = await _run_upgrade(argparse.Namespace())

	assert result == 0


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
	assert deploy_call["web_root"] == "web"


@pytest.mark.asyncio
async def test_run_deploy_reads_dockerfile_from_railway_plugin(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "Custom.Dockerfile").write_text("FROM scratch\n")
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		'app = ps.App(routes=[], plugins=[RailwayPlugin(dockerfile="Custom.Dockerfile")])\n'
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args(dockerfile=None))

	assert result == 0
	assert deploy_call["docker"].dockerfile_path == (project_root / "Custom.Dockerfile")


@pytest.mark.asyncio
async def test_run_deploy_requires_dockerfile_from_cli_or_plugin(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	(project_root / "web").mkdir()
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		"app = ps.App(routes=[], plugins=[RailwayPlugin()])\n"
	)
	monkeypatch.chdir(project_root)

	with pytest.raises(ValueError, match="dockerfile is required"):
		await _run_deploy(_make_deploy_args(dockerfile=None))


@pytest.mark.asyncio
async def test_run_deploy_passes_loaded_session_store_config(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin, RailwaySessionStore\n"
		"app = ps.App(\n"
		"    routes=[],\n"
		"    plugins=[RailwayPlugin(dockerfile='Dockerfile')],\n"
		"    session_store=RailwaySessionStore(),\n"
		")\n"
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args(dockerfile=None))

	assert result == 0
	assert deploy_call["uses_railway_session_store"] is True


@pytest.mark.asyncio
async def test_run_deploy_reads_web_root_from_app_file(monkeypatch, tmp_path) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "frontend").mkdir()
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		"app = ps.App(\n"
		"    codegen=ps.CodegenConfig(web_dir='frontend'),\n"
		"    routes=[],\n"
		'    plugins=[RailwayPlugin(dockerfile="Dockerfile")],\n'
		")\n"
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args(web_root=None))

	assert result == 0
	assert deploy_call["web_root"] == "frontend"


@pytest.mark.asyncio
async def test_run_deploy_flags_override_app_paths(monkeypatch, tmp_path) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "frontend").mkdir()
	(project_root / "Override.Dockerfile").write_text("FROM scratch\n")
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		"app = ps.App(\n"
		"    codegen=ps.CodegenConfig(web_dir='frontend'),\n"
		"    routes=[],\n"
		'    plugins=[RailwayPlugin(dockerfile="Dockerfile")],\n'
		")\n"
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(
		_make_deploy_args(
			dockerfile="Override.Dockerfile",
			web_root="web",
		)
	)

	assert result == 0
	assert deploy_call["docker"].dockerfile_path == (
		project_root / "Override.Dockerfile"
	)
	assert deploy_call["web_root"] == "web"


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
		'        RailwayPlugin(dockerfile="Dockerfile", project="project", environment="env", deployment_name="staging")\n'
		"    ],\n"
		")\n"
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(
		_make_deploy_args(
			project=None,
			environment=None,
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
async def test_run_deploy_reads_server_address_from_app_file(
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
		'    plugins=[RailwayPlugin(dockerfile="Dockerfile")],\n'
		'    server_address="https://app.example.com",\n'
		")\n"
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.setenv("PULSE_ENV", "dev")
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args(server_address=None))

	assert result == 0
	assert deploy_call["project"].server_address == "https://app.example.com"
	assert os.environ["PULSE_ENV"] == "dev"


@pytest.mark.asyncio
async def test_run_deploy_reads_env_server_address_from_app_file(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import os\n"
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		"app = ps.App(\n"
		"    routes=[],\n"
		'    plugins=[RailwayPlugin(dockerfile="Dockerfile")],\n'
		'    server_address=os.environ.get("PULSE_SERVER_ADDRESS"),\n'
		")\n"
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.setenv("PULSE_SERVER_ADDRESS", "https://env.example.com")
	monkeypatch.delenv("PULSE_ENV", raising=False)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args(server_address=None))

	assert result == 0
	assert deploy_call["project"].server_address == "https://env.example.com"
	assert "PULSE_ENV" not in os.environ


@pytest.mark.asyncio
async def test_run_deploy_server_address_flag_overrides_app_file(
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
		'    plugins=[RailwayPlugin(dockerfile="Dockerfile")],\n'
		'    server_address="https://app.example.com",\n'
		")\n"
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(
		_make_deploy_args(server_address="https://override.example.com")
	)

	assert result == 0
	assert deploy_call["project"].server_address == "https://override.example.com"


@pytest.mark.asyncio
async def test_run_deploy_flag_overrides_plugin_deployment_name(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		'app = ps.App(routes=[], plugins=[RailwayPlugin(dockerfile="Dockerfile", deployment_name="staging")])\n'
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args(deployment_name="preview"))

	assert result == 0
	assert deploy_call["deployment_name"] == "preview"


@pytest.mark.asyncio
async def test_run_deploy_reads_plugin_image_repository(monkeypatch, tmp_path) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		'app = ps.App(routes=[], plugins=[RailwayPlugin(dockerfile="Dockerfile", image_repository="ghcr.io/acme/stoneware-v3")])\n'
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args(image_repository=None))

	assert result == 0
	assert deploy_call["docker"].image_repository == "ghcr.io/acme/stoneware-v3"


@pytest.mark.asyncio
async def test_run_deploy_defaults_to_source_without_image_repository(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	deploy_call = _install_fake_deploy_source(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args(image_repository=None))

	assert result == 0
	assert deploy_call["docker"].image_repository is None


@pytest.mark.asyncio
async def test_run_deploy_explicit_image_repository_overrides_plugin(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	(project_root / "main.py").write_text(
		"import pulse as ps\n"
		"from pulse_railway import RailwayPlugin\n"
		'app = ps.App(routes=[], plugins=[RailwayPlugin(dockerfile="Dockerfile", image_repository="ghcr.io/acme/stoneware-v3")])\n'
	)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(
		_make_deploy_args(image_repository="ghcr.io/acme/override")
	)

	assert result == 0
	assert deploy_call["docker"].image_repository == "ghcr.io/acme/override"


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
		'app = ps.App(routes=[], plugins=[RailwayPlugin(dockerfile="Dockerfile", router_service="api")])\n'
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
async def test_run_deploy_source_resolves_paths_and_defaults(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	deploy_call = _install_fake_deploy_source(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args(image_repository=None))

	assert result == 0
	assert deploy_call["project"].service_prefix is None
	assert deploy_call["project"].service_name == "pulse-router"
	assert deploy_call["project"].redis_service_name == "pulse-redis"
	assert deploy_call["project"].janitor_service_name == "pulse-janitor"
	assert deploy_call["docker"].dockerfile_path == (project_root / "Dockerfile")
	assert deploy_call["docker"].context_path == project_root
	assert deploy_call["docker"].image_repository is None


@pytest.mark.asyncio
async def test_run_deploy_source_reads_target_from_railway_plugin(
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
		'        RailwayPlugin(dockerfile="Dockerfile", project="project", environment="env", deployment_name="staging")\n'
		"    ],\n"
		")\n"
	)
	deploy_call = _install_fake_deploy_source(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(
		_make_deploy_args(
			image_repository=None,
			project=None,
			environment=None,
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
	assert deploy_call["cli_token_env_name"] is None


@pytest.mark.asyncio
async def test_run_deploy_source_keeps_api_token_env_for_default_token(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	deploy_call = _install_fake_deploy_source(monkeypatch)
	monkeypatch.setenv("RAILWAY_API_TOKEN", "api-token")
	monkeypatch.chdir(project_root)

	result = await _run_deploy(
		_make_deploy_args(
			image_repository=None,
			project="project",
			environment="env",
			token="api-token",
		)
	)

	assert result == 0
	assert deploy_call["cli_token_env_name"] == "RAILWAY_API_TOKEN"


@pytest.mark.asyncio
async def test_run_deploy_source_defers_unmatched_explicit_token_env_name(
	monkeypatch,
	tmp_path,
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	deploy_call = _install_fake_deploy_source(monkeypatch)
	monkeypatch.setenv("RAILWAY_API_TOKEN", "ambient-api-token")
	monkeypatch.chdir(project_root)

	result = await _run_deploy(
		_make_deploy_args(
			image_repository=None,
			project="project",
			environment="env",
			token="explicit-account-token",
		)
	)

	assert result == 0
	assert deploy_call["cli_token_env_name"] is None


@pytest.mark.asyncio
async def test_run_deploy_source_requires_context_relative_app_paths(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	_install_fake_deploy_source(monkeypatch)
	monkeypatch.chdir(project_root)

	with pytest.raises(ValueError, match="app-file must be relative"):
		await _run_deploy(
			_make_deploy_args(
				image_repository=None, app_file=str(project_root / "main.py")
			)
		)


@pytest.mark.asyncio
async def test_run_deploy_source_rejects_managed_build_args(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	_install_fake_deploy_source(monkeypatch)
	monkeypatch.chdir(project_root)

	with pytest.raises(DeploymentError, match="PORT"):
		await _run_deploy(
			_make_deploy_args(image_repository=None, build_arg=["PORT=3000"])
		)


@pytest.mark.asyncio
async def test_run_deploy_rejects_no_gitignore_with_image_repository(
	monkeypatch, tmp_path
) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	_install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	with pytest.raises(ValueError, match="--no-gitignore cannot be used"):
		await _run_deploy(_make_deploy_args(no_gitignore=True))


@pytest.mark.asyncio
async def test_run_delete_builds_shared_project_defaults(monkeypatch) -> None:
	delete_call: dict[str, Any] = {}

	async def fake_delete_deployment(**kwargs: Any) -> None:
		delete_call.update(kwargs)

	async def fake_resolve_railway_target_ids(**kwargs: Any) -> tuple[str, str]:
		assert kwargs["project_name"] == "project"
		assert kwargs["environment_name"] == "env"
		return "project", "env"

	monkeypatch.setattr(
		"pulse_railway.cli.resolve_railway_target_ids",
		fake_resolve_railway_target_ids,
	)
	monkeypatch.setattr("pulse_railway.cli.delete_deployment", fake_delete_deployment)

	result = await _run_delete(
		argparse.Namespace(
			service="pulse-router",
			deployment_id="prod-260402-120000",
			project="project",
			environment="env",
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

	async def fake_resolve_railway_target_ids(**kwargs: Any) -> tuple[str, str]:
		assert kwargs["project_name"] == "project"
		assert kwargs["environment_name"] == "env"
		return "project", "env"

	monkeypatch.setattr(
		"pulse_railway.cli.resolve_railway_target_ids",
		fake_resolve_railway_target_ids,
	)
	monkeypatch.setattr(
		"pulse_railway.cli.resolve_deployment_id_by_name",
		fake_resolve_deployment_id_by_name,
	)
	monkeypatch.setattr("pulse_railway.cli.delete_deployment", fake_delete_deployment)

	result = await _run_remove(
		argparse.Namespace(
			service="pulse-router",
			deployment_name="redis-smoke",
			project="project",
			environment="env",
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
async def test_run_redeploy_defaults_to_active_deployment(
	monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
	redeploy_call: dict[str, Any] = {}

	async def fake_redeploy_deployment(**kwargs: Any) -> RedeployResult:
		redeploy_call.update(kwargs)
		return RedeployResult(
			deployment_id="prod-260402-120000",
			backend_service_id="svc-backend",
			backend_service_name="prod-260402-120000",
			backend_deployment_id="deploy-backend",
			backend_status="SUCCESS",
		)

	async def fake_resolve_railway_target_ids(**kwargs: Any) -> tuple[str, str]:
		assert kwargs["project_name"] == "project"
		assert kwargs["environment_name"] == "env"
		return "project", "env"

	monkeypatch.setattr(
		"pulse_railway.cli.resolve_railway_target_ids",
		fake_resolve_railway_target_ids,
	)
	monkeypatch.setattr(
		"pulse_railway.cli.redeploy_deployment",
		fake_redeploy_deployment,
	)

	result = await _run_redeploy(
		argparse.Namespace(
			service="pulse-router",
			deployment_id=None,
			project="project",
			environment="env",
			token="token",
			service_prefix=None,
			redis_url=None,
			redis_service=None,
			redis_prefix="pulse:railway",
		)
	)

	assert result == 0
	assert redeploy_call["deployment_id"] is None
	assert redeploy_call["project"].redis_service_name == "pulse-router-redis"
	assert '"backend_deployment_id": "deploy-backend"' in capsys.readouterr().out


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
