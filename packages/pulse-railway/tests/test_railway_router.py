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
from pulse_railway.constants import (
	CLIENT_LOADER_HEADER,
	CLIENT_LOADER_LOCATION_HEADER,
	INTERNAL_TOKEN_HEADER,
	PULSE_KV_KIND,
	PULSE_KV_PATH,
	PULSE_KV_URL,
	RAILWAY_ENVIRONMENT_ID,
	RAILWAY_PROJECT_ID,
	RAILWAY_TOKEN,
	REDIS_URL,
	STALE_AFFINITY_RELOAD_QUERY_PARAM,
)
from pulse_railway.router import StaticResolver, build_app, build_app_from_env
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
async def test_router_blocks_store_sync_internal_path(
	backend_servers: dict[str, str],
) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.post("/_pulse/internal/railway/store/sync", json={})
	await app.state.router.close()

	assert response.status_code == 404


@pytest.mark.asyncio
async def test_router_control_endpoint_promotes_deployment() -> None:
	store = MemoryDeploymentStore()
	app = build_app(
		StaticResolver(backends={}),
		store=store,
		internal_token="secret-token",
	)
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		unauthorized = await client.post(
			"/_pulse/internal/railway/promote",
			json={},
		)
		response = await client.post(
			"/_pulse/internal/railway/promote",
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
			json={
				"active": {
					"deployment_id": "prod-new",
					"service_name": "pulse-prod-new",
				},
				"draining": [
					{
						"deployment_id": "prod-old",
						"service_name": "pulse-prod-old",
						"drain_started_at": 123.0,
					}
				],
			},
		)
		active = await client.get(
			"/_pulse/internal/railway/active",
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
		)
	await app.state.router.close()

	assert unauthorized.status_code == 404
	assert response.status_code == 200
	assert active.json() == {"deployment_id": "prod-new"}
	assert await store.get_active_deployment() == "prod-new"
	draining = await store.list_draining_deployments()
	assert len(draining) == 1
	assert draining[0].deployment_id == "prod-old"
	assert draining[0].service_name == "pulse-prod-old"
	assert draining[0].drain_started_at == 123.0


@pytest.mark.asyncio
async def test_router_promote_rejects_active_deployment_in_draining() -> None:
	store = MemoryDeploymentStore()
	await store.set_active(deployment_id="prod-current", service_name="pulse-current")
	app = build_app(
		StaticResolver(backends={}),
		store=store,
		internal_token="secret-token",
	)
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.post(
			"/_pulse/internal/railway/promote",
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
			json={
				"active": {
					"deployment_id": "prod-new",
					"service_name": "pulse-prod-new",
				},
				"draining": [
					{
						"deployment_id": "prod-new",
						"service_name": "pulse-prod-new",
					}
				],
			},
		)
	await app.state.router.close()

	assert response.status_code == 400
	assert await store.get_active_deployment() == "prod-current"
	assert await store.get_deployment(deployment_id="prod-new") is None
	assert await store.list_draining_deployments() == []


@pytest.mark.asyncio
async def test_router_promote_rejects_duplicate_draining_deployment_ids() -> None:
	store = MemoryDeploymentStore()
	await store.set_active(deployment_id="prod-current", service_name="pulse-current")
	app = build_app(
		StaticResolver(backends={}),
		store=store,
		internal_token="secret-token",
	)
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.post(
			"/_pulse/internal/railway/promote",
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
			json={
				"active": {
					"deployment_id": "prod-new",
					"service_name": "pulse-prod-new",
				},
				"draining": [
					{
						"deployment_id": "prod-old",
						"service_name": "pulse-prod-old-a",
					},
					{
						"deployment_id": "prod-old",
						"service_name": "pulse-prod-old-b",
					},
				],
			},
		)
	await app.state.router.close()

	assert response.status_code == 400
	assert await store.get_active_deployment() == "prod-current"
	assert await store.get_deployment(deployment_id="prod-new") is None
	assert await store.get_deployment(deployment_id="prod-old") is None


@pytest.mark.asyncio
async def test_router_promote_rejects_invalid_drain_started_at() -> None:
	store = MemoryDeploymentStore()
	await store.set_active(deployment_id="prod-current", service_name="pulse-current")
	app = build_app(
		StaticResolver(backends={}),
		store=store,
		internal_token="secret-token",
	)
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.post(
			"/_pulse/internal/railway/promote",
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
			json={
				"active": {
					"deployment_id": "prod-new",
					"service_name": "pulse-prod-new",
				},
				"draining": [
					{
						"deployment_id": "prod-old",
						"service_name": "pulse-prod-old",
						"drain_started_at": "soon",
					}
				],
			},
		)
	await app.state.router.close()

	assert response.status_code == 400
	assert await store.get_active_deployment() == "prod-current"
	assert await store.get_deployment(deployment_id="prod-new") is None
	assert await store.get_deployment(deployment_id="prod-old") is None


@pytest.mark.asyncio
async def test_router_control_endpoint_deletes_inactive_deployment_state() -> None:
	store = MemoryDeploymentStore()
	await store.set_active(deployment_id="prod-new", service_name="pulse-prod-new")
	await store.mark_draining(
		deployment_id="prod-old",
		service_name="pulse-prod-old",
		now=123.0,
	)
	app = build_app(
		StaticResolver(backends={}),
		store=store,
		internal_token="secret-token",
	)
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.post(
			"/_pulse/internal/railway/delete",
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
			json={"deployment_id": "prod-old"},
		)
	await app.state.router.close()

	assert response.status_code == 200
	assert await store.get_active_deployment() == "prod-new"
	assert await store.get_deployment(deployment_id="prod-old") is None


