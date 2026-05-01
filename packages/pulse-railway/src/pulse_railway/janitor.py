from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field

import aiohttp

from pulse_railway.config import RailwayInternals, RailwayProject
from pulse_railway.constants import (
	DEFAULT_BACKEND_PORT,
	DEFAULT_JANITOR_LOCK_TTL_SECONDS,
	DEPLOYMENT_STATE_DRAINING,
	INTERNAL_RELOAD_PATH,
	INTERNAL_SESSIONS_PATH,
	INTERNAL_TOKEN_HEADER,
)
from pulse_railway.deployment import (
	list_deployment_service_records,
	validate_deployment_service_records,
)
from pulse_railway.railway import RailwayGraphQLClient, service_name_for_deployment
from pulse_railway.stack import resolve_project_internals
from pulse_railway.store import (
	DeploymentStore,
	RedisDeploymentStore,
)

JANITOR_STATUS_CONCURRENCY = 4
JANITOR_RELOAD_GRACE_SECONDS = 1.0


@dataclass(slots=True)
class JanitorResult:
	lock_acquired: bool
	scanned_count: int = 0
	deleted_deployments: list[str] = field(default_factory=list)
	force_deleted_deployments: list[str] = field(default_factory=list)
	skipped_deployments: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DeploymentSessionStatus:
	render_session_count: int


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
	force_delete = draining_for >= project.drain_ttl_seconds
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
				service_name=service_name,
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
		drainable=session_status.render_session_count == 0,
		force_delete=False,
	)


async def _fetch_deployment_session_status(
	session: aiohttp.ClientSession,
	*,
	service_name: str,
	internals: RailwayInternals,
) -> DeploymentSessionStatus:
	url = (
		f"http://{service_name}.railway.internal:{DEFAULT_BACKEND_PORT}"
		f"{INTERNAL_SESSIONS_PATH}"
	)
	async with session.get(
		url,
		headers={INTERNAL_TOKEN_HEADER: internals.internal_token},
	) as response:
		response.raise_for_status()
		payload = await response.json()
	return DeploymentSessionStatus(
		render_session_count=int(payload["render_session_count"]),
	)


async def _signal_deployment_reload(
	session: aiohttp.ClientSession,
	*,
	service_name: str,
	internals: RailwayInternals,
) -> int:
	url = (
		f"http://{service_name}.railway.internal:{DEFAULT_BACKEND_PORT}"
		f"{INTERNAL_RELOAD_PATH}"
	)
	async with session.post(
		url,
		headers={INTERNAL_TOKEN_HEADER: internals.internal_token},
	) as response:
		response.raise_for_status()
		payload = await response.json()
	return int(payload.get("reloaded_socket_count", 0))


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
				if internals.redis_url is None:
					raise RuntimeError("redis_url is required for janitor tracking")
				store = RedisDeploymentStore.from_url(
					url=internals.redis_url,
					prefix=project.redis_prefix,
				)
				created_store = True

			lock_acquired = await store.acquire_janitor_lock(
				token=lock_token,
				ttl_seconds=DEFAULT_JANITOR_LOCK_TTL_SECONDS,
			)
			if not lock_acquired:
				return JanitorResult(lock_acquired=False)

			timestamp = time.time() if now is None else now
			deployment_services = await list_deployment_service_records(
				client,
				project=project,
			)
			active_deployment_id = await store.get_active_deployment()
			active_service, draining = validate_deployment_service_records(
				deployment_services,
				active_deployment_id,
			)
			if active_service is not None:
				await store.set_active(
					deployment_id=active_service.deployment_id,
					service_name=active_service.service_name,
				)
			for service in draining:
				stored = await store.get_deployment(deployment_id=service.deployment_id)
				if (
					stored is None
					or stored.state != DEPLOYMENT_STATE_DRAINING
					or stored.drain_started_at is None
				):
					await store.mark_draining(
						deployment_id=service.deployment_id,
						service_name=service.service_name,
						now=(
							service.drain_started_at
							if service.state == DEPLOYMENT_STATE_DRAINING
							and service.drain_started_at is not None
							else timestamp
						),
					)
					stored = await store.get_deployment(
						deployment_id=service.deployment_id
					)
				assert stored is not None
				service.state = stored.state
				service.drain_started_at = stored.drain_started_at
			result = JanitorResult(lock_acquired=True, scanned_count=len(draining))
			draining_service_ids = {
				service.service_name: service.service_id for service in draining
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
					connected_reload_count = 0
					try:
						connected_reload_count = await _signal_deployment_reload(
							session,
							service_name=decision.service_name,
							internals=internals,
						)
					except Exception:
						connected_reload_count = 0
					if connected_reload_count > 0:
						await asyncio.sleep(JANITOR_RELOAD_GRACE_SECONDS)
					service_id = draining_service_ids.get(decision.service_name)
					if service_id is not None:
						await client.delete_service(
							service_id=service_id,
							environment_id=project.environment_id,
						)
					await store.delete_inactive_deployment(
						deployment_id=decision.deployment_id
					)
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
