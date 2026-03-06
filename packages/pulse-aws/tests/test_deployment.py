from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pulse_aws.baseline import BaselineStackOutputs
from pulse_aws.config import DockerBuild
from pulse_aws.constants import (
	AFFINITY_COOKIE_NAME,
	TARGET_GROUP_STICKINESS_DURATION_SECONDS,
)
from pulse_aws.deployment import (
	DeploymentError,
	_ensure_listener_certificate,
	_target_group_name,
	build_and_push_image,
	create_service_and_target_group,
	deploy,
)


def make_baseline() -> BaselineStackOutputs:
	return BaselineStackOutputs(
		deployment_name="prod",
		region="us-east-1",
		account="123456789012",
		stack_name="prod-baseline",
		listener_arn="arn:listener",
		alb_dns_name="prod.example.com",
		alb_hosted_zone_id="ZTEST123",
		private_subnet_ids=["subnet-private-a", "subnet-private-b"],
		public_subnet_ids=["subnet-public-a", "subnet-public-b"],
		alb_security_group_id="sg-alb",
		service_security_group_id="sg-service",
		cluster_name="pulse-prod",
		log_group_name="/aws/pulse/prod/app",
		ecr_repository_uri="123456789012.dkr.ecr.us-east-1.amazonaws.com/pulse-prod",
		vpc_id="vpc-123",
		execution_role_arn="arn:execution-role",
		task_role_arn="arn:task-role",
	)


class DummyReporter:
	def __init__(self) -> None:
		self.messages: list[tuple[str, str | None]] = []

	def section(self, message: str) -> None:
		self.messages.append(("section", message))

	def info(self, message: str) -> None:
		self.messages.append(("info", message))

	def success(self, message: str) -> None:
		self.messages.append(("success", message))

	def detail(self, message: str) -> None:
		self.messages.append(("detail", message))

	def warning(self, message: str) -> None:
		self.messages.append(("warning", message))

	def blank(self) -> None:
		self.messages.append(("blank", None))


class FakeProc:
	def __init__(self, returncode: int) -> None:
		self.returncode = returncode

	async def wait(self) -> int:
		return self.returncode


class FakeElbv2Client:
	def __init__(
		self,
		*,
		default_certificate: str,
		listener_certificates: list[str],
		ssl_policy: str | None = "ELBSecurityPolicy-TLS13-1-2-2021-06",
	) -> None:
		self.default_certificate = default_certificate
		self.listener_certificates = listener_certificates
		self.ssl_policy = ssl_policy
		self.modify_calls: list[dict[str, Any]] = []
		self.remove_calls: list[dict[str, Any]] = []
		self.default_actions = [
			{
				"Type": "fixed-response",
				"FixedResponseConfig": {"StatusCode": "503"},
			}
		]

	def describe_listeners(self, *, ListenerArns: list[str]) -> dict[str, Any]:
		return {
			"Listeners": [
				{
					"ListenerArn": ListenerArns[0],
					"Certificates": [{"CertificateArn": self.default_certificate}],
					"DefaultActions": self.default_actions,
					"SslPolicy": self.ssl_policy,
				}
			]
		}

	def modify_listener(self, **kwargs: Any) -> None:
		self.modify_calls.append(kwargs)

	def describe_listener_certificates(self, *, ListenerArn: str) -> dict[str, Any]:
		return {
			"Certificates": [
				{"CertificateArn": certificate}
				for certificate in self.listener_certificates
			]
		}

	def remove_listener_certificates(self, **kwargs: Any) -> None:
		self.remove_calls.append(kwargs)


class FakeCreateServiceElbv2Client:
	def __init__(self) -> None:
		self.create_rule_calls: list[dict[str, Any]] = []
		self.modify_target_group_attributes_calls: list[dict[str, Any]] = []

	def create_target_group(self, **kwargs: Any) -> dict[str, Any]:
		return {
			"TargetGroups": [
				{"TargetGroupArn": "arn:aws:elasticloadbalancing:target-group/test"}
			]
		}

	def describe_rules(self, *, ListenerArn: str) -> dict[str, Any]:
		return {
			"Rules": [
				{"Priority": "default", "Actions": []},
				{"Priority": "140", "Actions": []},
			]
		}

	def create_rule(self, **kwargs: Any) -> None:
		self.create_rule_calls.append(kwargs)

	def modify_target_group_attributes(self, **kwargs: Any) -> None:
		self.modify_target_group_attributes_calls.append(kwargs)

	def delete_rule(self, **kwargs: Any) -> None:
		return None

	def delete_target_group(self, **kwargs: Any) -> None:
		return None