@pytest.mark.asyncio
async def test_router_control_endpoint_rejects_active_deployment_delete() -> None:
	store = MemoryDeploymentStore()
	await store.set_active(deployment_id="prod-active", service_name="pulse-active")
	app = build_app(
		StaticResolver(backends={}),
		store=store,
		internal_token="secret-token",
	)
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.post(
			"/_pulse/internal/railway/delete",
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
			json={"deployment_id": "prod-active"},
		)
	await app.state.router.close()

	assert response.status_code == 400
	assert await store.get_active_deployment() == "prod-active"
	assert await store.get_deployment(deployment_id="prod-active") is not None


def test_build_app_from_env_requires_deployment_store(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv(RAILWAY_TOKEN, "token")
	monkeypatch.setenv(RAILWAY_PROJECT_ID, "project")
	monkeypatch.setenv(RAILWAY_ENVIRONMENT_ID, "environment")
	monkeypatch.delenv(REDIS_URL, raising=False)
	monkeypatch.delenv(PULSE_KV_KIND, raising=False)
	monkeypatch.delenv(PULSE_KV_URL, raising=False)
	monkeypatch.delenv(PULSE_KV_PATH, raising=False)

	with pytest.raises(RuntimeError, match="deployment store"):
		build_app_from_env()


@pytest.mark.asyncio
async def test_build_app_from_env_uses_redis_url(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv(RAILWAY_TOKEN, "token")
	monkeypatch.setenv(RAILWAY_PROJECT_ID, "project")
	monkeypatch.setenv(RAILWAY_ENVIRONMENT_ID, "environment")
	monkeypatch.setenv(REDIS_URL, "redis://localhost:6379/0")
	monkeypatch.delenv(PULSE_KV_KIND, raising=False)
	monkeypatch.delenv(PULSE_KV_URL, raising=False)
	monkeypatch.delenv(PULSE_KV_PATH, raising=False)

	app = build_app_from_env()

	assert app.state.router.store is not None
	await app.state.router.close()


@pytest.mark.asyncio
async def test_build_app_from_env_uses_explicit_kv_env(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv(RAILWAY_TOKEN, "token")
	monkeypatch.setenv(RAILWAY_PROJECT_ID, "project")
	monkeypatch.setenv(RAILWAY_ENVIRONMENT_ID, "environment")
	monkeypatch.delenv(REDIS_URL, raising=False)
	monkeypatch.setenv(PULSE_KV_KIND, "memory")
	monkeypatch.delenv(PULSE_KV_URL, raising=False)
	monkeypatch.delenv(PULSE_KV_PATH, raising=False)

	app = build_app_from_env()

	assert app.state.router.store is not None
	await app.state.router.close()


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

	assert response.status_code == 409
	assert response.json() == {"detail": "stale affinity"}


@pytest.mark.asyncio
async def test_router_redirects_client_loader_for_stale_http_affinity(
	backend_servers: dict[str, str],
) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
		follow_redirects=False,
	) as client:
		response = await client.get(
			"/",
			params={"pulse_deployment": "missing"},
			headers={
				CLIENT_LOADER_HEADER: "1",
				CLIENT_LOADER_LOCATION_HEADER: "http://app.example.com/users?tab=active",
			},
		)
	await app.state.router.close()

	assert response.status_code == 302
	assert response.headers["location"] == "http://app.example.com/users?tab=active"


@pytest.mark.asyncio
async def test_router_returns_404_for_unknown_backend_without_active_deployment(
	backend_servers: dict[str, str],
) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment=None))
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


@pytest.mark.asyncio
async def test_router_falls_back_to_active_backend_for_stale_socket_affinity(
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
			backends={"v2": f"http://127.0.0.1:{backend_port}"},
			active_deployment="v2",
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
			f"http://127.0.0.1:{router_port}?pulse_deployment=missing&{STALE_AFFINITY_RELOAD_QUERY_PARAM}=1",
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


@pytest.mark.asyncio
async def test_router_rejects_stale_socket_affinity_without_reload_opt_in(
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

	backend_runner = web.AppRunner(backend)
	await backend_runner.setup()
	backend_site = web.TCPSite(backend_runner, "127.0.0.1", backend_port)
	await backend_site.start()

	app = build_app(
		StaticResolver(
			backends={"v2": f"http://127.0.0.1:{backend_port}"},
			active_deployment="v2",
		)
	)
	server = uvicorn.Server(
		uvicorn.Config(app, host="127.0.0.1", port=router_port, log_level="warning")
	)
	server_task = asyncio.create_task(server.serve())
	await asyncio.sleep(0.5)

	client = socketio.AsyncClient(reconnection=False)
	try:
		with pytest.raises(socketio.exceptions.ConnectionError):
			await client.connect(
				f"http://127.0.0.1:{router_port}?pulse_deployment=missing",
				transports=["websocket"],
				headers={"Cookie": "pulse.sid=abc123"},
				auth={"render_id": "render-1"},
				socketio_path="socket.io",
				wait_timeout=5,
			)
		assert client.connected is False
	finally:
		if client.connected:
			await client.disconnect()
		server.should_exit = True
		await server_task
		await app.state.router.close()
		await backend_runner.cleanup()
