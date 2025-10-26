from __future__ import annotations

from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from pulse_aws.baseline import (
	DEFAULT_CDK_APP_DIR,
	BaselineStackOutputs,
	ensure_baseline_stack,
)

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
	"CustomDomainName": "pulse.example.com",
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

	def describe_stacks(self, *, StackName: str) -> dict:
		self.calls.append(StackName)
		queue = self._responses.setdefault(StackName, [])
		if not queue:
			raise _stack_not_found(StackName)
		response = queue.pop(0)
		if isinstance(response, Exception):
			raise response
		return response


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
			"pulse-dev-baseline": [_stack_response("CREATE_COMPLETE", DUMMY_OUTPUTS)],
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
		"pulse-dev-baseline": [
			_stack_not_found("pulse-dev-baseline"),
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
	monkeypatch.setattr("pulse_aws.baseline.asyncio.sleep", lambda _seconds: None)

	await ensure_baseline_stack(
		"dev",
		domains=["pulse.example.com", "www.pulse.example.com"],
		allowed_ingress_cidrs=["203.0.113.0/24"],
		workdir=str(DEFAULT_CDK_APP_DIR),
	)

	assert any(call[:2] == ["cdk", "synth"] for call in run.calls)
	assert any(
		call[:3] == ["cdk", "deploy", "pulse-dev-baseline"] for call in run.calls
	)
	deploy_call = next(call for call in run.calls if call[1] == "deploy")
	assert (
		"-c" in deploy_call
		and "domains=pulse.example.com,www.pulse.example.com" in deploy_call
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
