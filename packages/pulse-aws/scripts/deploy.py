#!/usr/bin/env python3
"""Deploy a minimal server to AWS ECS with baseline infrastructure.

This script orchestrates the full deployment workflow:
1. Ensure ACM certificate exists and is validated
2. Ensure baseline CloudFormation stack exists (VPC, ALB, ECS cluster, etc.)
3. Build and push Docker image to ECR
4. Register ECS task definition
5. Create ECS service and ALB target group
6. Install listener rules for header-based routing
7. Switch default traffic to the new deployment

The deployment uses header-based affinity (X-Pulse-Render-Affinity) to support
multiple concurrent versions with sticky sessions.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

# Add src to path so we can import pulse_aws
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pulse_aws.baseline import (
	check_domain_dns,
	ensure_acm_certificate,
	ensure_baseline_stack,
)
from pulse_aws.deployment import (
	build_and_push_image,
	create_service_and_target_group,
	generate_deployment_id,
	install_listener_rules_and_switch_traffic,
	register_task_definition,
)


async def main() -> None:
	"""Deploy the minimal server to AWS ECS."""
	domain = "test.stoneware.rocks"
	deployment_name = "test"

	# Path to Dockerfile (relative to repo root)
	repo_root = Path(__file__).parent.parent.parent.parent
	dockerfile_path = repo_root / "packages/pulse-aws/examples/Dockerfile"

	if not dockerfile_path.exists():
		print(f"❌ Dockerfile not found: {dockerfile_path}")
		sys.exit(1)

	print(f"🚀 Deploying to {deployment_name} environment")
	print(f"   Domain: {domain}")
	print()

	# Phase 1: Ensure certificate exists and is validated
	print("=" * 60)
	print("Phase 1: ACM Certificate")
	print("=" * 60)
	print()

	cert = await ensure_acm_certificate(domain)

	if not cert.arn:
		print("❌ No certificate ARN available")
		sys.exit(1)

	print(f"✓ Certificate ARN: {cert.arn}")
	print(f"✓ Certificate status: {cert.status}")
	print()

	if cert.status == "PENDING_VALIDATION":
		print("⚠️  Certificate is pending DNS validation!")
		print("   You must add the DNS records shown above before deploying.")
		print("   After adding the records, wait for the certificate to be issued")
		print("   (usually 5-10 minutes), then re-run this script.")
		print()
		sys.exit(0)

	# Phase 2: Ensure baseline stack exists
	print("=" * 60)
	print("Phase 2: Baseline Infrastructure")
	print("=" * 60)
	print()

	outputs = await ensure_baseline_stack(
		deployment_name,
		certificate_arn=cert.arn,
	)

	print(f"✓ Baseline stack: {outputs.stack_name}")
	print(f"✓ Cluster: {outputs.cluster_name}")
	print(f"✓ ECR Repository: {outputs.ecr_repository_uri}")
	print(f"✓ ALB DNS: {outputs.alb_dns_name}")
	print()

	# Check if domain DNS is configured correctly
	dns_config = check_domain_dns(domain, outputs.alb_dns_name)
	if dns_config:
		print("⚠️  Domain DNS Configuration Required")
		print("=" * 60)
		print()
		print(dns_config.format_for_display())
		print()
		print("⚠️  Your domain does not currently resolve to the load balancer.")
		print("   The deployment will continue, but the domain won't be accessible")
		print("   until you add the DNS record above.")
		print()
	else:
		print(f"✓ Domain DNS: {domain} → {outputs.alb_dns_name}")
		print()

	# Phase 3: Deploy application
	print("=" * 60)
	print("Phase 3: Deploy Application")
	print("=" * 60)
	print()

	# Generate deployment ID
	deployment_id = generate_deployment_id(deployment_name)
	print(f"📋 Deployment ID: {deployment_id}")
	print()

	# Generate drain secret
	drain_secret = secrets.token_urlsafe(32)
	print(f"🔐 Drain secret: {drain_secret}")
	print("   (Save this for draining the deployment later)")
	print()

	# Build and push image
	image_uri = await build_and_push_image(
		dockerfile_path=dockerfile_path,
		deployment_id=deployment_id,
		baseline=outputs,
		drain_secret=drain_secret,
		context_path=repo_root,
	)
	print()

	# Register task definition
	task_def_arn = await register_task_definition(
		image_uri=image_uri,
		deployment_id=deployment_id,
		baseline=outputs,
	)
	print()

	# Create service and target group
	service_arn, target_group_arn = await create_service_and_target_group(
		deployment_name=deployment_name,
		deployment_id=deployment_id,
		task_def_arn=task_def_arn,
		baseline=outputs,
	)
	print()

	# Install listener rules and switch traffic
	await install_listener_rules_and_switch_traffic(
		deployment_name=deployment_name,
		deployment_id=deployment_id,
		target_group_arn=target_group_arn,
		baseline=outputs,
	)
	print()

	# Success!
	print("=" * 60)
	print("🎉 Deployment Complete!")
	print("=" * 60)
	print()
	print(f"Deployment ID: {deployment_id}")
	print(f"Service ARN:   {service_arn}")
	print(f"Target Group:  {target_group_arn}")
	print()
	print("✅ Deployment is live and healthy!")
	print()
	print("Next steps:")
	print("1. Run verify.py to test the deployment:")
	print("   AWS_PROFILE=your-profile uv run packages/pulse-aws/scripts/verify.py")
	print()
	print("2. Access your application:")
	print(f"   https://{domain}/")
	print()
	print("3. To drain this deployment later:")
	print(f"   curl -X POST -H 'Authorization: Bearer {drain_secret}' \\")
	print(f"     https://{domain}/drain")
	print()


if __name__ == "__main__":
	asyncio.run(main())
