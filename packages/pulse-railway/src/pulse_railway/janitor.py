from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

import aiohttp

from pulse_railway.config import RailwayProject
from pulse_railway.constants import (
	DEFAULT_JANITOR_LOCK_TTL_SECONDS,
	INTERNAL_SESSIONS_PATH,
	INTERNAL_TOKEN_HEADER,
	RAILWAY_INTERNAL_TOKEN_ENV,
)
from pulse_railway.deployment import (
	resolve_or_create_internal_token,
	resolve_or_create_redis,
)
from pulse_railway.railway import RailwayGraphQLClient, service_name_for_deployment
from pulse_railway.tracker import DeploymentTracker, RedisDeploymentTracker


@dataclass(slots=True)
class JanitorResult:
	lock_acquired: bool
	scanned_count: int = 0
	deleted_deployments: list[str] = field(default_factory=list)
	force_deleted_deployments: list[str] = field(default_factory=list)
	skipped_deployments: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DeploymentSessionStatus:
	deployment_id: str
	connected_render_count: int
	resumable_render_count: int
	drainable: bool


async def _fetch_deployment_session_status(
	session: aiohttp.ClientSession,
	*,
	deployment_id: str,
	service_name: str,
	project: RailwayProject,
) -> DeploymentSessionStatus:
	if not project.internal_token:
		raise RuntimeError(f"missing required env var: {RAILWAY_INTERNAL_TOKEN_ENV}")
	url = (
		f"http://{service_name}.railway.internal:{project.backend_port}"
		f"{INTERNAL_SESSIONS_PATH}"
	)
	async with session.get(
		url,
		headers={INTERNAL_TOKEN_HEADER: project.internal_token},
	) as response:
		response.raise_for_status()
		payload = await response.json()
	return DeploymentSessionStatus(
		deployment_id=payload["deployment_id"],
		connected_render_count=int(payload["connected_render_count"]),
		resumable_render_count=int(payload["resumable_render_count"]),
		drainable=bool(payload["drainable"]),
	)


async def run_janitor(
	*,
	project: RailwayProject,
	tracker: DeploymentTracker | None = None,
	now: float | None = None,
) -> JanitorResult:
	created_tracker = False
	lock_acquired = False
	lock_token = secrets.token_hex(8)
	try:
		async with RailwayGraphQLClient(token=project.token) as client:
			if tracker is None:
				if not project.redis_url:
					resolved_redis = await resolve_or_create_redis(
						client,
						project=project,
					)
					project.redis_url = resolved_redis.internal_url
					project.redis_public_url = resolved_redis.public_url
					project.redis_service_name = resolved_redis.service.name
				tracker = RedisDeploymentTracker.from_url(
					url=project.redis_public_url or project.redis_url,
					prefix=project.redis_prefix,
					websocket_ttl_seconds=project.websocket_ttl_seconds,
				)
				created_tracker = True
			project.internal_token = await resolve_or_create_internal_token(
				client,
				project=project,
			)

			lock_acquired = await tracker.acquire_janitor_lock(
				token=lock_token,
				ttl_seconds=DEFAULT_JANITOR_LOCK_TTL_SECONDS,
			)
			if not lock_acquired:
				return JanitorResult(lock_acquired=False)

			timestamp = time.time() if now is None else now
			draining = await tracker.list_draining_deployments()
			result = JanitorResult(lock_acquired=True, scanned_count=len(draining))
			async with aiohttp.ClientSession(
				timeout=aiohttp.ClientTimeout(total=10, sock_connect=5)
			) as session:
				for deployment in draining:
					service_name = (
						deployment.service_name
						or service_name_for_deployment(
							project.service_prefix, deployment.deployment_id
						)
					)
					draining_for = (
						timestamp - deployment.drain_started_at
						if deployment.drain_started_at is not None
						else 0.0
					)
					force_delete = draining_for >= project.max_drain_age_seconds
					if not force_delete:
						try:
							session_status = await _fetch_deployment_session_status(
								session,
								deployment_id=deployment.deployment_id,
								service_name=service_name,
								project=project,
							)
						except Exception:
							result.skipped_deployments.append(deployment.deployment_id)
							continue
						if not session_status.drainable:
							result.skipped_deployments.append(deployment.deployment_id)
							continue
					service = await client.find_service_by_name(
						project_id=project.project_id,
						environment_id=project.environment_id,
						name=service_name,
					)
					if service is not None:
						await client.delete_service(
							service_id=service.id,
							environment_id=project.environment_id,
						)
					await tracker.clear_deployment(
						deployment_id=deployment.deployment_id
					)
					result.deleted_deployments.append(deployment.deployment_id)
					if force_delete:
						result.force_deleted_deployments.append(
							deployment.deployment_id
						)
		return result
	finally:
		if lock_acquired:
			assert tracker is not None
			await tracker.release_janitor_lock(token=lock_token)
		if created_tracker:
			assert tracker is not None
			await tracker.close()


__all__ = ["JanitorResult", "run_janitor"]
