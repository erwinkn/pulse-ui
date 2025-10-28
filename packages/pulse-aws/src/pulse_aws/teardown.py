"""Teardown helpers for AWS baseline infrastructure."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import boto3
from botocore.exceptions import ClientError

from pulse_aws.baseline import (
	STACK_DELETE_COMPLETE,
	STACK_DELETING,
	STACK_FAILED,
	STACK_NAME_TEMPLATE,
	BaselineStackError,
	describe_stack,
)
from pulse_aws.reporting import DeploymentContext, Reporter, create_context


def _prepare_context(
	context: DeploymentContext | None,
	reporter: Reporter | None,
) -> DeploymentContext:
	"""Normalize context/reporting configuration."""
	if context is None:
		return create_context(reporter=reporter)
	if reporter is not None:
		context.reporter = reporter
	return context


async def teardown_baseline_stack(
	deployment_name: str,
	*,
	region: str | None = None,
	poll_interval: float = 5.0,
	force: bool = False,
	context: DeploymentContext | None = None,
	reporter: Reporter | None = None,
) -> None:
	"""Delete the baseline CloudFormation stack and wait for completion.

	This function will:
	1. Check if any active Pulse ECS services exist (unless force=True)
	2. Delete the baseline CloudFormation stack
	3. Wait for deletion to complete
	4. Handle failure modes gracefully

	Args:
		deployment_name: Name of the deployment (e.g., "prod", "staging")
		region: AWS region (default: use current session region)
		poll_interval: How often to check stack status (seconds)
		force: Skip service existence checks and force deletion
		context: Optional deployment context controlling reporting behaviour
		reporter: Optional reporter override

	Raises:
		BaselineStackError: If deletion fails or active services exist
		ValueError: If deployment_name is empty

	Example::

		await teardown_baseline_stack("dev", force=True)
	"""
	if not deployment_name:
		msg = "deployment_name is required"
		raise ValueError(msg)

	stack_name = STACK_NAME_TEMPLATE.format(env=deployment_name)

	# Get region from session if not provided
	if region is None:
		sts = boto3.client("sts")
		region = cast(str, sts.meta.region_name)

	cfn = boto3.client("cloudformation", region_name=region)
	stack = describe_stack(cfn, stack_name)

	context = _prepare_context(context, reporter)
	reporter = context.reporter

	if not stack:
		reporter.success(f"Stack {stack_name} does not exist, nothing to teardown")
		return

	status = stack["StackStatus"]

	# Handle various stack states
	if status in STACK_FAILED:
		msg = (
			f"Stack {stack_name} is in a failed state ({status}). "
			f"You may need to manually fix or delete it from the AWS Console."
		)
		raise BaselineStackError(msg)

	if status in STACK_DELETING:
		reporter.info(
			f"⏳ Stack {stack_name} is already deleting, waiting for completion..."
		)
		await _wait_for_stack_deletion(cfn, stack_name, poll_interval)
		return

	# Check for active ECS services unless force is specified
	if not force:
		_check_for_active_services(deployment_name, region, reporter)

	# Delete the stack
	reporter.info(f"🗑️  Deleting stack {stack_name}...")
	try:
		cfn.delete_stack(StackName=stack_name)
	except ClientError as exc:
		msg = f"Failed to delete stack {stack_name}: {exc}"
		raise BaselineStackError(msg) from exc

	# Wait for deletion to complete
	await _wait_for_stack_deletion(cfn, stack_name, poll_interval)
	reporter.success(f"Stack {stack_name} deleted successfully")
	reporter.info("⏳ Stack resources may take a few minutes to be deleted...")


async def _wait_for_stack_deletion(
	cfn: Any,
	stack_name: str,
	poll_interval: float,
) -> None:
	"""Wait for a CloudFormation stack to be deleted."""
	while True:
		stack = describe_stack(cfn, stack_name)
		if not stack:
			# Stack no longer exists
			return

		status = stack["StackStatus"]
		if status == STACK_DELETE_COMPLETE:
			return
		if status in STACK_FAILED:
			msg = f"Stack {stack_name} deletion failed with status {status}"
			raise BaselineStackError(msg)

		await asyncio.sleep(max(poll_interval, 1.0))


def _check_for_active_services(
	deployment_name: str,
	region: str,
	reporter: Reporter,
) -> None:
	"""Check if any active Pulse ECS services exist for this deployment.

	Raises BaselineStackError if active services are found.
	"""
	ecs = boto3.client("ecs", region_name=region)
	stack_name = STACK_NAME_TEMPLATE.format(env=deployment_name)

	try:
		# Get the cluster name from the stack
		cfn = boto3.client("cloudformation", region_name=region)
		stack = describe_stack(cfn, stack_name)
		if not stack:
			# Stack doesn't exist, no services to check
			return

		outputs = {
			item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])
		}
		cluster_name = outputs.get("ClusterName")
		if not cluster_name:
			# No cluster output, can't check for services
			return

		# List services in the cluster
		try:
			response = ecs.list_services(cluster=cluster_name, maxResults=10)
			service_arns = response.get("serviceArns", [])

			if service_arns:
				# Get service details to check if any are active
				services_response = ecs.describe_services(
					cluster=cluster_name,
					services=service_arns,
				)
				active_services = [
					svc["serviceName"]
					for svc in services_response.get("services", [])
					if svc.get("status") == "ACTIVE" and svc.get("desiredCount", 0) > 0
				]

				if active_services:
					msg = (
						f"Cannot delete baseline stack {stack_name}: "
						f"{len(active_services)} active Pulse service(s) found: "
						f"{', '.join(active_services)}. "
						f"Drain and remove all services first, or use force=True to override."
					)
					raise BaselineStackError(msg)

		except ClientError as exc:
			if exc.response["Error"]["Code"] == "ClusterNotFoundException":
				# Cluster doesn't exist, no services to worry about
				return
			# For other errors, let it propagate
			raise

	except ClientError as exc:
		# If we can't check for services, warn but don't block
		reporter.warning(f"⚠️  Warning: Could not verify service status: {exc}")


__all__ = [
	"teardown_baseline_stack",
]
