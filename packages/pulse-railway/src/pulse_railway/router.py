from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any, Protocol, cast

import aiohttp
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

from pulse_railway.constants import (
	AFFINITY_HEADER,
	AFFINITY_QUERY_PARAM,
	CLIENT_LOADER_HEADER,
	CLIENT_LOADER_LOCATION_HEADER,
	DEFAULT_BACKEND_PORT,
	DEFAULT_REDIS_PREFIX,
	DEFAULT_ROUTER_HEALTH_PATH,
	INTERNAL_API_PREFIX,
	PULSE_REDIS_PREFIX,
	PULSE_SERVICE_PREFIX,
	PULSE_WEBSOCKET_HEARTBEAT_SECONDS,
	PULSE_WEBSOCKET_TTL_SECONDS,
	RAILWAY_ENVIRONMENT_ID,
	RAILWAY_PROJECT_ID,
	RAILWAY_TOKEN,
	STALE_AFFINITY_RELOAD_QUERY_PARAM,
)
from pulse_railway.railway import RailwayGraphQLClient, RailwayResolver, RouteTarget
from pulse_railway.store import (
	DeploymentStore,
	kv_store_spec_from_env,
)

_HOP_BY_HOP_HEADERS = {
	"connection",
	"keep-alive",
	"proxy-authenticate",
	"proxy-authorization",
	"te",
	"trailers",
	"transfer-encoding",
	"upgrade",
}
_WEBSOCKET_EXCLUDED_HEADERS = {
	"host",
	"upgrade",
	"connection",
	"sec-websocket-key",
	"sec-websocket-version",
	"sec-websocket-protocol",
	"sec-websocket-extensions",
}


def _http_to_ws_url(http_url: str) -> str:
	if http_url.startswith("https://"):
		return http_url.replace("https://", "wss://", 1)
	if http_url.startswith("http://"):
		return http_url.replace("http://", "ws://", 1)
	return http_url


class Resolver(Protocol):
	async def resolve(self, deployment_id: str) -> RouteTarget | None: ...

	async def resolve_active(self) -> RouteTarget | None: ...


@dataclass(slots=True)
class StaticResolver:
	backends: dict[str, str]
	active_deployment: str | None = None

	async def resolve(self, deployment_id: str) -> RouteTarget | None:
		base_url = self.backends.get(deployment_id)
		if not base_url:
			return None
		return RouteTarget(deployment_id=deployment_id, base_url=base_url)

	async def resolve_active(self) -> RouteTarget | None:
		if not self.active_deployment:
			return None
		return await self.resolve(self.active_deployment)


