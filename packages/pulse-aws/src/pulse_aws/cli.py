"""Command-line interface for pulse-aws."""

from __future__ import annotations

import argparse
import asyncio
import os
import warnings
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, cast

import boto3
import httpx

from pulse_aws.baseline import BaselineStackOutputs, describe_stack
from pulse_aws.config import DockerBuild, HealthCheckConfig, TaskConfig
from pulse_aws.deployment import deploy
from pulse_aws.teardown import teardown_baseline_stack


def _env(name: str) -> str | None:
	return os.environ.get(name)


def _env_int(name: str, default: int) -> int:
	value = os.environ.get(name)
	if not value:
		return default
	return int(value)


def _env_bool(name: str, default: bool) -> bool:
	value = os.environ.get(name)
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "y"}


def _parse_kv_items(items: Iterable[str] | None, label: str) -> dict[str, str]:
	parsed: dict[str, str] = {}
	if not items:
		return parsed
	for item in items:
		if "=" not in item:
			raise ValueError(f"{label} must be KEY=VALUE, got '{item}'")
		key, value = item.split("=", 1)
		if not key:
			raise ValueError(f"{label} must be KEY=VALUE, got '{item}'")
		parsed[key] = value
	return parsed


def _resolve_path(base: Path, raw: str) -> Path:
	path = Path(raw)
	if path.is_absolute():
		return path
	return (base / path).resolve()


def _add_deploy_args(parser: argparse.ArgumentParser) -> None:
	default_health = HealthCheckConfig()
	parser.add_argument(
		"--deployment-name",
		default=_env("PULSE_AWS_DEPLOYMENT_NAME"),
		help="Environment name (env: PULSE_AWS_DEPLOYMENT_NAME)",
	)
	parser.add_argument(
		"--domain",
		default=_env("PULSE_AWS_DOMAIN"),
		help="Public domain for the deployment (env: PULSE_AWS_DOMAIN)",
	)
	parser.add_argument(
		"--server-address",
		default=_env("PULSE_SERVER_ADDRESS"),
		help="Server address for Pulse (env: PULSE_SERVER_ADDRESS)",
	)
	parser.add_argument(
		"--project-root",
		default=_env("PULSE_AWS_PROJECT_ROOT"),
		help="Project root for resolving Dockerfile/context (default: cwd)",
	)
	parser.add_argument(
		"--app-file",
		default=_env("PULSE_AWS_APP_FILE") or "main.py",
		help="App entry file for Dockerfile build args (env: PULSE_AWS_APP_FILE)",
	)
	parser.add_argument(
		"--web-root",
		default=_env("PULSE_AWS_WEB_ROOT") or "web",
		help="Web root for Dockerfile build args (env: PULSE_AWS_WEB_ROOT)",
	)
	parser.add_argument(
		"--dockerfile",
		default=_env("PULSE_AWS_DOCKERFILE") or "Dockerfile",
		help="Path to Dockerfile (env: PULSE_AWS_DOCKERFILE)",
	)
	parser.add_argument(
		"--context",
		default=_env("PULSE_AWS_CONTEXT") or ".",
		help="Docker build context (env: PULSE_AWS_CONTEXT)",
	)
	parser.add_argument(
		"--build-arg",
		action="append",
		default=[],
		help="Extra docker build arg KEY=VALUE (repeatable)",
	)
	parser.add_argument(
		"--task-env",
		action="append",
		default=[],
		help="Extra task env KEY=VALUE (repeatable)",
	)
	parser.add_argument(
		"--task-cpu",
		default=_env("PULSE_AWS_TASK_CPU") or "256",
		help="ECS task CPU units (env: PULSE_AWS_TASK_CPU)",
	)
	parser.add_argument(
		"--task-memory",
		default=_env("PULSE_AWS_TASK_MEMORY") or "512",
		help="ECS task memory (env: PULSE_AWS_TASK_MEMORY)",
	)
	parser.add_argument(
		"--desired-count",
		type=int,
		default=_env_int("PULSE_AWS_DESIRED_COUNT", 2),
		help="Desired task count (env: PULSE_AWS_DESIRED_COUNT)",
	)
	parser.add_argument(
		"--drain-poll-seconds",
		type=int,
		default=_env_int("PULSE_AWS_DRAIN_POLL_SECONDS", 5),
		help="Drain poll interval (env: PULSE_AWS_DRAIN_POLL_SECONDS)",
	)
	parser.add_argument(
		"--drain-grace-seconds",
		type=int,
		default=_env_int("PULSE_AWS_DRAIN_GRACE_SECONDS", 20),
		help="Drain grace period (env: PULSE_AWS_DRAIN_GRACE_SECONDS)",
	)
	parser.add_argument(
		"--health-check-path",
		default=_env("PULSE_AWS_HEALTH_CHECK_PATH") or default_health.path,
		help="ALB health check path (env: PULSE_AWS_HEALTH_CHECK_PATH)",
	)
	parser.add_argument(
		"--health-check-interval",
		type=int,
		default=_env_int(
			"PULSE_AWS_HEALTH_CHECK_INTERVAL", default_health.interval_seconds
		),
		help="Health check interval (env: PULSE_AWS_HEALTH_CHECK_INTERVAL)",
	)
	parser.add_argument(
		"--health-check-timeout",
		type=int,
		default=_env_int(
			"PULSE_AWS_HEALTH_CHECK_TIMEOUT", default_health.timeout_seconds
		),
		help="Health check timeout (env: PULSE_AWS_HEALTH_CHECK_TIMEOUT)",
	)
	parser.add_argument(
		"--healthy-threshold",
		type=int,
		default=_env_int(
			"PULSE_AWS_HEALTHY_THRESHOLD", default_health.healthy_threshold
		),
		help="Healthy threshold (env: PULSE_AWS_HEALTHY_THRESHOLD)",
	)
	parser.add_argument(
		"--unhealthy-threshold",
		type=int,
		default=_env_int(
			"PULSE_AWS_UNHEALTHY_THRESHOLD", default_health.unhealthy_threshold
		),
		help="Unhealthy threshold (env: PULSE_AWS_UNHEALTHY_THRESHOLD)",
	)
	parser.add_argument(
		"--wait-for-health",
		action=argparse.BooleanOptionalAction,
		default=_env_bool("PULSE_AWS_WAIT_FOR_HEALTH", default_health.wait_for_health),
		help="Wait for healthy targets before switching",
	)
	parser.add_argument(
		"--min-healthy-targets",
		type=int,
		default=_env_int(
			"PULSE_AWS_MIN_HEALTHY_TARGETS", default_health.min_healthy_targets
		),
		help="Minimum healthy targets before switching",
	)


