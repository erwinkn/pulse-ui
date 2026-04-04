from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
import socketio
import uvicorn
from aiohttp import web
from httpx import ASGITransport, AsyncClient
from pulse_railway.constants import INTERNAL_STORE_SYNC_PATH, INTERNAL_TOKEN_HEADER
from pulse_railway.router import StaticResolver, build_app
from pulse_railway.store import MemoryDeploymentStore


@pytest_asyncio.fixture
async def backend_servers(
	unused_tcp_port_factory: Callable[[], int],
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
	assert response.headers["x-pulse-selected-deployment"] == "v2"


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
	assert response.headers["x-pulse-selected-deployment"] == "v1"


@pytest.mark.asyncio
async def test_router_blocks_internal_paths(backend_servers: dict[str, str]) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.get("/_pulse/internal/railway/sessions")
	await app.state.router.close()

	assert response.status_code == 404


@pytest.mark.asyncio
async def test_router_syncs_store_via_internal_endpoint(
	backend_servers: dict[str, str],
) -> None:
	store = MemoryDeploymentStore()
	app = build_app(
		StaticResolver(backends=backend_servers, active_deployment="v2"),
		store=store,
		internal_token="secret-token",
	)
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.post(
			INTERNAL_STORE_SYNC_PATH,
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
			json={
				"active": {
					"deployment_id": "v2",
					"service_name": "pulse-v2",
				},
				"draining": [
					{
						"deployment_id": "v1",
						"service_name": "pulse-v1",
					}
				],
			},
		)
	await app.state.router.close()

	assert response.status_code == 200
	assert response.json() == {
		"ok": True,
		"active_deployment_id": "v2",
		"draining_count": 1,
	}
	draining = await store.list_draining_deployments()
	assert [deployment.deployment_id for deployment in draining] == ["v1"]


@pytest.mark.asyncio
async def test_router_rejects_store_sync_without_valid_token(
	backend_servers: dict[str, str],
) -> None:
	app = build_app(
		StaticResolver(backends=backend_servers, active_deployment="v2"),
		store=MemoryDeploymentStore(),
		internal_token="secret-token",
	)
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.post(
			INTERNAL_STORE_SYNC_PATH,
			headers={INTERNAL_TOKEN_HEADER: "wrong-token"},
			json={
				"active": {
					"deployment_id": "v2",
					"service_name": "pulse-v2",
				}
			},
		)
	await app.state.router.close()

	assert response.status_code == 403


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


@pytest.mark.asyncio
async def test_router_records_http_activity(backend_servers: dict[str, str]) -> None:
	store = MemoryDeploymentStore()
	app = build_app(
		StaticResolver(backends=backend_servers, active_deployment="v2"),
		store=store,
	)
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.get("/")
	await app.state.router.close()

	assert response.status_code == 200
	assert await store.list_draining_deployments() == []


@pytest.mark.asyncio
async def test_router_forces_identity_encoding(
	unused_tcp_port_factory: Callable[[], int],
) -> None:
	app_backend = web.Application()

	async def root(request: web.Request) -> web.Response:
		return web.json_response(
			{"accept_encoding": request.headers.get("accept-encoding")}
		)

	app_backend.router.add_get("/", root)
	runner = web.AppRunner(app_backend)
	await runner.setup()
	port = unused_tcp_port_factory()
	site = web.TCPSite(runner, "127.0.0.1", port)
	await site.start()
	try:
		app = build_app(
			StaticResolver(
				backends={"v1": f"http://127.0.0.1:{port}"},
				active_deployment="v1",
			)
		)
		async with AsyncClient(
			transport=ASGITransport(app=app),
			base_url="http://testserver",
		) as client:
			response = await client.get("/", headers={"accept-encoding": "br, gzip"})
		await app.state.router.close()
		assert response.status_code == 200
		assert response.json() == {"accept_encoding": "identity"}
	finally:
		await runner.cleanup()


@pytest.mark.asyncio
async def test_router_proxies_socketio_websocket_without_store(
	unused_tcp_port_factory: Callable[[], int],
) -> None:
	sio = socketio.AsyncServer(
		async_mode="aiohttp",
		cors_allowed_origins="*",
		reconnection=False,
	)
	backend = web.Application()
	sio.attach(backend)
	backend_port = unused_tcp_port_factory()
	router_port = unused_tcp_port_factory()
	received: dict[str, str | None] = {}

	@sio.event
	async def connect(sid: str, environ: dict[str, str], auth: dict[str, str]) -> None:
		received["sid"] = sid
		received["cookie"] = environ.get("HTTP_COOKIE")
		received["render_id"] = auth.get("render_id")

	backend_runner = web.AppRunner(backend)
	await backend_runner.setup()
	backend_site = web.TCPSite(backend_runner, "127.0.0.1", backend_port)
	await backend_site.start()

	app = build_app(
		StaticResolver(
			backends={"v1": f"http://127.0.0.1:{backend_port}"},
			active_deployment="v1",
		)
	)
	server = uvicorn.Server(
		uvicorn.Config(app, host="127.0.0.1", port=router_port, log_level="warning")
	)
	server_task = asyncio.create_task(server.serve())
	await asyncio.sleep(0.5)

	client = socketio.AsyncClient(reconnection=False)
	try:
		await client.connect(
			f"http://127.0.0.1:{router_port}",
			transports=["websocket"],
			headers={"Cookie": "pulse.sid=abc123"},
			auth={"render_id": "render-1"},
			socketio_path="socket.io",
			wait_timeout=5,
		)
		assert client.connected is True
		assert received == {
			"sid": received["sid"],
			"cookie": "pulse.sid=abc123",
			"render_id": "render-1",
		}
	finally:
		if client.connected:
			await client.disconnect()
		server.should_exit = True
		await server_task
		await app.state.router.close()
		await backend_runner.cleanup()
