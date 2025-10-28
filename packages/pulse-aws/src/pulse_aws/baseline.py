from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import boto3
from botocore.exceptions import ClientError

from pulse_aws.certificate import (
	AcmCertificate,
	DnsConfiguration,
	DnsRecord,
	check_domain_dns,
	ensure_acm_certificate,
)
from pulse_aws.config import ReaperConfig

STACK_NAME_TEMPLATE = "{env}-baseline"
TOOLKIT_STACK_NAME = "CDKToolkit"
BASELINE_STACK_VERSION = "1.3.1"  # Bump when baseline stack changes
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CDK_APP_DIR = PACKAGE_ROOT / "src" / "pulse_aws" / "cdk"
STACK_SUCCEEDED = {
	"CREATE_COMPLETE",
	"UPDATE_COMPLETE",
	"UPDATE_ROLLBACK_COMPLETE",
}
STACK_FAILED = {
	"CREATE_FAILED",
	"ROLLBACK_FAILED",
	"ROLLBACK_COMPLETE",
	"DELETE_FAILED",
	"UPDATE_ROLLBACK_FAILED",
}
STACK_DELETING = {
	"DELETE_IN_PROGRESS",
}
STACK_DELETE_COMPLETE = "DELETE_COMPLETE"


class BaselineStackError(RuntimeError):
	"""Raised when provisioning or describing the baseline stack fails."""


@dataclass(slots=True)
class BaselineStackOutputs:
	deployment_name: str
	region: str
	account: str
	stack_name: str
	listener_arn: str
	alb_dns_name: str
	alb_hosted_zone_id: str
	private_subnet_ids: list[str]
	public_subnet_ids: list[str]
	alb_security_group_id: str
	service_security_group_id: str
	cluster_name: str
	log_group_name: str
	ecr_repository_uri: str
	vpc_id: str
	execution_role_arn: str
	task_role_arn: str

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)


async def ensure_baseline_stack(
	deployment_name: str,
	*,
	certificate_arn: str,
	allowed_ingress_cidrs: Sequence[str] | None = None,
	reaper_config: ReaperConfig | None = None,
	cdk_bin: str = "cdk",
	workdir: Path | str | None = None,
	poll_interval: float = 5.0,
	force_bootstrap: bool = False,
) -> BaselineStackOutputs:
	"""Ensure the shared AWS resources exist and return their identifiers.

	IMPORTANT: This function requires an ISSUED ACM certificate.
	The certificate must be created and validated BEFORE running this function.
	AWS will reject CloudFormation deployments that try to attach a PENDING_VALIDATION
	certificate to an ALB listener. Use ensure_acm_certificate() first and wait for
	validation to complete.

	Requires a certificate ARN. Use ensure_acm_certificate() to mint one:

	Args:
		deployment_name: Name for this deployment (e.g., "prod", "staging")
		certificate_arn: ARN of ACM certificate for HTTPS
		allowed_ingress_cidrs: Optional list of CIDR blocks for ALB access
		reaper_config: Optional reaper configuration (ReaperConfig instance)
		cdk_bin: Path to CDK binary (default: "cdk")
		workdir: Working directory for CDK commands
		poll_interval: How often to check stack status (seconds)
		force_bootstrap: Force re-running CDK bootstrap even if already bootstrapped
		skip_bootstrap_check: Skip bootstrap check entirely (faster but risky if not bootstrapped)

	Example::

		cert = await ensure_acm_certificate(["api.example.com"])
		if cert.dns_configuration:
			print(cert.dns_configuration.format_for_display())

		outputs = await ensure_baseline_stack(
			"prod",
			certificate_arn=cert.arn,
		)
	"""

	if not deployment_name:
		msg = "deployment_name is required"
		raise ValueError(msg)

	if not certificate_arn:
		msg = "certificate_arn is required"
		raise ValueError(msg)

	stack_name = STACK_NAME_TEMPLATE.format(env=deployment_name)

	sts = boto3.client("sts")
	region = cast(str, sts.meta.region_name)
	account = cast(str, sts.get_caller_identity()["Account"])

	cfn = boto3.client("cloudformation", region_name=region)
	stack = describe_stack(cfn, stack_name)

	# Check if stack exists and is up-to-date
	if stack and is_stack_healthy(stack):
		current_version = get_stack_version(stack)
		if current_version == BASELINE_STACK_VERSION:
			# Stack exists and is current version, return outputs
			return extract_stack_outputs(
				deployment_name,
				region,
				account,
				stack_name,
				stack,
			)
		else:
			# Stack exists but is outdated, will update below
			print(
				f"📦 Updating stack ({current_version} -> {BASELINE_STACK_VERSION})",
			)

	_ensure_bootstrap(cfn, cdk_bin, account, region, workdir, force=force_bootstrap)

	context = {
		"deployment_name": deployment_name,
		"certificate_arn": certificate_arn,
	}
	if allowed_ingress_cidrs:
		context["allowed_ingress_cidrs"] = ",".join(allowed_ingress_cidrs)

	# Add reaper config if provided
	if reaper_config:
		context["reaper_schedule_minutes"] = str(reaper_config.schedule_minutes)
		context["reaper_consecutive_periods"] = str(reaper_config.consecutive_periods)
		context["reaper_period_seconds"] = str(reaper_config.period_seconds)
		context["reaper_min_age_seconds"] = str(reaper_config.min_age_seconds)
		context["reaper_max_age_hours"] = str(reaper_config.max_age_hours)

	# Add version tag to track baseline stack version
	tags = {"pulse-cf-version": BASELINE_STACK_VERSION}

	cdk_run(cdk_bin, "synth", context, workdir)
	cdk_run(cdk_bin, "deploy", context, workdir, stack_name=stack_name, tags=tags)

	return await wait_for_stack_outputs(
		cfn,
		stack_name,
		deployment_name,
		region,
		account,
		poll_interval=poll_interval,
	)