def _add_verify_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument(
		"--deployment-name",
		default=_env("PULSE_AWS_DEPLOYMENT_NAME"),
		help="Environment name (env: PULSE_AWS_DEPLOYMENT_NAME)",
	)
	parser.add_argument(
		"--domain",
		default=_env("PULSE_AWS_DOMAIN"),
		help="Domain for sample curl output (env: PULSE_AWS_DOMAIN)",
	)
	parser.add_argument(
		"--health-check-path",
		default=_env("PULSE_AWS_HEALTH_CHECK_PATH") or HealthCheckConfig().path,
		help="Health check path (env: PULSE_AWS_HEALTH_CHECK_PATH)",
	)
	parser.add_argument(
		"--verify-ssl",
		action=argparse.BooleanOptionalAction,
		default=_env_bool("PULSE_AWS_VERIFY_SSL", False),
		help="Verify SSL certs when calling the ALB",
	)


def _add_teardown_args(parser: argparse.ArgumentParser) -> None:
	parser.add_argument(
		"--deployment-name",
		default=_env("PULSE_AWS_DEPLOYMENT_NAME"),
		help="Environment name (env: PULSE_AWS_DEPLOYMENT_NAME)",
	)
	parser.add_argument(
		"--force",
		action="store_true",
		help="Skip active service checks",
	)
	parser.add_argument(
		"--yes",
		action="store_true",
		help="Skip confirmation prompt",
	)
	parser.add_argument(
		"--poll-interval",
		type=float,
		default=float(_env_int("PULSE_AWS_POLL_INTERVAL", 5)),
		help="Polling interval seconds (env: PULSE_AWS_POLL_INTERVAL)",
	)
	parser.add_argument(
		"--region",
		default=_env("AWS_REGION") or _env("AWS_DEFAULT_REGION"),
		help="AWS region override",
	)