class FakeCreateServiceEcsClient:
	def describe_services(self, **kwargs: Any) -> dict[str, Any]:
		return {"services": []}

	def create_service(self, **kwargs: Any) -> dict[str, Any]:
		return {
			"service": {"serviceArn": "arn:aws:ecs:us-east-1:123456789012:service/test"}
		}


def test_target_group_name_is_deterministic_and_bounded():
	deployment_id = "stoneware-v3-preview-deployment-20250306-abcdef"
	name_one = _target_group_name(deployment_id)
	name_two = _target_group_name(deployment_id)

	assert name_one == name_two
	assert len(name_one) <= 32


def test_target_group_name_avoids_truncation_collisions():
	prefix = "stoneware-v3-preview-deployment-"
	name_one = _target_group_name(prefix + "alpha")
	name_two = _target_group_name(prefix + "beta")

	assert name_one != name_two


def test_ensure_listener_certificate_is_noop_when_already_current(monkeypatch):
	client = FakeElbv2Client(
		default_certificate="arn:cert/current",
		listener_certificates=["arn:cert/current"],
	)
	monkeypatch.setattr(
		"pulse_aws.deployment.boto3.client",
		lambda service_name, **_kwargs: client,
	)

	_ensure_listener_certificate(
		"arn:listener",
		"arn:cert/current",
		region="us-east-1",
		reporter=DummyReporter(),
	)

	assert client.modify_calls == []
	assert client.remove_calls == []


def test_ensure_listener_certificate_updates_default_and_removes_stale(monkeypatch):
	client = FakeElbv2Client(
		default_certificate="arn:cert/old-default",
		listener_certificates=[
			"arn:cert/old-default",
			"arn:cert/current",
			"arn:cert/stale",
		],
	)
	monkeypatch.setattr(
		"pulse_aws.deployment.boto3.client",
		lambda service_name, **_kwargs: client,
	)

	_ensure_listener_certificate(
		"arn:listener",
		"arn:cert/current",
		region="us-east-1",
		reporter=DummyReporter(),
	)

	assert len(client.modify_calls) == 1
	modify_call = client.modify_calls[0]
	assert modify_call["ListenerArn"] == "arn:listener"
	assert modify_call["Certificates"] == [{"CertificateArn": "arn:cert/current"}]
	assert modify_call["DefaultActions"] == client.default_actions
	assert modify_call["SslPolicy"] == "ELBSecurityPolicy-TLS13-1-2-2021-06"

	assert len(client.remove_calls) == 1
	removed = {
		certificate["CertificateArn"]
		for certificate in client.remove_calls[0]["Certificates"]
	}
	assert removed == {"arn:cert/old-default", "arn:cert/stale"}


@pytest.mark.asyncio
async def test_build_and_push_image_streams_build_output(tmp_path, monkeypatch):
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")

	calls: list[dict[str, Any]] = []

	async def fake_ecr_login(_region: str) -> None:
		return None

	async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> FakeProc:
		calls.append({"args": list(args), "kwargs": kwargs})
		return FakeProc(1)

	monkeypatch.setattr("pulse_aws.deployment._ecr_login", fake_ecr_login)
	monkeypatch.setattr(
		"pulse_aws.deployment.asyncio.create_subprocess_exec",
		fake_create_subprocess_exec,
	)

	with pytest.raises(DeploymentError, match="Docker build failed"):
		await build_and_push_image(
			dockerfile_path=dockerfile,
			deployment_name="prod",
			deployment_id="prod-20250306-abcdef",
			baseline=make_baseline(),
			context_path=tmp_path,
			reporter=DummyReporter(),
		)

	assert calls[0]["args"][:3] == ["docker", "buildx", "build"]
	assert calls[0]["kwargs"] == {}


