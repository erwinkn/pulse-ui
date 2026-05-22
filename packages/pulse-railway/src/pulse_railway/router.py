from __future__ import annotations

import asyncio
import hmac
import os
from collections.abc import AsyncGenerator
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
	INTERNAL_TOKEN_HEADER,
	PULSE_INTERNAL_TOKEN,
	PULSE_REDIS_PREFIX,
	PULSE_SERVICE_PREFIX,
	RAILWAY_ENVIRONMENT_ID,
	RAILWAY_PROJECT_ID,
	RAILWAY_TOKEN,
	STALE_AFFINITY_RELOAD_QUERY_PARAM,
)
from pulse_railway.railway.client import (
	RailwayGraphQLClient,
	RailwayResolver,
	RouteTarget,
)
from pulse_railway.store import (
	ActiveDeploymentError,
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
		internal_token: str = "",
	) -> None:
		self.resolver: Resolver = resolver
		self.store: DeploymentStore | None = store
		self.internal_token: str = internal_token
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

	def _authorize_internal_request(self, request: Request) -> None:
		header = request.headers.get(INTERNAL_TOKEN_HEADER)
		if not self.internal_token or header is None:
			raise HTTPException(status_code=404, detail="not found")
		if not hmac.compare_digest(header, self.internal_token):
			raise HTTPException(status_code=404, detail="not found")

	async def active_deployment(self, request: Request) -> JSONResponse:
		self._authorize_internal_request(request)
		if self.store is None:
			raise HTTPException(status_code=503, detail="deployment store unavailable")
		return JSONResponse({"deployment_id": await self.store.get_active_deployment()})

	async def promote_deployment(self, request: Request) -> JSONResponse:
		self._authorize_internal_request(request)
		if self.store is None:
			raise HTTPException(status_code=503, detail="deployment store unavailable")
		payload = await request.json()
		active = payload.get("active")
		if not isinstance(active, dict):
			raise HTTPException(status_code=400, detail="active deployment required")
		active_deployment_id = active.get("deployment_id")
		active_service_name = active.get("service_name")
		if not isinstance(active_deployment_id, str) or not isinstance(
			active_service_name, str
		):
			raise HTTPException(status_code=400, detail="active deployment invalid")
		draining = payload.get("draining", [])
		if not isinstance(draining, list):
			raise HTTPException(status_code=400, detail="draining deployments invalid")
		draining_records: list[tuple[str, str, float | None]] = []
		draining_deployment_ids: set[str] = set()
		for item in draining:
			if not isinstance(item, dict):
				raise HTTPException(
					status_code=400, detail="draining deployment invalid"
				)
			deployment_id = item.get("deployment_id")
			service_name = item.get("service_name")
			drain_started_at = item.get("drain_started_at")
			if not isinstance(deployment_id, str) or not isinstance(service_name, str):
				raise HTTPException(
					status_code=400, detail="draining deployment invalid"
				)
			if deployment_id == active_deployment_id:
				raise HTTPException(
					status_code=400,
					detail="active deployment cannot be draining",
				)
			if deployment_id in draining_deployment_ids:
				raise HTTPException(
					status_code=400,
					detail="duplicate draining deployment",
				)
			draining_deployment_ids.add(deployment_id)
			drain_started_at_float: float | None = None
			if drain_started_at is not None:
				if not isinstance(drain_started_at, str | int | float):
					raise HTTPException(
						status_code=400,
						detail="draining deployment drain_started_at invalid",
					)
				try:
					drain_started_at_float = float(drain_started_at)
				except ValueError as exc:
					raise HTTPException(
						status_code=400,
						detail="draining deployment drain_started_at invalid",
					) from exc
			draining_records.append(
				(deployment_id, service_name, drain_started_at_float)
			)
		await self.store.set_active(
			deployment_id=active_deployment_id,
			service_name=active_service_name,
		)
		for deployment_id, service_name, drain_started_at in draining_records:
			await self.store.mark_draining(
				deployment_id=deployment_id,
				service_name=service_name,
				now=drain_started_at,
			)
		for deployment in await self.store.list_deployments():
			if (
				deployment.deployment_id != active_deployment_id
				and deployment.deployment_id not in draining_deployment_ids
				and deployment.state != "draining"
			):
				await self.store.mark_draining(
					deployment_id=deployment.deployment_id,
					service_name=deployment.service_name,
				)
		return JSONResponse({"ok": True})

	async def register_deployment(self, request: Request) -> JSONResponse:
		self._authorize_internal_request(request)
		if self.store is None:
			raise HTTPException(status_code=503, detail="deployment store unavailable")
		payload = await request.json()
		deployment_id = payload.get("deployment_id")
		service_name = payload.get("service_name")
		if not isinstance(deployment_id, str) or not isinstance(service_name, str):
			raise HTTPException(
				status_code=400, detail="deployment registration invalid"
			)
		if await self.store.get_active_deployment() == deployment_id:
			raise HTTPException(
				status_code=400,
				detail="active deployment cannot be registered",
			)
		await self.store.register_deployment(
			deployment_id=deployment_id,
			service_name=service_name,
		)
		return JSONResponse({"ok": True})

	async def delete_deployment_state(self, request: Request) -> JSONResponse:
		self._authorize_internal_request(request)
		if self.store is None:
			raise HTTPException(status_code=503, detail="deployment store unavailable")
		payload = await request.json()
		deployment_id = payload.get("deployment_id")
		if not isinstance(deployment_id, str):
			raise HTTPException(status_code=400, detail="deployment_id required")
		try:
			await self.store.delete_inactive_deployment(deployment_id=deployment_id)
		except ActiveDeploymentError as exc:
			raise HTTPException(
				status_code=400,
				detail="active deployment cannot be deleted",
			) from exc
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

		tasks = [
			asyncio.create_task(client_to_backend()),
			asyncio.create_task(backend_to_client()),
		]
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
			with suppress(Exception):
				await backend_ws.close()
			with suppress(Exception):
				await websocket.close()


