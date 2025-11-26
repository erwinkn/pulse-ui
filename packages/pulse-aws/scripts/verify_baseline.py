#!/usr/bin/env python3
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Add src to path to import pulse_aws
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from pulse_aws.baseline import BaselineStackOutputs, ensure_baseline_stack


async def verify_resources(outputs: BaselineStackOutputs) -> None:
	print(f"\n🔍 Verifying resources for stack: {outputs.stack_name}")
	print(f"   Region: {outputs.region}")
	print(f"   Account: {outputs.account}")

	session = boto3.Session(region_name=outputs.region)

	# 1. Verify VPC
	print(f"1. Checking VPC: {outputs.vpc_id}...")
	ec2 = session.client("ec2")
	vpcs = ec2.describe_vpcs(VpcIds=[outputs.vpc_id])
	state = vpcs["Vpcs"][0]["State"]
	assert state == "available", f"VPC is in state {state}"
	print("   ✅ VPC exists and is available")

	# 2. Verify Subnets
	all_subnets = outputs.private_subnet_ids + outputs.public_subnet_ids
	print(f"2. Checking {len(all_subnets)} Subnets...")
	subnets = ec2.describe_subnets(SubnetIds=all_subnets)
	found_ids = {s["SubnetId"] for s in subnets["Subnets"]}
	assert len(found_ids) == len(all_subnets), "Some subnets are missing"
	print("   ✅ Subnets exist")

	# 3. Verify Security Groups
	print("3. Checking Security Groups...")
	sgs = ec2.describe_security_groups(
		GroupIds=[
			outputs.alb_security_group_id,
			outputs.service_security_group_id,
		]
	)
	assert len(sgs["SecurityGroups"]) == 2, "Security groups missing"
	print("   ✅ Security Groups exist")

	# 4. Verify ALB
	print(f"4. Checking ALB: {outputs.alb_dns_name}...")
	elbv2 = session.client("elbv2")
	# Resolve ALB ARN from Listener ARN
	listeners = elbv2.describe_listeners(ListenerArns=[outputs.listener_arn])
	lb_arn = listeners["Listeners"][0]["LoadBalancerArn"]

	lbs = elbv2.describe_load_balancers(LoadBalancerArns=[lb_arn])
	state = lbs["LoadBalancers"][0]["State"]["Code"]
	assert state == "active", f"ALB is in state {state}"
	print("   ✅ ALB exists and is active")

	# 5. Verify ECR
	repo_name = outputs.ecr_repository_uri.split("/")[1]
	print(f"5. Checking ECR Repo: {repo_name}...")
	ecr = session.client("ecr")
	repos = ecr.describe_repositories(repositoryNames=[repo_name])
	uri = repos["repositories"][0]["repositoryUri"]
	assert uri == outputs.ecr_repository_uri, f"ECR URI mismatch: {uri}"
	print("   ✅ ECR Repository exists")

	print("\n✨ All verifications passed!")


async def main() -> None:
	parser = argparse.ArgumentParser(
		description="Spin up and verify Pulse baseline infrastructure."
	)
	parser.add_argument(
		"--env",
		default=f"test-{uuid.uuid4().hex[:6]}",
		help="Environment name (default: random)",
	)
	parser.add_argument(
		"--domain",
		help="Domain name to use (will trigger DNS validation wait if no cert ARN provided)",
	)
	parser.add_argument(
		"--cert-arn",
		help="Existing ACM Certificate ARN to use (skips DNS validation)",
	)
	parser.add_argument(
		"--keep",
		action="store_true",
		help="Keep the stack after verification (default: destroy)",
	)
	parser.add_argument(
		"--region",
		help="AWS Region (defaults to environment)",
	)

	args = parser.parse_args()

	if not args.domain and not args.cert_arn:
		print("Error: Must provide either --domain or --cert-arn")
		sys.exit(1)

	if args.region:
		boto3.setup_default_session(region_name=args.region)

	print(f"🚀 Starting integration test for env: {args.env}")
	if args.keep:
		print("⚠️  Stack will be KEPT after verification")
	else:
		print("♻️  Stack will be DESTROYED after verification")

	try:
		# Create Stack
		outputs = await ensure_baseline_stack(
			env_name=args.env,
			domains=[args.domain] if args.domain else None,
			certificate_arn=args.cert_arn,
		)

		# Verify Resources
		await verify_resources(outputs)

	except Exception as e:
		print(f"\n❌ Test failed: {e}")
		if not args.keep:
			print("Attempting cleanup...")
			cleanup(args.env, args.region)
		sys.exit(1)

	if not args.keep:
		cleanup(outputs.env_name, outputs.region)


def cleanup(env_name: str, region: str | None = None) -> None:
	stack_name = f"pulse-{env_name}-baseline"
	print(f"\n🔥 Destroying stack: {stack_name}...")
	cfn = boto3.client("cloudformation", region_name=region)
	try:
		cfn.delete_stack(StackName=stack_name)
		print("   Delete initiated. Waiting for completion...")
		waiter = cfn.get_waiter("stack_delete_complete")
		waiter.wait(StackName=stack_name)
		print("   ✅ Stack deleted")
	except ClientError as e:
		print(f"   Failed to delete stack: {e}")


if __name__ == "__main__":
	asyncio.run(main())
