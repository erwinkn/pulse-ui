from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
import pytest_asyncio
import socketio
import uvicorn
from aiohttp import web
from httpx import ASGITransport, AsyncClient
from pulse_railway.constants import (
	CLIENT_LOADER_HEADER,
	CLIENT_LOADER_LOCATION_HEADER,
	PULSE_KV_KIND,
	PULSE_KV_PATH,
	PULSE_KV_URL,
	PULSE_ROUTER_CONNECTION_LIMIT,
	RAILWAY_ENVIRONMENT_ID,
	RAILWAY_PROJECT_ID,
	RAILWAY_TOKEN,
	REDIS_URL,
	STALE_AFFINITY_HEADER,
	STALE_AFFINITY_RELOAD_QUERY_PARAM,
)
from pulse_railway.router import (
	AffinityRouter,
	StaticResolver,
	build_app,
	build_app_from_env,
)
from pulse_railway.store import MemoryDeploymentStore
from socketio.exceptions import ConnectionError as SocketIOConnectionError
from starlette.websockets import WebSocket


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
async def test_router_keeps_form_posts_on_original_deployment_after_promotion(
	unused_tcp_port_factory: Callable[[], int],
) -> None:
	runners: list[web.AppRunner] = []
	backends: dict[str, str] = {}

	async def start_backend(name: str, status: int) -> None:
		app = web.Application()

		async def submit(request: web.Request) -> web.Response:
			return web.json_response(
				{
					"deployment": name,
					"query": dict(request.query),
				},
				status=status,
			)

		app.router.add_post("/_pulse/forms/render-1/form-1", submit)
		runner = web.AppRunner(app)
		await runner.setup()
		port = unused_tcp_port_factory()
		site = web.TCPSite(runner, "127.0.0.1", port)
		await site.start()
		runners.append(runner)
		backends[name] = f"http://127.0.0.1:{port}"

	await start_backend("prod-260721-190711", 204)
	await start_backend("prod-260721-201609", 410)
	app = build_app(
		StaticResolver(
			backends=backends,
			active_deployment="prod-260721-201609",
		)
	)
	try:
		async with AsyncClient(
			transport=ASGITransport(app=app),
			base_url="http://testserver",
		) as client:
			response = await client.post(
				"/_pulse/forms/render-1/form-1",
				params={
					"foo": "1",
					"pulse_deployment": "prod-260721-190711",
				},
			)
	finally:
		await app.state.router.close()
		for runner in runners:
			await runner.cleanup()

	assert response.status_code == 204
	assert response.headers["x-pulse-selected-deployment"] == "prod-260721-190711"


@pytest.mark.asyncio
async def test_router_marks_form_post_after_original_deployment_is_drained(
	backend_servers: dict[str, str],
) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.post(
			"/_pulse/forms/render-1/form-1",
			params={"pulse_deployment": "drained"},
			headers={"origin": "https://app.example.com"},
		)
	await app.state.router.close()

	assert response.status_code == 409
	assert response.headers[STALE_AFFINITY_HEADER] == "1"
	assert response.headers["access-control-allow-origin"] == "https://app.example.com"
	assert response.headers["access-control-allow-credentials"] == "true"
	assert response.headers["access-control-expose-headers"] == STALE_AFFINITY_HEADER


@pytest.mark.asyncio
async def test_router_allows_stale_affinity_form_preflight(
	backend_servers: dict[str, str],
) -> None:
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		response = await client.options(
			"/_pulse/forms/render-1/form-1",
			params={"pulse_deployment": "drained"},
			headers={
				"origin": "https://app.example.com",
				"access-control-request-method": "POST",
				"access-control-request-headers": "x-pulse-render-id",
			},
		)
	await app.state.router.close()

	assert response.status_code == 204
	assert response.headers["access-control-allow-origin"] == "https://app.example.com"
	assert response.headers["access-control-allow-methods"] == "POST"
	assert response.headers["access-control-allow-headers"] == "x-pulse-render-id"


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
async def test_router_does_not_expose_deployment_control_paths() -> None:
	app = build_app(StaticResolver(backends={}))
	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://testserver",
	) as client:
		responses = [
			await client.get("/_pulse/internal/railway/active"),
			await client.post("/_pulse/internal/railway/register", json={}),
			await client.post("/_pulse/internal/railway/promote", json={}),
			await client.post("/_pulse/internal/railway/delete", json={}),
		]
	await app.state.router.close()

	assert [response.status_code for response in responses] == [404, 404, 404, 404]


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
async def test_router_session_uses_default_connection_limit(
	monkeypatch: pytest.MonkeyPatch,
	backend_servers: dict[str, str],
) -> None:
	monkeypatch.delenv(PULSE_ROUTER_CONNECTION_LIMIT, raising=False)
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	connector = app.state.router.session.connector
	await app.state.router.close()

	assert connector.limit == 2048


