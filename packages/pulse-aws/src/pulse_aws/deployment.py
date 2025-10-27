"""Deployment workflow helpers for AWS ECS."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import boto3
from botocore.exceptions import ClientError

from pulse_aws.baseline import BaselineStackOutputs


class DeploymentError(RuntimeError):
	"""Raised when deployment operations fail."""


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


async def build_and_push_image(
	dockerfile_path: Path,
	deployment_id: str,
	baseline: BaselineStackOutputs,
	*,
	drain_secret: str,
	context_path: Path,
	build_args: dict[str, str] | None = None,
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
	if not dockerfile_path.exists():
		msg = f"Dockerfile not found: {dockerfile_path}"
		raise DeploymentError(msg)

	if not context_path.exists():
		msg = f"Build context path not found: {context_path}"
		raise DeploymentError(msg)

	ecr_repo = baseline.ecr_repository_uri
	image_uri = f"{ecr_repo}:{deployment_id}"

	# Authenticate Docker with ECR
	print("🔐 Authenticating Docker with ECR...")
	await _ecr_login(baseline.region)

	# Build the image
	print(f"🏗️  Building image {image_uri}...")
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
	print("📤 Pushing image to ECR...")
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

	print(f"✓ Image pushed: {image_uri}")
	return image_uri


async def _ecr_login(region: str) -> None:
	"""Authenticate Docker with ECR."""
	ecr = boto3.client("ecr", region_name=region)

	try:
		response = ecr.get_authorization_token()
		auth_data = response["authorizationData"][0]
		auth_token = str(auth_data["authorizationToken"])
		token = base64.b64decode(auth_token).decode()
		username, password = token.split(":", 1)
		registry = str(auth_data["proxyEndpoint"])

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
	ecs = boto3.client("ecs", region_name=baseline.region)

	family = f"{baseline.deployment_name}-app"
	container_name = "app"

	# Build environment variables
	environment = [
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

	print(f"📋 Registering task definition {family}...")
	try:
		response = ecs.register_task_definition(**task_def)
		task_def_arn = response["taskDefinition"]["taskDefinitionArn"]
		print(f"✓ Task definition registered: {task_def_arn}")
		return cast(str, task_def_arn)
	except ClientError as exc:
		msg = f"Failed to register task definition: {exc}"
		raise DeploymentError(msg) from exc


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
	print(f"🎯 Creating target group {tg_name}...")
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
		print(f"✓ Target group created: {target_group_arn}")
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
	print("🔗 Attaching target group to listener...")
	try:
		# Find the next available priority
		rules_response = elbv2.describe_rules(ListenerArn=baseline.listener_arn)
		existing_rules = rules_response["Rules"]
		max_priority = 99
		for rule in existing_rules:
			rule_priority = rule.get("Priority")
			if rule_priority != "default":
				try:
					priority = int(str(rule_priority))
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
		print(f"✓ Target group attached with routing rule (priority {next_priority})")
	except ClientError as exc:
		# Clean up target group if listener rule creation fails
		try:
			elbv2.delete_target_group(TargetGroupArn=target_group_arn)
		except Exception:
			pass
		msg = f"Failed to create listener rule: {exc}"
		raise DeploymentError(msg) from exc

	# Create ECS service
	print(f"🚀 Creating ECS service {service_name}...")
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
				{"key": "deployment-id", "value": deployment_id},
				{"key": "deployment-name", "value": deployment_name},
			],
		)
		service_arn = service_response["service"]["serviceArn"]
		print(f"✓ ECS service created: {service_arn}")
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
	elbv2 = boto3.client("elbv2", region_name=baseline.region)
	start_time = asyncio.get_event_loop().time()

	print(f"⏳ Waiting for {min_healthy_targets} healthy target(s)...")

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
				print(f"✓ {healthy_count}/{total_count} target(s) healthy")
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
				print(f"  Waiting... ({status}) [{elapsed:.0f}s elapsed]")
			else:
				print(f"  Waiting for targets to register... [{elapsed:.0f}s elapsed]")

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
	# Wait for targets to become healthy before switching traffic
	if wait_for_health:
		await wait_for_healthy_targets(
			target_group_arn=target_group_arn,
			baseline=baseline,
			min_healthy_targets=min_healthy_targets,
		)
		print()

	elbv2 = boto3.client("elbv2", region_name=baseline.region)

	# Switch default traffic to new target group (100% weight)
	print(f"🔄 Switching default traffic to {deployment_id}...")
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
		print(f"✓ Default traffic now routes to {deployment_id}")
	except ClientError as exc:
		msg = f"Failed to modify listener default action: {exc}"
		raise DeploymentError(msg) from exc


__all__ = [
	"DeploymentError",
	"build_and_push_image",
	"create_service_and_target_group",
	"generate_deployment_id",
	"install_listener_rules_and_switch_traffic",
	"register_task_definition",
	"wait_for_healthy_targets",
]
