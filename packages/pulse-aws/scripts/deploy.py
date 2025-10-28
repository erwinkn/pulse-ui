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
import json
import secrets
import sys
from pathlib import Path

from pulse_aws.deployment import DockerBuild, DrainConfig, deploy


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

	# Get or create cached drain secret
	drain_secret = get_or_create_drain_secret(deployment_name)
	print(f"🔐 Drain secret: {drain_secret}")
	print(f"   (Cached in .pulse/{deployment_name}/secrets.json)")
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
		drain=DrainConfig(drain_secret=drain_secret),
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
	if int(result["drained_count"]) > 0:
		print(f"Drained {result['drained_count']} previous deployment(s)")
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
	print("3. Monitor reaper cleanup in CloudWatch Logs:")
	print(f"   Log group: /aws/lambda/{deployment_name}-baseline-ReaperFunction*")
	print()


if __name__ == "__main__":
	asyncio.run(main())
