from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest
from pulse_aws.cli import _add_deploy_args, _run_deploy


def _deploy_result() -> dict[str, str]:
	return {
		"deployment_id": "prod-20250306-abcdef",
		"service_arn": "arn:service",
		"target_group_arn": "arn:target-group",
		"image_uri": "image:tag",
		"marked_draining_count": "0",
	}


def _make_deploy_args(**overrides: Any) -> argparse.Namespace:
	values: dict[str, Any] = {
		"deployment_name": "prod",
		"domain": "app.example.com",
		"server_address": None,
		"app_file": "main.py",
		"web_root": "web",
		"dockerfile": "Dockerfile",
		"context": ".",
		"cdk_bin": "custom-cdk",
		"cdk_workdir": "infra/cdk",
		"build_arg": [],
		"task_env": [],
		"task_cpu": "256",
		"task_memory": "512",
		"desired_count": 2,
		"drain_poll_seconds": 5,
		"drain_grace_seconds": 20,
		"health_check_path": "/_pulse/health",
		"health_check_interval": 30,
		"health_check_timeout": 5,
		"healthy_threshold": 2,
		"unhealthy_threshold": 3,
		"wait_for_health": True,
		"min_healthy_targets": 2,
	}
	values.update(overrides)
	return argparse.Namespace(**values)


def _install_fake_deploy(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
	deploy_call: dict[str, Any] = {}

	async def fake_deploy(**kwargs: Any) -> dict[str, str]:
		deploy_call.update(kwargs)
		return _deploy_result()

	monkeypatch.setattr("pulse_aws.cli.deploy", fake_deploy)
	return deploy_call


def _write_deploy_fixture(root: Path) -> None:
	(root / "web").mkdir(parents=True)
	(root / "infra" / "cdk").mkdir(parents=True)
	(root / "Dockerfile").write_text("FROM scratch\n")
	(root / "main.py").write_text("print('hello')\n")


def test_deploy_parser_reads_cdk_env_overrides(monkeypatch):
	monkeypatch.setenv("PULSE_AWS_CDK_BIN", "custom-cdk")
	monkeypatch.setenv("PULSE_AWS_CDK_WORKDIR", "infra/cdk")
	parser = argparse.ArgumentParser()

	_add_deploy_args(parser)
	args = parser.parse_args([])

	assert args.cdk_bin == "custom-cdk"
	assert args.cdk_workdir == "infra/cdk"


@pytest.mark.asyncio
async def test_run_deploy_passes_cdk_overrides(monkeypatch, tmp_path):
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	args = _make_deploy_args()

	result = await _run_deploy(args)

	assert result == 0
	assert deploy_call["cdk_bin"] == "custom-cdk"
	assert deploy_call["cdk_workdir"] == (project_root / "infra" / "cdk").resolve()
	assert deploy_call["domain"] == "app.example.com"
	assert deploy_call["deployment_name"] == "prod"


@pytest.mark.asyncio
async def test_run_deploy_resolves_host_paths_from_invocation_cwd(
	monkeypatch, tmp_path
):
	invocation_cwd = tmp_path / "workspace"
	tools_dir = invocation_cwd / "tools"
	cdk_workdir = invocation_cwd / "infra" / "cdk"
	invocation_cwd.mkdir()
	_write_deploy_fixture(invocation_cwd)
	tools_dir.mkdir()
	(tools_dir / "cdk").write_text("#!/bin/sh\n")

	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(invocation_cwd)

	args = _make_deploy_args(
		cdk_bin="./tools/cdk",
		cdk_workdir="infra/cdk",
	)

	result = await _run_deploy(args)

	assert result == 0
	assert deploy_call["docker"].dockerfile_path == (invocation_cwd / "Dockerfile")
	assert deploy_call["docker"].context_path == invocation_cwd
	assert deploy_call["cdk_bin"] == str((invocation_cwd / "tools" / "cdk").resolve())
	assert deploy_call["cdk_workdir"] == cdk_workdir.resolve()


@pytest.mark.asyncio
async def test_run_deploy_leaves_bare_cdk_bin_for_path_lookup(monkeypatch, tmp_path):
	project_root = tmp_path / "project"
	project_root.mkdir()
	_write_deploy_fixture(project_root)
	deploy_call = _install_fake_deploy(monkeypatch)
	monkeypatch.chdir(project_root)

	args = _make_deploy_args()

	result = await _run_deploy(args)

	assert result == 0
	assert deploy_call["cdk_bin"] == "custom-cdk"
