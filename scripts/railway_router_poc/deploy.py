from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass

from scripts.railway_router_poc.railway import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	RailwayGraphQLClient,
	service_name_for_deployment,
	validate_deployment_id,
)


@dataclass(slots=True)
class DeployResult:
	deployment_id: str
	service_id: str
	service_name: str
	railway_deployment_id: str
	status: str
	public_domain: str | None


async def deploy_backend(
	*,
	token: str,
	project_id: str,
	environment_id: str,
	service_prefix: str,
	deployment_id: str,
	image: str,
	backend_port: int,
	num_replicas: int,
	activate: bool,
	expose_domain: bool,
) -> DeployResult:
	service_name = service_name_for_deployment(service_prefix, deployment_id)
	async with RailwayGraphQLClient(token=token) as client:
		service_id = await client.create_service(
			project_id=project_id,
			environment_id=environment_id,
			name=service_name,
			image=image,
		)
		await client.update_service_instance(
			service_id=service_id,
			environment_id=environment_id,
			num_replicas=num_replicas,
		)
		railway_deployment_id = await client.deploy_service(
			service_id=service_id,
			environment_id=environment_id,
		)
		deployment = await client.wait_for_deployment(
			deployment_id=railway_deployment_id
		)
		public_domain: str | None = None
		if expose_domain and deployment["status"] == "SUCCESS":
			public_domain = await client.create_service_domain(
				service_id=service_id,
				environment_id=environment_id,
				target_port=backend_port,
			)
		if activate and deployment["status"] == "SUCCESS":
			await client.upsert_variable(
				project_id=project_id,
				environment_id=environment_id,
				name=ACTIVE_DEPLOYMENT_VARIABLE,
				value=deployment_id,
			)
		return DeployResult(
			deployment_id=deployment_id,
			service_id=service_id,
			service_name=service_name,
			railway_deployment_id=railway_deployment_id,
			status=deployment["status"],
			public_domain=public_domain,
		)


async def delete_backend(
	*,
	token: str,
	project_id: str,
	environment_id: str,
	service_prefix: str,
	deployment_id: str,
) -> None:
	service_name = service_name_for_deployment(service_prefix, deployment_id)
	async with RailwayGraphQLClient(token=token) as client:
		for service in await client.list_services(project_id=project_id):
			if service["name"] == service_name:
				await client.delete_service(
					service_id=service["id"],
					environment_id=environment_id,
				)
				return
		raise RuntimeError(f"service {service_name} not found")


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Railway router POC deploy helper")
	subparsers = parser.add_subparsers(dest="command", required=True)

	deploy_parser = subparsers.add_parser("deploy")
	deploy_parser.add_argument("--deployment", required=True)
	deploy_parser.add_argument("--image", required=True)
	deploy_parser.add_argument("--project-id", default=os.getenv("RAILWAY_PROJECT_ID"))
	deploy_parser.add_argument(
		"--environment-id",
		default=os.getenv("RAILWAY_ENVIRONMENT_ID"),
	)
	deploy_parser.add_argument("--token", default=os.getenv("RAILWAY_TOKEN"))
	deploy_parser.add_argument("--service-prefix", default="poc-")
	deploy_parser.add_argument("--backend-port", type=int, default=80)
	deploy_parser.add_argument("--num-replicas", type=int, default=1)
	deploy_parser.add_argument("--no-activate", action="store_true")
	deploy_parser.add_argument("--expose-domain", action="store_true")

	delete_parser = subparsers.add_parser("delete")
	delete_parser.add_argument("--deployment", required=True)
	delete_parser.add_argument("--project-id", default=os.getenv("RAILWAY_PROJECT_ID"))
	delete_parser.add_argument(
		"--environment-id",
		default=os.getenv("RAILWAY_ENVIRONMENT_ID"),
	)
	delete_parser.add_argument("--token", default=os.getenv("RAILWAY_TOKEN"))
	delete_parser.add_argument("--service-prefix", default="poc-")
	return parser


def main() -> None:
	args = build_parser().parse_args()
	if not args.token or not args.project_id or not args.environment_id:
		raise SystemExit("token, project id, and environment id are required")
	deployment_id = validate_deployment_id(args.deployment)
	if args.command == "deploy":
		result = asyncio.run(
			deploy_backend(
				token=args.token,
				project_id=args.project_id,
				environment_id=args.environment_id,
				service_prefix=args.service_prefix,
				deployment_id=deployment_id,
				image=args.image,
				backend_port=args.backend_port,
				num_replicas=args.num_replicas,
				activate=not args.no_activate,
				expose_domain=args.expose_domain,
			)
		)
		print(json.dumps(asdict(result), indent=2, sort_keys=True))
		return
	if args.command == "delete":
		asyncio.run(
			delete_backend(
				token=args.token,
				project_id=args.project_id,
				environment_id=args.environment_id,
				service_prefix=args.service_prefix,
				deployment_id=deployment_id,
			)
		)


if __name__ == "__main__":
	main()
