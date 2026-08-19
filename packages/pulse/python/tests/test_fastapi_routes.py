from typing import Any

import httpx
import pulse as ps
import pytest
from fastapi import APIRouter, Response
from pulse.api_router import PulseAPIRoute
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send


class _DocsProxy:
	def __init__(self, **_: Any) -> None:
		pass

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		await PlainTextResponse("app docs")(scope, receive, send)

	async def proxy_websocket(self, _: Any) -> None:
		raise AssertionError("unexpected websocket request")

	async def close(self) -> None:
		pass


@pytest.mark.asyncio
async def test_fastapi_routes_unwrap_reactive_response_values():
	app = ps.App(routes=[])

	@app.fastapi.get("/reactive")
	def reactive_payload() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
		count = ps.Signal(2)
		doubled = ps.Computed(lambda: count() * 2)
		return {
			"count": count,
			"nested": {"doubled": doubled},
			"items": ps.reactive([count, {"status": ps.Signal("ok")}]),
		}

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get("/reactive")

	assert response.status_code == 200
	assert response.json() == {
		"count": 2,
		"nested": {"doubled": 4},
		"items": [2, {"status": "ok"}],
	}


@pytest.mark.asyncio
async def test_included_fastapi_routers_unwrap_reactive_response_values():
	app = ps.App(routes=[])
	router = APIRouter()

	@router.get("/reactive")
	def reactive_payload() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
		return {"count": ps.Signal(3)}

	app.fastapi.include_router(router, prefix="/api")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get("/api/reactive")

	assert response.status_code == 200
	assert response.json() == {"count": 3}


def _route_at(app: ps.App, path: str):
	for route in app.fastapi.routes:
		if getattr(route, "path", None) == path:
			return route
	raise AssertionError(f"no route {path}")


def test_pulse_api_route_keeps_user_endpoint():
	app = ps.App(routes=[])

	def hello() -> dict[str, Any]:
		return {"n": ps.Signal(1)}

	app.fastapi.get("/hello")(hello)

	assert _route_at(app, "/hello").endpoint is hello


@pytest.mark.asyncio
async def test_included_pulse_route_class_router_keeps_user_endpoint():
	app = ps.App(routes=[])
	router = APIRouter(route_class=PulseAPIRoute)

	def reactive_payload() -> dict[str, Any]:
		return {"count": ps.Signal(4)}

	router.get("/reactive")(reactive_payload)
	app.fastapi.include_router(router, prefix="/api")

	assert _route_at(app, "/api/reactive").endpoint is reactive_payload

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get("/api/reactive")

	assert response.status_code == 200
	assert response.json() == {"count": 4}


@pytest.mark.asyncio
async def test_fastapi_routes_leave_response_instances_unchanged():
	app = ps.App(routes=[])

	@app.fastapi.get("/raw")
	def raw_response():  # pyright: ignore[reportUnusedFunction]
		return Response("raw", media_type="text/plain")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get("/raw")

	assert response.status_code == 200
	assert response.text == "raw"
	assert response.headers["content-type"].startswith("text/plain")


def test_fastapi_docs_use_reserved_framework_routes():
	app = ps.App(routes=[])

	assert app.fastapi.openapi_url == "/_pulse/openapi.json"
	assert app.fastapi.docs_url == "/_pulse/docs"
	assert app.fastapi.redoc_url is None
	assert app.fastapi.swagger_ui_oauth2_redirect_url == "/_pulse/docs/oauth2-redirect"


@pytest.mark.asyncio
async def test_fastapi_docs_respond_under_reserved_framework_routes():
	app = ps.App(routes=[])
	transport = httpx.ASGITransport(app=app.fastapi)

	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		responses = [
			await client.get("/_pulse/openapi.json"),
			await client.get("/_pulse/docs"),
			await client.get("/_pulse/docs/oauth2-redirect"),
		]
		redoc = await client.get("/_pulse/redoc")

	assert [response.status_code for response in responses] == [200, 200, 200]
	assert responses[0].json()["info"]["title"] == "Pulse UI Server"
	assert redoc.status_code == 404


@pytest.mark.asyncio
async def test_user_docs_route_reaches_react_app_on_cold_request(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://react.test")
	monkeypatch.setattr("pulse.app.ReactProxy", _DocsProxy)

	@ps.component
	def docs_page():
		return ps.div("App docs")

	app = ps.App(
		routes=[ps.Route("/docs", render=docs_page)],
		session_store=ps.CookieSessionStore(secret="test-secret"),
	)
	app.setup("http://testserver")
	transport = httpx.ASGITransport(app=app.fastapi)

	try:
		async with httpx.AsyncClient(
			transport=transport, base_url="http://testserver"
		) as client:
			response = await client.get("/docs")
	finally:
		await app.close()

	assert response.status_code == 200
	assert response.text == "app docs"


def test_fastapi_config_is_honored():
	app = ps.App(
		routes=[],
		fastapi=ps.FastAPIConfig(
			title="Custom API",
			version="9.1",
			docs_url=None,
			redoc_url=None,
			openapi_url=None,
		),
	)

	assert app.fastapi.title == "Custom API"
	assert app.fastapi.version == "9.1"
	assert app.fastapi.routes == []


@pytest.mark.asyncio
async def test_fastapi_config_customizes_docs_and_openapi_urls():
	app = ps.App(
		routes=[],
		fastapi=ps.FastAPIConfig(
			title="Custom API",
			docs_url="/api/docs",
			redoc_url=None,
			openapi_url="/api/openapi.json",
			swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
		),
	)
	transport = httpx.ASGITransport(app=app.fastapi)

	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		docs = await client.get("/api/docs")
		openapi = await client.get("/api/openapi.json")

	assert docs.status_code == 200
	assert "/api/openapi.json" in docs.text
	assert openapi.status_code == 200
	assert openapi.json()["info"]["title"] == "Custom API"


def test_openapi_schema_includes_only_user_routes():
	app = ps.App(routes=[], mode="subdomains")

	@app.fastapi.get("/api/users")
	def users() -> list[object]:  # pyright: ignore[reportUnusedFunction]
		return []

	app.setup("http://testserver")

	assert set(app.fastapi.openapi()["paths"]) == {"/api/users"}
