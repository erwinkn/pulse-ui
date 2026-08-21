import asyncio
from datetime import UTC, datetime
from typing import Any, override

import httpx
import pulse as ps
import pytest
from fastapi import Response
from fastapi.responses import RedirectResponse
from pulse.context import PulseContext


class BlockingSessionStore(ps.SessionStore):
	data: dict[str, dict[str, Any]]
	auth_save_started: asyncio.Event
	allow_auth_save: asyncio.Event

	def __init__(self) -> None:
		self.data = {}
		self.auth_save_started = asyncio.Event()
		self.allow_auth_save = asyncio.Event()

	@override
	async def get(self, sid: str) -> dict[str, Any] | None:
		return self.data.get(sid)

	@override
	async def create(self, sid: str) -> dict[str, Any]:
		self.data[sid] = {}
		return {}

	@override
	async def delete(self, sid: str) -> None:
		self.data.pop(sid, None)

	@override
	async def save(self, sid: str, session: dict[str, Any]) -> None:
		if "auth" in session:
			self.auth_save_started.set()
			await self.allow_auth_save.wait()
		self.data[sid] = dict(session)


def test_cookie_session_store_round_trips_json_data() -> None:
	store = ps.CookieSessionStore(secret="test-secret")
	session = {"user": {"id": 7}, "roles": ["admin"], "active": True}

	decoded = store.decode(store.encode("sid", session))

	assert decoded is not None
	assert decoded[0] == "sid"
	assert dict(decoded[1]) == session


def test_cookie_session_store_rejects_non_json_data_without_mutation() -> None:
	store = ps.CookieSessionStore(secret="test-secret")
	session = {"last_seen": datetime.now(UTC)}

	with pytest.raises(TypeError, match="JSON-compatible"):
		store.encode("sid", session)

	assert "last_seen" in session


@pytest.mark.parametrize(
	"value",
	[
		("tuple",),
		{1: "non-string key"},
		float("inf"),
	],
)
def test_cookie_session_store_rejects_lossy_json_values(value: object) -> None:
	store = ps.CookieSessionStore(secret="test-secret")
	session: dict[str, Any] = {"value": value}

	with pytest.raises(TypeError, match="Session data"):
		store.encode("sid", session)

	assert session["value"] is value


def test_cookie_session_store_rejects_cycles_without_mutation() -> None:
	store = ps.CookieSessionStore(secret="test-secret")
	value: list[object] = []
	value.append(value)
	session: dict[str, Any] = {"value": value}

	with pytest.raises(TypeError, match="cycle"):
		store.encode("sid", session)

	assert session["value"] is value


def test_cookie_session_store_rejects_oversized_data_without_mutation() -> None:
	store = ps.CookieSessionStore(secret="test-secret", max_cookie_bytes=40)
	session = {"value": "x" * 100}

	with pytest.raises(ValueError, match="too large"):
		store.encode("sid", session)

	assert session == {"value": "x" * 100}


@pytest.mark.asyncio
async def test_server_session_save_blocks_http_response_until_persisted(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	store = BlockingSessionStore()
	app = ps.App(routes=[], session_store=store)

	@app.fastapi.get("/login")
	def login():  # pyright: ignore[reportUnusedFunction]
		ps.session()["auth"] = "ok"
		return RedirectResponse("/destination")

	app.setup("http://example.com")

	with PulseContext(app=app):
		transport = httpx.ASGITransport(app=app.fastapi)
		async with httpx.AsyncClient(
			transport=transport, base_url="http://testserver"
		) as client:
			request_task = asyncio.create_task(
				client.get("/login", follow_redirects=False)
			)

			await asyncio.wait_for(store.auth_save_started.wait(), timeout=1)
			await asyncio.sleep(0)
			assert not request_task.done()

			store.allow_auth_save.set()
			response = await asyncio.wait_for(request_task, timeout=1)

	assert response.status_code == 307
	assert any(session.get("auth") == "ok" for session in store.data.values())


@pytest.mark.asyncio
async def test_server_session_response_wait_survives_superseded_save(
	monkeypatch: pytest.MonkeyPatch,
):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	store = BlockingSessionStore()
	app = ps.App(routes=[], session_store=store)
	app.setup("http://example.com")

	session = await app.get_or_create_session(None)
	await session.handle_response(Response())
	store.allow_auth_save.set()
	session.data["auth"] = "baseline"
	await session.handle_response(Response())
	store.allow_auth_save.clear()
	store.auth_save_started.clear()
	session.data["auth"] = "first"

	async def handle_response() -> None:
		await session.handle_response(Response())

	first_response = asyncio.create_task(handle_response())
	await asyncio.wait_for(store.auth_save_started.wait(), timeout=1)
	assert not first_response.done()

	store.auth_save_started.clear()
	session.data["auth"] = "second"
	second_response = asyncio.create_task(handle_response())
	await asyncio.wait_for(store.auth_save_started.wait(), timeout=1)

	store.allow_auth_save.set()
	await asyncio.wait_for(asyncio.gather(first_response, second_response), timeout=1)

	assert any(
		session_data.get("auth") == "second" for session_data in store.data.values()
	)


@pytest.mark.asyncio
async def test_http_request_without_render_does_not_retain_user_session(
	monkeypatch: pytest.MonkeyPatch,
):
	"""Cookie-less requests (bots, health checks) must not accumulate sessions."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[])
	app.setup("http://example.com")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		for _ in range(3):
			resp = await client.get("/_pulse/health", cookies=None)
			assert resp.status_code == 200

	assert app.user_sessions == {}


@pytest.mark.asyncio
async def test_prerender_request_retains_user_session(
	monkeypatch: pytest.MonkeyPatch,
):
	"""Sessions that own a render session stay alive after the request."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")

	@ps.component
	def home():
		return ps.div("ok")

	app = ps.App(routes=[ps.Route("a", home)])
	app.setup("http://example.com")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		resp = await client.post(
			"/_pulse/prerender",
			json={
				"paths": ["/a"],
				"routeInfo": {
					"pathname": "/a",
					"hash": "",
					"query": "",
					"queryParams": {},
					"pathParams": {},
					"catchall": [],
				},
			},
		)
		assert resp.status_code == 200

	assert len(app.user_sessions) == 1
	assert len(app.render_sessions) == 1
	await app.close()