class AffinityRouter:
	def __init__(
		self,
		resolver: Resolver,
		store: DeploymentStore | None = None,
		websocket_heartbeat_seconds: int = 15,
	) -> None:
		self.resolver: Resolver = resolver
		self.store: DeploymentStore | None = store
		self.websocket_heartbeat_seconds: int = websocket_heartbeat_seconds
		self._session: aiohttp.ClientSession | None = None
		self._active_websockets: set[aiohttp.ClientWebSocketResponse] = set()
		self._tasks: set[asyncio.Task[Any]] = set()

	@property
	def session(self) -> aiohttp.ClientSession:
		if self._session is None:
			self._session = aiohttp.ClientSession(
				cookie_jar=aiohttp.DummyCookieJar(),
				timeout=aiohttp.ClientTimeout(total=None, sock_connect=30),
			)
		return self._session

	def _track_task(self, task: asyncio.Task[Any]) -> None:
		self._tasks.add(task)
		task.add_done_callback(self._tasks.discard)

	async def close(self) -> None:
		for task in list(self._tasks):
			task.cancel()
		if self._tasks:
			with suppress(Exception):
				await asyncio.gather(*self._tasks, return_exceptions=True)
			self._tasks.clear()
		for websocket in list(self._active_websockets):
			self._active_websockets.discard(websocket)
			with suppress(Exception):
				await websocket.close()
		if self._session is not None:
			await self._session.close()
			self._session = None
		if self.store is not None:
			await self.store.close()

	async def _resolve_target(
		self,
		deployment_id: str | None,
	) -> RouteTarget:
		if deployment_id:
			target = await self.resolver.resolve(deployment_id)
			if target is not None:
				return target
			raise HTTPException(status_code=404, detail="deployment not found")
		target = await self.resolver.resolve_active()
		if target is None:
			raise HTTPException(status_code=404, detail="deployment not found")
		return target

	async def _resolve_from_http(self, request: Request) -> RouteTarget:
		deployment_id = request.query_params.get(AFFINITY_QUERY_PARAM)
		if not deployment_id:
			deployment_id = request.headers.get(AFFINITY_HEADER)
		return await self._resolve_target(deployment_id)

	async def _resolve_from_websocket(self, websocket: WebSocket) -> RouteTarget:
		deployment_id = websocket.query_params.get(AFFINITY_QUERY_PARAM)
		if not deployment_id:
			deployment_id = websocket.headers.get(AFFINITY_HEADER)
		try:
			return await self._resolve_target(deployment_id)
		except HTTPException:
			reload_on_stale_affinity = (
				websocket.query_params.get(STALE_AFFINITY_RELOAD_QUERY_PARAM) == "1"
			)
			if deployment_id and reload_on_stale_affinity:
				target = await self.resolver.resolve_active()
				if target is not None:
					return target
			raise

	async def health(self) -> JSONResponse:
		return JSONResponse({"ok": True})

	@staticmethod
	def _is_internal_path(path: str) -> bool:
		internal_prefix = INTERNAL_API_PREFIX.lstrip("/")
		return path == internal_prefix or path.startswith(f"{internal_prefix}/")

	async def proxy_http(self, request: Request, path: str) -> Response:
		if self._is_internal_path(path):
			raise HTTPException(status_code=404, detail="not found")
		deployment_id = request.query_params.get(AFFINITY_QUERY_PARAM)
		if not deployment_id:
			deployment_id = request.headers.get(AFFINITY_HEADER)
		client_loader = request.headers.get(CLIENT_LOADER_HEADER) == "1"
		client_loader_location = request.headers.get(CLIENT_LOADER_LOCATION_HEADER)
		try:
			target = await self._resolve_target(deployment_id)
		except HTTPException:
			if deployment_id and await self.resolver.resolve_active() is not None:
				if client_loader and client_loader_location:
					return Response(
						status_code=302,
						headers={"location": client_loader_location},
					)
				return JSONResponse(
					{"detail": "stale affinity"},
					status_code=409,
				)
			raise
		if self.store is not None:
			await self.store.record_request(deployment_id=target.deployment_id)
		url = target.base_url.rstrip("/")
		if path:
			url += "/" + path
		if request.url.query:
			url += "?" + request.url.query

		headers: list[tuple[str, str]] = []
		for key, value in request.headers.items():
			key_lower = key.lower()
			if (
				key_lower == "host"
				or key_lower == "accept-encoding"
				or key_lower in _HOP_BY_HOP_HEADERS
			):
				continue
			headers.append((key, value))
		headers.append(("accept-encoding", "identity"))

		async with self.session.request(
			request.method,
			url,
			headers=headers,
			data=await request.body(),
			allow_redirects=False,
		) as response:
			body = await response.read()
			proxied_headers = {
				key: value
				for key, value in response.headers.items()
				if key.lower() not in _HOP_BY_HOP_HEADERS
			}
			proxied_headers["x-pulse-selected-deployment"] = target.deployment_id
			return Response(
				content=body,
				status_code=response.status,
				headers=proxied_headers,
			)

	async def proxy_websocket(self, websocket: WebSocket, path: str) -> None:
		if self._is_internal_path(path):
			raise HTTPException(status_code=404, detail="not found")
		target = await self._resolve_from_websocket(websocket)
		backend_url = _http_to_ws_url(target.base_url.rstrip("/"))
		if path:
			backend_url += "/" + path
		if websocket.url.query:
			backend_url += "?" + websocket.url.query

		headers: dict[str, str] = {}
		for key, value in websocket.headers.items():
			if key.lower() in _WEBSOCKET_EXCLUDED_HEADERS:
				continue
			headers[key] = value

		requested_protocols = [
			value.strip()
			for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
			if value.strip()
		]
		backend_ws = await self.session.ws_connect(
			backend_url,
			headers=headers,
			protocols=requested_protocols,
			autoclose=True,
			autoping=True,
		)
		lease_id: str | None = None
		if self.store is not None:
			lease_id = await self.store.create_websocket_lease(
				deployment_id=target.deployment_id
			)
		self._active_websockets.add(backend_ws)
		await websocket.accept(subprotocol=backend_ws.protocol)

		async def client_to_backend() -> None:
			try:
				while True:
					message = await websocket.receive()
					message_type = message["type"]
					if message_type == "websocket.disconnect":
						await backend_ws.close()
						return
					if message.get("text") is not None:
						await backend_ws.send_str(cast(str, message["text"]))
						continue
					if message.get("bytes") is not None:
						await backend_ws.send_bytes(cast(bytes, message["bytes"]))
			except WebSocketDisconnect:
				await backend_ws.close()

		async def backend_to_client() -> None:
			async for message in backend_ws:
				if message.type == aiohttp.WSMsgType.TEXT:
					await websocket.send_text(cast(str, message.data))
				elif message.type == aiohttp.WSMsgType.BINARY:
					await websocket.send_bytes(cast(bytes, message.data))
				elif message.type == aiohttp.WSMsgType.CLOSE:
					await websocket.close()
					return
				elif message.type == aiohttp.WSMsgType.ERROR:
					raise RuntimeError("backend websocket error")

		async def websocket_heartbeat() -> None:
			if self.store is None or lease_id is None:
				return
			while True:
				await asyncio.sleep(self.websocket_heartbeat_seconds)
				await self.store.refresh_websocket_lease(
					deployment_id=target.deployment_id,
					lease_id=lease_id,
				)

		tasks = [
			asyncio.create_task(client_to_backend()),
			asyncio.create_task(backend_to_client()),
		]
		if self.store is not None and lease_id is not None:
			tasks.append(asyncio.create_task(websocket_heartbeat()))
		for task in tasks:
			self._track_task(task)
		try:
			done, pending = await asyncio.wait(
				tasks, return_when=asyncio.FIRST_COMPLETED
			)
			for task in pending:
				task.cancel()
			for task in done:
				exc = task.exception()
				if exc is not None and not isinstance(exc, WebSocketDisconnect):
					raise exc
		finally:
			self._active_websockets.discard(backend_ws)
			if self.store is not None and lease_id is not None:
				with suppress(Exception):
					await self.store.remove_websocket_lease(
						deployment_id=target.deployment_id,
						lease_id=lease_id,
					)
			with suppress(Exception):
				await backend_ws.close()
			with suppress(Exception):
				await websocket.close()


