#!/usr/bin/env python3
"""Verify deployments are working correctly.

This script:
1. Discovers all active deployments in the environment
2. Tests the ALB default endpoint (should route to newest deployment)
3. Tests header-based affinity to each deployment
4. Verifies health endpoints are responding
5. Reports the status of all deployments
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
import warnings
from pathlib import Path

import boto3
import httpx
from pulse_aws.baseline import BaselineStackOutputs, describe_stack

# Suppress SSL warnings when using verify=False
warnings.filterwarnings("ignore", message="Unverified HTTPS request")


def get_or_create_drain_secret(deployment_name: str) -> str:
	"""Get or create a stable drain secret for this deployment environment.

	The drain secret is cached in .pulse/<deployment_name>/secrets.json
	and is shared across all deployments in the same environment.

	Args:
	    deployment_name: The deployment environment name (e.g., "prod", "dev")

	Returns:
	    The drain secret (32-byte URL-safe token)
	"""

	secrets_dir = Path.cwd() / ".pulse" / deployment_name
	secrets_file = secrets_dir / "secrets.json"

	# Try to load existing secrets
	if secrets_file.exists():
		try:
			with secrets_file.open() as f:
				data = json.load(f)
				if drain_secret := data.get("drain_secret"):
					return str(drain_secret)
		except (json.JSONDecodeError, OSError):
			pass  # Will regenerate below

	# Generate new secret
	drain_secret = secrets.token_urlsafe(32)

	# Save to file
	secrets_dir.mkdir(parents=True, exist_ok=True)
	with secrets_file.open("w") as f:
		json.dump({"drain_secret": drain_secret}, f, indent=2)

	return drain_secret


async def main() -> None:
	"""Verify all deployments are working."""
	deployment_name = "test"
	domain = "test.stoneware.rocks"

	print(f"🔍 Verifying deployments for: {deployment_name}")
	print()

	# Get baseline stack outputs
	print("📋 Loading baseline stack outputs...")
	cfn = boto3.client("cloudformation")
	sts = boto3.client("sts")
	region = sts.meta.region_name
	account = sts.get_caller_identity()["Account"]

	stack_name = f"{deployment_name}-baseline"
	stack = describe_stack(cfn, stack_name)

	if not stack:
		print(f"❌ Baseline stack {stack_name} not found")
		print("   Run deploy.py first to create the baseline infrastructure")
		sys.exit(1)

	# Extract outputs
	outputs_dict = {
		item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])
	}

	baseline = BaselineStackOutputs(
		deployment_name=deployment_name,
		region=region,
		account=account,
		stack_name=stack_name,
		listener_arn=outputs_dict["ListenerArn"],
		alb_dns_name=outputs_dict["AlbDnsName"],
		alb_hosted_zone_id=outputs_dict["AlbHostedZoneId"],
		private_subnet_ids=outputs_dict["PrivateSubnets"].split(","),
		public_subnet_ids=outputs_dict["PublicSubnets"].split(","),
		alb_security_group_id=outputs_dict["AlbSecurityGroupId"],
		service_security_group_id=outputs_dict["ServiceSecurityGroupId"],
		cluster_name=outputs_dict["ClusterName"],
		log_group_name=outputs_dict["LogGroupName"],
		ecr_repository_uri=outputs_dict["EcrRepositoryUri"],
		vpc_id=outputs_dict["VpcId"],
		execution_role_arn=outputs_dict["ExecutionRoleArn"],
		task_role_arn=outputs_dict["TaskRoleArn"],
	)

	print(f"✓ ALB DNS: {baseline.alb_dns_name}")
	print(f"✓ Cluster: {baseline.cluster_name}")
	print()

	# Discover active deployments
	print("🔎 Discovering active deployments...")
	ecs = boto3.client("ecs", region_name=region)

	try:
		services_response = ecs.list_services(cluster=baseline.cluster_name)
		service_arns = services_response.get("serviceArns", [])

		if not service_arns:
			print("❌ No services found in cluster")
			print("   Run deploy.py to deploy a service")
			sys.exit(1)

		# Get service details
		services_detail = ecs.describe_services(
			cluster=baseline.cluster_name,
			services=service_arns,
		)

		active_services = [
			svc
			for svc in services_detail.get("services", [])
			if svc.get("status") == "ACTIVE"
		]

		print(f"✓ Found {len(active_services)} active service(s)")
		print()

		# Extract deployment IDs and filter for those with running tasks
		all_deployment_ids = [svc["serviceName"] for svc in active_services]
		running_deployment_ids = [
			svc["serviceName"]
			for svc in active_services
			if svc.get("runningCount", 0) > 0
		]

		for idx, deployment_id in enumerate(all_deployment_ids, 1):
			# Find matching service
			svc = next(s for s in active_services if s["serviceName"] == deployment_id)
			running = svc.get("runningCount", 0)
			desired = svc.get("desiredCount", 0)
			status = "✓" if running > 0 else "○"
			print(f"   {status} {idx}. {deployment_id}")
			print(f"      Tasks: {running}/{desired} running")

		print()

	except Exception as exc:
		print(f"❌ Failed to list services: {exc}")
		sys.exit(1)

	# Test endpoints
	print("=" * 60)
	print("🧪 Testing Endpoints")
	print("=" * 60)
	print()

	base_url = f"https://{baseline.alb_dns_name}"
	print(f"Base URL: {base_url}")
	print()

	async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
		# Test 1: Default endpoint (no header)
		print("1️⃣  Testing default endpoint (no affinity header)...")
		try:
			response = await client.get(base_url)
			if response.status_code == 200:
				data = response.json()
				affinity = response.headers.get("X-Pulse-Render-Affinity", "none")
				print(f"   ✓ Status: {response.status_code}")
				print(f"   ✓ Response: {data}")
				print(f"   ✓ Affinity header: {affinity}")
			else:
				print(f"   ❌ Status: {response.status_code}")
				print(f"   ❌ Response: {response.text}")
		except Exception as exc:
			print(f"   ❌ Request failed: {exc}")
		print()

		# Test 2: Health endpoint
		print("2️⃣  Testing health endpoint...")
		try:
			response = await client.get(f"{base_url}/_health")
			if response.status_code == 200:
				data = response.json()
				print(f"   ✓ Status: {response.status_code}")
				print(f"   ✓ Response: {data}")
			else:
				print(f"   ⚠️  Status: {response.status_code}")
				print(f"   ⚠️  Response: {response.text}")
		except Exception as exc:
			print(f"   ❌ Request failed: {exc}")
		print()

		# Test 3: Header-based affinity for each deployment with running tasks
		if len(running_deployment_ids) > 1:
			print("3️⃣  Testing header-based affinity...")
			for deployment_id in running_deployment_ids:
				print(f"   Testing affinity to: {deployment_id}")
				try:
					response = await client.get(
						base_url,
						headers={"X-Pulse-Render-Affinity": deployment_id},
					)
					if response.status_code == 200:
						data = response.json()
						returned_id = data.get("deployment_id")
						if returned_id == deployment_id:
							print(f"      ✓ Routed correctly to {returned_id}")
						else:
							print(
								f"      ❌ Expected {deployment_id}, got {returned_id}"
							)
					else:
						print(f"      ❌ Status: {response.status_code}")
				except Exception as exc:
					print(f"      ❌ Request failed: {exc}")
			print()
		elif len(running_deployment_ids) == 1:
			print("3️⃣  Only one deployment with running tasks, skipping affinity test")
			print()

	# Summary
	print("=" * 60)
	print("📊 Summary")
	print("=" * 60)
	print()
	print(
		f"Running deployments: {len(running_deployment_ids)}/{len(all_deployment_ids)}"
	)
	print(f"Cluster: {baseline.cluster_name}")
	print(f"ALB: {baseline.alb_dns_name}")
	print()
	if running_deployment_ids:
		print("To test with domain:")
		print(f"  curl https://{domain}/")
		print(f"  curl https://{domain}/_health")
		print()
		if len(running_deployment_ids) > 1:
			print("To test affinity:")
			for deployment_id in running_deployment_ids:
				print(f"  curl -H 'X-Pulse-Render-Affinity: {deployment_id}' \\")
				print(f"    https://{domain}/")
	else:
		print("⚠️  No deployments with running tasks found")


if __name__ == "__main__":
	asyncio.run(main())