@pytest.mark.asyncio
async def test_router_session_reads_connection_limit_env(
	monkeypatch: pytest.MonkeyPatch,
	backend_servers: dict[str, str],
) -> None:
	monkeypatch.setenv(PULSE_ROUTER_CONNECTION_LIMIT, "4096")
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))
	connector = app.state.router.session.connector
	await app.state.router.close()

	assert connector.limit == 4096


@pytest.mark.asyncio
async def test_router_session_rejects_invalid_connection_limit(
	monkeypatch: pytest.MonkeyPatch,
	backend_servers: dict[str, str],
) -> None:
	monkeypatch.setenv(PULSE_ROUTER_CONNECTION_LIMIT, "0")
	app = build_app(StaticResolver(backends=backend_servers, active_deployment="v2"))

	try:
		with pytest.raises(
			RuntimeError, match=f"{PULSE_ROUTER_CONNECTION_LIMIT} must be >= 1"
		):
			_ = app.state.router.session
	finally:
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
	assert response.headers[STALE_AFFINITY_HEADER] == "1"


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
	async def connect(  # pyright: ignore[reportUnusedFunction]
		sid: str, environ: dict[str, str], auth: dict[str, str]
	) -> None:
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
		uvicorn.Config(
			app,
			host="127.0.0.1",
			port=router_port,
			log_level="warning",
			ws="wsproto",
		)
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
		await client.disconnect()
		server.should_exit = True
		await server_task
		await app.state.router.close()
		await backend_runner.cleanup()


@pytest.mark.asyncio
async def test_router_closes_backend_websocket_when_client_accept_fails(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class BackendWebSocket:
		protocol: str | None = None
		closed: bool = False

		async def close(self) -> None:
			self.closed = True

	class FakeSession:
		def __init__(self, websocket: BackendWebSocket) -> None:
			self.websocket: BackendWebSocket = websocket

		async def ws_connect(self, *_args: Any, **_kwargs: Any) -> BackendWebSocket:
			return self.websocket

	class RejectingWebSocket:
		headers: dict[str, str] = {}
		query_params: dict[str, str] = {}
		url: SimpleNamespace = SimpleNamespace(query="")
		closed: bool = False

		async def accept(self, *_args: Any, **_kwargs: Any) -> None:
			raise RuntimeError("client disconnected before accept")

		async def close(self) -> None:
			self.closed = True

	backend_ws = BackendWebSocket()
	router = AffinityRouter(
		StaticResolver(backends={"v1": "http://backend"}, active_deployment="v1")
	)
	monkeypatch.setattr(
		router.session, "ws_connect", FakeSession(backend_ws).ws_connect
	)
	websocket = RejectingWebSocket()

	try:
		with pytest.raises(RuntimeError, match="client disconnected"):
			await router.proxy_websocket(
				cast(WebSocket, cast(object, websocket)), "socket.io/"
			)
	finally:
		await router.close()

	assert backend_ws.closed is True
	assert websocket.closed is True


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
	async def connect(  # pyright: ignore[reportUnusedFunction]
		sid: str, environ: dict[str, str], auth: dict[str, str]
	) -> None:
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
		with pytest.raises(SocketIOConnectionError):
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
		await client.disconnect()
		server.should_exit = True
		await server_task
		await app.state.router.close()
		await backend_runner.cleanup()