def _ensure_bootstrap(
	cfn: Any,
	cdk_bin: str,
	account: str,
	region: str,
	workdir: Path | str | None,
	*,
	force: bool = False,
) -> None:
	"""Ensure CDK is bootstrapped in the target account/region.

	Args:
		cfn: CloudFormation client
		cdk_bin: Path to CDK binary
		account: AWS account ID
		region: AWS region
		workdir: Working directory for CDK commands
		force: Force re-running bootstrap even if already bootstrapped
	"""
	if not force:
		stack = describe_stack(cfn, TOOLKIT_STACK_NAME)
		if stack and is_stack_healthy(stack):
			return

	target = f"aws://{account}/{region}"
	cdk_run(cdk_bin, "bootstrap", {}, workdir, stack_name=target)


def cdk_run(
	cdk_bin: str,
	command: str,
	context: Mapping[str, str],
	workdir: Path | str | None,
	stack_name: str | None = None,
	tags: Mapping[str, str] | None = None,
) -> None:
	# Bootstrap doesn't need the CDK app, so run it from anywhere
	if command == "bootstrap":
		args = [cdk_bin, command]
		if stack_name:
			args.append(stack_name)
		try:
			subprocess.run(args, check=True)
		except FileNotFoundError as exc:
			msg = f"Unable to execute '{cdk_bin}'. Install AWS CDK CLI and try again."
			raise BaselineStackError(msg) from exc
		except subprocess.CalledProcessError as exc:
			msg = f"'{' '.join(args)}' exited with code {exc.returncode}"
			raise BaselineStackError(msg) from exc
		return

	# Other commands need to run from the CDK app directory
	cwd = Path(workdir) if workdir is not None else DEFAULT_CDK_APP_DIR
	if not cwd.exists():
		msg = f"CDK app directory '{cwd}' does not exist"
		raise BaselineStackError(msg)
	args = [cdk_bin, command]
	if stack_name:
		args.append(stack_name)
	for key, value in context.items():
		args.extend(["-c", f"{key}={value}"])
	if command == "deploy":
		args.extend(["--require-approval", "never"])
		# Add tags for version tracking
		if tags:
			for key, value in tags.items():
				args.extend(["--tags", f"{key}={value}"])
	try:
		subprocess.run(
			args,
			check=True,
			cwd=str(cwd),
		)
	except FileNotFoundError as exc:
		msg = f"Unable to execute '{cdk_bin}'. Install AWS CDK CLI and try again."
		raise BaselineStackError(msg) from exc
	except subprocess.CalledProcessError as exc:
		msg = f"'{' '.join(args)}' exited with code {exc.returncode}"
		raise BaselineStackError(msg) from exc


