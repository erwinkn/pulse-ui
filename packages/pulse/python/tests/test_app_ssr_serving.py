"""Tests for the single-server SSR serving block (catch-all GET route)."""

from pathlib import Path
from typing import Any, cast

import httpx
import pulse as ps
import pytest
from pulse.routing import Route


@ps.component
def ssr_home():
	return ps.div("home")


class _StubSSRResponse:
	status_code: int = 200
	text: str = "<html>ssr-ok</html>"


class _StubSSRClient:
	def __init__(self) -> None:
		self.requests: list[dict[str, Any]] = []

	async def post(self, url: str, json: Any) -> _StubSSRResponse:
		self.requests.append({"url": url, "json": json})
		return _StubSSRResponse()

	async def aclose(self) -> None:
		pass


def _make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ps.App:
	monkeypatch.setenv("PULSE_SSR_SERVER_ADDRESS", "http://localhost:3001")
	public_dir = tmp_path / "public"
	public_dir.mkdir(parents=True)
	(public_dir / "robots.txt").write_text("User-agent: *")
	app = ps.App(
		routes=[Route("/", ssr_home)],
		codegen=ps.CodegenConfig(web_dir=str(tmp_path)),
	)
	app.setup("http://example.com")
	return app


@pytest.mark.asyncio
async def test_catch_all_serves_ssr_html(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	app = _make_app(tmp_path, monkeypatch)
	stub = _StubSSRClient()
	app._ssr_client = cast(httpx.AsyncClient, cast(object, stub))  # pyright: ignore[reportPrivateUsage]

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		resp = await client.get("/", headers={"accept": "text/html"})

	assert resp.status_code == 200
	assert resp.text == "<html>ssr-ok</html>"
	assert len(stub.requests) == 1
	request = stub.requests[0]
	assert request["url"] == "http://localhost:3001/render"
	assert "prerender" in request["json"]


@pytest.mark.asyncio
async def test_catch_all_returns_404_for_unknown_route(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	app = _make_app(tmp_path, monkeypatch)

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		resp = await client.get("/missing", headers={"accept": "text/html"})

	assert resp.status_code == 404


@pytest.mark.asyncio
async def test_catch_all_serves_static_files(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	app = _make_app(tmp_path, monkeypatch)

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		resp = await client.get("/robots.txt")

	assert resp.status_code == 200
	assert resp.text == "User-agent: *"


@pytest.mark.asyncio
async def test_catch_all_returns_502_when_ssr_server_unreachable(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	app = _make_app(tmp_path, monkeypatch)

	class _FailingSSRClient:
		async def post(self, url: str, json: Any) -> _StubSSRResponse:
			raise httpx.ConnectError("connection refused")

		async def aclose(self) -> None:
			pass

	app._ssr_client = cast(httpx.AsyncClient, cast(object, _FailingSSRClient()))  # pyright: ignore[reportPrivateUsage]

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		resp = await client.get("/", headers={"accept": "text/html"})

	assert resp.status_code == 502


@pytest.mark.asyncio
async def test_catch_all_routes_dev_asset_requests_to_proxy(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	from starlette.requests import Request
	from starlette.responses import PlainTextResponse, Response

	monkeypatch.setenv("PULSE_ENV", "dev")
	monkeypatch.setenv("PULSE_ASSET_SERVER_ADDRESS", "http://localhost:5173")
	app = _make_app(tmp_path, monkeypatch)
	assert app._asset_proxy is not None  # pyright: ignore[reportPrivateUsage]

	class _StubProxy:
		async def __call__(self, request: Request) -> Response:
			return PlainTextResponse("proxied:" + request.url.path)

		async def close(self) -> None:
			pass

	from pulse.proxy import DevServerProxy

	app._asset_proxy = cast(DevServerProxy, cast(object, _StubProxy()))  # pyright: ignore[reportPrivateUsage]

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		vite_resp = await client.get("/src/main.tsx")
		# Non-HTML accept headers also route to the dev server
		js_resp = await client.get("/some-module.js", headers={"accept": "*/*"})

	assert vite_resp.text == "proxied:/src/main.tsx"
	assert js_resp.text == "proxied:/some-module.js"


def test_setup_requires_ssr_server_address(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	monkeypatch.delenv("PULSE_SSR_SERVER_ADDRESS", raising=False)
	app = ps.App(
		routes=[Route("/", ssr_home)],
		codegen=ps.CodegenConfig(web_dir=str(tmp_path)),
	)
	with pytest.raises(RuntimeError, match="PULSE_SSR_SERVER_ADDRESS"):
		app.setup("http://example.com")
