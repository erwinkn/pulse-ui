from __future__ import annotations

import os
from dataclasses import dataclass

from pulse_railway.constants import DEFAULT_REDIS_PREFIX, PULSE_REDIS_PREFIX
from pulse_railway.store import (
	ActiveDeploymentError,
	DeploymentStore,
	kv_store_spec_from_env,
)


@dataclass(slots=True)
class DrainingDeployment:
	deployment_id: str
	service_name: str
	drain_started_at: float | None = None


def deployment_store_from_env(env: dict[str, str] | None = None) -> DeploymentStore:
	values = dict(os.environ) if env is None else env
	spec = kv_store_spec_from_env(values)
	if spec is None:
		raise RuntimeError("missing required deployment store env vars")
	return DeploymentStore(
		store=spec,
		prefix=values.get(PULSE_REDIS_PREFIX, DEFAULT_REDIS_PREFIX),
		owns_store=True,
	)


async def get_active_deployment(store: DeploymentStore) -> str | None:
	return await store.get_active_deployment()


async def register_deployment(
	store: DeploymentStore,
	*,
	deployment_id: str,
	service_name: str,
) -> None:
	if await store.get_active_deployment() == deployment_id:
		raise ActiveDeploymentError(deployment_id)
	await store.register_deployment(
		deployment_id=deployment_id,
		service_name=service_name,
	)


async def promote_deployment(
	store: DeploymentStore,
	*,
	active_deployment_id: str,
	active_service_name: str,
	draining: list[DrainingDeployment],
) -> None:
	draining_deployment_ids: set[str] = set()
	for deployment in draining:
		if deployment.deployment_id == active_deployment_id:
			raise ValueError("active deployment cannot be draining")
		if deployment.deployment_id in draining_deployment_ids:
			raise ValueError("duplicate draining deployment")
		draining_deployment_ids.add(deployment.deployment_id)

	existing_deployments = await store.list_deployments()
	await store.set_active(
		deployment_id=active_deployment_id,
		service_name=active_service_name,
	)
	for deployment in draining:
		await store.mark_draining(
			deployment_id=deployment.deployment_id,
			service_name=deployment.service_name,
			now=deployment.drain_started_at,
		)
	for deployment in existing_deployments:
		if (
			deployment.deployment_id != active_deployment_id
			and deployment.deployment_id not in draining_deployment_ids
			and deployment.state != "draining"
		):
			await store.mark_draining(
				deployment_id=deployment.deployment_id,
				service_name=deployment.service_name,
			)


async def delete_deployment_state(
	store: DeploymentStore,
	*,
	deployment_id: str,
) -> None:
	await store.delete_inactive_deployment(deployment_id=deployment_id)


__all__ = [
	"DrainingDeployment",
	"delete_deployment_state",
	"deployment_store_from_env",
	"get_active_deployment",
	"promote_deployment",
	"register_deployment",
]
