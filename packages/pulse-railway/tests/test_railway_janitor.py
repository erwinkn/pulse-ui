from __future__ import annotations

import asyncio

import pulse_railway.janitor as janitor_module
import pytest
from pulse_railway.config import RailwayInternals, RailwayProject
from pulse_railway.constants import (
	DEPLOYMENT_STATE_DRAINING,
	PULSE_DEPLOYMENT_ID,
	PULSE_DEPLOYMENT_STATE,
	PULSE_DRAIN_STARTED_AT,
)
from pulse_railway.janitor import DeploymentSessionStatus, run_janitor
from pulse_railway.railway import ServiceRecord, TemplateRecord
from pulse_railway.store import MemoryDeploymentStore


class _FakeClient:
	def __init__(self, **_: object) -> None:
		self.deleted_service_ids: list[str] = []
		self.services = {
			"pulse-deploy1": ServiceRecord(id="svc-1", name="pulse-deploy1")
		}
		self.service_variables = {"svc-1": {PULSE_DEPLOYMENT_ID: "deploy1"}}

	async def __aenter__(self) -> "_FakeClient":
		return self

	async def __aexit__(self, *_: object) -> None:
		return None

	async def get_project_variables(
		self, *, project_id: str, environment_id: str
	) -> dict[str, str]:
		assert project_id == "project"
		assert environment_id == "env"
		return {}

	async def get_service_variables_for_deployment(
		self, *, project_id: str, environment_id: str, service_id: str
	) -> dict[str, str]:
		assert project_id == "project"
		assert environment_id == "env"
		return dict(self.service_variables.get(service_id, {}))

	async def upsert_variable(self, **kwargs: object) -> None:
		service_id = kwargs.get("service_id")
		assert isinstance(service_id, str)
		name = kwargs.get("name")
		value = kwargs.get("value")
		assert isinstance(name, str)
		assert isinstance(value, str)
		self.service_variables.setdefault(service_id, {})[name] = value

	async def find_service_by_name(
		self, *, project_id: str, environment_id: str, name: str
	) -> ServiceRecord | None:
		assert project_id == "project"
		assert environment_id == "env"
		return self.services.get(name)

	async def list_services(
		self, *, project_id: str, environment_id: str
	) -> list[ServiceRecord]:
		assert project_id == "project"
		assert environment_id == "env"
		return list(self.services.values())

	async def delete_service(self, *, service_id: str, environment_id: str) -> None:
		assert environment_id == "env"
		self.deleted_service_ids.append(service_id)


def _internals(**overrides: object) -> RailwayInternals:
	values = {
		"service_prefix": "pulse-",
		"internal_token": "secret-token",
		"redis_url": "redis://test",
	}
	values.update(overrides)
	return RailwayInternals(**values)


