from __future__ import annotations

import asyncio
import hmac
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any, Protocol, cast

import aiohttp
from fastapi import FastAPI, Header, HTTPException, Request, Response, WebSocket
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

from pulse_railway.constants import (
	AFFINITY_HEADER,
	AFFINITY_QUERY_PARAM,
	DEFAULT_BACKEND_PORT,
	DEFAULT_REDIS_PREFIX,
	DEFAULT_ROUTER_HEALTH_PATH,
	DEFAULT_SERVICE_PREFIX,
	INTERNAL_API_PREFIX,
	INTERNAL_TOKEN_HEADER,
	INTERNAL_TRACKER_SYNC_PATH,
	RAILWAY_ENVIRONMENT_ID_ENV,
	RAILWAY_INTERNAL_TOKEN_ENV,
	RAILWAY_PROJECT_ID_ENV,
	RAILWAY_REDIS_PREFIX_ENV,
	RAILWAY_REDIS_URL_ENV,
	RAILWAY_SERVICE_PREFIX_ENV,
	RAILWAY_TOKEN_ENV,
	RAILWAY_WEBSOCKET_HEARTBEAT_SECONDS_ENV,
	RAILWAY_WEBSOCKET_TTL_SECONDS_ENV,
)
from pulse_railway.railway import RailwayGraphQLClient, RailwayResolver, RouteTarget
from pulse_railway.tracker import DeploymentTracker, RedisDeploymentTracker

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
		tracker: DeploymentTracker | None = None,
		websocket_heartbeat_seconds: int = 15,
	) -> None:
		self.resolver = resolver
		self.tracker = tracker
		self.websocket_heartbeat_seconds = websocket_heartbeat_seconds
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
		if self.tracker is not None:
			await self.tracker.close()

	async def _resolve_from_http(self, request: Request) -> RouteTarget:
		deployment_id = request.query_params.get(AFFINITY_QUERY_PARAM)
		if not deployment_id:
			deployment_id = request.headers.get(AFFINITY_HEADER)
		target = (
			await self.resolver.resolve(deployment_id)
			if deployment_id
			else await self.resolver.resolve_active()
		)
		if target is None:
			raise HTTPException(status_code=404, detail="deployment not found")
		return target

	async def _resolve_from_websocket(self, websocket: WebSocket) -> RouteTarget:
		deployment_id = websocket.query_params.get(AFFINITY_QUERY_PARAM)
		if not deployment_id:
			deployment_id = websocket.headers.get(AFFINITY_HEADER)
		target = (
			await self.resolver.resolve(deployment_id)
			if deployment_id
			else await self.resolver.resolve_active()
		)
		if target is None:
			raise HTTPException(status_code=404, detail="deployment not found")
		return target

	async def health(self) -> JSONResponse:
		return JSONResponse({"ok": True})

	@staticmethod
	def _is_internal_path(path: str) -> bool:
		internal_prefix = INTERNAL_API_PREFIX.lstrip("/")
		return path == internal_prefix or path.startswith(f"{internal_prefix}/")

	async def proxy_http(self, request: Request, path: str) -> Response:
		if self._is_internal_path(path):
			raise HTTPException(status_code=404, detail="not found")
		target = await self._resolve_from_http(request)
		if self.tracker is not None:
			await self.tracker.record_request(deployment_id=target.deployment_id)
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
			protocols=requested_protocols or None,
			autoclose=True,
			autoping=True,
		)
		lease_id: str | None = None
		if self.tracker is not None:
			lease_id = await self.tracker.create_websocket_lease(
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
			if self.tracker is None or lease_id is None:
				return
			while True:
				await asyncio.sleep(self.websocket_heartbeat_seconds)
				await self.tracker.refresh_websocket_lease(
					deployment_id=target.deployment_id,
					lease_id=lease_id,
				)

		tasks = [
			asyncio.create_task(client_to_backend()),
			asyncio.create_task(backend_to_client()),
		]
		if self.tracker is not None and lease_id is not None:
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
			if self.tracker is not None and lease_id is not None:
				with suppress(Exception):
					await self.tracker.remove_websocket_lease(
						deployment_id=target.deployment_id,
						lease_id=lease_id,
					)
			with suppress(Exception):
				await backend_ws.close()
			with suppress(Exception):
				await websocket.close()


def build_app(
	resolver: Resolver,
	tracker: DeploymentTracker | None = None,
	websocket_heartbeat_seconds: int = 15,
	internal_token: str = "",
) -> FastAPI:
	router = AffinityRouter(
		resolver,
		tracker=tracker,
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

	@app.post(INTERNAL_TRACKER_SYNC_PATH)
	async def sync_tracker(
		payload: dict[str, Any],
		x_internal_token: str | None = Header(
			default=None, alias=INTERNAL_TOKEN_HEADER
		),
	) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
		if tracker is None:
			raise HTTPException(status_code=503, detail="tracker unavailable")
		if not internal_token or x_internal_token is None:
			raise HTTPException(status_code=403, detail="forbidden")
		if not hmac.compare_digest(x_internal_token, internal_token):
			raise HTTPException(status_code=403, detail="forbidden")

		active = payload.get("active")
		if not isinstance(active, dict):
			raise HTTPException(status_code=400, detail="active is required")
		active_deployment_id = active.get("deployment_id")
		active_service_name = active.get("service_name")
		if not isinstance(active_deployment_id, str) or not isinstance(
			active_service_name, str
		):
			raise HTTPException(
				status_code=400,
				detail="active deployment_id and service_name are required",
			)

		await tracker.mark_active(
			deployment_id=active_deployment_id,
			service_name=active_service_name,
		)

		draining_payload = payload.get("draining") or []
		if not isinstance(draining_payload, list):
			raise HTTPException(status_code=400, detail="draining must be a list")
		draining_count = 0
		for item in draining_payload:
			if not isinstance(item, dict):
				raise HTTPException(
					status_code=400,
					detail="draining entries must be objects",
				)
			draining_deployment_id = item.get("deployment_id")
			draining_service_name = item.get("service_name")
			if not isinstance(draining_deployment_id, str):
				raise HTTPException(
					status_code=400,
					detail="draining deployment_id is required",
				)
			if draining_service_name is not None and not isinstance(
				draining_service_name, str
			):
				raise HTTPException(
					status_code=400,
					detail="draining service_name must be a string",
				)
			await tracker.mark_draining(
				deployment_id=draining_deployment_id,
				service_name=draining_service_name,
			)
			draining_count += 1

		return JSONResponse(
			{
				"ok": True,
				"active_deployment_id": active_deployment_id,
				"draining_count": draining_count,
			}
		)

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
	token = os.environ.get(RAILWAY_TOKEN_ENV)
	project_id = os.environ.get(RAILWAY_PROJECT_ID_ENV)
	environment_id = os.environ.get(RAILWAY_ENVIRONMENT_ID_ENV)
	if not token or not project_id or not environment_id:
		raise RuntimeError(
			f"missing required env vars: {RAILWAY_TOKEN_ENV}, {RAILWAY_PROJECT_ID_ENV}, {RAILWAY_ENVIRONMENT_ID_ENV}"
		)
	client = RailwayGraphQLClient(token=token)
	resolver = RailwayResolver(
		client=client,
		project_id=project_id,
		environment_id=environment_id,
		service_prefix=os.environ.get(
			RAILWAY_SERVICE_PREFIX_ENV, DEFAULT_SERVICE_PREFIX
		),
		backend_port=int(
			os.environ.get("PULSE_RAILWAY_BACKEND_PORT", str(DEFAULT_BACKEND_PORT))
		),
	)
	tracker = None
	redis_url = os.environ.get(RAILWAY_REDIS_URL_ENV)
	if redis_url:
		tracker = RedisDeploymentTracker.from_url(
			url=redis_url,
			prefix=os.environ.get(RAILWAY_REDIS_PREFIX_ENV, DEFAULT_REDIS_PREFIX),
			websocket_ttl_seconds=int(
				os.environ.get(RAILWAY_WEBSOCKET_TTL_SECONDS_ENV, "45")
			),
		)
	return build_app(
		resolver,
		tracker=tracker,
		websocket_heartbeat_seconds=int(
			os.environ.get(RAILWAY_WEBSOCKET_HEARTBEAT_SECONDS_ENV, "15")
		),
		internal_token=os.environ.get(RAILWAY_INTERNAL_TOKEN_ENV, ""),
	)


__all__ = ["StaticResolver", "build_app", "build_app_from_env"]
