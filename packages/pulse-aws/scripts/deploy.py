#!/usr/bin/env python3
"""Deploy a minimal server to AWS ECS with baseline infrastructure.

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
- SSM Parameter Store for deployment state management
- CloudWatch EMF metrics for graceful draining orchestration
- Reaper Lambda for automated cleanup of drained deployments
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from pulse_aws.config import DockerBuild
from pulse_aws.deployment import deploy


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

	# Deploy!
	print("=" * 60)
	print("Starting Deployment")
	print("=" * 60)
	print()

	result = await deploy(
		domain=domain,
		deployment_name=deployment_name,
		docker=DockerBuild(
			dockerfile_path=dockerfile_path,
			context_path=repo_root,
		),
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
	print(f"   https://{domain}/")
	print()
	print("3. Monitor deployment state in SSM:")
	print(f"   Parameter: /apps/{deployment_name}/{result['deployment_id']}/state")
	print()
	print("4. Monitor reaper cleanup in CloudWatch Logs:")
	print(f"   Log group: /aws/lambda/{deployment_name}-baseline-ReaperFunction*")
	print()


if __name__ == "__main__":
	asyncio.run(main())
