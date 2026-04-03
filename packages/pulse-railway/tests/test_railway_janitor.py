from __future__ import annotations

import pytest
from pulse_railway.config import RailwayProject
from pulse_railway.janitor import run_janitor
from pulse_railway.railway import ServiceRecord, TemplateRecord
from pulse_railway.tracker import MemoryDeploymentTracker


class _FakeClient:
	def __init__(self, **_: object) -> None:
		self.deleted_service_ids: list[str] = []
		self.services = {
			"pulse-deploy1": ServiceRecord(id="svc-1", name="pulse-deploy1")
		}

	async def __aenter__(self) -> "_FakeClient":
		return self

	async def __aexit__(self, *_: object) -> None:
		return None

	async def find_service_by_name(
		self, *, project_id: str, environment_id: str, name: str
	) -> ServiceRecord | None:
		assert project_id == "project"
		assert environment_id == "env"
		return self.services.get(name)

	async def delete_service(self, *, service_id: str, environment_id: str) -> None:
		assert environment_id == "env"
		self.deleted_service_ids.append(service_id)


@pytest.mark.asyncio
async def test_janitor_deletes_idle_draining_deployments(monkeypatch) -> None:
	tracker = MemoryDeploymentTracker()
	await tracker.mark_active(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	await tracker.mark_draining(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	created_clients: list[_FakeClient] = []

	def fake_client(**_: object) -> _FakeClient:
		client = _FakeClient()
		created_clients.append(client)
		return client

	monkeypatch.setattr("pulse_railway.janitor.RailwayGraphQLClient", fake_client)

	result = await run_janitor(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			service_prefix="pulse-",
			drain_grace_seconds=60,
			max_drain_age_seconds=600,
		),
		tracker=tracker,
		now=120,
	)

	assert result.deleted_deployments == ["deploy1"]
	assert created_clients[0].deleted_service_ids == ["svc-1"]
	assert await tracker.list_draining_deployments() == []


@pytest.mark.asyncio
async def test_janitor_keeps_draining_deployments_with_live_websockets(
	monkeypatch,
) -> None:
	tracker = MemoryDeploymentTracker()
	await tracker.mark_active(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	await tracker.mark_draining(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	await tracker.create_websocket_lease(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)

	def fake_client(**_: object) -> _FakeClient:
		return _FakeClient()

	monkeypatch.setattr("pulse_railway.janitor.RailwayGraphQLClient", fake_client)

	result = await run_janitor(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			service_prefix="pulse-",
			drain_grace_seconds=60,
			max_drain_age_seconds=600,
		),
		tracker=tracker,
		now=120,
	)

	assert result.deleted_deployments == []
	assert result.skipped_deployments == ["deploy1"]


@pytest.mark.asyncio
async def test_janitor_resolves_project_redis_when_url_missing(monkeypatch) -> None:
	class _FakeRedisTracker(MemoryDeploymentTracker):
		def __init__(self) -> None:
			super().__init__()
			self.closed = False

		async def close(self) -> None:
			self.closed = True

	fake_tracker = _FakeRedisTracker()
	tracker_urls: list[str] = []
	service_state = {
		"pulse-router-redis": ServiceRecord(
			id="svc-redis",
			name="pulse-router-redis",
		)
	}

	class _RedisClient(_FakeClient):
		async def get_template_by_code(self, *, code: str) -> TemplateRecord:
			assert code == "redis"
			return TemplateRecord(
				id="template-1",
				code="redis",
				serialized_config={"services": {"template-service": {"name": "Redis"}}},
			)

		async def deploy_template(self, **_: object) -> str:
			return "workflow-1"

		async def get_service_variables_for_deployment(
			self, *, project_id: str, environment_id: str, service_id: str
		) -> dict[str, str]:
			assert project_id == "project"
			assert environment_id == "env"
			assert service_id == "svc-redis"
			return {
				"REDIS_URL": "redis://pulse-router-redis.railway.internal:6379",
				"REDIS_PUBLIC_URL": "redis://public-host:6379",
			}

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			assert project_id == "project"
			assert environment_id == "env"
			return service_state.get(name)

	monkeypatch.setattr("pulse_railway.janitor.RailwayGraphQLClient", _RedisClient)
	monkeypatch.setattr(
		"pulse_railway.janitor.RedisDeploymentTracker.from_url",
		lambda **kwargs: tracker_urls.append(kwargs["url"]) or fake_tracker,
	)

	result = await run_janitor(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			service_prefix="pulse-",
			redis_service_name="pulse-router-redis",
		),
		now=120,
	)

	assert result.lock_acquired is True
	assert fake_tracker.closed is True
	assert tracker_urls == ["redis://public-host:6379"]
