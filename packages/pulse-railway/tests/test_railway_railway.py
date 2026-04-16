from __future__ import annotations

import asyncio

import httpx
import pytest
from pulse_railway.railway import RailwayGraphQLClient


@pytest.mark.asyncio
async def test_update_service_instance_includes_cron_schedule(monkeypatch) -> None:
	calls: list[tuple[str, dict[str, object] | None]] = []

	async def fake_graphql(
		self: RailwayGraphQLClient,
		query: str,
		variables: dict[str, object] | None = None,
	) -> object:
		calls.append((query, variables))
		return {}

	monkeypatch.setattr(RailwayGraphQLClient, "graphql", fake_graphql)
	client = RailwayGraphQLClient(token="token")
	try:
		await client.update_service_instance(
			service_id="svc-1",
			environment_id="env",
			source_image="image:latest",
			num_replicas=1,
			start_command="pulse-railway janitor run",
			cron_schedule="*/5 * * * *",
			restart_policy_type="NEVER",
		)
	finally:
		await client.aclose()

	assert len(calls) == 1
	query, variables = calls[0]
	assert "serviceInstanceUpdate" in query
	assert variables is not None
	assert variables["serviceId"] == "svc-1"
	assert variables["environmentId"] == "env"
	assert variables["input"] == {
		"source": {"image": "image:latest"},
		"numReplicas": 1,
		"startCommand": "pulse-railway janitor run",
		"cronSchedule": "*/5 * * * *",
		"restartPolicyType": "NEVER",
	}


def test_graphql_client_uses_longer_read_timeout() -> None:
	client = RailwayGraphQLClient(token="token")
	try:
		timeout = client._client.timeout
		assert isinstance(timeout, httpx.Timeout)
		assert timeout.connect == 30.0
		assert timeout.read == 120.0
		assert timeout.write == 120.0
		assert timeout.pool == 120.0
	finally:
		asyncio.run(client.aclose())


@pytest.mark.asyncio
async def test_graphql_client_auto_detects_project_token_auth() -> None:
	request_headers: list[httpx.Headers] = []

	def handler(request: httpx.Request) -> httpx.Response:
		request_headers.append(request.headers)
		payload = request.read().decode()
		if "projectToken" in payload:
			assert request.headers["Project-Access-Token"] == "token"
			return httpx.Response(
				200,
				json={"data": {"projectToken": {"projectId": "project"}}},
			)
		assert request.headers["Project-Access-Token"] == "token"
		return httpx.Response(200, json={"data": {"variables": []}})

	client = RailwayGraphQLClient(token="token")
	client._client = httpx.AsyncClient(
		base_url=client.endpoint,
		headers={"Content-Type": "application/json"},
		transport=httpx.MockTransport(handler),
		timeout=client._client.timeout,
	)
	try:
		result = await client.get_project_variables(
			project_id="project",
			environment_id="env",
		)
	finally:
		await client.aclose()

	assert result == {}
	assert len(request_headers) == 2


@pytest.mark.asyncio
async def test_graphql_client_falls_back_to_bearer_auth() -> None:
	request_headers: list[httpx.Headers] = []

	def handler(request: httpx.Request) -> httpx.Response:
		request_headers.append(request.headers)
		payload = request.read().decode()
		if "projectToken" in payload:
			assert request.headers["Project-Access-Token"] == "token"
			return httpx.Response(403, json={"errors": [{"message": "forbidden"}]})
		assert request.headers["Authorization"] == "Bearer token"
		return httpx.Response(200, json={"data": {"variables": []}})

	client = RailwayGraphQLClient(token="token")
	client._client = httpx.AsyncClient(
		base_url=client.endpoint,
		headers={"Content-Type": "application/json"},
		transport=httpx.MockTransport(handler),
		timeout=client._client.timeout,
	)
	try:
		result = await client.get_project_variables(
			project_id="project",
			environment_id="env",
		)
	finally:
		await client.aclose()

	assert result == {}
	assert len(request_headers) == 2


@pytest.mark.asyncio
async def test_create_project_uses_bearer_auth() -> None:
	request_headers: list[httpx.Headers] = []

	def handler(request: httpx.Request) -> httpx.Response:
		request_headers.append(request.headers)
		assert request.headers["Authorization"] == "Bearer token"
		return httpx.Response(200, json={"data": {"projectCreate": {"id": "project"}}})

	client = RailwayGraphQLClient(token="token")
	client._client = httpx.AsyncClient(
		base_url=client.endpoint,
		headers={"Content-Type": "application/json"},
		transport=httpx.MockTransport(handler),
		timeout=client._client.timeout,
	)
	try:
		project_id = await client.create_project(name="pulse", workspace_id="workspace")
	finally:
		await client.aclose()

	assert project_id == "project"
	assert len(request_headers) == 1