async def _run_deploy(args: argparse.Namespace) -> int:
	if not args.deployment_name:
		raise ValueError("deployment_name is required (--deployment-name)")
	if not args.domain:
		raise ValueError("domain is required (--domain)")

	project_root = (
		Path(args.project_root).resolve() if args.project_root else Path.cwd()
	)
	dockerfile_path = _resolve_path(project_root, args.dockerfile)
	context_path = _resolve_path(project_root, args.context)

	if not dockerfile_path.exists():
		raise ValueError(f"Dockerfile not found: {dockerfile_path}")
	if not context_path.exists():
		raise ValueError(f"Context path not found: {context_path}")
	if Path(args.app_file).is_absolute():
		raise ValueError("app-file must be relative to the Docker build context")
	if Path(args.web_root).is_absolute():
		raise ValueError("web-root must be relative to the Docker build context")
	app_path = _resolve_path(context_path, args.app_file)
	if not app_path.exists():
		raise ValueError(f"App file not found: {app_path}")
	web_root_path = _resolve_path(context_path, args.web_root)
	if not web_root_path.exists():
		raise ValueError(f"Web root not found: {web_root_path}")

	server_address = args.server_address or f"https://{args.domain}"

	build_args = _parse_kv_items(args.build_arg, "--build-arg")
	build_args.setdefault("APP_FILE", args.app_file)
	build_args.setdefault("WEB_ROOT", args.web_root)
	build_args.setdefault("PULSE_SERVER_ADDRESS", server_address)

	task_env = _parse_kv_items(args.task_env, "--task-env")
	task_env.setdefault("PULSE_SERVER_ADDRESS", server_address)

	docker = DockerBuild(
		dockerfile_path=dockerfile_path,
		context_path=context_path,
		build_args=build_args,
	)
	task_config = TaskConfig(
		cpu=str(args.task_cpu),
		memory=str(args.task_memory),
		desired_count=args.desired_count,
		drain_poll_seconds=args.drain_poll_seconds,
		drain_grace_seconds=args.drain_grace_seconds,
		env_vars=task_env,
	)
	health_check = HealthCheckConfig(
		path=args.health_check_path,
		interval_seconds=args.health_check_interval,
		timeout_seconds=args.health_check_timeout,
		healthy_threshold=args.healthy_threshold,
		unhealthy_threshold=args.unhealthy_threshold,
		wait_for_health=args.wait_for_health,
		min_healthy_targets=args.min_healthy_targets,
	)

	print(f"🚀 Deploying to {args.deployment_name}")
	print(f"   Domain: {args.domain}")
	print(f"   Dockerfile: {dockerfile_path}")
	print(f"   Context: {context_path}")
	print(f"   Server address: {server_address}")
	print()

	result = await deploy(
		domain=args.domain,
		deployment_name=args.deployment_name,
		docker=docker,
		task=task_config,
		health_check=health_check,
	)

	print()
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
	return 0


