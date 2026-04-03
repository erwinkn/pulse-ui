from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest
from pulse_railway.cli import (
	_add_deploy_args,
	_add_janitor_run_args,
	_run_delete,
	_run_deploy,
	_run_janitor_run,
)
from pulse_railway.deployment import DeployResult
from pulse_railway.janitor import JanitorResult


def _make_deploy_args(**overrides: Any) -> argparse.Namespace:
	values: dict[str, Any] = {
		"service": "pulse-router",
		"deployment_name": "prod",
		"deployment_id": None,
		"project_id": "project",
		"environment_id": "env",
		"token": "token",
		"service_prefix": None,
		"server_address": None,
		"redis_url": None,
		"redis_service": None,
		"redis_prefix": "pulse:railway",
		"janitor_service": None,
		"janitor_image": None,
		"janitor_interval_seconds": 60,
		"drain_grace_seconds": 60,
		"max_drain_age_seconds": 86400,
		"app_file": "main.py",
		"web_root": "web",
		"dockerfile": "Dockerfile",
		"context": ".",
		"image_repository": None,
		"router_image": None,
		"build_arg": [],
		"env": [],
		"backend_port": 8000,
		"backend_replicas": 1,
		"router_replicas": 1,
	}
	values.update(overrides)
	return argparse.Namespace(**values)


def _install_fake_deploy(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
	deploy_call: dict[str, Any] = {}

	async def fake_deploy(**kwargs: Any) -> DeployResult:
		deploy_call.update(kwargs)
		return DeployResult(
			deployment_id="prod-260402-120000",
			backend_service_id="svc-2",
			backend_service_name="pulse-prod-260402-120000",
			backend_image="ttl.sh/backend:24h",
			router_service_id="svc-1",
			router_service_name="pulse-router",
			router_image="ttl.sh/router:24h",
			router_domain="pulse-router-production.up.railway.app",
			server_address="https://pulse-router-production.up.railway.app",
			backend_deployment_id="deploy-svc-2",
			router_deployment_id="deploy-svc-1",
			backend_status="SUCCESS",
			router_status="SUCCESS",
		)

	monkeypatch.setattr("pulse_railway.cli.deploy", fake_deploy)
	return deploy_call


def _write_deploy_fixture(root: Path) -> None:
	(root / "web").mkdir(parents=True)
	(root / "Dockerfile").write_text("FROM scratch\n")
	(root / "main.py").write_text("print('hello')\n")


def test_deploy_parser_reads_env_overrides(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_RAILWAY_SERVICE", "router")
	monkeypatch.setenv("PULSE_RAILWAY_APP_FILE", "examples/aws-ecs/main.py")
	parser = argparse.ArgumentParser()

	_add_deploy_args(parser)
	args = parser.parse_args([])

	assert args.service == "router"
	assert args.app_file == "examples/aws-ecs/main.py"


def test_janitor_parser_reads_service_env_defaults(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_RAILWAY_PROJECT_ID", "project")
	monkeypatch.setenv("PULSE_RAILWAY_ENVIRONMENT_ID", "env")
	monkeypatch.setenv("PULSE_RAILWAY_TOKEN", "token")
	parser = argparse.ArgumentParser()

	_add_janitor_run_args(parser)
	args = parser.parse_args([])

	assert args.project_id == "project"
	assert args.environment_id == "env"
	assert args.token == "token"


@pytest.mark.asyncio
async def test_run_deploy_resolves_paths_and_defaults(monkeypatch, tmp_path) -> None:
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	result = await _run_deploy(_make_deploy_args())

	assert result == 0
	assert deploy_call["project"].service_prefix == "pulse-"
	assert deploy_call["project"].redis_service_name == "pulse-router-redis"
	assert deploy_call["project"].janitor_service_name == "pulse-router-janitor"
	assert deploy_call["docker"].dockerfile_path == (project_root / "Dockerfile")
	assert deploy_call["docker"].context_path == project_root


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
async def test_run_janitor_run_invokes_janitor(monkeypatch) -> None:
	janitor_call: dict[str, Any] = {}

	async def fake_run_janitor(**kwargs: Any) -> JanitorResult:
		janitor_call.update(kwargs)
		return JanitorResult(lock_acquired=True, scanned_count=1)

	monkeypatch.setattr("pulse_railway.cli.run_janitor", fake_run_janitor)

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
