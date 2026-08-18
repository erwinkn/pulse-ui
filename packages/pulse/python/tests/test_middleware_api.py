from collections.abc import Awaitable, Callable
from typing import Any, override

import httpx
import pulse as ps
import pytest
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pulse.middleware import ApiResponse
from pulse.plugin import Plugin
from pulse.request import PulseRequest
from pulse.routing import Route


class RecordingApiMiddleware(ps.PulseMiddleware):
	def __init__(self) -> None:
		super().__init__()
		self.paths: list[str] = []
		self.methods: list[str] = []
		self.sessions: list[dict[str, Any]] = []

	@override
	async def api(
		self,
		*,
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ApiResponse]],
	) -> ApiResponse:
		self.paths.append(request.path)
		self.methods.append(request.method)
		self.sessions.append(dict(session))
		return await next()


class ErrorReportingApiMiddleware(ps.PulseMiddleware):
	def __init__(self) -> None:
		super().__init__()
		self.errors: list[Exception] = []

	@override
	async def api(
		self,
		*,
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ApiResponse]],
	) -> ApiResponse:
		try:
			return await next()
		except Exception as exc:
			self.errors.append(exc)
			raise


class ShortCircuitApiMiddleware(ps.PulseMiddleware):
	@override
	async def api(
		self,
		*,
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ApiResponse]],
	) -> ApiResponse:
		if request.path == "/secret":
			return JSONResponse({"detail": "unauthorized"}, status_code=401)
		return await next()


class HeaderApiMiddleware(ps.PulseMiddleware):
	@override
	async def api(
		self,
		*,
		request: PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ApiResponse]],
	) -> ApiResponse:
		response = await next()
		response.headers["x-pulse-api"] = "1"
		return response


class PluginRoutePlugin(Plugin):
	@override
	def on_setup(self, app: ps.App) -> None:
		@app.fastapi.get("/plugin-route")
		def plugin_route() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
			return {"plugin": True}

		router = APIRouter()

		@router.get("/included")
		def plugin_included() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
			return {"plugin": True}

		app.fastapi.include_router(router, prefix="/plugin")


@ps.component
def prerender_home():
	return ps.div("ok")


def _client(app: ps.App) -> httpx.AsyncClient:
	transport = httpx.ASGITransport(app=app.fastapi)
	return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_api_middleware_runs_for_user_fastapi_routes():
	mw = RecordingApiMiddleware()
	app = ps.App(routes=[], middleware=mw)

	@app.fastapi.get("/api/hello")
	def hello() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		return {"hello": "world"}

	async with _client(app) as client:
		response = await client.get("/api/hello")

	assert response.status_code == 200
	assert response.json() == {"hello": "world"}
	assert mw.paths == ["/api/hello"]
	assert mw.methods == ["GET"]


@pytest.mark.asyncio
async def test_api_middleware_runs_for_included_routers():
	mw = RecordingApiMiddleware()
	app = ps.App(routes=[], middleware=mw)
	router = APIRouter()

	@router.post("/items")
	def create_item() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		return {"created": "yes"}

	app.fastapi.include_router(router, prefix="/api")

	async with _client(app) as client:
		response = await client.post("/api/items")

	assert response.status_code == 200
	assert response.json() == {"created": "yes"}
	assert mw.paths == ["/api/items"]
	assert mw.methods == ["POST"]


@pytest.mark.asyncio
async def test_api_middleware_can_short_circuit_user_routes():
	app = ps.App(routes=[], middleware=ShortCircuitApiMiddleware())

	@app.fastapi.get("/secret")
	def secret() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		return {"secret": "value"}

	@app.fastapi.get("/public")
	def public() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		return {"ok": "yes"}

	async with _client(app) as client:
		denied = await client.get("/secret")
		allowed = await client.get("/public")

	assert denied.status_code == 401
	assert denied.json() == {"detail": "unauthorized"}
	assert allowed.status_code == 200
	assert allowed.json() == {"ok": "yes"}


@pytest.mark.asyncio
async def test_api_middleware_can_modify_response_headers():
	app = ps.App(routes=[], middleware=HeaderApiMiddleware())

	@app.fastapi.get("/api/hello")
	def hello() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		return {"hello": "world"}

	async with _client(app) as client:
		response = await client.get("/api/hello")

	assert response.status_code == 200
	assert response.headers["x-pulse-api"] == "1"


@pytest.mark.asyncio
async def test_api_middleware_can_catch_user_route_exceptions():
	mw = ErrorReportingApiMiddleware()
	app = ps.App(routes=[], middleware=mw)

	@app.fastapi.get("/api/boom")
	def boom() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		raise RuntimeError("user api failed")

	transport = httpx.ASGITransport(app=app.fastapi, raise_app_exceptions=False)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get("/api/boom")

	assert response.status_code == 500
	assert len(mw.errors) == 1
	assert str(mw.errors[0]) == "user api failed"


