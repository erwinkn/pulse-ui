#!/usr/bin/env python3
"""Teardown baseline infrastructure deployed by test_deploy.py.

This script safely removes the baseline CloudFormation stack, including:
- VPC, subnets, routing tables
- Application Load Balancer (ALB)
- ECS cluster
- CloudWatch log group
- ECR repository
- Security groups

NOTE: This script does NOT delete the ACM certificate, which can be reused
for future deployments. To delete the certificate, use the AWS Console or CLI.

SAFETY CHECKS
=============
By default, the script will:
1. Check for active ECS services and refuse to delete if any exist
2. Prompt for confirmation before proceeding
3. Wait for deletion to complete

Use --force to bypass the active service check (dangerous if apps are running).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add src to path so we can import pulse_aws
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pulse_aws.teardown import teardown_baseline_stack


async def main() -> None:
	"""Teardown baseline infrastructure."""
	deployment_name = "test"
	force = "--force" in sys.argv

	print(f"🗑️  Tearing down baseline infrastructure: {deployment_name}")
	print()

	if force:
		print("⚠️  --force flag detected: skipping active service checks")
		print()

	# Confirm before proceeding
	print("This will delete:")
	print("  • VPC and all networking resources")
	print("  • Application Load Balancer")
	print("  • ECS cluster")
	print("  • CloudWatch log group")
	print("  • ECR repository (and all images)")
	print("  • Security groups")
	print()
	print("The ACM certificate will NOT be deleted and can be reused.")
	print()

	response = input("Are you sure you want to continue? (yes/no): ")
	if response.lower() not in ("yes", "y"):
		print("❌ Teardown cancelled")
		sys.exit(0)

	print()
	print("🔄 Starting teardown...")
	print("   (This may take 5-10 minutes)")
	print()

	try:
		await teardown_baseline_stack(
			deployment_name,
			force=force,
		)

		print()
		print("=" * 60)
		print("🎉 Teardown complete!")
		print("=" * 60)
		print()
		print(f"The baseline stack for '{deployment_name}' has been removed.")
		print()
		print("Note: The ACM certificate was not deleted. To remove it:")
		print("  aws acm list-certificates")
		print("  aws acm delete-certificate --certificate-arn <arn>")
		print()

	except Exception as exc:
		print()
		print("=" * 60)
		print("❌ Teardown failed")
		print("=" * 60)
		print()
		print(f"Error: {exc}")
		print()

		if "active Pulse service(s) found" in str(exc):
			print("Active ECS services are still running. Options:")
			print("1. Drain and remove services manually via AWS Console/CLI")
			print("2. Re-run with --force to override this check (DANGEROUS)")
			print()
			print("To check running services:")
			print(f"  aws ecs list-services --cluster {deployment_name}")
			print()

		sys.exit(1)


if __name__ == "__main__":
	asyncio.run(main())
