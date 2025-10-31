from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from botocore.exceptions import ClientError
from pulse_aws.baseline import (
	BASELINE_STACK_VERSION,
	DEFAULT_CDK_APP_DIR,
	BaselineStackError,
	BaselineStackOutputs,
	ensure_baseline_stack,
)
from pulse_aws.certificate import check_domain_dns
from pulse_aws.teardown import teardown_baseline_stack

DUMMY_OUTPUTS = {
	"ListenerArn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/pulse-dev/abc/def",
	"AlbDnsName": "pulse-dev-123.us-east-1.elb.amazonaws.com",
	"AlbHostedZoneId": "Z32O12XQLNTSW2",
	"PrivateSubnets": "subnet-private-a,subnet-private-b",
	"PublicSubnets": "subnet-public-a,subnet-public-b",
	"AlbSecurityGroupId": "sg-alb",
	"ServiceSecurityGroupId": "sg-service",
	"ClusterName": "pulse-dev",
	"LogGroupName": "/aws/pulse/dev/app",
	"EcrRepositoryUri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/pulse-dev",
	"VpcId": "vpc-123",
	"ExecutionRoleArn": "arn:aws:iam::123456789012:role/pulse-dev-execution",
	"TaskRoleArn": "arn:aws:iam::123456789012:role/pulse-dev-task",
}


class FakeStsClient:
	def __init__(self) -> None:
		self.meta = type("Meta", (), {"region_name": "us-east-1"})()

	def get_caller_identity(self) -> dict:
		return {"Account": "123456789012"}


class ClientFactory:
	def __init__(self, services: dict[str, object]) -> None:
		self.services = services

	def __call__(self, service_name: str, **_kwargs):  # noqa: ANN001
		return self.services[service_name]


class FakeCloudFormationClient:
	def __init__(self, responses: dict[str, list[Exception | dict]]) -> None:
		self._responses = {key: list(value) for key, value in responses.items()}
		self.calls: list[str] = []
		self.delete_calls: list[str] = []

	def describe_stacks(self, *, StackName: str) -> dict:
		self.calls.append(StackName)
		queue = self._responses.setdefault(StackName, [])
		if not queue:
			raise _stack_not_found(StackName)
		response = queue.pop(0)
		if isinstance(response, Exception):
			raise response
		return response

	def delete_stack(self, *, StackName: str) -> dict:
		self.delete_calls.append(StackName)
		return {"ResponseMetadata": {"HTTPStatusCode": 200}}


class FakeRun:
	def __init__(self) -> None:
		self.calls: list[list[str]] = []

	def __call__(self, args, **kwargs):  # noqa: ANN001
		self.calls.append(list(args))
		return SimpleNamespace(returncode=0)


@pytest.mark.asyncio
async def test_ensure_baseline_stack_short_circuits_when_stack_is_healthy(
	tmp_path, monkeypatch
):
	cfn = FakeCloudFormationClient(
		{
			"dev-baseline": [_stack_response("CREATE_COMPLETE", DUMMY_OUTPUTS)],
		},
	)
	sts = FakeStsClient()
	monkeypatch.setattr(
		"pulse_aws.baseline.boto3.client",
		ClientFactory({"cloudformation": cfn, "sts": sts}),
	)
	run = FakeRun()
	monkeypatch.setattr("pulse_aws.baseline.subprocess.run", run)

	outputs = await ensure_baseline_stack(
		"dev",
		certificate_arn="arn:aws:acm:us-east-1:123456789012:certificate/abc",
		workdir=str(DEFAULT_CDK_APP_DIR),
	)

	assert isinstance(outputs, BaselineStackOutputs)
	assert outputs.listener_arn == DUMMY_OUTPUTS["ListenerArn"]
	assert run.calls == []


@pytest.mark.asyncio
async def test_ensure_baseline_stack_runs_cdk_when_stack_missing(tmp_path, monkeypatch):
	responses = {
		"dev-baseline": [
			_stack_not_found("dev-baseline"),
			_stack_response("CREATE_COMPLETE", DUMMY_OUTPUTS),
		],
		"CDKToolkit": [
			_stack_not_found("CDKToolkit"),
		],
	}
	cfn = FakeCloudFormationClient(responses)
	sts = FakeStsClient()
	monkeypatch.setattr(
		"pulse_aws.baseline.boto3.client",
		ClientFactory({"cloudformation": cfn, "sts": sts}),
	)
	run = FakeRun()
	monkeypatch.setattr("pulse_aws.baseline.subprocess.run", run)

	async def fake_sleep(_seconds):
		pass

	monkeypatch.setattr("pulse_aws.baseline.asyncio.sleep", fake_sleep)

	await ensure_baseline_stack(
		"dev",
		certificate_arn="arn:aws:acm:us-east-1:123456789012:certificate/abc",
		allowed_ingress_cidrs=["203.0.113.0/24"],
		workdir=str(DEFAULT_CDK_APP_DIR),
	)

	assert any(call[:2] == ["cdk", "synth"] for call in run.calls)
	assert any(call[:3] == ["cdk", "deploy", "dev-baseline"] for call in run.calls)
	deploy_call = next(call for call in run.calls if call[1] == "deploy")
	assert (
		"-c" in deploy_call
		and "certificate_arn=arn:aws:acm:us-east-1:123456789012:certificate/abc"
		in deploy_call
	)