async def _run_verify(args: argparse.Namespace) -> int:
	if not args.deployment_name:
		raise ValueError("deployment_name is required (--deployment-name)")

	if not args.verify_ssl:
		warnings.filterwarnings("ignore", message="Unverified HTTPS request")

	print(f"🔍 Verifying deployments for: {args.deployment_name}")
	print()

	print("📋 Loading baseline stack outputs...")
	cfn = boto3.client("cloudformation")
	sts = boto3.client("sts")
	region = sts.meta.region_name
	if not region:
		raise ValueError("AWS region not configured")
	account = sts.get_caller_identity().get("Account")
	if not account:
		raise ValueError("AWS account not available")
	region = cast(str, region)
	account = cast(str, account)

	stack_name = f"{args.deployment_name}-baseline"
	stack = describe_stack(cfn, stack_name)

	if not stack:
		print(f"❌ Baseline stack {stack_name} not found")
		print("   Run deploy first to create the baseline infrastructure")
		return 1

	outputs = cast(list[dict[str, str]], stack.get("Outputs", []))
	outputs_dict = {item["OutputKey"]: item["OutputValue"] for item in outputs}

	baseline = BaselineStackOutputs(
		deployment_name=args.deployment_name,
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

	print("🔎 Discovering active deployments...")
	ecs = boto3.client("ecs", region_name=region)

	try:
		services_response = ecs.list_services(cluster=baseline.cluster_name)
		service_arns = cast(list[str], services_response.get("serviceArns", []))

		if not service_arns:
			print("❌ No services found in cluster")
			print("   Run deploy to deploy a service")
			return 1

		services_detail = ecs.describe_services(
			cluster=baseline.cluster_name,
			services=service_arns,
		)

		services = cast(list[dict[str, Any]], services_detail.get("services", []))
		active_services = [svc for svc in services if svc.get("status") == "ACTIVE"]

		print(f"✓ Found {len(active_services)} active service(s)")
		print()

		all_deployment_ids = [cast(str, svc["serviceName"]) for svc in active_services]
		running_deployment_ids = [
			cast(str, svc["serviceName"])
			for svc in active_services
			if (svc.get("runningCount", 0) or 0) > 0
		]

		for idx, deployment_id in enumerate(all_deployment_ids, 1):
			svc = next(s for s in active_services if s["serviceName"] == deployment_id)
			running = int(svc.get("runningCount", 0) or 0)
			desired = int(svc.get("desiredCount", 0) or 0)
			status = "✓" if running > 0 else "○"
			print(f"   {status} {idx}. {deployment_id}")
			print(f"      Tasks: {running}/{desired} running")

		print()

	except Exception as exc:
		print(f"❌ Failed to list services: {exc}")
		return 1

	print("=" * 60)
	print("🧪 Testing Endpoints")
	print("=" * 60)
	print()

	base_url = f"https://{baseline.alb_dns_name}"
	print(f"Base URL: {base_url}")
	print()

	async with httpx.AsyncClient(timeout=10.0, verify=args.verify_ssl) as client:
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

		print("2️⃣  Testing health endpoint...")
		try:
			response = await client.get(f"{base_url}{args.health_check_path}")
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
	if running_deployment_ids and args.domain:
		print("To test with domain:")
		print(f"  curl https://{args.domain}/")
		print(f"  curl https://{args.domain}{args.health_check_path}")
		print()
		if len(running_deployment_ids) > 1:
			print("To test affinity:")
			for deployment_id in running_deployment_ids:
				print(f"  curl -H 'X-Pulse-Render-Affinity: {deployment_id}' \\")
				print(f"    https://{args.domain}/")
	elif not running_deployment_ids:
		print("⚠️  No deployments with running tasks found")
	return 0


async def _run_teardown(args: argparse.Namespace) -> int:
	if not args.deployment_name:
		raise ValueError("deployment_name is required (--deployment-name)")

	print(f"🗑️  Tearing down baseline infrastructure: {args.deployment_name}")
	print()

	if args.force:
		print("⚠️  --force flag detected: skipping active service checks")
		print()

	if not args.yes:
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
			return 0

	print()
	print("🔄 Starting teardown...")
	print("   (This may take 5-10 minutes)")
	print()

	try:
		await teardown_baseline_stack(
			args.deployment_name,
			force=args.force,
			poll_interval=args.poll_interval,
			region=args.region,
		)
		print()
		print("=" * 60)
		print("🎉 Teardown complete!")
		print("=" * 60)
		print()
		print(f"The baseline stack for '{args.deployment_name}' has been removed.")
		print()
		print("Note: The ACM certificate was not deleted. To remove it:")
		print("  aws acm list-certificates")
		print("  aws acm delete-certificate --certificate-arn <arn>")
		print()
		return 0
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
			print(f"  aws ecs list-services --cluster {args.deployment_name}")
			print()
		return 1


def deploy_main(argv: Sequence[str] | None = None) -> int:
	parser = argparse.ArgumentParser(prog="pulse-aws deploy")
	_add_deploy_args(parser)
	args = parser.parse_args(argv)
	try:
		return asyncio.run(_run_deploy(args))
	except ValueError as exc:
		print(f"❌ {exc}")
		return 1


def verify_main(argv: Sequence[str] | None = None) -> int:
	parser = argparse.ArgumentParser(prog="pulse-aws verify")
	_add_verify_args(parser)
	args = parser.parse_args(argv)
	try:
		return asyncio.run(_run_verify(args))
	except ValueError as exc:
		print(f"❌ {exc}")
		return 1


def teardown_main(argv: Sequence[str] | None = None) -> int:
	parser = argparse.ArgumentParser(prog="pulse-aws teardown")
	_add_teardown_args(parser)
	args = parser.parse_args(argv)
	try:
		return asyncio.run(_run_teardown(args))
	except ValueError as exc:
		print(f"❌ {exc}")
		return 1


def main(argv: Sequence[str] | None = None) -> int:
	parser = argparse.ArgumentParser(prog="pulse-aws")
	sub = parser.add_subparsers(dest="command", required=True)

	deploy_parser = sub.add_parser("deploy", help="Deploy a Pulse app to ECS")
	_add_deploy_args(deploy_parser)
	deploy_parser.set_defaults(_runner=_run_deploy)

	verify_parser = sub.add_parser("verify", help="Verify ECS deployments")
	_add_verify_args(verify_parser)
	verify_parser.set_defaults(_runner=_run_verify)

	teardown_parser = sub.add_parser("teardown", help="Teardown baseline stack")
	_add_teardown_args(teardown_parser)
	teardown_parser.set_defaults(_runner=_run_teardown)

	args = parser.parse_args(argv)
	runner = getattr(args, "_runner", None)
	if runner is None:
		parser.error("command required")
	try:
		return asyncio.run(runner(args))
	except ValueError as exc:
		print(f"❌ {exc}")
		return 1


__all__ = ["deploy_main", "verify_main", "teardown_main", "main"]