@pytest.mark.asyncio
async def test_build_and_push_image_streams_push_output(tmp_path, monkeypatch):
	dockerfile = tmp_path / "Dockerfile"
	dockerfile.write_text("FROM scratch\n")

	procs = [FakeProc(0), FakeProc(1)]
	calls: list[dict[str, Any]] = []

	async def fake_ecr_login(_region: str) -> None:
		return None

	async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> FakeProc:
		calls.append({"args": list(args), "kwargs": kwargs})
		return procs.pop(0)

	monkeypatch.setattr("pulse_aws.deployment._ecr_login", fake_ecr_login)
	monkeypatch.setattr(
		"pulse_aws.deployment.asyncio.create_subprocess_exec",
		fake_create_subprocess_exec,
	)

	with pytest.raises(DeploymentError, match="Docker push failed"):
		await build_and_push_image(
			dockerfile_path=dockerfile,
			deployment_name="prod",
			deployment_id="prod-20250306-abcdef",
			baseline=make_baseline(),
			context_path=tmp_path,
			reporter=DummyReporter(),
		)

	assert calls[0]["args"][:3] == ["docker", "buildx", "build"]
	assert calls[1]["args"][:2] == ["docker", "push"]
	assert calls[0]["kwargs"] == {}
	assert calls[1]["kwargs"] == {}


@pytest.mark.asyncio
async def test_create_service_and_target_group_adds_header_and_cookie_affinity_rules(
	monkeypatch,
):
	elbv2 = FakeCreateServiceElbv2Client()
	ecs = FakeCreateServiceEcsClient()

	def fake_boto3_client(service_name: str, **_kwargs: Any) -> Any:
		if service_name == "elbv2":
			return elbv2
		if service_name == "ecs":
			return ecs
		raise AssertionError(f"Unexpected boto3 client: {service_name}")

	monkeypatch.setattr(
		"pulse_aws.deployment.boto3.client",
		fake_boto3_client,
	)

	service_arn, target_group_arn = await create_service_and_target_group(
		deployment_name="test",
		deployment_id="test-20260306-151500Z",
		task_def_arn="arn:task-definition",
		baseline=make_baseline(),
		reporter=DummyReporter(),
	)

	assert service_arn == "arn:aws:ecs:us-east-1:123456789012:service/test"
	assert target_group_arn == "arn:aws:elasticloadbalancing:target-group/test"
	assert elbv2.modify_target_group_attributes_calls == [
		{
			"TargetGroupArn": "arn:aws:elasticloadbalancing:target-group/test",
			"Attributes": [
				{"Key": "stickiness.enabled", "Value": "true"},
				{"Key": "stickiness.type", "Value": "lb_cookie"},
				{
					"Key": "stickiness.lb_cookie.duration_seconds",
					"Value": str(TARGET_GROUP_STICKINESS_DURATION_SECONDS),
				},
			],
		}
	]
	assert len(elbv2.create_rule_calls) == 2

	header_rule, cookie_rule = elbv2.create_rule_calls
	assert header_rule["Priority"] == 141
	assert header_rule["Conditions"] == [
		{
			"Field": "http-header",
			"HttpHeaderConfig": {
				"HttpHeaderName": "X-Pulse-Render-Affinity",
				"Values": ["test-20260306-151500Z"],
			},
		}
	]
	assert cookie_rule["Priority"] == 142
	assert cookie_rule["Conditions"] == [
		{
			"Field": "http-header",
			"HttpHeaderConfig": {
				"HttpHeaderName": "Cookie",
				"Values": [f"*{AFFINITY_COOKIE_NAME}=test-20260306-151500Z*"],
			},
		}
	]