def _stack_response(status: str, outputs: dict[str, str] | None = None) -> dict:
	outputs = outputs or {}
	return {
		"Stacks": [
			{
				"StackStatus": status,
				"Outputs": [
					{"OutputKey": key, "OutputValue": value}
					for key, value in outputs.items()
				],
				"Tags": [{"Key": "pulse-cf-version", "Value": BASELINE_STACK_VERSION}],
			},
		],
	}


def _stack_not_found(name: str) -> ClientError:
	return ClientError(
		{
			"Error": {
				"Code": "ValidationError",
				"Message": f"Stack with id {name} does not exist",
			},
		},
		"DescribeStacks",
	)


class FakeEcsClient:
	def __init__(self, services: list[dict[str, Any]] | None = None) -> None:
		self.services = services or []

	def list_services(self, *, cluster: str, maxResults: int = 10) -> dict[str, Any]:
		if not self.services:
			return {"serviceArns": []}
		return {"serviceArns": [svc["serviceArn"] for svc in self.services]}

	def describe_services(self, *, cluster: str, services: list[str]) -> dict[str, Any]:
		return {"services": self.services}


# Teardown tests


@pytest.mark.asyncio
async def test_teardown_baseline_stack_when_stack_does_not_exist(monkeypatch):
	cfn = FakeCloudFormationClient(
		{
			"dev-baseline": [_stack_not_found("dev-baseline")],
		},
	)
	sts = FakeStsClient()
	monkeypatch.setattr(
		"pulse_aws.baseline.boto3.client",
		ClientFactory({"cloudformation": cfn, "sts": sts}),
	)

	# Should complete without error
	await teardown_baseline_stack("dev")
	assert len(cfn.delete_calls) == 0


@pytest.mark.asyncio
async def test_teardown_baseline_stack_deletes_stack_when_no_services(monkeypatch):
	cfn = FakeCloudFormationClient(
		{
			"dev-baseline": [
				_stack_response("CREATE_COMPLETE", DUMMY_OUTPUTS),
				_stack_response("DELETE_IN_PROGRESS"),
				_stack_not_found("dev-baseline"),
			],
		},
	)
	sts = FakeStsClient()
	ecs = FakeEcsClient(services=[])
	monkeypatch.setattr(
		"pulse_aws.baseline.boto3.client",
		ClientFactory({"cloudformation": cfn, "sts": sts, "ecs": ecs}),
	)

	async def fake_sleep(_seconds):
		pass

	monkeypatch.setattr("pulse_aws.baseline.asyncio.sleep", fake_sleep)

	await teardown_baseline_stack("dev")
	assert "dev-baseline" in cfn.delete_calls


def test_check_domain_dns_handles_cloudflare_proxy(monkeypatch):
	domain = "app.example.com"
	target = "alb.example.com"

	domain_ips = {"104.16.0.1"}
	target_ips = {"203.0.113.10"}

	def fake_resolve(host: str) -> set[str]:
		if host == domain:
			return set(domain_ips)
		if host == target:
			return set(target_ips)
		return set()

	monkeypatch.setattr(
		"pulse_aws.certificate._resolve_ip_addresses",
		fake_resolve,
	)

	result = check_domain_dns(domain, target)
	assert result is None


def test_check_domain_dns_detects_mismatch(monkeypatch):
	domain = "app.example.com"
	target = "alb.example.com"

	domain_ips = {"198.51.100.10"}
	target_ips = {"203.0.113.10"}

	def fake_resolve(host: str) -> set[str]:
		if host == domain:
			return set(domain_ips)
		if host == target:
			return set(target_ips)
		return set()

	monkeypatch.setattr(
		"pulse_aws.certificate._resolve_ip_addresses",
		fake_resolve,
	)

	result = check_domain_dns(domain, target)
	assert result is not None


