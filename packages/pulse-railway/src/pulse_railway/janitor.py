from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field

import aiohttp

from pulse_railway.config import RailwayInternals, RailwayProject
from pulse_railway.constants import (
	DEFAULT_JANITOR_LOCK_TTL_SECONDS,
	INTERNAL_SESSIONS_PATH,
	INTERNAL_TOKEN_HEADER,
)
from pulse_railway.deployment import (
	resolve_project_internals,
)
from pulse_railway.railway import RailwayGraphQLClient, service_name_for_deployment
from pulse_railway.store import DeploymentStore, RedisDeploymentStore

JANITOR_STATUS_CONCURRENCY = 4


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


@dataclass(slots=True)
class _DrainDecision:
	deployment_id: str
	service_name: str
	drainable: bool
	force_delete: bool


async def _probe_draining_deployment(
	session: aiohttp.ClientSession,
	*,
	deployment_id: str,
	service_name: str,
	drain_started_at: float | None,
	project: RailwayProject,
	internals: RailwayInternals,
	now: float,
	semaphore: asyncio.Semaphore,
) -> _DrainDecision:
	draining_for = now - drain_started_at if drain_started_at is not None else 0.0
	force_delete = draining_for >= project.max_drain_age_seconds
	if force_delete:
		return _DrainDecision(
			deployment_id=deployment_id,
			service_name=service_name,
			drainable=True,
			force_delete=True,
		)
	async with semaphore:
		try:
			session_status = await _fetch_deployment_session_status(
				session,
				deployment_id=deployment_id,
				service_name=service_name,
				project=project,
				internals=internals,
			)
		except Exception:
			return _DrainDecision(
				deployment_id=deployment_id,
				service_name=service_name,
				drainable=False,
				force_delete=False,
			)
	return _DrainDecision(
		deployment_id=deployment_id,
		service_name=service_name,
		drainable=session_status.drainable,
		force_delete=False,
	)


async def _fetch_deployment_session_status(
	session: aiohttp.ClientSession,
	*,
	deployment_id: str,
	service_name: str,
	project: RailwayProject,
	internals: RailwayInternals,
) -> DeploymentSessionStatus:
	url = (
		f"http://{service_name}.railway.internal:{project.backend_port}"
		f"{INTERNAL_SESSIONS_PATH}"
	)
	async with session.get(
		url,
		headers={INTERNAL_TOKEN_HEADER: internals.internal_token},
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
	store: DeploymentStore | None = None,
	now: float | None = None,
) -> JanitorResult:
	created_store = False
	lock_acquired = False
	lock_token = secrets.token_hex(8)
	try:
		async with RailwayGraphQLClient(token=project.token) as client:
			internals = await resolve_project_internals(client, project=project)
			if store is None:
				if internals.store_url is None:
					raise RuntimeError("redis_url is required for janitor tracking")
				store = RedisDeploymentStore.from_url(
					url=internals.store_url,
					prefix=project.redis_prefix,
					websocket_ttl_seconds=project.websocket_ttl_seconds,
				)
				created_store = True

			lock_acquired = await store.acquire_janitor_lock(
				token=lock_token,
				ttl_seconds=DEFAULT_JANITOR_LOCK_TTL_SECONDS,
			)
			if not lock_acquired:
				return JanitorResult(lock_acquired=False)

			timestamp = time.time() if now is None else now
			draining = await store.list_draining_deployments()
			result = JanitorResult(lock_acquired=True, scanned_count=len(draining))
			services_by_name = {
				service.name: service
				for service in await client.list_services(
					project_id=project.project_id,
					environment_id=project.environment_id,
				)
			}
			async with aiohttp.ClientSession(
				timeout=aiohttp.ClientTimeout(total=10, sock_connect=5)
			) as session:
				semaphore = asyncio.Semaphore(JANITOR_STATUS_CONCURRENCY)
				decisions = await asyncio.gather(
					*[
						_probe_draining_deployment(
							session,
							deployment_id=deployment.deployment_id,
							service_name=deployment.service_name
							or service_name_for_deployment(
								internals.service_prefix, deployment.deployment_id
							),
							drain_started_at=deployment.drain_started_at,
							project=project,
							internals=internals,
							now=timestamp,
							semaphore=semaphore,
						)
						for deployment in draining
					]
				)
				for decision in decisions:
					if not decision.drainable:
						result.skipped_deployments.append(decision.deployment_id)
						continue
					service = services_by_name.get(decision.service_name)
					if service is not None:
						await client.delete_service(
							service_id=service.id,
							environment_id=project.environment_id,
						)
					await store.clear_deployment(deployment_id=decision.deployment_id)
					result.deleted_deployments.append(decision.deployment_id)
					if decision.force_delete:
						result.force_deleted_deployments.append(decision.deployment_id)
		return result
	finally:
		if lock_acquired:
			assert store is not None
			await store.release_janitor_lock(token=lock_token)
		if created_store:
			assert store is not None
			await store.close()


__all__ = ["JanitorResult", "run_janitor"]
