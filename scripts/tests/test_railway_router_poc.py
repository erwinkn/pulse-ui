from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from aiohttp import web
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response

from scripts.railway_router_poc.deploy import deploy_backend
from scripts.railway_router_poc.railway import (
	ACTIVE_DEPLOYMENT_VARIABLE,
	RailwayGraphQLClient,
	RailwayResolver,
	service_name_for_deployment,
	validate_deployment_id,
)
from scripts.railway_router_poc.router import StaticResolver, build_app


@pytest_asyncio.fixture
async def backend_servers(
	unused_tcp_port_factory: callable,
) -> AsyncIterator[dict[str, str]]:
	runners: list[web.AppRunner] = []
	urls: dict[str, str] = {}

	async def start_backend(name: str) -> None:
		app = web.Application()

		async def root(_: web.Request) -> web.Response:
			return web.json_response({"deployment": name})

		async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
			ws = web.WebSocketResponse()
			await ws.prepare(request)
			async for message in ws:
				if message.type == web.WSMsgType.TEXT:
					await ws.send_str(
						json.dumps({"deployment": name, "message": message.data})
					)
			return ws

		app.router.add_get("/", root)
		app.router.add_get("/ws", websocket_handler)
		runner = web.AppRunner(app)
		await runner.setup()
		port = unused_tcp_port_factory()
		site = web.TCPSite(runner, "127.0.0.1", port)
		await site.start()
		runners.append(runner)
		urls[name] = f"http://127.0.0.1:{port}"

	await start_backend("v1")
	await start_backend("v2")
	try:
		yield urls
	finally:
		for runner in runners:
			await runner.cleanup()


@pytest.mark.asyncio
async def test_router_uses_active_backend(backend_servers: dict[str, str]) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.get("/")
	await app.state.router.close()

	assert response.status_code == 200
	assert response.json() == {"deployment": "v2"}
	assert response.headers["x-poc-selected-deployment"] == "v2"


@pytest.mark.asyncio
async def test_router_prefers_query_param(backend_servers: dict[str, str]) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.get("/", params={"pulse_deployment": "v1"})
	await app.state.router.close()

	assert response.status_code == 200
	assert response.json() == {"deployment": "v1"}
	assert response.headers["x-poc-selected-deployment"] == "v1"


@pytest.mark.asyncio
async def test_router_prefers_header(backend_servers: dict[str, str]) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.get("/", headers={"x-pulse-deployment": "v1"})
	await app.state.router.close()

	assert response.status_code == 200
	assert response.json() == {"deployment": "v1"}


@pytest.mark.asyncio
async def test_router_returns_404_for_unknown_backend(
	backend_servers: dict[str, str],
) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.get("/", params={"pulse_deployment": "missing"})
	await app.state.router.close()

	assert response.status_code == 404


def test_deployment_id_validation() -> None:
	assert validate_deployment_id("V1") == "v1"
	assert service_name_for_deployment("poc-", "v1") == "poc-v1"
	with pytest.raises(ValueError):
		validate_deployment_id("bad_id")


@pytest.mark.asyncio
async def test_railway_resolver_uses_active_variable() -> None:
	def handler(request: Request) -> Response:
		payload = json.loads(request.content.decode())
		query = payload["query"]
		if "variables(projectId" in query:
			return Response(
				200,
				json={"data": {"variables": {ACTIVE_DEPLOYMENT_VARIABLE: "v2"}}},
			)
		if "project(id:" in query:
			return Response(
				200,
				json={
					"data": {
						"project": {
							"services": {
								"edges": [
									{"node": {"id": "1", "name": "poc-v1"}},
									{"node": {"id": "2", "name": "poc-v2"}},
								]
							}
						}
					}
				},
			)
		raise AssertionError(query)

	client = RailwayGraphQLClient(token="token")
	client._client = AsyncClient(transport=MockTransport(handler), base_url="https://x")
	resolver = RailwayResolver(
		client=client,
		project_id="project",
		environment_id="env",
		service_prefix="poc-",
		backend_port=80,
	)
	target = await resolver.resolve_active()
	assert target is not None
	assert target.deployment_id == "v2"
	assert target.base_url == "http://poc-v2.railway.internal:80"
	await client.aclose()


@pytest.mark.asyncio
async def test_deploy_backend_happy_path() -> None:
	def handler(request: Request) -> Response:
		payload = json.loads(request.content.decode())
		query = payload["query"]
		if "serviceCreate" in query:
			return Response(200, json={"data": {"serviceCreate": {"id": "service-1"}}})
		if "serviceInstanceUpdate" in query:
			return Response(200, json={"data": {"serviceInstanceUpdate": True}})
		if "serviceInstanceDeployV2" in query:
			return Response(200, json={"data": {"serviceInstanceDeployV2": "deploy-1"}})
		if "deployment(id:" in query:
			return Response(
				200,
				json={
					"data": {
						"deployment": {
							"id": "deploy-1",
							"status": "SUCCESS",
							"createdAt": "2026-01-01T00:00:00Z",
							"staticUrl": None,
						}
					}
				},
			)
		if "serviceDomainCreate" in query:
			return Response(
				200,
				json={
					"data": {"serviceDomainCreate": {"domain": "poc-v1.up.railway.app"}}
				},
			)
		if "variableUpsert" in query:
			return Response(200, json={"data": {"variableUpsert": True}})
		raise AssertionError(query)

	client = RailwayGraphQLClient(token="token")
	client._client = AsyncClient(transport=MockTransport(handler), base_url="https://x")

	class _FakeClient(RailwayGraphQLClient):
		def __init__(self, **_: object) -> None:
			self._wrapped = client

		async def __aenter__(self) -> RailwayGraphQLClient:
			return self._wrapped

		async def __aexit__(self, *_: object) -> None:
			return None

	monkeypatch = pytest.MonkeyPatch()
	monkeypatch.setattr(
		"scripts.railway_router_poc.deploy.RailwayGraphQLClient",
		_FakeClient,
	)
	try:
		result = await deploy_backend(
			token="token",
			project_id="project",
			environment_id="env",
			service_prefix="poc-",
			deployment_id="v1",
			image="traefik/whoami:v1.10",
			backend_port=80,
			num_replicas=1,
			activate=True,
			expose_domain=True,
		)
	finally:
		monkeypatch.undo()
		await client.aclose()

	assert result.service_name == "poc-v1"
	assert result.public_domain == "poc-v1.up.railway.app"
	assert result.status == "SUCCESS"