@pytest.mark.asyncio
async def test_teardown_baseline_stack_fails_when_active_services_exist(monkeypatch):
	# _check_for_active_services needs two describe_stacks calls:
	# one in teardown_baseline_stack, one in _check_for_active_services
	cfn = FakeCloudFormationClient(
		{
			"dev-baseline": [
				_stack_response("CREATE_COMPLETE", DUMMY_OUTPUTS),
				_stack_response("CREATE_COMPLETE", DUMMY_OUTPUTS),
			],
		},
	)
	sts = FakeStsClient()
	ecs = FakeEcsClient(
		services=[
			{
				"serviceArn": "arn:aws:ecs:us-east-1:123456789012:service/dev/pulse-app-v1",
				"serviceName": "pulse-app-v1",
				"status": "ACTIVE",
				"desiredCount": 2,
			},
		],
	)
	monkeypatch.setattr(
		"pulse_aws.baseline.boto3.client",
		ClientFactory({"cloudformation": cfn, "sts": sts, "ecs": ecs}),
	)

	with pytest.raises(BaselineStackError) as exc_info:
		await teardown_baseline_stack("dev")

	assert "active Pulse service(s) found" in str(exc_info.value)
	assert "pulse-app-v1" in str(exc_info.value)
	assert len(cfn.delete_calls) == 0


@pytest.mark.asyncio
async def test_teardown_baseline_stack_force_bypasses_service_check(monkeypatch):
	cfn = FakeCloudFormationClient(
		{
			"dev-baseline": [
				_stack_response("CREATE_COMPLETE", DUMMY_OUTPUTS),
				_stack_response("DELETE_IN_PROGRESS"),
				_stack_not_found("dev-baseline"),
			],
		},
	)
	sts = FakeStsClient()
	ecs = FakeEcsClient(
		services=[
			{
				"serviceArn": "arn:aws:ecs:us-east-1:123456789012:service/dev/pulse-app-v1",
				"serviceName": "pulse-app-v1",
				"status": "ACTIVE",
				"desiredCount": 2,
			},
		],
	)
	monkeypatch.setattr(
		"pulse_aws.baseline.boto3.client",
		ClientFactory({"cloudformation": cfn, "sts": sts, "ecs": ecs}),
	)

	async def fake_sleep(_seconds):
		pass

	monkeypatch.setattr("pulse_aws.baseline.asyncio.sleep", fake_sleep)

	# Should succeed despite active services
	await teardown_baseline_stack("dev", force=True)
	assert "dev-baseline" in cfn.delete_calls


@pytest.mark.asyncio
async def test_teardown_baseline_stack_fails_on_failed_stack_state(monkeypatch):
	cfn = FakeCloudFormationClient(
		{
			"dev-baseline": [
				_stack_response("UPDATE_ROLLBACK_FAILED"),
			],
		},
	)
	sts = FakeStsClient()
	monkeypatch.setattr(
		"pulse_aws.baseline.boto3.client",
		ClientFactory({"cloudformation": cfn, "sts": sts}),
	)

	with pytest.raises(BaselineStackError) as exc_info:
		await teardown_baseline_stack("dev")

	assert "failed state" in str(exc_info.value)
	assert "UPDATE_ROLLBACK_FAILED" in str(exc_info.value)
	assert len(cfn.delete_calls) == 0


@pytest.mark.asyncio
async def test_teardown_baseline_stack_waits_if_already_deleting(monkeypatch):
	cfn = FakeCloudFormationClient(
		{
			"dev-baseline": [
				_stack_response("DELETE_IN_PROGRESS"),
				_stack_response("DELETE_IN_PROGRESS"),
				_stack_not_found("dev-baseline"),
			],
		},
	)
	sts = FakeStsClient()
	monkeypatch.setattr(
		"pulse_aws.baseline.boto3.client",
		ClientFactory({"cloudformation": cfn, "sts": sts}),
	)

	async def fake_sleep(_seconds):
		pass

	monkeypatch.setattr("pulse_aws.baseline.asyncio.sleep", fake_sleep)

	await teardown_baseline_stack("dev")
	# Should not call delete_stack since it's already deleting
	assert len(cfn.delete_calls) == 0


@pytest.mark.asyncio
async def test_teardown_baseline_stack_handles_delete_failure(monkeypatch):
	cfn = FakeCloudFormationClient(
		{
			"dev-baseline": [
				_stack_response("CREATE_COMPLETE", DUMMY_OUTPUTS),
				_stack_response("DELETE_IN_PROGRESS"),
				_stack_response("DELETE_FAILED"),
			],
		},
	)
	sts = FakeStsClient()
	ecs = FakeEcsClient(services=[])
	monkeypatch.setattr(
		"pulse_aws.baseline.boto3.client",
		ClientFactory({"cloudformation": cfn, "sts": sts, "ecs": ecs}),
	)

	async def fake_sleep(_seconds):
		pass

	monkeypatch.setattr("pulse_aws.baseline.asyncio.sleep", fake_sleep)

	with pytest.raises(BaselineStackError) as exc_info:
		await teardown_baseline_stack("dev")

	assert "deletion failed" in str(exc_info.value)
	assert "DELETE_FAILED" in str(exc_info.value)
