import httpx
import pytest
from pulse import App, Route, component
from pulse.proxy import WebProxy
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send
from starlette.websockets import WebSocket


@component
def DummyPage():
	return None


def test_framework_namespace_is_reserved():
	"""User routes cannot overlap with framework-owned endpoints."""
	with pytest.raises(ValueError, match=r"Routes under '/_pulse/\*' are reserved"):
		App(routes=[Route("/_pulse/debug", render=DummyPage)])


@pytest.mark.asyncio
async def test_backend_only_app_needs_no_web_upstream(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.delenv("PULSE_WEB_UPSTREAM", raising=False)
	app = App()
	app.setup()

	transport = httpx.ASGITransport(app=app.asgi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		health = await client.get("/_pulse/health")
		unmatched = await client.get("/web-route")

	assert health.status_code == 200
	assert unmatched.status_code == 404
	assert app._proxy is None  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_web_proxy_is_an_unmatched_session_free_fallback(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_WEB_UPSTREAM", "http://web:3000")
	proxied_paths: list[str] = []

	async def proxy_call(
		self: WebProxy, scope: Scope, receive: Receive, send: Send
	) -> None:
		proxied_paths.append(scope["path"])
		await send(
			{
				"type": "http.response.start",
				"status": 200,
				"headers": [(b"content-type", b"text/plain")],
			}
		)
		await send({"type": "http.response.body", "body": b"web"})

	monkeypatch.setattr(WebProxy, "__call__", proxy_call)
	app = App()

	@app.fastapi.get("/api/value")
	def api_value() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
		return JSONResponse({"source": "api"})

	session_calls = 0
	original_get_or_create_session = app.get_or_create_session

	async def get_or_create_session(raw_cookie: str | None):
		nonlocal session_calls
		session_calls += 1
		return await original_get_or_create_session(raw_cookie)

	monkeypatch.setattr(app, "get_or_create_session", get_or_create_session)
	app.setup()

	transport = httpx.ASGITransport(app=app.asgi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		web = await client.get("/asset.js")
		api = await client.get("/api/value")
		method_not_allowed = await client.post("/api/value")
		redirect = await client.get("/api/value/")

	assert web.text == "web"
	assert api.json() == {"source": "api"}
	assert method_not_allowed.status_code == 405
	assert redirect.status_code == 307
	assert proxied_paths == ["/asset.js"]
	assert session_calls == 3


def test_invalid_web_upstream_fails_during_setup(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_WEB_UPSTREAM", "http://web:3000/path")
	app = App()

	with pytest.raises(ValueError, match="web_upstream"):
		app.setup()


@pytest.mark.asyncio
async def test_user_websocket_route_takes_priority_over_web_proxy(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_WEB_UPSTREAM", "http://web:3000")
	proxy_called = False

	async def proxy_call(
		self: WebProxy, scope: Scope, receive: Receive, send: Send
	) -> None:
		nonlocal proxy_called
		proxy_called = True

	monkeypatch.setattr(WebProxy, "__call__", proxy_call)
	app = App()

	@app.fastapi.websocket("/api/ws")
	async def api_websocket(  # pyright: ignore[reportUnusedFunction]
		websocket: WebSocket,
	):
		await websocket.accept()
		await websocket.send_text("api")
		await websocket.close()

	app.setup()
	messages: list[Message] = [{"type": "websocket.connect"}]
	sent: list[Message] = []

	async def receive() -> Message:
		return messages.pop(0)

	async def send(message: Message) -> None:
		sent.append(message)

	scope: Scope = {
		"type": "websocket",
		"asgi": {"version": "3.0"},
		"http_version": "1.1",
		"scheme": "ws",
		"server": ("testserver", 80),
		"client": ("testclient", 50000),
		"root_path": "",
		"path": "/api/ws",
		"raw_path": b"/api/ws",
		"query_string": b"",
		"headers": [],
		"subprotocols": [],
		"state": {},
	}
	await app.asgi(scope, receive, send)

	assert not proxy_called
	assert {"type": "websocket.send", "text": "api"} in sent


@pytest.mark.asyncio
async def test_socket_io_is_under_framework_namespace(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.delenv("PULSE_WEB_UPSTREAM", raising=False)
	app = App()
	app.setup()

	transport = httpx.ASGITransport(app=app.asgi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		current = await client.get("/_pulse/socket.io/?EIO=4&transport=polling")

	assert current.status_code == 200


@pytest.mark.asyncio
async def test_socket_io_rejects_foreign_origins(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.delenv("PULSE_WEB_UPSTREAM", raising=False)
	app = App()
	app.setup()

	transport = httpx.ASGITransport(app=app.asgi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get(
			"/_pulse/socket.io/?EIO=4&transport=polling",
			headers={"origin": "https://other.example"},
		)

	assert response.status_code == 400


@pytest.mark.asyncio
async def test_framework_does_not_add_cors_middleware(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.delenv("PULSE_WEB_UPSTREAM", raising=False)
	app = App()
	app.setup()

	transport = httpx.ASGITransport(app=app.asgi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		response = await client.get(
			"/_pulse/health", headers={"origin": "https://other.example"}
		)

	assert "access-control-allow-origin" not in response.headers