def _install_internals(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
	async def fake_resolve_project_internals(
		*_args: object, **_kwargs: object
	) -> RailwayInternals:
		return _internals(**overrides)

	monkeypatch.setattr(
		"pulse_railway.janitor.resolve_project_internals",
		fake_resolve_project_internals,
	)


@pytest.mark.asyncio
async def test_janitor_deletes_idle_draining_deployments(monkeypatch) -> None:
	store = MemoryDeploymentStore()
	await store.mark_active(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	await store.mark_draining(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	created_clients: list[_FakeClient] = []

	def fake_client(**_: object) -> _FakeClient:
		client = _FakeClient()
		client.service_variables["svc-1"].update(
			{
				PULSE_DEPLOYMENT_STATE: DEPLOYMENT_STATE_DRAINING,
				PULSE_DRAIN_STARTED_AT: "0",
			}
		)
		created_clients.append(client)
		return client

	monkeypatch.setattr("pulse_railway.janitor.RailwayGraphQLClient", fake_client)
	_install_internals(monkeypatch)

	async def fake_status(*args: object, **kwargs: object) -> DeploymentSessionStatus:
		return DeploymentSessionStatus(
			deployment_id="deploy1",
			connected_render_count=0,
			resumable_render_count=0,
			drainable=True,
		)

	monkeypatch.setattr(
		"pulse_railway.janitor._fetch_deployment_session_status", fake_status
	)

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
		store=store,
		now=120,
	)

	assert result.deleted_deployments == ["deploy1"]
	assert created_clients[0].deleted_service_ids == ["svc-1"]
	assert await store.list_draining_deployments() == []


@pytest.mark.asyncio
async def test_janitor_keeps_draining_deployments_with_live_websockets(
	monkeypatch,
) -> None:
	store = MemoryDeploymentStore()
	await store.mark_active(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	await store.mark_draining(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)

	def fake_client(**_: object) -> _FakeClient:
		client = _FakeClient()
		client.service_variables["svc-1"].update(
			{
				PULSE_DEPLOYMENT_STATE: DEPLOYMENT_STATE_DRAINING,
				PULSE_DRAIN_STARTED_AT: "0",
			}
		)
		return client

	monkeypatch.setattr("pulse_railway.janitor.RailwayGraphQLClient", fake_client)
	_install_internals(monkeypatch)

	async def fake_status(*args: object, **kwargs: object) -> DeploymentSessionStatus:
		return DeploymentSessionStatus(
			deployment_id="deploy1",
			connected_render_count=0,
			resumable_render_count=1,
			drainable=False,
		)

	monkeypatch.setattr(
		"pulse_railway.janitor._fetch_deployment_session_status", fake_status
	)

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
		store=store,
		now=120,
	)

	assert result.deleted_deployments == []
	assert result.skipped_deployments == ["deploy1"]


@pytest.mark.asyncio
async def test_janitor_force_deletes_when_max_drain_age_is_exceeded(
	monkeypatch,
) -> None:
	store = MemoryDeploymentStore()
	await store.mark_active(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	await store.mark_draining(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	await store.record_request(deployment_id="deploy1", now=119)

	created_clients: list[_FakeClient] = []

	def fake_client(**_: object) -> _FakeClient:
		client = _FakeClient()
		client.service_variables["svc-1"].update(
			{
				PULSE_DEPLOYMENT_STATE: DEPLOYMENT_STATE_DRAINING,
				PULSE_DRAIN_STARTED_AT: "0",
			}
		)
		created_clients.append(client)
		return client

	monkeypatch.setattr("pulse_railway.janitor.RailwayGraphQLClient", fake_client)
	_install_internals(monkeypatch)
	monkeypatch.setattr(
		"pulse_railway.janitor._fetch_deployment_session_status",
		pytest.fail,
	)

	result = await run_janitor(
		project=RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			service_name="pulse-router",
			service_prefix="pulse-",
			drain_grace_seconds=60,
			max_drain_age_seconds=60,
		),
		store=store,
		now=120,
	)

	assert result.deleted_deployments == ["deploy1"]
	assert result.force_deleted_deployments == ["deploy1"]
	assert created_clients[0].deleted_service_ids == ["svc-1"]
	assert await store.list_draining_deployments() == []


@pytest.mark.asyncio
async def test_janitor_signals_reload_before_delete(monkeypatch) -> None:
	store = MemoryDeploymentStore()
	await store.mark_active(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)
	await store.mark_draining(
		deployment_id="deploy1",
		service_name="pulse-deploy1",
		now=0,
	)

	created_clients: list[_FakeClient] = []

	def fake_client(**_: object) -> _FakeClient:
		client = _FakeClient()
		client.service_variables["svc-1"].update(
			{
				PULSE_DEPLOYMENT_STATE: DEPLOYMENT_STATE_DRAINING,
				PULSE_DRAIN_STARTED_AT: "0",
			}
		)
		created_clients.append(client)
		return client

	reload_calls: list[str] = []
	sleep_calls: list[float] = []

	async def fake_reload(*args: object, **kwargs: object) -> int:
		reload_calls.append(kwargs["service_name"])
		return 2

	async def fake_sleep(delay: float) -> None:
		sleep_calls.append(delay)

	monkeypatch.setattr("pulse_railway.janitor.RailwayGraphQLClient", fake_client)
	_install_internals(monkeypatch)
	monkeypatch.setattr("pulse_railway.janitor._signal_deployment_reload", fake_reload)
	monkeypatch.setattr("pulse_railway.janitor.asyncio.sleep", fake_sleep)

	async def fake_status(*args: object, **kwargs: object) -> DeploymentSessionStatus:
		return DeploymentSessionStatus(
			deployment_id="deploy1",
			connected_render_count=0,
			resumable_render_count=0,
			drainable=True,
		)

	monkeypatch.setattr(
		"pulse_railway.janitor._fetch_deployment_session_status", fake_status
	)

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
		store=store,
		now=120,
	)

	assert result.deleted_deployments == ["deploy1"]
	assert reload_calls == ["pulse-deploy1"]
	assert sleep_calls == [janitor_module.JANITOR_RELOAD_GRACE_SECONDS]
	assert created_clients[0].deleted_service_ids == ["svc-1"]


@pytest.mark.asyncio
async def test_janitor_lists_services_once_and_probes_concurrently(
	monkeypatch,
) -> None:
	store = MemoryDeploymentStore()
	deployment_ids = [
		f"deploy{index}"
		for index in range(janitor_module.JANITOR_STATUS_CONCURRENCY + 2)
	]
	for deployment_id in deployment_ids:
		service_name = f"pulse-{deployment_id}"
		await store.mark_active(
			deployment_id=deployment_id,
			service_name=service_name,
			now=0,
		)
		await store.mark_draining(
			deployment_id=deployment_id,
			service_name=service_name,
			now=0,
		)

	class _CountingClient(_FakeClient):
		def __init__(self, **kwargs: object) -> None:
			super().__init__(**kwargs)
			self.deleted_service_ids = []
			self.list_services_calls = 0
			self.find_service_by_name_calls = 0
			self.services = {
				f"pulse-{deployment_id}": ServiceRecord(
					id=f"svc-{deployment_id}",
					name=f"pulse-{deployment_id}",
				)
				for deployment_id in deployment_ids
			}
			self.service_variables = {
				f"svc-{deployment_id}": {
					PULSE_DEPLOYMENT_ID: deployment_id,
					PULSE_DEPLOYMENT_STATE: DEPLOYMENT_STATE_DRAINING,
					PULSE_DRAIN_STARTED_AT: "0",
				}
				for deployment_id in deployment_ids
			}

		async def list_services(
			self, *, project_id: str, environment_id: str
		) -> list[ServiceRecord]:
			assert project_id == "project"
			assert environment_id == "env"
			self.list_services_calls += 1
			return list(self.services.values())

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			self.find_service_by_name_calls += 1
			raise AssertionError(
				f"unexpected service scan for {name}; janitor should reuse list_services"
			)

	created_clients: list[_CountingClient] = []

	def fake_client(**_: object) -> _CountingClient:
		client = _CountingClient()
		created_clients.append(client)
		return client

	monkeypatch.setattr("pulse_railway.janitor.RailwayGraphQLClient", fake_client)
	_install_internals(monkeypatch)

	started = 0
	in_flight = 0
	max_in_flight = 0
	release = asyncio.Event()
	skipped_deployment = deployment_ids[-1]

	async def fake_status(*args: object, **kwargs: object) -> DeploymentSessionStatus:
		nonlocal started, in_flight, max_in_flight
		deployment_id = kwargs["deployment_id"]
		started += 1
		in_flight += 1
		max_in_flight = max(max_in_flight, in_flight)
		if started >= janitor_module.JANITOR_STATUS_CONCURRENCY:
			release.set()
		await release.wait()
		await asyncio.sleep(0)
		in_flight -= 1
		return DeploymentSessionStatus(
			deployment_id=deployment_id,
			connected_render_count=0,
			resumable_render_count=0,
			drainable=deployment_id != skipped_deployment,
		)

	monkeypatch.setattr(
		"pulse_railway.janitor._fetch_deployment_session_status", fake_status
	)

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
		store=store,
		now=120,
	)

	assert result.deleted_deployments == deployment_ids[:-1]
	assert result.skipped_deployments == [skipped_deployment]
	assert created_clients[0].list_services_calls == 1
	assert created_clients[0].find_service_by_name_calls == 0
	assert max_in_flight == janitor_module.JANITOR_STATUS_CONCURRENCY
	remaining = await store.list_draining_deployments()
	assert [deployment.deployment_id for deployment in remaining] == [
		skipped_deployment
	]


@pytest.mark.asyncio
async def test_janitor_resolves_project_redis_when_url_missing(monkeypatch) -> None:
	class _FakeRedisStore(MemoryDeploymentStore):
		def __init__(self) -> None:
			super().__init__()
			self.closed = False

		async def close(self) -> None:
			self.closed = True

	fake_store = _FakeRedisStore()
	store_urls: list[str] = []
	service_state = {
		"pulse-router-redis": ServiceRecord(
			id="svc-redis",
			name="pulse-router-redis",
		)
	}

	class _RedisClient(_FakeClient):
		def __init__(self, **kwargs: object) -> None:
			super().__init__(**kwargs)
			self.services = dict(service_state)
			self.service_variables = {"svc-redis": {}}

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
			}

		async def find_service_by_name(
			self, *, project_id: str, environment_id: str, name: str
		) -> ServiceRecord | None:
			assert project_id == "project"
			assert environment_id == "env"
			return service_state.get(name)

	monkeypatch.setattr("pulse_railway.janitor.RailwayGraphQLClient", _RedisClient)
	monkeypatch.setattr(
		"pulse_railway.janitor.RedisDeploymentStore.from_url",
		lambda **kwargs: store_urls.append(kwargs["url"]) or fake_store,
	)

	async def fake_internal_token(*args: object, **kwargs: object) -> str:
		return "secret-token"

	monkeypatch.setattr(
		"pulse_railway.deployment.resolve_or_create_internal_token",
		fake_internal_token,
	)

	project = RailwayProject(
		project_id="project",
		environment_id="env",
		token="token",
		service_name="pulse-router",
		service_prefix="pulse-",
		redis_service_name="pulse-router-redis",
	)
	result = await run_janitor(
		project=project,
		now=120,
	)

	assert result.lock_acquired is True
	assert fake_store.closed is True
	assert store_urls == ["redis://pulse-router-redis.railway.internal:6379"]
	assert project.redis_url is None