@pytest.mark.asyncio
def _patch_deploy_dependencies(
	monkeypatch: pytest.MonkeyPatch,
	reporter: DummyReporter,
	baseline: BaselineStackOutputs,
	*,
	domain_routing_result: tuple[bool, bool],
) -> tuple[dict[str, Any], dict[str, Any]]:
	baseline_call: dict[str, Any] = {}
	certificate_call: dict[str, Any] = {}

	async def fake_ensure_certificate_ready(*_args: Any, **_kwargs: Any) -> str:
		return "arn:cert/current"

	async def fake_ensure_baseline_stack(
		deployment_name: str,
		**kwargs: Any,
	) -> BaselineStackOutputs:
		baseline_call["deployment_name"] = deployment_name
		baseline_call.update(kwargs)
		return baseline

	def fake_ensure_listener_certificate(
		listener_arn: str,
		certificate_arn: str,
		*,
		region: str,
		reporter: DummyReporter,
	) -> None:
		certificate_call["listener_arn"] = listener_arn
		certificate_call["certificate_arn"] = certificate_arn
		certificate_call["region"] = region

	async def fake_build_and_push_image(**_kwargs: Any) -> str:
		return "image:tag"

	async def fake_register_task_definition(**_kwargs: Any) -> str:
		return "arn:task-definition"

	async def fake_create_service_and_target_group(**_kwargs: Any) -> tuple[str, str]:
		return ("arn:service", "arn:target-group")

	async def fake_noop(**_kwargs: Any) -> None:
		return None

	async def fake_mark_previous_deployments_as_draining(
		**_kwargs: Any,
	) -> list[str]:
		return []

	async def fake_ensure_domain_routing(
		*_args: Any,
		**_kwargs: Any,
	) -> tuple[bool, bool]:
		return domain_routing_result

	monkeypatch.setattr(
		"pulse_aws.deployment.create_context",
		lambda: SimpleNamespace(reporter=reporter),
	)
	monkeypatch.setattr(
		"pulse_aws.deployment._ensure_certificate_ready",
		fake_ensure_certificate_ready,
	)
	monkeypatch.setattr(
		"pulse_aws.baseline.ensure_baseline_stack",
		fake_ensure_baseline_stack,
	)
	monkeypatch.setattr(
		"pulse_aws.deployment._ensure_listener_certificate",
		fake_ensure_listener_certificate,
	)
	monkeypatch.setattr(
		"pulse_aws.deployment.build_and_push_image",
		fake_build_and_push_image,
	)
	monkeypatch.setattr(
		"pulse_aws.deployment.register_task_definition",
		fake_register_task_definition,
	)
	monkeypatch.setattr(
		"pulse_aws.deployment.create_service_and_target_group",
		fake_create_service_and_target_group,
	)
	monkeypatch.setattr("pulse_aws.deployment.set_deployment_state", fake_noop)
	monkeypatch.setattr(
		"pulse_aws.deployment.install_listener_rules_and_switch_traffic",
		fake_noop,
	)
	monkeypatch.setattr("pulse_aws.deployment.update_service_state_tag", fake_noop)
	monkeypatch.setattr(
		"pulse_aws.deployment.mark_previous_deployments_as_draining",
		fake_mark_previous_deployments_as_draining,
	)
	monkeypatch.setattr(
		"pulse_aws.deployment._ensure_domain_routing",
		fake_ensure_domain_routing,
	)

	return baseline_call, certificate_call


@pytest.mark.asyncio
async def test_deploy_passes_cdk_overrides_to_baseline(monkeypatch, tmp_path):
	custom_cdk_dir = tmp_path / "custom-cdk"
	custom_cdk_dir.mkdir()
	reporter = DummyReporter()
	baseline = make_baseline()
	baseline_call, certificate_call = _patch_deploy_dependencies(
		monkeypatch,
		reporter,
		baseline,
		domain_routing_result=(True, False),
	)

	result = await deploy(
		domain="app.example.com",
		deployment_name="prod",
		docker=DockerBuild(
			dockerfile_path=tmp_path / "Dockerfile",
			context_path=tmp_path,
		),
		cdk_bin="custom-cdk",
		cdk_workdir=custom_cdk_dir,
	)

	assert baseline_call["deployment_name"] == "prod"
	assert baseline_call["cdk_bin"] == "custom-cdk"
	assert baseline_call["workdir"] == custom_cdk_dir
	assert certificate_call == {
		"listener_arn": baseline.listener_arn,
		"certificate_arn": "arn:cert/current",
		"region": baseline.region,
	}
	assert result["certificate_arn"] == "arn:cert/current"


@pytest.mark.asyncio
async def test_deploy_summary_reports_unverified_cloudflare_domain(
	monkeypatch, tmp_path
):
	reporter = DummyReporter()
	baseline = make_baseline()
	_patch_deploy_dependencies(
		monkeypatch,
		reporter,
		baseline,
		domain_routing_result=(False, True),
	)

	await deploy(
		domain="app.example.com",
		deployment_name="prod",
		docker=DockerBuild(
			dockerfile_path=tmp_path / "Dockerfile",
			context_path=tmp_path,
		),
	)

	assert (
		"detail",
		"app.example.com is served via Cloudflare proxy. "
		+ "ALB reachability could not be verified automatically.",
	) in reporter.messages
