from __future__ import annotations

import pulse_railway.store as store_module
import pytest
from pulse_railway.constants import ACTIVE_DEPLOYMENT_VARIABLE
from pulse_railway.railway import RailwayResolver, ServiceRecord
from pulse_railway.store import RedisDeploymentStore


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
async def test_redis_store_batches_draining_hash_fetches(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(store_module, "redis", object())

	class _FakePipeline:
		def __init__(self, client: "_FakeRedisClient") -> None:
			self.client = client
			self.keys: list[str] = []

		def hgetall(self, key: str) -> None:
			self.keys.append(key)

		async def execute(self) -> list[dict[str, str]]:
			self.client.pipeline_execute_calls += 1
			self.client.pipeline_keys = list(self.keys)
			return [dict(self.client.records[key]) for key in self.keys]

	class _FakeRedisClient:
		def __init__(self) -> None:
			self.records = {
				"pulse:railway:deployment:v1": {
					"state": "draining",
					"service_name": "pulse-v1",
					"last_seen_at": "10.0",
					"drain_started_at": "9.0",
				},
				"pulse:railway:deployment:v2": {
					"state": "active",
					"service_name": "pulse-v2",
					"last_seen_at": "11.0",
				},
				"pulse:railway:deployment:v3": {
					"state": "draining",
					"service_name": "pulse-v3",
					"last_seen_at": "12.0",
					"drain_started_at": "8.0",
				},
			}
			self.pipeline_execute_calls = 0
			self.pipeline_keys: list[str] = []
			self.serial_hgetall_calls = 0

		async def smembers(self, key: str) -> set[str]:
			assert key == "pulse:railway:deployments"
			return {"v1", "v2", "v3"}

		def pipeline(self) -> _FakePipeline:
			return _FakePipeline(self)

		async def hgetall(self, key: str) -> dict[str, str]:
			self.serial_hgetall_calls += 1
			return dict(self.records[key])

	client = _FakeRedisClient()
	store = RedisDeploymentStore(client=client)

	draining = await store.list_draining_deployments()

	assert {deployment.deployment_id for deployment in draining} == {"v1", "v3"}
	assert client.pipeline_execute_calls == 1
	assert set(client.pipeline_keys) == {
		"pulse:railway:deployment:v1",
		"pulse:railway:deployment:v2",
		"pulse:railway:deployment:v3",
	}
	assert client.serial_hgetall_calls == 0
	assert {
		(deployment.deployment_id, deployment.last_seen_at, deployment.drain_started_at)
		for deployment in draining
	} == {
		("v1", 10.0, 9.0),
		("v3", 12.0, 8.0),
	}
