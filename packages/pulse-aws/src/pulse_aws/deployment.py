"""Deployment workflow helpers for AWS ECS."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import boto3
from botocore.exceptions import ClientError

from pulse_aws.baseline import BaselineStackOutputs
from pulse_aws.certificate import (
	CertificateError,
	DnsConfiguration,
	check_domain_dns,
	domain_uses_cloudflare_proxy,
	ensure_acm_certificate,
)
from pulse_aws.reporting import DeploymentContext, Reporter, create_context


class DeploymentError(RuntimeError):
	"""Raised when deployment operations fail."""


@dataclass
class DockerBuild:
	"""Docker build configuration.

	Attributes:
	    dockerfile_path: Path to the Dockerfile
	    context_path: Path to the Docker build context directory
	    build_args: Additional build arguments to pass to docker build
	"""

	dockerfile_path: Path
	context_path: Path
	build_args: dict[str, str] = field(default_factory=dict)


@dataclass
class TaskConfig:
	"""ECS task configuration.

	Attributes:
	    cpu: CPU units (256, 512, 1024, etc.)
	    memory: Memory in MB (512, 1024, 2048, etc.)
	    desired_count: Number of tasks to run
	    env_vars: Environment variables for the task
	"""

	cpu: str = "256"
	memory: str = "512"
	desired_count: int = 2
	env_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class HealthCheckConfig:
	"""ALB health check configuration.

	Attributes:
	    path: Path for ALB health checks
	    interval_seconds: Seconds between health checks
	    timeout_seconds: Health check timeout in seconds
	    healthy_threshold: Consecutive successes to be healthy
	    unhealthy_threshold: Consecutive failures to be unhealthy
	    wait_for_health: Wait for targets to be healthy before switching traffic
	    min_healthy_targets: Minimum healthy targets required before switching
	"""

	path: str = "/_health"
	interval_seconds: int = 30
	timeout_seconds: int = 5
	healthy_threshold: int = 2
	unhealthy_threshold: int = 3
	wait_for_health: bool = True
	min_healthy_targets: int = 2


@dataclass
class DrainConfig:
	"""Drain configuration.

	Attributes:
	    drain_secret: Secret for drain endpoint (auto-generated if None)
	    timeout_seconds: Maximum time to wait for draining (unused, kept for compatibility)
	    poll_interval: Seconds between drain health checks (unused, kept for compatibility)
	"""

	drain_secret: str | None = None
	timeout_seconds: float = 180
	poll_interval: float = 10


def generate_deployment_id(deployment_name: str) -> str:
	"""Generate a timestamped deployment ID.

	Args:
	    deployment_name: The deployment environment name (e.g., "prod", "dev")

	Returns:
	    A deployment ID like "prod-20251027-183000Z"

	Example::

	    deployment_id = generate_deployment_id("prod")
	    # Returns: "prod-20251027-183000Z"
	"""
	timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%SZ")
	return f"{deployment_name}-{timestamp}"


def _resolve_reporter(reporter: Reporter | None) -> Reporter:
	if reporter is None:
		return create_context().reporter
	return reporter


async def _wait_for_confirmation(
	context: DeploymentContext,
	message: str,
) -> None:
	"""Prompt the user to confirm before continuing; abort on cancel."""
	if not context.interactive:
		return

	context.reporter.info(message)
	context.reporter.detail("Press Enter to continue or type 'cancel' to abort.")
	try:
		response = await asyncio.to_thread(input, "> ")
	except EOFError:
		response = ""
	except KeyboardInterrupt as exc:
		raise DeploymentError("Deployment cancelled by user") from exc

	if response.strip().lower() in {"cancel", "c", "quit", "q"}:
		raise DeploymentError("Deployment cancelled by user")


async def _prompt_retry(
	context: DeploymentContext,
	message: str,
) -> bool:
	"""Ask the user whether to retry waiting; returns False to skip further checks."""
	if not context.interactive:
		return False

	context.reporter.info(message)
	context.reporter.detail(
		"Press Enter to retry, type 'skip' to continue without waiting, or 'cancel' to abort."
	)
	try:
		response = await asyncio.to_thread(input, "> ")
	except EOFError:
		response = ""
	except KeyboardInterrupt as exc:
		raise DeploymentError("Deployment cancelled by user") from exc

	response = response.strip().lower()
	if response in {"cancel", "c", "quit", "q"}:
		raise DeploymentError("Deployment cancelled by user")
	if response == "skip":
		return False
	return True


def _prepare_context(
	context: DeploymentContext | None,
	reporter: Reporter | None,
) -> DeploymentContext:
	"""Normalize context/reporter configuration."""
	if context is None:
		return create_context(reporter=reporter)
	if reporter is not None:
		context.reporter = reporter
	return context


def _emit_dns_instructions(config: DnsConfiguration, reporter: Reporter) -> None:
	"""Print DNS instructions via the reporter."""
	instructions = config.format_for_display()
	for line in instructions.splitlines():
		reporter.info(line)


async def _ensure_certificate_ready(
	domain: str,
	provided_arn: str | None,
	context: DeploymentContext,
) -> str:
	"""Ensure an ISSUED ACM certificate exists for the deployment domain."""
	reporter = context.reporter

	if provided_arn:
		reporter.info(f"Using provided ACM certificate: {provided_arn}")
		return provided_arn

	reporter.info(f"Ensuring ACM certificate for {domain}...")
	try:
		cert = await ensure_acm_certificate(
			domain,
			wait=False,
			announce=False,
		)
	except CertificateError as exc:
		raise DeploymentError(str(exc)) from exc

	if not cert.arn:
		raise DeploymentError("No certificate ARN available")

	if cert.dns_configuration:
		reporter.blank()
		_emit_dns_instructions(cert.dns_configuration, reporter)
		reporter.blank()

	if cert.status == "ISSUED":
		reporter.success(f"Certificate ready: {cert.arn}")
		return cert.arn

	message = (
		f"Certificate for {domain} is pending DNS validation. "
		"Add the required DNS records before continuing."
	)

	if context.ci:
		reporter.warning(message)
		raise DeploymentError(
			f"{message} Configure the DNS records shown above and rerun the deployment."
		)

	reporter.warning(message)
	await _wait_for_confirmation(
		context,
		"Press Enter once the DNS validation records have been created.",
	)

	try:
		cert = await ensure_acm_certificate(
			domain,
			wait=True,
			announce=False,
		)
	except CertificateError as exc:
		raise DeploymentError(str(exc)) from exc

	if cert.status != "ISSUED":
		raise DeploymentError(
			f"Certificate for {domain} did not become ISSUED (status: {cert.status})"
		)

	reporter.success(f"Certificate issued: {cert.arn}")
	return cert.arn


async def _ensure_domain_routing(
	domain: str,
	baseline: BaselineStackOutputs,
	context: DeploymentContext,
) -> tuple[bool, bool]:
	"""Ensure the custom domain resolves to the ALB, prompting the user if needed.

	Returns:
	    Tuple of (is_ready, is_proxied)
	"""
	reporter = context.reporter
	config = check_domain_dns(domain, baseline.alb_dns_name)

	if config is None:
		proxied = domain_uses_cloudflare_proxy(domain)
		if proxied:
			reporter.info(
				f"{domain} appears to be served through Cloudflare; skipping direct ALB IP verification."
			)
			return True, True
		reporter.success(f"{domain} resolves to {baseline.alb_dns_name}; DNS is ready.")
		return True, False

	reporter.warning(
		f"{domain} does not yet resolve to the load balancer ({baseline.alb_dns_name})."
	)
	reporter.blank()
	_emit_dns_instructions(config, reporter)
	reporter.blank()

	if context.ci:
		reporter.warning(
			"DNS propagation cannot be confirmed in CI. Update the record and rerun verification."
		)
		return False, False

	while True:
		should_retry = await _prompt_retry(
			context,
			f"Update the DNS record for {domain}. Press Enter to re-check once propagation should be complete.",
		)
		if not should_retry:
			reporter.warning(
				f"Skipping DNS wait. Ensure {domain} points to {baseline.alb_dns_name} before going live."
			)
			return False, False

		config = check_domain_dns(domain, baseline.alb_dns_name)
		if config is None:
			proxied = domain_uses_cloudflare_proxy(domain)
			if proxied:
				reporter.info(
					f"{domain} appears to be served through Cloudflare; skipping direct ALB IP verification."
				)
				return True, True
			reporter.success(f"{domain} now resolves to {baseline.alb_dns_name}.")
			return True, False

		reporter.warning(
			f"{domain} still does not resolve to the load balancer. DNS changes can take a few minutes."
		)
		reporter.blank()
		_emit_dns_instructions(config, reporter)
		reporter.blank()


async def build_and_push_image(
	dockerfile_path: Path,
	deployment_id: str,
	baseline: BaselineStackOutputs,
	*,
	drain_secret: str,
	context_path: Path,
	build_args: dict[str, str] | None = None,
	reporter: Reporter | None = None,
) -> str:
	"""Build a Docker image and push it to the baseline ECR repository.

	Args:
	    dockerfile_path: Path to the Dockerfile
	    deployment_id: Unique deployment ID to use as the image tag
	    baseline: Baseline stack outputs containing ECR repository URI
	    drain_secret: Secret for the drain endpoint
	    context_path: Path to the Docker build context directory
	    build_args: Additional build arguments to pass to docker build

	Returns:
	    The full image URI with tag (e.g., "123.dkr.ecr.us-east-1.amazonaws.com/repo:tag")

	Raises:
	    DeploymentError: If build or push fails
	"""
	reporter = _resolve_reporter(reporter)

	if not dockerfile_path.exists():
		msg = f"Dockerfile not found: {dockerfile_path}"
		raise DeploymentError(msg)

	if not context_path.exists():
		msg = f"Build context path not found: {context_path}"
		raise DeploymentError(msg)

	ecr_repo = baseline.ecr_repository_uri
	image_uri = f"{ecr_repo}:{deployment_id}"

	# Authenticate Docker with ECR
	reporter.info("Authenticating Docker with ECR...")
	await _ecr_login(baseline.region)

	# Build the image
	reporter.info(f"Building image: {image_uri}")
	all_build_args = {
		"DEPLOYMENT_ID": deployment_id,
		"DRAIN_SECRET": drain_secret,
		**(build_args or {}),
	}

	build_cmd = [
		"docker",
		"build",
		"--platform",
		"linux/amd64",
		"-f",
		str(dockerfile_path),
		"-t",
		image_uri,
	]

	for key, value in all_build_args.items():
		build_cmd.extend(["--build-arg", f"{key}={value}"])

	# Add the build context path
	build_cmd.append(str(context_path))

	try:
		proc = await asyncio.create_subprocess_exec(
			*build_cmd,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.STDOUT,
		)
		stdout, _ = await proc.communicate()
		if proc.returncode != 0:
			output = stdout.decode() if stdout else ""
			msg = f"Docker build failed:\n{output}"
			raise DeploymentError(msg)
	except FileNotFoundError as exc:
		msg = "Docker is not installed or not in PATH"
		raise DeploymentError(msg) from exc

	# Push the image
	reporter.info("Pushing image to ECR...")
	push_cmd = ["docker", "push", image_uri]
	try:
		proc = await asyncio.create_subprocess_exec(
			*push_cmd,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.STDOUT,
		)
		stdout, _ = await proc.communicate()
		if proc.returncode != 0:
			output = stdout.decode() if stdout else ""
			msg = f"Docker push failed:\n{output}"
			raise DeploymentError(msg)
	except FileNotFoundError as exc:
		msg = "Docker is not installed or not in PATH"
		raise DeploymentError(msg) from exc

	reporter.success(f"Image pushed: {image_uri}")
	return image_uri


async def _ecr_login(region: str) -> None:
	"""Authenticate Docker with ECR."""
	ecr = boto3.client("ecr", region_name=region)

	try:
		response = ecr.get_authorization_token()
		auth_data = cast(dict[str, str], response["authorizationData"][0])
		auth_token = auth_data["authorizationToken"]
		token = base64.b64decode(auth_token).decode()
		username, password = token.split(":", 1)
		registry = auth_data["proxyEndpoint"]

		# Login to Docker
		login_cmd: list[str] = [
			"docker",
			"login",
			"--username",
			username,
			"--password-stdin",
			registry,
		]
		proc = await asyncio.create_subprocess_exec(
			*login_cmd,
			stdin=asyncio.subprocess.PIPE,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
		)
		await proc.communicate(input=password.encode())
		if proc.returncode != 0:
			msg = "Failed to authenticate with ECR"
			raise DeploymentError(msg)
	except ClientError as exc:
		msg = f"Failed to get ECR authorization token: {exc}"
		raise DeploymentError(msg) from exc


async def register_task_definition(
	image_uri: str,
	deployment_id: str,
	baseline: BaselineStackOutputs,
	*,
	cpu: str = "256",
	memory: str = "512",
	env_vars: dict[str, str] | None = None,
	reporter: Reporter | None = None,
) -> str:
	"""Register an ECS Fargate task definition.

	Args:
	    image_uri: Full URI of the Docker image
	    deployment_id: Unique deployment ID
	    baseline: Baseline stack outputs
	    cpu: CPU units (256, 512, 1024, etc.)
	    memory: Memory in MB (512, 1024, 2048, etc.)
	    env_vars: Additional environment variables

	Returns:
	    The ARN of the registered task definition

	Raises:
	    DeploymentError: If registration fails
	"""
	reporter = _resolve_reporter(reporter)

	ecs = boto3.client("ecs", region_name=baseline.region)

	family = f"{baseline.deployment_name}-app"
	container_name = "app"

	# Build environment variables
	environment = [
		{"name": "DEPLOYMENT_NAME", "value": baseline.deployment_name},
		{"name": "DEPLOYMENT_ID", "value": deployment_id},
		*[{"name": k, "value": v} for k, v in (env_vars or {}).items()],
	]

	task_def = {
		"family": family,
		"networkMode": "awsvpc",
		"requiresCompatibilities": ["FARGATE"],
		"cpu": cpu,
		"memory": memory,
		"executionRoleArn": baseline.execution_role_arn,
		"taskRoleArn": baseline.task_role_arn,
		"containerDefinitions": [
			{
				"name": container_name,
				"image": image_uri,
				"essential": True,
				"portMappings": [
					{
						"containerPort": 8000,
						"protocol": "tcp",
					}
				],
				"environment": environment,
				"logConfiguration": {
					"logDriver": "awslogs",
					"options": {
						"awslogs-group": baseline.log_group_name,
						"awslogs-region": baseline.region,
						"awslogs-stream-prefix": deployment_id,
					},
				},
			}
		],
		"tags": [
			{"key": "deployment-id", "value": deployment_id},
			{"key": "deployment-name", "value": baseline.deployment_name},
		],
	}

	reporter.info(f"Registering task definition: {family}")
	try:
		response = ecs.register_task_definition(**task_def)
		task_def_arn = response["taskDefinition"]["taskDefinitionArn"]
		reporter.success(f"Task definition registered: {task_def_arn}")
		return cast(str, task_def_arn)
	except ClientError as exc:
		msg = f"Failed to register task definition: {exc}"
		raise DeploymentError(msg) from exc


async def set_deployment_state(
	deployment_name: str,
	deployment_id: str,
	state: str,
	*,
	region: str,
	reporter: Reporter | None = None,
) -> None:
	"""Set the deployment state in SSM Parameter Store.

	Args:
	    deployment_name: The deployment environment name (e.g., "prod", "dev")
	    deployment_id: Unique deployment ID
	    state: Deployment state ("active" or "draining")
	    region: AWS region
	    reporter: Optional reporter for logging

	Raises:
	    DeploymentError: If SSM parameter update fails
	"""
	reporter = _resolve_reporter(reporter)

	ssm = boto3.client("ssm", region_name=region)
	param_name = f"/apps/{deployment_name}/{deployment_id}/state"

	try:
		ssm.put_parameter(
			Name=param_name,
			Value=state,
			Type="String",
			Overwrite=True,
		)
		reporter.detail(f"Set SSM parameter {param_name} = {state}")
	except ClientError as exc:
		msg = f"Failed to set deployment state in SSM: {exc}"
		raise DeploymentError(msg) from exc


async def mark_previous_deployments_as_draining(
	deployment_name: str,
	current_deployment_id: str,
	baseline: BaselineStackOutputs,
	*,
	reporter: Reporter | None = None,
) -> list[str]:
	"""Mark all previous deployments as draining in SSM and update service tags.

	For each deployment that is not the current one:
	1. Set SSM parameter `/apps/<deployment_name>/<deployment_id>/state` to "draining"
	2. Tag the ECS service with `state=draining`

	Args:
	    deployment_name: The deployment environment name
	    current_deployment_id: The current deployment ID (should NOT be marked as draining)
	    baseline: Baseline stack outputs
	    reporter: Optional reporter for logging

	Returns:
	    List of deployment IDs that were marked as draining

	Raises:
	    DeploymentError: If listing services or updating state fails
	"""
	reporter = _resolve_reporter(reporter)

	ecs = boto3.client("ecs", region_name=baseline.region)

	reporter.info("Marking previous deployments as draining...")

	# Find all active services except the current one
	try:
		response = ecs.list_services(cluster=baseline.cluster_name)
		service_arns = response.get("serviceArns", [])

		if not service_arns:
			reporter.info("No previous deployments found")
			return []

		# Get service details
		services_detail = ecs.describe_services(
			cluster=baseline.cluster_name,
			services=service_arns,
		)

		# Filter for active services, excluding current
		previous_services = [
			svc
			for svc in services_detail.get("services", [])
			if svc.get("status") == "ACTIVE"
			and svc["serviceName"] != current_deployment_id
		]

		if not previous_services:
			reporter.info("No previous deployments to mark as draining")
			return []

	except ClientError as exc:
		msg = f"Failed to list services: {exc}"
		raise DeploymentError(msg) from exc

	# Mark each previous deployment as draining
	drained_ids = []

	for svc in previous_services:
		old_deployment_id = svc["serviceName"]
		service_arn = svc["serviceArn"]

		reporter.detail(f"Marking {old_deployment_id} as draining...")

		# Set SSM parameter
		await set_deployment_state(
			deployment_name=deployment_name,
			deployment_id=old_deployment_id,
			state="draining",
			region=baseline.region,
			reporter=reporter,
		)

		# Update service tags
		try:
			ecs.tag_resource(
				resourceArn=service_arn,
				tags=[
					{"key": "deployment_name", "value": deployment_name},
					{"key": "deployment_id", "value": old_deployment_id},
					{"key": "state", "value": "draining"},
				],
			)
		except ClientError as exc:
			reporter.warning(f"Failed to tag service {old_deployment_id}: {exc}")

		drained_ids.append(old_deployment_id)

	if drained_ids:
		reporter.success(f"Marked {len(drained_ids)} deployment(s) as draining")

	return drained_ids


async def create_service_and_target_group(
	deployment_name: str,
	deployment_id: str,
	task_def_arn: str,
	baseline: BaselineStackOutputs,
	*,
	desired_count: int = 2,
	health_check_path: str = "/_health",
	health_check_interval: int = 30,
	health_check_timeout: int = 5,
	healthy_threshold: int = 2,
	unhealthy_threshold: int = 3,
	reporter: Reporter | None = None,
) -> tuple[str, str]:
	"""Create an ALB target group and ECS service for a deployment.

	Args:
	    deployment_name: The deployment environment name
	    deployment_id: Unique deployment ID
	    task_def_arn: ARN of the task definition to use
	    baseline: Baseline stack outputs
	    desired_count: Number of tasks to run
	    health_check_path: Path for ALB health checks
	    health_check_interval: Seconds between health checks
	    health_check_timeout: Health check timeout in seconds
	    healthy_threshold: Consecutive successes to be healthy
	    unhealthy_threshold: Consecutive failures to be unhealthy

	Returns:
	    Tuple of (service_arn, target_group_arn)

	Raises:
	    DeploymentError: If a service with this deployment_id already exists or creation fails
	"""
	reporter = _resolve_reporter(reporter)

	ecs = boto3.client("ecs", region_name=baseline.region)
	elbv2 = boto3.client("elbv2", region_name=baseline.region)

	service_name = deployment_id
	tg_name = deployment_id[:32]  # ALB target group names limited to 32 chars

	# Check if service already exists
	try:
		response = ecs.describe_services(
			cluster=baseline.cluster_name,
			services=[service_name],
		)
		services = response.get("services", [])
		if services and services[0].get("status") != "INACTIVE":
			msg = (
				f"Service {service_name} already exists in cluster {baseline.cluster_name}. "
				f"Use a different deployment_id or delete the existing service first."
			)
			raise DeploymentError(msg)
	except ClientError:
		pass  # Service doesn't exist, continue

	# Create target group
	reporter.info(f"Creating target group {tg_name}...")
	try:
		tg_response = elbv2.create_target_group(
			Name=tg_name,
			Protocol="HTTP",
			Port=8000,
			VpcId=baseline.vpc_id,
			TargetType="ip",
			HealthCheckEnabled=True,
			HealthCheckProtocol="HTTP",
			HealthCheckPath=health_check_path,
			HealthCheckIntervalSeconds=health_check_interval,
			HealthCheckTimeoutSeconds=health_check_timeout,
			HealthyThresholdCount=healthy_threshold,
			UnhealthyThresholdCount=unhealthy_threshold,
			Tags=[
				{"Key": "deployment-id", "Value": deployment_id},
				{"Key": "deployment-name", "Value": deployment_name},
			],
		)
		target_group_arn = tg_response["TargetGroups"][0]["TargetGroupArn"]
		reporter.success(f"Target group created: {target_group_arn}")
	except ClientError as exc:
		if exc.response["Error"]["Code"] == "DuplicateTargetGroupName":
			msg = (
				f"Target group {tg_name} already exists. "
				f"This deployment_id may have been used before. "
				f"Delete the old target group or use a new deployment_id."
			)
			raise DeploymentError(msg) from exc
		msg = f"Failed to create target group: {exc}"
		raise DeploymentError(msg) from exc

	# Attach target group to listener with a temporary rule
	# AWS requires target groups to be associated with a listener before creating an ECS service
	reporter.info("Attaching target group to HTTPS listener...")
	try:
		# Find the next available priority
		rules_response = elbv2.describe_rules(ListenerArn=baseline.listener_arn)
		existing_rules = rules_response["Rules"]
		max_priority = 99
		for rule in existing_rules:
			rule_priority = rule.get("Priority")
			if rule_priority != "default":
				try:
					priority = int(str(rule_priority))  # pyright: ignore[reportUnknownArgumentType]
					max_priority = max(max_priority, priority)
				except ValueError:
					pass
		next_priority = max_priority + 1

		# Create header-based routing rule for sticky sessions
		elbv2.create_rule(
			ListenerArn=baseline.listener_arn,
			Priority=next_priority,
			Conditions=[
				{
					"Field": "http-header",
					"HttpHeaderConfig": {
						"HttpHeaderName": "X-Pulse-Render-Affinity",
						"Values": [deployment_id],
					},
				}
			],
			Actions=[
				{
					"Type": "forward",
					"TargetGroupArn": target_group_arn,
				}
			],
			Tags=[
				{"Key": "deployment-id", "Value": deployment_id},
				{"Key": "deployment-name", "Value": deployment_name},
			],
		)
		reporter.success(
			f"Target group attached with routing rule (priority {next_priority})"
		)
	except ClientError as exc:
		# Clean up target group if listener rule creation fails
		try:
			elbv2.delete_target_group(TargetGroupArn=target_group_arn)
		except Exception:
			pass
		msg = f"Failed to create listener rule: {exc}"
		raise DeploymentError(msg) from exc

	# Create ECS service
	reporter.info(f"Creating ECS service {service_name}...")
	try:
		service_response = ecs.create_service(
			cluster=baseline.cluster_name,
			serviceName=service_name,
			taskDefinition=task_def_arn,
			desiredCount=desired_count,
			launchType="FARGATE",
			networkConfiguration={
				"awsvpcConfiguration": {
					"subnets": baseline.private_subnet_ids,
					"securityGroups": [baseline.service_security_group_id],
					"assignPublicIp": "DISABLED",
				}
			},
			loadBalancers=[
				{
					"targetGroupArn": target_group_arn,
					"containerName": "app",
					"containerPort": 8000,
				}
			],
			healthCheckGracePeriodSeconds=60,
			tags=[
				{"key": "deployment_id", "value": deployment_id},
				{"key": "deployment_name", "value": deployment_name},
				{"key": "state", "value": "active"},
			],
		)
		service_arn = service_response["service"]["serviceArn"]
		reporter.success(f"ECS service created: {service_arn}")
		return cast(str, service_arn), cast(str, target_group_arn)
	except ClientError as exc:
		# Clean up the target group if service creation fails
		try:
			elbv2.delete_target_group(TargetGroupArn=target_group_arn)
		except Exception:
			pass  # Best effort cleanup
		msg = f"Failed to create ECS service: {exc}"
		raise DeploymentError(msg) from exc


async def wait_for_healthy_targets(
	target_group_arn: str,
	baseline: BaselineStackOutputs,
	*,
	min_healthy_targets: int = 1,
	timeout_seconds: float = 300,
	poll_interval: float = 10,
	reporter: Reporter | None = None,
) -> None:
	"""Wait for target group to have healthy targets.

	Args:
	    target_group_arn: ARN of the target group to check
	    baseline: Baseline stack outputs
	    min_healthy_targets: Minimum number of healthy targets required
	    timeout_seconds: Maximum time to wait (default: 5 minutes)
	    poll_interval: Seconds between health checks (default: 10)

	Raises:
	    DeploymentError: If timeout is reached before targets become healthy
	"""
	reporter = _resolve_reporter(reporter)

	elbv2 = boto3.client("elbv2", region_name=baseline.region)
	start_time = asyncio.get_event_loop().time()

	reporter.info(f"Waiting for {min_healthy_targets} healthy target(s)...")

	while True:
		elapsed = asyncio.get_event_loop().time() - start_time
		if elapsed >= timeout_seconds:
			msg = f"Timeout waiting for healthy targets after {timeout_seconds:.0f}s"
			raise DeploymentError(msg)

		try:
			response = elbv2.describe_target_health(TargetGroupArn=target_group_arn)
			targets = response.get("TargetHealthDescriptions", [])

			healthy_count = sum(
				1
				for t in targets
				if t.get("TargetHealth", {}).get("State") == "healthy"
			)
			total_count = len(targets)

			if healthy_count >= min_healthy_targets:
				reporter.success(f"{healthy_count}/{total_count} target(s) healthy")
				return

			# Show progress
			if total_count > 0:
				states = {}
				for t in targets:
					state = t.get("TargetHealth", {}).get("State", "unknown")
					states[state] = states.get(state, 0) + 1
				status = ", ".join(
					f"{count} {state}" for state, count in states.items()
				)
				reporter.detail(f"Waiting... ({status}) [{elapsed:.0f}s elapsed]")
			else:
				reporter.detail(
					f"Waiting for targets to register... [{elapsed:.0f}s elapsed]"
				)

		except ClientError as exc:
			msg = f"Failed to check target health: {exc}"
			raise DeploymentError(msg) from exc

		await asyncio.sleep(poll_interval)


async def install_listener_rules_and_switch_traffic(
	deployment_name: str,
	deployment_id: str,
	target_group_arn: str,
	baseline: BaselineStackOutputs,
	*,
	priority_start: int = 100,
	wait_for_health: bool = True,
	min_healthy_targets: int = 2,
	reporter: Reporter | None = None,
) -> None:
	"""Wait for deployment health then switch default traffic to the new deployment.

	The header-based routing rule (X-Pulse-Render-Affinity: <deployment_id>) is already
	created in create_service_and_target_group(). This function waits for targets to
	become healthy, then updates the listener default action to forward 100% of new
	traffic to the new target group.

	Existing header rules for prior deployments remain, ensuring sticky sessions continue
	to work for old tabs while new tabs get the latest version.

	Args:
	    deployment_name: The deployment environment name
	    deployment_id: Unique deployment ID
	    target_group_arn: ARN of the target group to route to
	    baseline: Baseline stack outputs
	    priority_start: Unused, kept for API compatibility
	    wait_for_health: Wait for targets to be healthy before switching (default: True)
	    min_healthy_targets: Minimum healthy targets required (default: 2)

	Raises:
	    DeploymentError: If health checks or traffic switching fail
	"""
	reporter = _resolve_reporter(reporter)

	# Wait for targets to become healthy before switching traffic
	if wait_for_health:
		await wait_for_healthy_targets(
			target_group_arn=target_group_arn,
			baseline=baseline,
			min_healthy_targets=min_healthy_targets,
			reporter=reporter,
		)
		reporter.blank()

	elbv2 = boto3.client("elbv2", region_name=baseline.region)

	# Switch default traffic to new target group (100% weight)
	reporter.info(f"Switching default traffic to {deployment_id}...")
	try:
		elbv2.modify_listener(
			ListenerArn=baseline.listener_arn,
			DefaultActions=[
				{
					"Type": "forward",
					"TargetGroupArn": target_group_arn,
				}
			],
		)
		reporter.success(f"Default traffic now routes to {deployment_id}")
	except ClientError as exc:
		msg = f"Failed to modify listener default action: {exc}"
		raise DeploymentError(msg) from exc


async def drain_previous_deployments(
	current_deployment_id: str,
	baseline: BaselineStackOutputs,
	drain_secret: str,
	*,
	timeout_seconds: float = 180,
	poll_interval: float = 10,
	reporter: Reporter | None = None,
) -> list[str]:
	"""Drain all previous deployments by calling their /drain endpoint.

	This function finds all active ECS services (excluding the current one)
	and calls the /drain endpoint on each. It does not wait for health checks
	to fail; the deployments will drain asynchronously.

	Args:
	    current_deployment_id: The deployment ID that should NOT be drained
	    baseline: Baseline stack outputs
	    drain_secret: Secret for authenticating drain requests
	    timeout_seconds: Unused, kept for API compatibility
	    poll_interval: Unused, kept for API compatibility

	Returns:
	    List of deployment IDs that were successfully drained

	Raises:
	    DeploymentError: If listing services or making drain requests fail
	"""
	import httpx

	reporter = _resolve_reporter(reporter)

	ecs = boto3.client("ecs", region_name=baseline.region)

	# Find all active services except the current one
	reporter.info("Finding previous deployments to drain...")
	try:
		response = ecs.list_services(cluster=baseline.cluster_name)
		service_arns = response.get("serviceArns", [])

		if not service_arns:
			reporter.info("No previous deployments found")
			return []

		# Get service details
		services_detail = ecs.describe_services(
			cluster=baseline.cluster_name,
			services=service_arns,
		)

		# Filter for active services with running tasks, excluding current
		previous_deployments: list[str] = [
			svc["serviceName"]
			for svc in services_detail.get("services", [])
			if svc.get("status") == "ACTIVE"
			and svc.get("runningCount", 0) > 0
			and svc["serviceName"] != current_deployment_id
		]

		if not previous_deployments:
			reporter.info("No previous deployments with running tasks found")
			return []

		reporter.info(f"Found {len(previous_deployments)} deployment(s) to drain:")

	except ClientError as exc:
		msg = f"Failed to list services: {exc}"
		raise DeploymentError(msg) from exc

	# Call /drain endpoint for each previous deployment
	base_url = f"https://{baseline.alb_dns_name}"
	drained_deployments = []

	async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
		for dep_id in previous_deployments:
			reporter.detail(f"Draining {dep_id}...")
			try:
				# Use affinity header to route to specific deployment
				response = await client.post(
					f"{base_url}/drain",
					headers={
						"Authorization": f"Bearer {drain_secret}",
						"X-Pulse-Render-Affinity": dep_id,
					},
				)

				if response.status_code == 200:
					data = response.json()
					status = data.get("status", "unknown")
					if status == "ok":
						reporter.success(f"Drain initiated for {dep_id}")
						drained_deployments.append(dep_id)
					elif status == "already_draining":
						reporter.detail(f"{dep_id} was already draining")
						drained_deployments.append(dep_id)
					else:
						reporter.warning(
							f"Unexpected drain status for {dep_id}: {status}"
						)
				else:
					reporter.warning(
						f"Drain request failed with status {response.status_code}"
					)
					reporter.detail(f"Response: {response.text}")

			except Exception as exc:
				reporter.warning(f"Failed to drain {dep_id}: {exc}")

	if not drained_deployments:
		reporter.info("No deployments were successfully drained")
		return []

	return drained_deployments


async def cleanup_inactive_deployments(
	deployment_name: str,
	baseline: BaselineStackOutputs,
	*,
	dry_run: bool = False,
	reporter: Reporter | None = None,
) -> list[str]:
	"""Clean up deployments with no running tasks that are marked as draining.

	This is a wrapper around the reaper's cleanup logic for manual cleanup.
	The reaper Lambda handles automated cleanup, but this function can be
	called manually if needed.

	Args:
	    deployment_name: The deployment environment name
	    baseline: Baseline stack outputs
	    dry_run: If True, only report what would be deleted without deleting

	Returns:
	    List of deployment IDs that were cleaned up (or would be in dry_run mode)

	Raises:
	    DeploymentError: If cleanup operations fail
	"""
	# Import cleanup logic from reaper
	from pulse_aws import reaper_lambda

	reporter = _resolve_reporter(reporter)

	if dry_run:
		reporter.warning(
			"Dry run mode not supported when using reaper cleanup logic. Skipping cleanup."
		)
		return []

	reporter.info("Looking for inactive deployments to clean up...")

	# Create AWS clients
	ecs = boto3.client("ecs", region_name=baseline.region)
	elbv2 = boto3.client("elbv2", region_name=baseline.region)

	# Call the reaper's cleanup function
	try:
		cleaned_count = reaper_lambda.cleanup_inactive_services(
			cluster=baseline.cluster_name,
			listener_arn=baseline.listener_arn,
			ecs=ecs,
			elbv2=elbv2,
		)

		if cleaned_count > 0:
			reporter.info(f"Cleaned up {cleaned_count} deployment(s)")
		else:
			reporter.info("No inactive deployments found")

		# Return empty list since we don't track individual deployment IDs
		# (the reaper logs them to stdout)
		return []

	except Exception as exc:
		msg = f"Failed to clean up inactive deployments: {exc}"
		raise DeploymentError(msg) from exc


async def deploy(
	*,
	domain: str,
	deployment_name: str,
	docker: DockerBuild,
	task: TaskConfig | None = None,
	health_check: HealthCheckConfig | None = None,
	drain: DrainConfig | None = None,
	certificate_arn: str | None = None,
	context: DeploymentContext | None = None,
	reporter: Reporter | None = None,
) -> dict[str, str]:
	"""Deploy an application to AWS ECS with full blue-green deployment workflow.

	This function orchestrates the complete deployment:
	1. Ensure ACM certificate exists and is validated
	2. Ensure baseline infrastructure exists (includes reaper Lambda)
	3. Build and push Docker image
	4. Register ECS task definition
	5. Create ECS service and ALB target group
	6. Mark deployment as active in SSM
	7. Install listener rules for header-based routing
	8. Switch default traffic to the new deployment
	9. Mark previous deployments as draining
	10. Call drain endpoint on previous deployments

	Note: Cleanup of old deployments is handled automatically by the reaper Lambda
	which runs every 1-5 minutes and removes draining services with runningCount==0.

	Args:
	    domain: Domain name for the deployment (e.g., "app.example.com")
	    deployment_name: Environment name (e.g., "prod", "staging")
	    docker: Docker build configuration
	    task: ECS task configuration (uses defaults if None)
	    health_check: ALB health check configuration (uses defaults if None)
	    drain: Drain and cleanup configuration (uses defaults if None)
	    certificate_arn: ACM certificate ARN (looked up if not provided)
	    context: Optional deployment execution context (auto-detected if omitted)
	    reporter: Optional reporter to override logging behaviour

	Returns:
	    Dictionary with deployment information:
	        - deployment_id: The deployment ID
	        - service_arn: ECS service ARN
	        - target_group_arn: ALB target group ARN
	        - task_def_arn: Task definition ARN
	        - image_uri: Docker image URI
	        - cluster_name: ECS cluster name
	        - alb_dns_name: ALB DNS name
	        - drain_secret: The drain secret used
	        - drained_count: Number of deployments drained (cleanup by reaper)
	        - certificate_arn: ACM certificate ARN used
	        - domain_ready: Whether the custom domain resolves to the ALB ("True"/"False")

	Raises:
	    DeploymentError: If any deployment step fails

	Example::

	    result = await deploy(
	        domain="app.example.com",
	        deployment_name="prod",
	        docker=DockerBuild(
	            dockerfile_path=Path("Dockerfile"),
	            context_path=Path("."),
	            build_args={"VERSION": "1.0.0"},
	        ),
	        task=TaskConfig(cpu="512", memory="1024", desired_count=3),
	        health_check=HealthCheckConfig(path="/health"),
	    )
	"""
	from pulse_aws.baseline import ensure_baseline_stack

	context = _prepare_context(context, reporter)
	reporter = context.reporter

	reporter.section(f"Deploy {deployment_name}")

	# Use defaults for optional configs
	task = task or TaskConfig()
	health_check = health_check or HealthCheckConfig()
	drain = drain or DrainConfig()

	# Ensure certificate
	reporter.section("ACM Certificate")
	cert_arn = await _ensure_certificate_ready(domain, certificate_arn, context)

	# Ensure baseline infrastructure
	reporter.section("Baseline Infrastructure")
	baseline = await ensure_baseline_stack(
		deployment_name,
		certificate_arn=cert_arn,
	)
	reporter.success("Baseline stack ready")
	reporter.detail(f"ALB DNS: {baseline.alb_dns_name}")

	# Generate deployment ID
	deployment_id = generate_deployment_id(deployment_name)
	reporter.section("Container Image")

	# Generate drain secret if not provided
	if not drain.drain_secret:
		import secrets as secrets_module

		drain.drain_secret = secrets_module.token_urlsafe(32)
		reporter.detail("Generated drain secret for this deployment")
	else:
		reporter.detail("Using existing drain secret")

	# Build and push image
	image_uri = await build_and_push_image(
		dockerfile_path=docker.dockerfile_path,
		deployment_id=deployment_id,
		baseline=baseline,
		drain_secret=drain.drain_secret,
		context_path=docker.context_path,
		build_args=docker.build_args or None,
		reporter=reporter,
	)

	# Register task definition
	reporter.section("ECS Service")
	task_def_arn = await register_task_definition(
		image_uri=image_uri,
		deployment_id=deployment_id,
		baseline=baseline,
		cpu=task.cpu,
		memory=task.memory,
		env_vars=task.env_vars or None,
		reporter=reporter,
	)

	# Create service and target group
	service_arn, target_group_arn = await create_service_and_target_group(
		deployment_name=deployment_name,
		deployment_id=deployment_id,
		task_def_arn=task_def_arn,
		baseline=baseline,
		desired_count=task.desired_count,
		health_check_path=health_check.path,
		health_check_interval=health_check.interval_seconds,
		health_check_timeout=health_check.timeout_seconds,
		healthy_threshold=health_check.healthy_threshold,
		unhealthy_threshold=health_check.unhealthy_threshold,
		reporter=reporter,
	)

	# Mark this deployment as active in SSM
	await set_deployment_state(
		deployment_name=deployment_name,
		deployment_id=deployment_id,
		state="active",
		region=baseline.region,
		reporter=reporter,
	)

	# Install listener rules and switch traffic
	await install_listener_rules_and_switch_traffic(
		deployment_name=deployment_name,
		deployment_id=deployment_id,
		target_group_arn=target_group_arn,
		baseline=baseline,
		wait_for_health=health_check.wait_for_health,
		min_healthy_targets=health_check.min_healthy_targets,
		reporter=reporter,
	)

	# Mark previous deployments as draining in SSM and service tags
	reporter.blank()
	await mark_previous_deployments_as_draining(
		deployment_name=deployment_name,
		current_deployment_id=deployment_id,
		baseline=baseline,
		reporter=reporter,
	)

	# Drain previous deployments
	reporter.section("Post-Deployment")
	drained = await drain_previous_deployments(
		current_deployment_id=deployment_id,
		baseline=baseline,
		drain_secret=drain.drain_secret,
		timeout_seconds=drain.timeout_seconds,
		poll_interval=drain.poll_interval,
		reporter=reporter,
	)

	# Note: Cleanup of inactive deployments is now handled by the reaper Lambda
	# which runs every minute and automatically removes draining services with
	# runningCount==0. No need to clean up during deployment.

	# Verify DNS routing to the load balancer
	domain_ready, domain_proxied = await _ensure_domain_routing(
		domain,
		baseline,
		context,
	)

	reporter.section("Summary")
	reporter.success(f"Deployment {deployment_id} complete")
	reporter.detail(f"Service ARN: {service_arn}")
	reporter.detail(f"Target Group: {target_group_arn}")
	reporter.detail(f"Image URI: {image_uri}")
	if domain_proxied:
		reporter.detail(
			f"{domain} is served via Cloudflare proxy; ALB IP verification skipped."
		)

	return {
		"deployment_id": deployment_id,
		"service_arn": service_arn,
		"target_group_arn": target_group_arn,
		"task_def_arn": task_def_arn,
		"image_uri": image_uri,
		"cluster_name": baseline.cluster_name,
		"alb_dns_name": baseline.alb_dns_name,
		"drain_secret": drain.drain_secret,
		"drained_count": str(len(drained)),
		"certificate_arn": cert_arn,
		"domain_ready": str(domain_ready),
		"domain_proxied": str(domain_proxied),
	}


__all__ = [
	"DeploymentError",
	"DockerBuild",
	"TaskConfig",
	"HealthCheckConfig",
	"DrainConfig",
	"build_and_push_image",
	"cleanup_inactive_deployments",
	"create_service_and_target_group",
	"deploy",
	"drain_previous_deployments",
	"generate_deployment_id",
	"install_listener_rules_and_switch_traffic",
	"mark_previous_deployments_as_draining",
	"register_task_definition",
	"set_deployment_state",
	"wait_for_healthy_targets",
]