async def wait_for_stack_outputs(
	cfn: Any,
	stack_name: str,
	deployment_name: str,
	region: str,
	account: str,
	*,
	poll_interval: float,
) -> BaselineStackOutputs:
	while True:
		stack = describe_stack(cfn, stack_name)
		if not stack:
			msg = f"Stack {stack_name} not found after deployment"
			raise BaselineStackError(msg)

		status = stack["StackStatus"]
		if status in STACK_SUCCEEDED:
			return extract_stack_outputs(
				deployment_name,
				region,
				account,
				stack_name,
				stack,
			)
		if status in STACK_FAILED:
			msg = f"Stack {stack_name} failed with status {status}"
			raise BaselineStackError(msg)
		await asyncio.sleep(max(poll_interval, 1.0))


def extract_stack_outputs(
	deployment_name: str,
	region: str,
	account: str,
	stack_name: str,
	stack: Mapping[str, Any],
) -> BaselineStackOutputs:
	outputs = {
		item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])
	}

	def require(key: str) -> str:
		if key not in outputs or not outputs[key]:
			msg = f"Missing CloudFormation output '{key}' on stack {stack_name}"
			raise BaselineStackError(msg)
		return outputs[key]

	return BaselineStackOutputs(
		deployment_name=deployment_name,
		region=region,
		account=account,
		stack_name=stack_name,
		listener_arn=require("ListenerArn"),
		alb_dns_name=require("AlbDnsName"),
		alb_hosted_zone_id=require("AlbHostedZoneId"),
		private_subnet_ids=split_commas(require("PrivateSubnets")),
		public_subnet_ids=split_commas(require("PublicSubnets")),
		alb_security_group_id=require("AlbSecurityGroupId"),
		service_security_group_id=require("ServiceSecurityGroupId"),
		cluster_name=require("ClusterName"),
		log_group_name=require("LogGroupName"),
		ecr_repository_uri=require("EcrRepositoryUri"),
		vpc_id=require("VpcId"),
		execution_role_arn=require("ExecutionRoleArn"),
		task_role_arn=require("TaskRoleArn"),
	)


def split_commas(value: str) -> list[str]:
	return [item.strip() for item in value.split(",") if item.strip()]


def describe_stack(cfn: Any, stack_name: str) -> dict[str, Any] | None:
	try:
		response = cfn.describe_stacks(StackName=stack_name)
	except ClientError as exc:
		if (
			exc.response["Error"]["Code"] == "ValidationError"
			and "does not exist" in exc.response["Error"]["Message"]
		):
			return None
		raise
	return response["Stacks"][0]


def is_stack_healthy(stack: Mapping[str, Any]) -> bool:
	return stack.get("StackStatus") in STACK_SUCCEEDED


def get_stack_version(stack: Mapping[str, Any]) -> str | None:
	"""Extract the baseline version from stack tags."""
	tags = stack.get("Tags", [])
	for tag in tags:
		if tag.get("Key") == "pulse-cf-version":
			return tag.get("Value")
	return None


__all__ = [
	"AcmCertificate",
	"BASELINE_STACK_VERSION",
	"BaselineStackError",
	"BaselineStackOutputs",
	"DnsConfiguration",
	"DnsRecord",
	"STACK_DELETE_COMPLETE",
	"STACK_DELETING",
	"STACK_FAILED",
	"STACK_NAME_TEMPLATE",
	"STACK_SUCCEEDED",
	"check_domain_dns",
	"describe_stack",
	"ensure_acm_certificate",
	"ensure_baseline_stack",
]
