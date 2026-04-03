from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any, Protocol, cast

import aiohttp
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse
from starlette.datastructures import URL
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

from scripts.railway_router_poc.railway import (
	AFFINITY_HEADER,
	AFFINITY_QUERY_PARAM,
	RailwayGraphQLClient,
	RailwayResolver,
	RouteTarget,
)

logger = logging.getLogger(__name__)

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


def _decode_header(value: bytes) -> str:
	return value.decode("latin-1")


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
	def __init__(self, resolver: Resolver) -> None:
		self.resolver = resolver
		self._session: aiohttp.ClientSession | None = None
		self._active_websockets: set[aiohttp.ClientWebSocketResponse] = set()
		self._tasks: set[asyncio.Task[Any]] = set()
		self._closing = asyncio.Event()

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
		self._closing.set()
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

	async def debug_routes(self, request: Request) -> JSONResponse:
		target = await self._resolve_from_http(request)
		return JSONResponse(
			{
				"deployment": target.deployment_id,
				"base_url": target.base_url,
			}
		)

	async def health(self) -> JSONResponse:
		return JSONResponse({"ok": True})

	async def proxy_http(self, request: Request) -> Any:
		target = await self._resolve_from_http(request)
		url = URL(target.base_url.rstrip("/") + request.url.path)
		if request.url.query:
			url = url.replace(query=request.url.query)

		headers: list[tuple[str, str]] = []
		for key, value in request.headers.items():
			key_lower = key.lower()
			if key_lower == "host" or key_lower in _HOP_BY_HOP_HEADERS:
				continue
			headers.append((key, value))

		response = await self.session.request(
			request.method,
			str(url),
			headers=headers,
			data=await request.body(),
			allow_redirects=False,
		)
		body = await response.read()
		proxied_headers = {
			key: value
			for key, value in response.headers.items()
			if key.lower() not in _HOP_BY_HOP_HEADERS
		}
		proxied_headers["x-poc-selected-deployment"] = target.deployment_id
		return (
			JSONResponse(
				content=json.loads(body.decode())
				if proxied_headers.get("content-type", "").startswith(
					"application/json"
				)
				else {"body": body.decode()},
				status_code=response.status,
				headers=proxied_headers,
			)
			if request.url.path == "/_poc/json"
			else (
				type(
					"_ProxyResponse",
					(JSONResponse,),
					{},
				)(content={}, status_code=200)
			)
		)

	async def proxy_http_passthrough(
		self, scope: Scope, receive: Receive, send: Send
	) -> None:
		request = Request(scope, receive=receive)
		target = await self._resolve_from_http(request)
		url = target.base_url.rstrip("/") + request.url.path
		if request.url.query:
			url += "?" + request.url.query

		headers: list[tuple[str, str]] = []
		for key_bytes, value_bytes in cast(
			list[tuple[bytes, bytes]], scope.get("headers") or []
		):
			key = _decode_header(key_bytes)
			key_lower = key.lower()
			if key_lower == "host" or key_lower in _HOP_BY_HOP_HEADERS:
				continue
			headers.append((key, _decode_header(value_bytes)))

		body = await request.body()
		response = await self._session.request(
			scope["method"],
			url,
			headers=headers,
			data=body,
			allow_redirects=False,
		)
		try:
			await send(
				{
					"type": "http.response.start",
					"status": response.status,
					"headers": [
						(key.encode("latin-1"), value.encode("latin-1"))
						for key, value in response.headers.items()
						if key.lower() not in _HOP_BY_HOP_HEADERS
					]
					+ [
						(
							b"x-poc-selected-deployment",
							target.deployment_id.encode("latin-1"),
						)
					],
				}
			)
			await send(
				{
					"type": "http.response.body",
					"body": await response.read(),
					"more_body": False,
				}
			)
		finally:
			response.close()

	async def proxy_websocket(self, websocket: WebSocket) -> None:
		target = await self._resolve_from_websocket(websocket)
		target_url = _http_to_ws_url(target.base_url.rstrip("/")) + websocket.url.path
		if websocket.url.query:
			target_url += "?" + websocket.url.query

		headers: list[tuple[str, str]] = []
		for key, value in websocket.headers.items():
			key_lower = key.lower()
			if (
				key_lower in _WEBSOCKET_EXCLUDED_HEADERS
				or key_lower in _HOP_BY_HOP_HEADERS
			):
				continue
			headers.append((key, value))

		scope_subprotocols = cast(list[str] | None, websocket.scope.get("subprotocols"))
		subprotocols = list(scope_subprotocols or [])
		upstream_ws: aiohttp.ClientWebSocketResponse | None = None
		client_to_upstream_task: asyncio.Task[Any] | None = None
		upstream_to_client_task: asyncio.Task[Any] | None = None
		try:
			upstream_ws = await self.session.ws_connect(
				target_url,
				headers=headers,
				protocols=subprotocols,
			)
			self._active_websockets.add(upstream_ws)
			await websocket.accept(subprotocol=upstream_ws.protocol)

			async def _client_to_upstream() -> None:
				assert upstream_ws is not None
				while not self._closing.is_set():
					try:
						message = await websocket.receive()
					except WebSocketDisconnect:
						return
					if message.get("type") == "websocket.disconnect":
						return
					if message.get("type") != "websocket.receive":
						continue
					if message.get("text") is not None:
						await upstream_ws.send_str(message["text"])
					if message.get("bytes") is not None:
						await upstream_ws.send_bytes(message["bytes"])

			async def _upstream_to_client() -> None:
				assert upstream_ws is not None
				while not self._closing.is_set():
					message = await upstream_ws.receive()
					if message.type == aiohttp.WSMsgType.TEXT:
						await websocket.send_text(message.data)
						continue
					if message.type == aiohttp.WSMsgType.BINARY:
						await websocket.send_bytes(message.data)
						continue
					return

			client_to_upstream_task = asyncio.create_task(_client_to_upstream())
			upstream_to_client_task = asyncio.create_task(_upstream_to_client())
			self._track_task(client_to_upstream_task)
			self._track_task(upstream_to_client_task)
			done, pending = await asyncio.wait(
				{client_to_upstream_task, upstream_to_client_task},
				return_when=asyncio.FIRST_COMPLETED,
			)
			for task in pending:
				task.cancel()
			with suppress(Exception):
				await asyncio.gather(*pending, return_exceptions=True)
			for task in done:
				exc = task.exception()
				if exc and not isinstance(exc, asyncio.CancelledError):
					raise exc
		finally:
			if client_to_upstream_task is not None:
				client_to_upstream_task.cancel()
				with suppress(Exception):
					await client_to_upstream_task
			if upstream_to_client_task is not None:
				upstream_to_client_task.cancel()
				with suppress(Exception):
					await upstream_to_client_task
			if upstream_ws is not None:
				self._active_websockets.discard(upstream_ws)
				with suppress(Exception):
					await upstream_ws.close()
			with suppress(Exception):
				await websocket.close()


