from __future__ import annotations

import pytest
from pulse_railway.constants import PULSE_DEPLOYMENT_ID, PULSE_KV_KIND, PULSE_KV_URL
from pulse_railway.railway import RailwayResolver, ServiceRecord
from pulse_railway.store import (
	ActiveDeploymentError,
	DeploymentStore,
	MemoryStore,
	RedisDeploymentStore,
	RedisStore,
	kv_store_spec_from_env,
)


@pytest.mark.asyncio
async def test_resolver_skips_service_refresh_when_active_deployment_is_unchanged(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	now = 100.0
	monkeypatch.setattr("pulse_railway.railway.client.time.monotonic", lambda: now)

	class _FakeClient:
		def __init__(self) -> None:
			self.service_calls = 0

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

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			if service_id == "svc-1":
				return {PULSE_DEPLOYMENT_ID: "v1"}
			if service_id == "svc-2":
				return {PULSE_DEPLOYMENT_ID: "v2"}
			return {}

	client = _FakeClient()
	store = DeploymentStore(MemoryStore())
	await store.set_active(deployment_id="v1", service_name="pulse-v1")
	resolver = RailwayResolver(
		client=client,
		project_id="project",
		environment_id="env",
		service_prefix="pulse",
		store=store,
		cache_ttl_seconds=5.0,
	)

	first = await resolver.resolve_active()
	second = await resolver.resolve_active()

	assert first is not None
	assert first.deployment_id == "v1"
	assert second is not None
	assert second.deployment_id == "v1"
	assert client.service_calls == 0

	now = 106.0
	third = await resolver.resolve_active()

	assert third is not None
	assert third.deployment_id == "v1"
	assert client.service_calls == 0

	now = 112.0
	await store.set_active(deployment_id="v2", service_name="pulse-v2")
	fourth = await resolver.resolve_active()

	assert fourth is not None
	assert fourth.deployment_id == "v2"
	assert client.service_calls == 0


@pytest.mark.asyncio
async def test_resolver_only_routes_registered_deployments() -> None:
	class _FakeClient:
		def __init__(self) -> None:
			self.service_calls = 0

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			assert project_id == "project"
			assert environment_id == "env"
			self.service_calls += 1
			return [
				ServiceRecord(id="svc-router", name="pulse-router"),
				ServiceRecord(id="svc-backend", name="pulse-v1"),
			]

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			if service_id == "svc-backend":
				return {PULSE_DEPLOYMENT_ID: "v1"}
			return {}

	client = _FakeClient()
	store = DeploymentStore(MemoryStore())
	await store.register_deployment(deployment_id="v1", service_name="pulse-v1")
	resolver = RailwayResolver(
		client=client,
		project_id="project",
		environment_id="env",
		service_prefix="pulse",
		store=store,
		cache_ttl_seconds=5.0,
	)

	assert await resolver.resolve("router") is None
	target = await resolver.resolve("v1")

	assert target is not None
	assert target.deployment_id == "v1"
	assert client.service_calls == 0


@pytest.mark.asyncio
async def test_resolver_does_not_discover_unregistered_services() -> None:
	class _FakeClient:
		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			raise AssertionError("router must not use Railway GraphQL discovery")

	resolver = RailwayResolver(
		client=_FakeClient(),  # pyright: ignore[reportArgumentType]
		project_id="project",
		environment_id="env",
		service_prefix="pulse",
		store=DeploymentStore(MemoryStore()),
		cache_ttl_seconds=5.0,
	)

	assert await resolver.resolve("v1") is None


@pytest.mark.asyncio
async def test_deployment_store_uses_kv_for_deployments() -> None:
	store = DeploymentStore(MemoryStore())

	await store.set_active(
		deployment_id="v1",
		service_name="pulse-v1",
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
	assert draining[0].drain_started_at == 12.0

	await store.set_active(
		deployment_id="v2",
		service_name="pulse-v2",
	)
	await store.delete_inactive_deployment(deployment_id="v1")
	assert await store.list_draining_deployments() == []
	deployments = await store.list_deployments()
	assert [deployment.deployment_id for deployment in deployments] == ["v2"]


@pytest.mark.asyncio
async def test_deployment_store_rejects_deleting_active_deployment() -> None:
	store = DeploymentStore(MemoryStore())

	await store.set_active(
		deployment_id="v1",
		service_name="pulse-v1",
	)

	with pytest.raises(ActiveDeploymentError):
		await store.delete_inactive_deployment(deployment_id="v1")

	assert await store.get_active_deployment() == "v1"
	assert await store.get_deployment(deployment_id="v1") is not None


@pytest.mark.asyncio
async def test_deployment_store_registers_pending_deployment() -> None:
	store = DeploymentStore(MemoryStore())

	await store.register_deployment(deployment_id="v2", service_name="pulse-v2")

	deployment = await store.get_deployment("v2")
	assert deployment is not None
	assert deployment.deployment_id == "v2"
	assert deployment.state == "pending"
	assert deployment.service_name == "pulse-v2"
	assert deployment.drain_started_at is None
	assert await store.get_active_deployment() is None


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

	await store.set_active(
		deployment_id="v1",
		service_name="pulse-v1",
	)
	await store.set_active(
		deployment_id="v2",
		service_name="pulse-v2",
	)
	await store.set_active(
		deployment_id="v3",
		service_name="pulse-v3",
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
		(deployment.deployment_id, deployment.drain_started_at)
		for deployment in draining
	} == {
		("v1", 14.0),
		("v3", 15.0),
	}
	assert client.data["pulse:railway:deployment:v1"].startswith("{")


def test_kv_store_spec_round_trip_from_env() -> None:
	spec = kv_store_spec_from_env(
		{
			PULSE_KV_KIND: "redis",
			PULSE_KV_URL: "redis://localhost:6379/0",
		}
	)
	assert isinstance(spec, RedisStore)
	assert spec.url == "redis://localhost:6379/0"