def build_app(
	resolver: Resolver,
	store: DeploymentStore | None = None,
	internal_token: str = "",
) -> FastAPI:
	router = AffinityRouter(
		resolver,
		store=store,
		internal_token=internal_token,
	)

	@asynccontextmanager
	async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
		yield
		await router.close()

	app = FastAPI(lifespan=lifespan)
	app.state.router = router

	@app.get(DEFAULT_ROUTER_HEALTH_PATH)
	async def healthz() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
		return await router.health()

	@app.get(f"{INTERNAL_API_PREFIX}/railway/active")
	async def active_deployment(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
		return await router.active_deployment(request)

	@app.post(f"{INTERNAL_API_PREFIX}/railway/promote")
	async def promote_deployment(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
		return await router.promote_deployment(request)

	@app.post(f"{INTERNAL_API_PREFIX}/railway/register")
	async def register_deployment(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
		return await router.register_deployment(request)

	@app.post(f"{INTERNAL_API_PREFIX}/railway/delete")
	async def delete_deployment_state(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
		return await router.delete_deployment_state(request)

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
	store = None
	spec = kv_store_spec_from_env(dict(os.environ))
	if spec is None:
		raise RuntimeError("missing required router deployment store env vars")
	store = DeploymentStore(
		store=spec,
		prefix=os.environ.get(PULSE_REDIS_PREFIX, DEFAULT_REDIS_PREFIX),
		owns_store=True,
	)
	client = RailwayGraphQLClient(token=token)
	resolver = RailwayResolver(
		client=client,
		project_id=project_id,
		environment_id=environment_id,
		service_prefix=os.environ.get(PULSE_SERVICE_PREFIX),
		store=store,
		backend_port=DEFAULT_BACKEND_PORT,
	)
	return build_app(
		resolver,
		store=store,
		internal_token=os.environ.get(PULSE_INTERNAL_TOKEN, ""),
	)


__all__ = ["StaticResolver", "build_app", "build_app_from_env"]
