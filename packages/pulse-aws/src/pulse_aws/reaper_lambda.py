"""
ECS Reaper Lambda — Automated cleanup of draining deployments.

This Lambda runs on a schedule (EventBridge) and:
1. Finds ECS services tagged state=draining
2. Checks if all tasks have readiness="ready" in SSM Parameter Store
3. Sets desiredCount=0 when ready OR max age exceeded
4. Cleans up services with runningCount=0 (service, target group, listener rule)
5. Cleans up stuck deployments in "deploying" state that exceed max age

Environment variables:
- PULSE_AWS_CLUSTER: ECS cluster name
- PULSE_AWS_DEPLOYMENT_NAME: Deployment environment name (e.g., "test", "prod")
- PULSE_AWS_REAPER_MAX_AGE_HR: Maximum service age in hours (force retire, default: 1.0)
- PULSE_AWS_REAPER_DEPLOYMENT_TIMEOUT: Maximum deployment time in hours before cleanup (default: 1.0)
- PULSE_AWS_LISTENER_ARN: ALB listener ARN for rule cleanup
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, cast

import boto3

# Configuration from environment (only used by Lambda handler)
CLUSTER = os.environ.get("PULSE_AWS_CLUSTER", "")
DEPLOYMENT_NAME = os.environ.get("PULSE_AWS_DEPLOYMENT_NAME", "")
LISTENER_ARN = os.environ.get("PULSE_AWS_LISTENER_ARN", "")
MAX_AGE_HR = float(os.getenv("PULSE_AWS_REAPER_MAX_AGE_HR", "1.0"))
DEPLOYMENT_TIMEOUT = float(os.getenv("PULSE_AWS_REAPER_DEPLOYMENT_TIMEOUT", "1.0"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
	"""Lambda handler for ECS reaper."""
	# Create AWS clients for this invocation
	ecs = boto3.client("ecs")
	elbv2 = boto3.client("elbv2")

	print(f"🔄 Reaper invoked for cluster={CLUSTER}, deployment={DEPLOYMENT_NAME}")

	# Step 1: Find draining services and scale them to 0 if ready
	ssm = boto3.client("ssm")
	drained_count = process_draining_services(
		cluster=CLUSTER,
		ecs=ecs,
		ssm_client=ssm,
		max_age_hr=MAX_AGE_HR,
	)

	# Step 2: Clean up stuck deploying services
	stuck_deploying_count = cleanup_stuck_deploying_services(
		cluster=CLUSTER,
		listener_arn=LISTENER_ARN,
		max_age_hr=DEPLOYMENT_TIMEOUT,
		ecs=ecs,
		elbv2=elbv2,
		ssm_client=ssm,
	)

	# Step 3: Clean up services with runningCount=0
	cleaned_count = cleanup_inactive_services(
		cluster=CLUSTER,
		listener_arn=LISTENER_ARN,
		ecs=ecs,
		elbv2=elbv2,
		ssm_client=ssm,
	)

	result = {
		"drained": drained_count,
		"stuck_deploying_cleaned": stuck_deploying_count,
		"cleaned": cleaned_count,
		"timestamp": datetime.now(timezone.utc).isoformat(),
	}

	print(f"✅ Reaper complete: {json.dumps(result)}")
	return result


def process_draining_services(
	cluster: str,
	ecs: Any,
	ssm_client: Any,
	max_age_hr: float = 1.0,
) -> int:
	"""Find draining services and set desiredCount=0 if ready.

	Args:
	    cluster: ECS cluster name
	    ecs: boto3 ECS client
	    ssm_client: boto3 SSM client
	    max_age_hr: Maximum service age in hours (force retire)

	Returns:
	    Number of services that were set to desiredCount=0
	"""
	print("🔍 Looking for draining services...")

	# Find all services in the cluster
	service_arns: list[str] = []
	paginator = ecs.get_paginator("list_services")
	for page in paginator.paginate(cluster=cluster):
		service_arns.extend(page.get("serviceArns", []))

	if not service_arns:
		print("  No services found")
		return 0

	# Get service details
	services = []
	for i in range(0, len(service_arns), 10):
		batch = service_arns[i : i + 10]
		response = ecs.describe_services(cluster=cluster, services=batch)
		services.extend(response.get("services", []))

	# Filter for ACTIVE services with state=draining tag (skip deploying)
	draining_services: list[dict[str, Any]] = []
	for svc in services:
		if svc.get("status") != "ACTIVE":
			continue

		# Check tags
		tags = ecs.list_tags_for_resource(resourceArn=svc["serviceArn"]).get("tags", [])
		tag_dict = {tag["key"]: tag["value"] for tag in tags}

		if tag_dict.get("state") == "draining":
			draining_services.append(
				{
					"service": svc,
					"deployment_id": tag_dict.get("deployment_id"),
				}
			)

	if not draining_services:
		print("  No draining services found")
		return 0

	print(f"  Found {len(draining_services)} draining service(s)")

	# Process each draining service
	drained_count = 0
	for item in draining_services:
		svc = item["service"]
		deployment_id = item["deployment_id"]

		if not deployment_id:
			print(f"  ⚠️  {svc['serviceName']}: missing deployment_id tag, skipping")
			continue

		# Check if already at desiredCount=0
		if svc.get("desiredCount", 0) == 0:
			print(f"  ⏭️  {deployment_id}: already at desiredCount=0")
			continue

		# Check age
		created_at = svc.get("createdAt")
		if not created_at:
			print(f"  ⚠️  {deployment_id}: missing createdAt, skipping")
			continue

		age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()

		# Check if max age exceeded (force retire)
		max_age_seconds = max_age_hr * 3600
		force_retire = age_seconds >= max_age_seconds

		if force_retire:
			print(
				f"  🚨 {deployment_id}: MAX_AGE exceeded ({age_seconds / 3600:.1f}h >= {max_age_hr}h), forcing retirement"
			)
			scale_service_to_zero(ecs, cluster, svc["serviceArn"], deployment_id)
			drained_count += 1
			continue

		# Check if all tasks are ShutdownReady=1
		running_count = svc.get("runningCount", 0)
		if running_count == 0:
			print(f"  ⏭️  {deployment_id}: no running tasks")
			continue

		# Get task IDs
		task_arns = ecs.list_tasks(cluster=cluster, serviceName=svc["serviceName"]).get(
			"taskArns", []
		)

		if not task_arns:
			print(f"  ⏭️  {deployment_id}: no tasks to check")
			continue

		# Describe tasks to get task IDs
		task_details = ecs.describe_tasks(cluster=cluster, tasks=task_arns).get(
			"tasks", []
		)
		task_ids = [task["taskArn"].split("/")[-1] for task in task_details]

		print(f"  📊 {deployment_id}: checking {len(task_ids)} task(s)")

		# Check SSM parameters for each task
		all_ready = check_all_tasks_ready(
			ssm_client=ssm_client,
			deployment_id=deployment_id,
			task_ids=task_ids,
		)

		if all_ready:
			print(f"  ✅ {deployment_id}: all tasks draining, scaling to 0")
			scale_service_to_zero(ecs, cluster, svc["serviceArn"], deployment_id)
			drained_count += 1
		else:
			print(f"  ⏳ {deployment_id}: tasks not draining yet")

	return drained_count


def check_all_tasks_ready(
	ssm_client: Any,
	deployment_id: str,
	task_ids: list[str],
) -> bool:
	"""Check if all tasks have state="draining" in SSM.

	Args:
	    ssm_client: boto3 SSM client
	    deployment_id: Deployment ID
	    task_ids: List of task IDs to check

	Returns:
	    True if all tasks are draining (ready for shutdown), False otherwise
	"""
	if not task_ids:
		return False

	# Check SSM parameters for each task
	for task_id in task_ids:
		param_name = f"/apps/{DEPLOYMENT_NAME}/{deployment_id}/tasks/{task_id}"

		try:
			response = ssm_client.get_parameter(Name=param_name)
			value = response["Parameter"]["Value"]
			if value != "draining":
				return False
		except ssm_client.exceptions.ParameterNotFound:
			# Parameter doesn't exist, task not ready (assume healthy, not draining)
			return False
		except Exception as e:
			print(f"  ⚠️  Failed to check task {task_id} state: {e}")
			return False

	return True


def scale_service_to_zero(
	ecs: Any, cluster: str, service_arn: str, deployment_id: str
) -> None:
	"""Set service desiredCount to 0.

	Args:
	    ecs: boto3 ECS client
	    cluster: ECS cluster name
	    service_arn: ARN of the service to scale
	    deployment_id: Deployment ID (for logging)
	"""
	try:
		ecs.update_service(cluster=cluster, service=service_arn, desiredCount=0)
		print(f"  ✅ {deployment_id}: set desiredCount=0")
	except Exception as e:
		print(f"  ❌ {deployment_id}: failed to scale to 0: {e}")


def is_service_draining(ecs: Any, service_arn: str) -> bool:
	"""Check if a service is tagged with state=draining.

	Args:
	    ecs: boto3 ECS client
	    service_arn: ARN of the ECS service to check

	Returns:
	    True if service is tagged state=draining, False otherwise
	"""
	try:
		tags = ecs.list_tags_for_resource(resourceArn=service_arn).get("tags", [])
		tag_dict = {tag["key"]: tag["value"] for tag in tags}
		return tag_dict.get("state") == "draining"
	except Exception:
		return False


def is_service_deploying(ecs: Any, service_arn: str) -> bool:
	"""Check if a service is tagged with state=deploying.

	Args:
	    ecs: boto3 ECS client
	    service_arn: ARN of the ECS service to check

	Returns:
	    True if service is tagged state=deploying, False otherwise
	"""
	try:
		tags = ecs.list_tags_for_resource(resourceArn=service_arn).get("tags", [])
		tag_dict = {tag["key"]: tag["value"] for tag in tags}
		return tag_dict.get("state") == "deploying"
	except Exception:
		return False


def cleanup_stuck_deploying_services(
	cluster: str,
	listener_arn: str,
	max_age_hr: float,
	ecs: Any,
	elbv2: Any,
	ssm_client: Any,
) -> int:
	"""Clean up services stuck in deploying state that exceed max age.

	Args:
	    cluster: ECS cluster name
	    listener_arn: ALB listener ARN for rule cleanup
	    max_age_hr: Maximum age in hours before cleanup
	    ecs: boto3 ECS client
	    elbv2: boto3 ELBv2 client
	    ssm_client: boto3 SSM client

	Returns:
	    Number of services that were cleaned up
	"""
	print("🔍 Looking for stuck deploying services...")

	# Find all services
	service_arns: list[str] = []
	paginator = ecs.get_paginator("list_services")
	for page in paginator.paginate(cluster=cluster):
		service_arns.extend(page.get("serviceArns", []))

	if not service_arns:
		print("  No services found")
		return 0

	# Get service details
	services: list[dict[str, Any]] = []
	for i in range(0, len(service_arns), 10):
		batch = service_arns[i : i + 10]
		response = ecs.describe_services(cluster=cluster, services=batch)
		services.extend(response.get("services", []))

	# Filter for ACTIVE services with state=deploying that exceed max age
	max_age_seconds = max_age_hr * 3600
	stuck_services: list[dict[str, Any]] = []
	for svc in services:
		if svc.get("status") != "ACTIVE":
			continue

		if not is_service_deploying(ecs, svc["serviceArn"]):
			continue

		# Check age
		created_at = svc.get("createdAt")
		if not created_at:
			continue

		age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
		if age_seconds >= max_age_seconds:
			stuck_services.append(svc)

	if not stuck_services:
		print("  No stuck deploying services found")
		return 0

	print(f"  Found {len(stuck_services)} stuck deploying service(s)")

	# Get listener rules to find target groups
	rules_map = get_listener_rules_map(elbv2, listener_arn)

	# Clean up each stuck service
	cleaned_count = 0
	for svc in stuck_services:
		deployment_id = cast(str, svc["serviceName"])
		service_arn = svc["serviceArn"]
		created_at = svc.get("createdAt")
		age_hours = (
			(datetime.now(timezone.utc) - created_at).total_seconds() / 3600
			if created_at
			else 0
		)

		print(
			f"  🧹 {deployment_id}: cleaning up stuck deployment (age: {age_hours:.1f}h)..."
		)

		# Scale to 0 first
		if svc.get("desiredCount", 0) > 0:
			try:
				ecs.update_service(cluster=cluster, service=service_arn, desiredCount=0)
				print("    ✅ Scaled to desiredCount=0")
			except Exception as e:
				print(f"    ⚠️  Failed to scale to 0: {e}")

		# Delete listener rule and target group
		rule_info = rules_map.get(deployment_id)
		if rule_info:
			# Delete rule first
			try:
				elbv2.delete_rule(RuleArn=rule_info["rule_arn"])
				print("    ✅ Deleted listener rule")
			except Exception as e:
				print(f"    ⚠️  Failed to delete listener rule: {e}")

			# Delete target group
			if rule_info.get("target_group_arn"):
				try:
					elbv2.delete_target_group(
						TargetGroupArn=rule_info["target_group_arn"]
					)
					print("    ✅ Deleted target group")
				except Exception as e:
					print(f"    ⚠️  Failed to delete target group: {e}")

		# Clean up SSM parameters
		cleanup_ssm_parameters(ssm_client, deployment_id)

		# Delete ECS service
		try:
			ecs.delete_service(cluster=cluster, service=service_arn, force=True)
			print("    ✅ Deleted ECS service")
			cleaned_count += 1
		except Exception as e:
			print(f"    ❌ Failed to delete service: {e}")

	return cleaned_count


def cleanup_inactive_services(
	cluster: str,
	listener_arn: str,
	ecs: Any,
	elbv2: Any,
	ssm_client: Any,
) -> int:
	"""Clean up services with runningCount=0 that are marked as draining.

	Args:
	    cluster: ECS cluster name
	    listener_arn: ALB listener ARN for rule cleanup
	    ecs: boto3 ECS client
	    elbv2: boto3 ELBv2 client
	    ssm_client: boto3 SSM client

	Returns:
	    Number of services that were cleaned up
	"""
	print("🧹 Looking for inactive services to clean up...")

	# Find all services
	service_arns: list[str] = []
	paginator = ecs.get_paginator("list_services")
	for page in paginator.paginate(cluster=cluster):
		service_arns.extend(page.get("serviceArns", []))

	if not service_arns:
		print("  No services found")
		return 0

	# Get service details
	services: list[dict[str, Any]] = []
	for i in range(0, len(service_arns), 10):
		batch = service_arns[i : i + 10]
		response = ecs.describe_services(cluster=cluster, services=batch)
		services.extend(response.get("services", []))

	# Filter for ACTIVE services with runningCount=0 that are tagged as draining
	# We ONLY clean up draining services, not active or deploying ones
	inactive_services = [
		svc
		for svc in services
		if svc.get("status") == "ACTIVE"
		and svc.get("runningCount", 0) == 0
		and is_service_draining(ecs, svc["serviceArn"])
		and not is_service_deploying(ecs, svc["serviceArn"])
	]

	if not inactive_services:
		print("  No inactive services found")
		return 0

	print(f"  Found {len(inactive_services)} inactive service(s)")

	# Get listener rules to find target groups
	rules_map = get_listener_rules_map(elbv2, listener_arn)

	# Clean up each inactive service
	cleaned_count = 0
	for svc in inactive_services:
		deployment_id = cast(str, svc["serviceName"])
		service_arn = svc["serviceArn"]

		print(f"  🧹 {deployment_id}: cleaning up...")

		# Delete listener rule and target group
		rule_info = rules_map.get(deployment_id)
		if rule_info:
			# Delete rule first
			try:
				elbv2.delete_rule(RuleArn=rule_info["rule_arn"])
				print("    ✅ Deleted listener rule")
			except Exception as e:
				print(f"    ⚠️  Failed to delete listener rule: {e}")

			# Delete target group
			if rule_info.get("target_group_arn"):
				try:
					elbv2.delete_target_group(
						TargetGroupArn=rule_info["target_group_arn"]
					)
					print("    ✅ Deleted target group")
				except Exception as e:
					print(f"    ⚠️  Failed to delete target group: {e}")

		# Clean up SSM parameters
		cleanup_ssm_parameters(ssm_client, deployment_id)

		# Delete ECS service
		try:
			ecs.delete_service(cluster=cluster, service=service_arn, force=True)
			print("    ✅ Deleted ECS service")
			cleaned_count += 1
		except Exception as e:
			print(f"    ❌ Failed to delete service: {e}")

	return cleaned_count


def cleanup_ssm_parameters(
	ssm_client: Any,
	deployment_id: str,
) -> None:
	"""Clean up SSM parameters for a deployment.

	Deletes:
	- /apps/{deployment_name}/{deployment_id}/state (deployment state)
	- /apps/{deployment_name}/{deployment_id}/tasks/* (all task parameters)

	Args:
	    ssm_client: boto3 SSM client
	    deployment_id: Deployment ID
	"""
	print(f"    🧹 Cleaning up SSM parameters for {deployment_id}...")

	# Delete deployment state parameter
	state_param = f"/apps/{DEPLOYMENT_NAME}/{deployment_id}/state"
	try:
		ssm_client.delete_parameter(Name=state_param)
		print(f"      ✅ Deleted deployment state: {state_param}")
	except ssm_client.exceptions.ParameterNotFound:
		print(f"      ⏭️  Deployment state parameter not found: {state_param}")
	except Exception as e:
		print(f"      ⚠️  Failed to delete deployment state: {e}")

	# List and delete all task parameters
	tasks_prefix = f"/apps/{DEPLOYMENT_NAME}/{deployment_id}/tasks/"
	try:
		paginator = ssm_client.get_paginator("get_parameters_by_path")
		task_params_deleted = 0

		for page in paginator.paginate(Path=tasks_prefix, Recursive=False):
			params = page.get("Parameters", [])
			if params:
				names = [p["Name"] for p in params]
				# Delete in batches of 10 (SSM limit)
				for i in range(0, len(names), 10):
					batch = names[i : i + 10]
					try:
						ssm_client.delete_parameters(Names=batch)
						task_params_deleted += len(batch)
					except Exception as e:
						print(f"      ⚠️  Failed to delete task parameters batch: {e}")

		if task_params_deleted > 0:
			print(f"      ✅ Deleted {task_params_deleted} task parameter(s)")
		else:
			print(f"      ⏭️  No task parameters found under {tasks_prefix}")
	except Exception as e:
		print(f"      ⚠️  Failed to list/delete task parameters: {e}")


def get_listener_rules_map(elbv2: Any, listener_arn: str) -> dict[str, dict[str, str]]:
	"""Build a map of deployment_id -> rule/target group info.

	Args:
	    elbv2: boto3 ELBv2 client
	    listener_arn: ALB listener ARN

	Returns:
	    Dictionary mapping deployment_id to rule/target group information
	"""
	rules_map = {}

	try:
		response = elbv2.describe_rules(ListenerArn=listener_arn)

		for rule in response.get("Rules", []):
			# Skip default rule
			if rule.get("Priority") == "default":
				continue

			# Check if this is a header-based affinity rule
			for condition in rule.get("Conditions", []):
				if condition.get("Field") == "http-header":
					header_config = condition.get("HttpHeaderConfig", {})
					if header_config.get("HttpHeaderName") == "X-Pulse-Render-Affinity":
						values = header_config.get("Values", [])
						if values:
							dep_id = values[0]
							actions = rule.get("Actions", [])
							tg_arn = (
								actions[0].get("TargetGroupArn") if actions else None
							)
							rules_map[dep_id] = {
								"rule_arn": rule["RuleArn"],
								"target_group_arn": tg_arn,
							}

	except Exception as e:
		print(f"  ⚠️  Failed to describe listener rules: {e}")

	return rules_map
