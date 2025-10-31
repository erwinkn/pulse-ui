#!/usr/bin/env python3
"""Deploy a Pulse app to AWS ECS with baseline infrastructure.

This script orchestrates the full deployment workflow:
1. Ensure ACM certificate exists and is validated
2. Ensure baseline CloudFormation stack exists (VPC, ALB, ECS cluster, etc.)
3. Build and push Docker image to ECR
4. Register ECS task definition
5. Create ECS service and ALB target group
6. Mark deployment as active in SSM and previous deployments as draining
7. Install listener rules for header-based routing
8. Switch default traffic to the new deployment

The deployment uses:
- Header-based affinity (X-Pulse-Render-Affinity) for sticky sessions
- SSM Parameter Store for deployment and task state management
- Reaper Lambda for automated cleanup of drained deployments
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from pulse_aws.config import DockerBuild, HealthCheckConfig, TaskConfig
from pulse_aws.deployment import deploy

# ============================================================================
# Configuration - Edit these variables for your deployment
# ============================================================================

# Deployment configuration
DOMAIN = "test.stoneware.rocks"
DEPLOYMENT_NAME = "test"

# Docker configuration
# Path to Dockerfile (relative to repo root or absolute)
DOCKERFILE_PATH = "examples/aws-ecs/Dockerfile"
# Docker build context path (relative to repo root or absolute)
CONTEXT_PATH = "examples/aws-ecs"

# Drain configuration
DRAIN_POLL_SECONDS = 5
DRAIN_GRACE_SECONDS = 20

# Health check configuration
HEALTH_CHECK_PATH = "/_pulse/health"

# ============================================================================


async def main() -> None:
	"""Deploy a Pulse app to AWS ECS."""
	repo_root = Path(__file__).parent.parent.parent.parent

	# Resolve Dockerfile path
	dockerfile_path = Path(DOCKERFILE_PATH)
	if not dockerfile_path.is_absolute():
		dockerfile_path = repo_root / dockerfile_path

	# Resolve context path
	context_path = Path(CONTEXT_PATH)
	if not context_path.is_absolute():
		context_path = repo_root / context_path

	if not dockerfile_path.exists():
		print(f"❌ Dockerfile not found: {dockerfile_path}")
		sys.exit(1)

	if not context_path.exists():
		print(f"❌ Context path not found: {context_path}")
		sys.exit(1)

	print(f"🚀 Deploying to {DEPLOYMENT_NAME} environment")
	print(f"   Domain: {DOMAIN}")
	print(f"   Dockerfile: {dockerfile_path}")
	print(f"   Context: {context_path}")
	print()

	# Prepare build args (DEPLOYMENT_NAME and DEPLOYMENT_ID are added automatically by build_and_push_image)
	docker = DockerBuild(
		dockerfile_path=dockerfile_path,
		context_path=context_path,
		build_args={
			"PULSE_SERVER_ADDRESS": f"https://{DOMAIN}",
		},
	)

	# Prepare task config with drain settings
	task_config = TaskConfig(
		drain_poll_seconds=DRAIN_POLL_SECONDS,
		drain_grace_seconds=DRAIN_GRACE_SECONDS,
		env_vars={
			"PULSE_SERVER_ADDRESS": f"https://{DOMAIN}",
		},
	)

	# Health check configuration
	health_check_config = HealthCheckConfig(path=HEALTH_CHECK_PATH)

	# Deploy!
	print("=" * 60)
	print("Starting Deployment")
	print("=" * 60)
	print()

	result = await deploy(
		domain=DOMAIN,
		deployment_name=DEPLOYMENT_NAME,
		docker=docker,
		task=task_config,
		health_check=health_check_config,
	)

	# Success!
	print("=" * 60)
	print("🎉 Deployment Complete!")
	print("=" * 60)
	print()
	print(f"Deployment ID: {result['deployment_id']}")
	print(f"Service ARN:   {result['service_arn']}")
	print(f"Target Group:  {result['target_group_arn']}")
	print(f"Image URI:     {result['image_uri']}")
	print()
	if int(result.get("marked_draining_count", 0)) > 0:
		print(
			f"Marked {result['marked_draining_count']} previous deployment(s) as draining"
		)
		print("(Reaper will clean them up automatically within 1-5 minutes)")
	print()
	print("✅ Deployment is live and healthy!")
	print()
	print("Next steps:")
	print("1. Run verify.py to test the deployment:")
	print("   AWS_PROFILE=your-profile uv run packages/pulse-aws/scripts/verify.py")
	print()
	print("2. Access your application:")
	print(f"   https://{DOMAIN}/")
	print()
	print("3. Monitor deployment state in SSM:")
	print(f"   Parameter: /apps/{DEPLOYMENT_NAME}/{result['deployment_id']}/state")
	print()
	print("4. Monitor reaper cleanup in CloudWatch Logs:")
	print(f"   Log group: /aws/lambda/{DEPLOYMENT_NAME}-baseline-ReaperFunction*")
	print()


if __name__ == "__main__":
	asyncio.run(main())