@pytest.mark.asyncio
async def test_api_middleware_skips_pulse_framework_and_docs_routes():
	mw = RecordingApiMiddleware()
	app = ps.App(
		routes=[Route("/", prerender_home)],
		middleware=mw,
		mode="subdomains",
	)
	app.setup("http://testserver")

	try:
		async with _client(app) as client:
			health = await client.get("/_pulse/health")
			docs = await client.get("/_pulse/docs")
			openapi = await client.get("/_pulse/openapi.json")
			prerender = await client.post(
				"/_pulse/prerender",
				json={
					"paths": ["/"],
					"routeInfo": {
						"pathname": "/",
						"hash": "",
						"query": "",
						"queryParams": {},
						"pathParams": {},
						"catchall": [],
					},
				},
			)
	finally:
		await app.close()

	assert health.status_code == 200
	assert docs.status_code == 200
	assert openapi.status_code == 200
	assert prerender.status_code == 200
	assert mw.paths == []


@pytest.mark.asyncio
async def test_api_middleware_skips_plugin_on_setup_routes():
	mw = RecordingApiMiddleware()
	app = ps.App(
		routes=[],
		middleware=mw,
		plugins=[PluginRoutePlugin()],
		mode="subdomains",
	)
	app.setup("http://testserver")

	try:
		async with _client(app) as client:
			direct = await client.get("/plugin-route")
			included = await client.get("/plugin/included")
	finally:
		await app.close()

	assert direct.status_code == 200
	assert direct.json() == {"plugin": True}
	assert included.status_code == 200
	assert included.json() == {"plugin": True}
	assert mw.paths == []


@pytest.mark.asyncio
async def test_api_middleware_runs_for_user_routes_after_setup():
	mw = RecordingApiMiddleware()
	app = ps.App(routes=[], middleware=mw, mode="subdomains")

	@app.fastapi.get("/api/before")
	def before() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		return {"when": "before"}

	app.setup("http://testserver")

	@app.fastapi.get("/api/after")
	def after() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		return {"when": "after"}

	router = APIRouter()

	@router.get("/included")
	def included() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		return {"when": "after-include"}

	app.fastapi.include_router(router, prefix="/api")

	try:
		async with _client(app) as client:
			before_res = await client.get("/api/before")
			after_res = await client.get("/api/after")
			included_res = await client.get("/api/included")
			health = await client.get("/_pulse/health")
	finally:
		await app.close()

	assert before_res.json() == {"when": "before"}
	assert after_res.json() == {"when": "after"}
	assert included_res.json() == {"when": "after-include"}
	assert health.status_code == 200
	assert mw.paths == ["/api/before", "/api/after", "/api/included"]


@pytest.mark.asyncio
async def test_api_middleware_receives_session_after_setup():
	mw = RecordingApiMiddleware()
	app = ps.App(routes=[], middleware=mw, mode="subdomains")

	@app.fastapi.get("/api/session")
	def read_session() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
		ps.session()["seen"] = True
		return {"ok": True}

	app.setup("http://testserver")

	try:
		async with _client(app) as client:
			response = await client.get("/api/session")
	finally:
		await app.close()

	assert response.status_code == 200
	assert len(mw.sessions) == 1
	# Session exists (cookie store mints one) even if empty at hook entry
	assert isinstance(mw.sessions[0], dict)


@pytest.mark.asyncio
async def test_api_middleware_stack_runs_in_order():
	order: list[str] = []

	class First(ps.PulseMiddleware):
		@override
		async def api(
			self,
			*,
			request: PulseRequest,
			session: dict[str, Any],
			next: Callable[[], Awaitable[ApiResponse]],
		) -> ApiResponse:
			order.append("first")
			response = await next()
			order.append("first-after")
			return response

	class Second(ps.PulseMiddleware):
		@override
		async def api(
			self,
			*,
			request: PulseRequest,
			session: dict[str, Any],
			next: Callable[[], Awaitable[ApiResponse]],
		) -> ApiResponse:
			order.append("second")
			return await next()

	app = ps.App(routes=[], middleware=[First(), Second()])

	@app.fastapi.get("/api/hello")
	def hello() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		order.append("handler")
		return {"hello": "world"}

	async with _client(app) as client:
		response = await client.get("/api/hello")

	assert response.status_code == 200
	assert order == ["first", "second", "handler", "first-after"]


@pytest.mark.asyncio
async def test_api_middleware_rejects_non_response_return():
	class BadMiddleware(ps.PulseMiddleware):
		@override
		async def api(
			self,
			*,
			request: PulseRequest,
			session: dict[str, Any],
			next: Callable[[], Awaitable[ApiResponse]],
		) -> ApiResponse:
			return {"not": "a response"}  # pyright: ignore[reportReturnType]

	app = ps.App(routes=[], middleware=BadMiddleware())

	@app.fastapi.get("/api/hello")
	def hello() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
		return {"hello": "world"}

	transport = httpx.ASGITransport(app=app.fastapi, raise_app_exceptions=False)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get("/api/hello")

	assert response.status_code == 500


def test_latency_middleware_accepts_api_ms():
	mw = ps.LatencyMiddleware(api_ms=10.0)
	assert mw.api_ms == 10.0
