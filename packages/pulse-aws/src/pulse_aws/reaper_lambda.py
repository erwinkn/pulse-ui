"""
ECS Reaper Lambda — Automated cleanup of draining deployments.

This Lambda runs on a schedule (EventBridge) and:
1. Finds ECS services tagged state=draining
2. Checks if all tasks have ShutdownReady=1 (via CloudWatch metrics)
3. Sets desiredCount=0 when ready OR max age exceeded
4. Cleans up services with runningCount=0 (service, target group, listener rule)

Environment variables:
- CLUSTER: ECS cluster name
- DEPLOYMENT_NAME: Deployment environment name (e.g., "test", "prod")
- CONSEC: Consecutive periods with ShutdownReady=1 required (default: 2)
- PERIOD: CloudWatch metric period in seconds (default: 60)
- MIN_AGE_SEC: Minimum service age before retirement (default: 60)
- MAX_AGE_HR: Maximum service age in hours (force retire, default: 1.0)
- LISTENER_ARN: ALB listener ARN for rule cleanup
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

# Configuration from environment (only used by Lambda handler)
CLUSTER = os.environ.get("CLUSTER", "")
DEPLOYMENT_NAME = os.environ.get("DEPLOYMENT_NAME", "")
LISTENER_ARN = os.environ.get("LISTENER_ARN", "")
CONSEC = int(os.getenv("CONSEC", "2"))
PERIOD = int(os.getenv("PERIOD", "60"))
MIN_AGE_SEC = int(os.getenv("MIN_AGE_SEC", "60"))
MAX_AGE_HR = float(os.getenv("MAX_AGE_HR", "1.0"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
	"""Lambda handler for ECS reaper."""
	# Create AWS clients for this invocation
	ecs = boto3.client("ecs")
	elbv2 = boto3.client("elbv2")
	cloudwatch = boto3.client("cloudwatch")

	print(f"🔄 Reaper invoked for cluster={CLUSTER}, deployment={DEPLOYMENT_NAME}")

	# Step 1: Find draining services and scale them to 0 if ready
	drained_count = process_draining_services(
		cluster=CLUSTER,
		deployment_name=DEPLOYMENT_NAME,
		ecs=ecs,
		cloudwatch_client=cloudwatch,
		consec=CONSEC,
		period=PERIOD,
		min_age_sec=MIN_AGE_SEC,
		max_age_hr=MAX_AGE_HR,
	)

	# Step 2: Clean up services with runningCount=0
	cleaned_count = cleanup_inactive_services(
		cluster=CLUSTER,
		listener_arn=LISTENER_ARN,
		ecs=ecs,
		elbv2=elbv2,
	)

	result = {
		"drained": drained_count,
		"cleaned": cleaned_count,
		"timestamp": datetime.now(timezone.utc).isoformat(),
	}

	print(f"✅ Reaper complete: {json.dumps(result)}")
	return result


def process_draining_services(
	cluster: str,
	deployment_name: str,
	ecs: Any,
	cloudwatch_client: Any,
	consec: int = 2,
	period: int = 60,
	min_age_sec: int = 60,
	max_age_hr: float = 1.0,
) -> int:
	"""Find draining services and set desiredCount=0 if ready.

	Args:
	    cluster: ECS cluster name
	    deployment_name: Deployment environment name
	    ecs: boto3 ECS client
	    cloudwatch_client: boto3 CloudWatch client
	    consec: Consecutive periods with ShutdownReady==1 required
	    period: CloudWatch metric period in seconds
	    min_age_sec: Minimum service age before retirement
	    max_age_hr: Maximum service age in hours (force retire)

	Returns:
	    Number of services that were set to desiredCount=0
	"""
	print("🔍 Looking for draining services...")

	# Find all services in the cluster
	service_arns = []
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

	# Filter for ACTIVE services with state=draining tag
	draining_services = []
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
					"deployment_name": tag_dict.get("deployment_name"),
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

		# Enforce minimum age
		if age_seconds < min_age_sec:
			print(
				f"  ⏭️  {deployment_id}: too young ({age_seconds:.0f}s < {min_age_sec}s)"
			)
			continue

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

		# Check CloudWatch metrics for each task
		all_ready = check_all_tasks_ready(
			cloudwatch_client=cloudwatch_client,
			deployment_name=item["deployment_name"] or deployment_name,
			deployment_id=deployment_id,
			task_ids=task_ids,
			consec=consec,
			period=period,
		)

		if all_ready:
			print(f"  ✅ {deployment_id}: all tasks ready, scaling to 0")
			scale_service_to_zero(ecs, cluster, svc["serviceArn"], deployment_id)
			drained_count += 1
		else:
			print(f"  ⏳ {deployment_id}: tasks not ready yet")

	return drained_count


def check_all_tasks_ready(
	cloudwatch_client: Any,
	deployment_name: str,
	deployment_id: str,
	task_ids: list[str],
	consec: int,
	period: int,
) -> bool:
	"""Check if all tasks have ShutdownReady=1 for CONSEC consecutive periods.

	Args:
	    cloudwatch_client: boto3 CloudWatch client
	    deployment_name: Deployment environment name
	    deployment_id: Deployment ID
	    task_ids: List of task IDs to check
	    consec: Consecutive periods with ShutdownReady==1 required
	    period: CloudWatch metric period in seconds

	Returns:
	    True if all tasks are ready for shutdown, False otherwise
	"""
	# Query CloudWatch metrics for each task
	end_time = datetime.now(timezone.utc)
	start_time = end_time - timedelta(seconds=period * consec)

	# Build metric queries
	metric_queries = []
	for idx, task_id in enumerate(task_ids):
		metric_queries.append(
			{
				"Id": f"m{idx}",
				"MetricStat": {
					"Metric": {
						"Namespace": "App/Drain",
						"MetricName": "ShutdownReady",
						"Dimensions": [
							{"Name": "deployment_name", "Value": deployment_name},
							{"Name": "deployment_id", "Value": deployment_id},
							{"Name": "task_id", "Value": task_id},
						],
					},
					"Period": period,
					"Stat": "Maximum",
				},
			}
		)

	if not metric_queries:
		return False

	# CloudWatch GetMetricData has a limit of 500 queries
	if len(metric_queries) > 500:
		print(
			f"  ⚠️  Too many tasks ({len(task_ids)}), checking first 500 only (CW limit)"
		)
		metric_queries = metric_queries[:500]

	try:
		response = cloudwatch_client.get_metric_data(
			MetricDataQueries=metric_queries,
			StartTime=start_time,
			EndTime=end_time,
		)

		# Check if all tasks have ShutdownReady=1 for all periods
		for result in response.get("MetricDataResults", []):
			values = result.get("Values", [])

			# Need at least CONSEC datapoints
			if len(values) < consec:
				return False

			# Check if last CONSEC values are all 1
			recent_values = values[-consec:]
			if not all(v == 1 for v in recent_values):
				return False

		return True

	except Exception as e:
		print(f"  ⚠️  CloudWatch metric check failed: {e}")
		return False


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


def cleanup_inactive_services(
	cluster: str,
	listener_arn: str,
	ecs: Any,
	elbv2: Any,
) -> int:
	"""Clean up services with runningCount=0 that are marked as draining.

	Args:
	    cluster: ECS cluster name
	    listener_arn: ALB listener ARN for rule cleanup
	    ecs: boto3 ECS client
	    elbv2: boto3 ELBv2 client

	Returns:
	    Number of services that were cleaned up
	"""
	print("🧹 Looking for inactive services to clean up...")

	# Find all services
	service_arns = []
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

	# Filter for ACTIVE services with runningCount=0 that are tagged as draining
	# We ONLY clean up draining services, not active ones (which might just be spinning up)
	inactive_services = [
		svc
		for svc in services
		if svc.get("status") == "ACTIVE"
		and svc.get("runningCount", 0) == 0
		and is_service_draining(ecs, svc["serviceArn"])
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
		deployment_id = svc["serviceName"]
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

		# Delete ECS service
		try:
			ecs.delete_service(cluster=cluster, service=service_arn, force=True)
			print("    ✅ Deleted ECS service")
			cleaned_count += 1
		except Exception as e:
			print(f"    ❌ Failed to delete service: {e}")

	return cleaned_count


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