def build_app(
	resolver: Resolver,
	store: DeploymentStore | None = None,
	websocket_heartbeat_seconds: int = 15,
) -> FastAPI:
	router = AffinityRouter(
		resolver,
		store=store,
		websocket_heartbeat_seconds=websocket_heartbeat_seconds,
	)

	@asynccontextmanager
	async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
		yield
		await router.close()

	app = FastAPI(lifespan=lifespan)
	app.state.router = router

	@app.get(DEFAULT_ROUTER_HEALTH_PATH)
	async def healthz() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
		return await router.health()

	@app.api_route(
		"/{path:path}",
		methods=["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"],
	)
	async def proxy_http(path: str, request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
		return await router.proxy_http(request, path)

	@app.websocket("/{path:path}")
	async def proxy_websocket(path: str, websocket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
		await router.proxy_websocket(websocket, path)

	return app


def build_app_from_env() -> FastAPI:
	token = os.environ.get(RAILWAY_TOKEN)
	project_id = os.environ.get(RAILWAY_PROJECT_ID)
	environment_id = os.environ.get(RAILWAY_ENVIRONMENT_ID)
	if not token or not project_id or not environment_id:
		raise RuntimeError(
			f"missing required env vars: {RAILWAY_TOKEN}, {RAILWAY_PROJECT_ID}, {RAILWAY_ENVIRONMENT_ID}"
		)
	client = RailwayGraphQLClient(token=token)
	resolver = RailwayResolver(
		client=client,
		project_id=project_id,
		environment_id=environment_id,
		service_prefix=os.environ.get(PULSE_SERVICE_PREFIX),
		backend_port=int(
			os.environ.get("PULSE_BACKEND_PORT", str(DEFAULT_BACKEND_PORT))
		),
	)
	store = None
	spec = kv_store_spec_from_env(dict(os.environ))
	if spec is not None:
		store = DeploymentStore(
			store=spec,
			prefix=os.environ.get(PULSE_REDIS_PREFIX, DEFAULT_REDIS_PREFIX),
			websocket_ttl_seconds=int(
				os.environ.get(PULSE_WEBSOCKET_TTL_SECONDS, "45")
			),
			owns_store=True,
		)
	return build_app(
		resolver,
		store=store,
		websocket_heartbeat_seconds=int(
			os.environ.get(PULSE_WEBSOCKET_HEARTBEAT_SECONDS, "15")
		),
	)


__all__ = ["StaticResolver", "build_app", "build_app_from_env"]
