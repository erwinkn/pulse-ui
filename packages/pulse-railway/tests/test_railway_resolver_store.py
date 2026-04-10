from __future__ import annotations

import pytest
from pulse_railway.constants import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	PULSE_KV_KIND,
	PULSE_KV_URL,
)
from pulse_railway.railway import RailwayResolver, ServiceRecord
from pulse_railway.store import (
	DeploymentStore,
	InMemoryKVStore,
	RedisDeploymentStore,
	RedisKVStore,
	kv_store_spec_from_env,
)


@pytest.mark.asyncio
async def test_resolver_skips_service_refresh_when_active_deployment_is_unchanged(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	now = 100.0
	monkeypatch.setattr("pulse_railway.railway.time.monotonic", lambda: now)

	class _FakeClient:
		def __init__(self) -> None:
			self.variable_calls = 0
			self.service_calls = 0
			self.active_deployment = "v1"

		async def get_project_variables(
			self,
			*,
			project_id: str,
			environment_id: str,
			service_id: str | None = None,
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			assert service_id is None
			self.variable_calls += 1
			return {ACTIVE_DEPLOYMENT_VARIABLE: self.active_deployment}

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			assert project_id == "project"
			assert environment_id == "env"
			self.service_calls += 1
			return [
				ServiceRecord(id="svc-1", name="pulse-v1"),
				ServiceRecord(id="svc-2", name="pulse-v2"),
			]

	client = _FakeClient()
	resolver = RailwayResolver(
		client=client,
		project_id="project",
		environment_id="env",
		service_prefix="pulse",
		cache_ttl_seconds=5.0,
	)

	first = await resolver.resolve_active()
	second = await resolver.resolve_active()

	assert first is not None
	assert first.deployment_id == "v1"
	assert second is not None
	assert second.deployment_id == "v1"
	assert client.variable_calls == 1
	assert client.service_calls == 1

	now = 106.0
	third = await resolver.resolve_active()

	assert third is not None
	assert third.deployment_id == "v1"
	assert client.variable_calls == 2
	assert client.service_calls == 1

	now = 112.0
	client.active_deployment = "v2"
	fourth = await resolver.resolve_active()

	assert fourth is not None
	assert fourth.deployment_id == "v2"
	assert client.variable_calls == 3
	assert client.service_calls == 2


@pytest.mark.asyncio
async def test_deployment_store_uses_kv_for_deployments_and_leases() -> None:
	store = DeploymentStore(InMemoryKVStore())

	await store.mark_active(
		deployment_id="v1",
		service_name="pulse-v1",
		now=10.0,
	)
	lease_id = await store.create_websocket_lease(
		deployment_id="v1",
		service_name="pulse-v1",
		now=11.0,
	)
	await store.mark_draining(
		deployment_id="v1",
		service_name="pulse-v1",
		now=12.0,
	)

	draining = await store.list_draining_deployments()

	assert len(draining) == 1
	assert draining[0].deployment_id == "v1"
	assert draining[0].state == "draining"
	assert draining[0].service_name == "pulse-v1"
	assert draining[0].last_seen_at == 11.0
	assert draining[0].drain_started_at == 12.0
	assert await store.count_websocket_leases(deployment_id="v1") == 1

	await store.remove_websocket_lease(
		deployment_id="v1",
		lease_id=lease_id,
		now=13.0,
	)
	assert await store.count_websocket_leases(deployment_id="v1") == 0

	await store.clear_deployment(deployment_id="v1")
	assert await store.list_draining_deployments() == []


@pytest.mark.asyncio
async def test_redis_store_batches_draining_deployment_fetches() -> None:
	class _FakeRedisClient:
		def __init__(self) -> None:
			self.data: dict[str, str] = {}
			self.aclose_called = False

		async def get(self, key: str) -> str | None:
			return self.data.get(key)

		async def set(
			self,
			key: str,
			value: str,
			*,
			ex: int | None = None,
			nx: bool = False,
		) -> bool:
			if nx and key in self.data:
				return False
			_ = ex
			self.data[key] = value
			return True

		async def delete(self, key: str) -> None:
			self.data.pop(key, None)

		async def scan_iter(self, match: str):
			prefix = match[:-1] if match.endswith("*") else match
			for key in sorted(self.data):
				if key.startswith(prefix):
					yield key

		async def aclose(self) -> None:
			self.aclose_called = True

	client = _FakeRedisClient()
	store = RedisDeploymentStore(client=client)

	await store.mark_active(
		deployment_id="v1",
		service_name="pulse-v1",
		now=10.0,
	)
	await store.mark_active(
		deployment_id="v2",
		service_name="pulse-v2",
		now=11.0,
	)
	await store.record_request(
		deployment_id="v1",
		service_name="pulse-v1",
		now=12.0,
	)
	await store.mark_active(
		deployment_id="v3",
		service_name="pulse-v3",
		now=13.0,
	)
	await store.mark_draining(
		deployment_id="v1",
		service_name="pulse-v1",
		now=14.0,
	)
	await store.mark_draining(
		deployment_id="v3",
		service_name="pulse-v3",
		now=15.0,
	)

	draining = await store.list_draining_deployments()

	assert {deployment.deployment_id for deployment in draining} == {"v1", "v3"}
	assert {
		(deployment.deployment_id, deployment.last_seen_at, deployment.drain_started_at)
		for deployment in draining
	} == {
		("v1", 12.0, 14.0),
		("v3", 13.0, 15.0),
	}
	assert client.data["pulse:railway:deployment:v1"].startswith("{")


def test_kv_store_spec_round_trip_from_env() -> None:
	spec = kv_store_spec_from_env(
		{
			PULSE_KV_KIND: "redis",
			PULSE_KV_URL: "redis://localhost:6379/0",
		}
	)
	assert isinstance(spec, RedisKVStore)
	assert spec.url == "redis://localhost:6379/0"
