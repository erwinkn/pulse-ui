from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest
from pulse_aws.cli import _add_deploy_args, _run_deploy, _run_verify


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


def _make_verify_args(**overrides: Any) -> argparse.Namespace:
	values: dict[str, Any] = {
		"deployment_name": "prod",
		"domain": "app.example.com",
		"health_check_path": "/_pulse/health",
		"verify_ssl": False,
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


class _FakeStsClient:
	def __init__(self) -> None:
		self.meta = type("Meta", (), {"region_name": "us-east-1"})()

	def get_caller_identity(self) -> dict[str, str]:
		return {"Account": "123456789012"}


class _FakeEcsClient:
	def list_services(self, *, cluster: str) -> dict[str, list[str]]:
		assert cluster == "pulse-prod"
		return {"serviceArns": ["arn:service/a", "arn:service/b"]}

	def describe_services(
		self, *, cluster: str, services: list[str]
	) -> dict[str, list[dict[str, Any]]]:
		assert cluster == "pulse-prod"
		assert services == ["arn:service/a", "arn:service/b"]
		return {
			"services": [
				{
					"serviceName": "prod-old",
					"status": "ACTIVE",
					"runningCount": 2,
					"desiredCount": 2,
				},
				{
					"serviceName": "prod-new",
					"status": "ACTIVE",
					"runningCount": 2,
					"desiredCount": 2,
				},
			]
		}


class _FakeResponse:
	def __init__(
		self,
		*,
		status_code: int,
		text: str = "",
		headers: dict[str, str] | None = None,
		json_body: dict[str, Any] | None = None,
	) -> None:
		self.status_code = status_code
		self.text = text
		self.headers = headers or {}
		self._json_body = json_body

	def json(self) -> dict[str, Any]:
		if self._json_body is None:
			raise AssertionError("json() should not have been called for this response")
		return self._json_body


class _FakeAsyncClient:
	def __init__(
		self,
		responses: list[_FakeResponse],
		calls: list[dict[str, Any]],
		**_kwargs: Any,
	):
		self._responses = list(responses)
		self._calls = calls

	async def __aenter__(self) -> "_FakeAsyncClient":
		return self

	async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
		return None

	async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
		self._calls.append({"url": url, **kwargs})
		return self._responses.pop(0)


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


@pytest.mark.asyncio
async def test_run_verify_checks_dedicated_deployment_endpoint(
	monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
	monkeypatch.setattr(
		"pulse_aws.cli.describe_stack",
		lambda _cfn, _stack_name: {
			"Outputs": [
				{"OutputKey": "ListenerArn", "OutputValue": "arn:listener"},
				{"OutputKey": "AlbDnsName", "OutputValue": "alb.example.com"},
				{"OutputKey": "AlbHostedZoneId", "OutputValue": "ZTEST"},
				{"OutputKey": "PrivateSubnets", "OutputValue": "subnet-a,subnet-b"},
				{"OutputKey": "PublicSubnets", "OutputValue": "subnet-c,subnet-d"},
				{"OutputKey": "AlbSecurityGroupId", "OutputValue": "sg-alb"},
				{"OutputKey": "ServiceSecurityGroupId", "OutputValue": "sg-service"},
				{"OutputKey": "ClusterName", "OutputValue": "pulse-prod"},
				{"OutputKey": "LogGroupName", "OutputValue": "/aws/pulse/prod/app"},
				{"OutputKey": "EcrRepositoryUri", "OutputValue": "123.dkr.ecr/prod"},
				{"OutputKey": "VpcId", "OutputValue": "vpc-123"},
				{"OutputKey": "ExecutionRoleArn", "OutputValue": "arn:execution"},
				{"OutputKey": "TaskRoleArn", "OutputValue": "arn:task"},
			]
		},
	)

	def fake_boto3_client(service_name: str, **_kwargs: Any) -> Any:
		if service_name == "sts":
			return _FakeStsClient()
		if service_name == "ecs":
			return _FakeEcsClient()
		if service_name == "cloudformation":
			return object()
		raise AssertionError(f"Unexpected boto3 client: {service_name}")

	monkeypatch.setattr("pulse_aws.cli.boto3.client", fake_boto3_client)

	calls: list[dict[str, Any]] = []
	responses = [
		_FakeResponse(
			status_code=200,
			text="<html>ok</html>",
			headers={"content-type": "text/html; charset=utf-8"},
		),
		_FakeResponse(
			status_code=200,
			json_body={"health": "ok"},
			headers={"content-type": "application/json"},
		),
		_FakeResponse(
			status_code=200,
			json_body={"deployment_id": "prod-old"},
			headers={"content-type": "application/json"},
		),
		_FakeResponse(
			status_code=200,
			json_body={"deployment_id": "prod-new"},
			headers={"content-type": "application/json"},
		),
	]
	monkeypatch.setattr(
		"pulse_aws.cli.httpx.AsyncClient",
		lambda **kwargs: _FakeAsyncClient(responses, calls, **kwargs),
	)

	result = await _run_verify(_make_verify_args())

	assert result == 0
	assert [call["url"] for call in calls] == [
		"https://alb.example.com",
		"https://alb.example.com/_pulse/health",
		"https://alb.example.com/_pulse/meta",
		"https://alb.example.com/_pulse/meta",
	]
	assert calls[2]["params"] == {"pulse_deployment": "prod-old"}
	assert calls[3]["params"] == {"pulse_deployment": "prod-new"}

	output = capsys.readouterr().out
	assert "✓ Content-Type: text/html; charset=utf-8" in output
	assert "✓ Routed correctly to prod-old" in output
	assert "✓ Routed correctly to prod-new" in output


@pytest.mark.asyncio
async def test_run_verify_uses_reserved_metadata_endpoint(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setattr(
		"pulse_aws.cli.describe_stack",
		lambda _cfn, _stack_name: {
			"Outputs": [
				{"OutputKey": "ListenerArn", "OutputValue": "arn:listener"},
				{"OutputKey": "AlbDnsName", "OutputValue": "alb.example.com"},
				{"OutputKey": "AlbHostedZoneId", "OutputValue": "ZTEST"},
				{"OutputKey": "PrivateSubnets", "OutputValue": "subnet-a,subnet-b"},
				{"OutputKey": "PublicSubnets", "OutputValue": "subnet-c,subnet-d"},
				{"OutputKey": "AlbSecurityGroupId", "OutputValue": "sg-alb"},
				{"OutputKey": "ServiceSecurityGroupId", "OutputValue": "sg-service"},
				{"OutputKey": "ClusterName", "OutputValue": "pulse-prod"},
				{"OutputKey": "LogGroupName", "OutputValue": "/aws/pulse/prod/app"},
				{"OutputKey": "EcrRepositoryUri", "OutputValue": "123.dkr.ecr/prod"},
				{"OutputKey": "VpcId", "OutputValue": "vpc-123"},
				{"OutputKey": "ExecutionRoleArn", "OutputValue": "arn:execution"},
				{"OutputKey": "TaskRoleArn", "OutputValue": "arn:task"},
			]
		},
	)

	def fake_boto3_client(service_name: str, **_kwargs: Any) -> Any:
		if service_name == "sts":
			return _FakeStsClient()
		if service_name == "ecs":
			return _FakeEcsClient()
		if service_name == "cloudformation":
			return object()
		raise AssertionError(f"Unexpected boto3 client: {service_name}")

	monkeypatch.setattr("pulse_aws.cli.boto3.client", fake_boto3_client)

	calls: list[dict[str, Any]] = []
	responses = [
		_FakeResponse(
			status_code=200, text="ok", headers={"content-type": "text/plain"}
		),
		_FakeResponse(
			status_code=200,
			json_body={"health": "ok"},
			headers={"content-type": "application/json"},
		),
		_FakeResponse(
			status_code=200,
			json_body={"deployment_id": "prod-old"},
			headers={"content-type": "application/json"},
		),
		_FakeResponse(
			status_code=200,
			json_body={"deployment_id": "prod-new"},
			headers={"content-type": "application/json"},
		),
	]
	monkeypatch.setattr(
		"pulse_aws.cli.httpx.AsyncClient",
		lambda **kwargs: _FakeAsyncClient(responses, calls, **kwargs),
	)

	result = await _run_verify(
		_make_verify_args(health_check_path="/custom-prefix/healthz")
	)

	assert result == 0
	assert calls[2]["url"] == "https://alb.example.com/_pulse/meta"
