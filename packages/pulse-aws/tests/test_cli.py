from __future__ import annotations

import argparse
from typing import Any

import pytest
from pulse_aws.cli import _add_deploy_args, _run_deploy


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
	web_root = project_root / "web"
	cdk_workdir = project_root / "infra" / "cdk"
	project_root.mkdir()
	web_root.mkdir(parents=True)
	cdk_workdir.mkdir(parents=True)
	(project_root / "Dockerfile").write_text("FROM scratch\n")
	(project_root / "main.py").write_text("print('hello')\n")

	deploy_call: dict[str, Any] = {}

	async def fake_deploy(**kwargs: Any) -> dict[str, str]:
		deploy_call.update(kwargs)
		return {
			"deployment_id": "prod-20250306-abcdef",
			"service_arn": "arn:service",
			"target_group_arn": "arn:target-group",
			"image_uri": "image:tag",
			"marked_draining_count": "0",
		}

	monkeypatch.setattr("pulse_aws.cli.deploy", fake_deploy)

	args = argparse.Namespace(
		deployment_name="prod",
		domain="app.example.com",
		server_address=None,
		project_root=str(project_root),
		app_file="main.py",
		web_root="web",
		dockerfile="Dockerfile",
		context=".",
		cdk_bin="custom-cdk",
		cdk_workdir="infra/cdk",
		build_arg=[],
		task_env=[],
		task_cpu="256",
		task_memory="512",
		desired_count=2,
		drain_poll_seconds=5,
		drain_grace_seconds=20,
		health_check_path="/_pulse/health",
		health_check_interval=30,
		health_check_timeout=5,
		healthy_threshold=2,
		unhealthy_threshold=3,
		wait_for_health=True,
		min_healthy_targets=2,
	)

	result = await _run_deploy(args)

	assert result == 0
	assert deploy_call["cdk_bin"] == "custom-cdk"
	assert deploy_call["cdk_workdir"] == cdk_workdir.resolve()
	assert deploy_call["domain"] == "app.example.com"
	assert deploy_call["deployment_name"] == "prod"