def build_app(resolver: Resolver) -> FastAPI:
	router = AffinityRouter(resolver)

	@asynccontextmanager
	async def lifespan(_: FastAPI) -> AsyncIterator[None]:
		yield
		await router.close()

	app = FastAPI(lifespan=lifespan)
	app.state.router = router

	@app.get("/_poc/health")
	async def _health() -> JSONResponse:
		return await router.health()

	@app.get("/_poc/route")
	async def _route(request: Request) -> JSONResponse:
		return await router.debug_routes(request)

	@app.websocket("/{path:path}")
	async def _proxy_ws(websocket: WebSocket, path: str) -> None:
		await router.proxy_websocket(websocket)

	@app.api_route(
		"/{path:path}",
		methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
	)
	async def _proxy_http(request: Request, path: str) -> Any:
		target = await router._resolve_from_http(request)
		url = target.base_url.rstrip("/") + request.url.path
		if request.url.query:
			url += "?" + request.url.query

		headers: list[tuple[str, str]] = []
		for key, value in request.headers.items():
			if key.lower() == "host" or key.lower() in _HOP_BY_HOP_HEADERS:
				continue
			headers.append((key, value))

		response = await router.session.request(
			request.method,
			url,
			headers=headers,
			data=await request.body(),
			allow_redirects=False,
		)
		content = await response.read()
		return JSONResponse(
			content=json.loads(content.decode())
			if response.headers.get("content-type", "").startswith("application/json")
			else {"body": content.decode()},
			status_code=response.status,
			headers={
				key: value
				for key, value in response.headers.items()
				if key.lower() not in _HOP_BY_HOP_HEADERS
			}
			| {"x-poc-selected-deployment": target.deployment_id},
		)

	return app


def build_app_from_env() -> FastAPI:
	static_backends = os.getenv("POC_STATIC_BACKENDS")
	if static_backends:
		backends = json.loads(static_backends)
		resolver = StaticResolver(
			backends=backends,
			active_deployment=os.getenv("POC_ACTIVE_DEPLOYMENT"),
		)
		return build_app(resolver)

	token = os.environ["RAILWAY_TOKEN"]
	project_id = os.environ["RAILWAY_PROJECT_ID"]
	environment_id = os.environ["RAILWAY_ENVIRONMENT_ID"]
	service_prefix = os.getenv("POC_SERVICE_PREFIX", "poc-")
	backend_port = int(os.getenv("POC_BACKEND_PORT", "80"))
	client = RailwayGraphQLClient(token=token)
	resolver = RailwayResolver(
		client=client,
		project_id=project_id,
		environment_id=environment_id,
		service_prefix=service_prefix,
		backend_port=backend_port,
	)
	return build_app(resolver)
