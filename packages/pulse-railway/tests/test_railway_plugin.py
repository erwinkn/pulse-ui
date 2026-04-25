from __future__ import annotations

import httpx
import pulse as ps
import pytest
from pulse_railway.constants import (
	AFFINITY_QUERY_PARAM,
	INTERNAL_RELOAD_PATH,
	INTERNAL_SESSIONS_PATH,
	INTERNAL_TOKEN_HEADER,
	PULSE_DEPLOYMENT_ID,
	PULSE_INTERNAL_TOKEN,
	STALE_AFFINITY_RELOAD_QUERY_PARAM,
)
from pulse_railway.plugin import RailwayDirectivesMiddleware, RailwayPlugin


class _TrackedRenderSessions(dict[str, object]):
	def __init__(self) -> None:
		super().__init__()
		self.values_calls = 0

	def values(self):
		self.values_calls += 1
		return super().values()


@pytest.mark.asyncio
async def test_prerender_adds_affinity_query_directives(monkeypatch) -> None:
	monkeypatch.setenv(PULSE_DEPLOYMENT_ID, "prod-260402-120000")
	plugin = RailwayPlugin(dockerfile="Dockerfile")
	plugin.on_startup(ps.App(routes=[]))

	middleware = RailwayDirectivesMiddleware(plugin)
	result = await middleware.prerender(
		payload={"paths": ["/"], "routeInfo": {}},
		request=object(),
		session={},
		next=lambda: _ok_prerender(),
	)

	assert isinstance(result, ps.Ok)
	assert result.payload["directives"]["query"][AFFINITY_QUERY_PARAM] == (
		"prod-260402-120000"
	)
	assert result.payload["directives"]["socketio"]["query"] == {
		AFFINITY_QUERY_PARAM: "prod-260402-120000",
		STALE_AFFINITY_RELOAD_QUERY_PARAM: "1",
	}


async def _ok_prerender() -> ps.Ok[ps.Prerender]:
	return ps.Ok(
		{
			"views": {},
			"directives": {
				"headers": {"X-Pulse-Render-Id": "render-id"},
				"query": {},
				"socketio": {
					"auth": {"render_id": "render-id"},
					"headers": {},
					"query": {},
				},
			},
		}
	)


@pytest.mark.asyncio
async def test_plugin_exposes_deployment_metadata_endpoint(monkeypatch) -> None:
	monkeypatch.setenv(PULSE_DEPLOYMENT_ID, "prod-260402-120000")
	plugin = RailwayPlugin(dockerfile="Dockerfile")

	app = ps.App(routes=[], plugins=[plugin], mode="subdomains")
	plugin.on_startup(app)
	app.setup("https://app.example.com")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="https://app.example.com"
	) as client:
		response = await client.get("/_pulse/meta")

	assert response.status_code == 200
	assert response.json() == {
		"status": "ok",
		"deployment_id": "prod-260402-120000",
		"api_prefix": "/_pulse",
	}


@pytest.mark.asyncio
async def test_plugin_exposes_internal_session_endpoint(monkeypatch) -> None:
	monkeypatch.setenv(PULSE_DEPLOYMENT_ID, "prod-260402-120000")
	monkeypatch.setenv(PULSE_INTERNAL_TOKEN, "secret-token")
	plugin = RailwayPlugin(dockerfile="Dockerfile")

	app = ps.App(routes=[], plugins=[plugin], mode="subdomains")
	plugin.on_startup(app)
	app.setup("https://app.example.com")
	session = await app.get_or_create_session(None)
	connected = app.create_render("connected", session)
	connected.connect(lambda _message: None)
	resumable = app.create_render("resumable", session)
	render_sessions = _TrackedRenderSessions()
	render_sessions[connected.id] = connected
	render_sessions[resumable.id] = resumable
	app.render_sessions = render_sessions

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="https://app.example.com"
	) as client:
		forbidden = await client.get(INTERNAL_SESSIONS_PATH)
		response = await client.get(
			INTERNAL_SESSIONS_PATH,
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
		)

	assert forbidden.status_code == 403
	assert response.status_code == 200
	assert app.render_sessions.values_calls == 1
	assert response.json() == {
		"deployment_id": "prod-260402-120000",
		"connected_render_count": 1,
		"resumable_render_count": 1,
		"drainable": False,
		"session_timeout_seconds": 60.0,
	}


@pytest.mark.asyncio
async def test_plugin_exposes_internal_reload_endpoint(monkeypatch) -> None:
	monkeypatch.setenv(PULSE_DEPLOYMENT_ID, "prod-260402-120000")
	monkeypatch.setenv(PULSE_INTERNAL_TOKEN, "secret-token")
	plugin = RailwayPlugin(dockerfile="Dockerfile")

	app = ps.App(routes=[], plugins=[plugin], mode="subdomains")
	plugin.on_startup(app)
	app.setup("https://app.example.com")
	session = await app.get_or_create_session(None)
	connected = app.create_render("connected", session)
	connected.connect(lambda _message: None)
	resumable = app.create_render("resumable", session)
	render_sessions = _TrackedRenderSessions()
	render_sessions[connected.id] = connected
	render_sessions[resumable.id] = resumable
	app.render_sessions = render_sessions
	app._socket_to_render = {"socket-1": connected.id}  # pyright: ignore[reportAttributeAccessIssue]
	emitted: list[tuple[str, object, str | None]] = []

	async def fake_emit(event: str, payload: object, to: str | None = None) -> None:
		emitted.append((event, payload, to))

	app.sio.emit = fake_emit  # pyright: ignore[reportAttributeAccessIssue]

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="https://app.example.com"
	) as client:
		forbidden = await client.post(INTERNAL_RELOAD_PATH)
		response = await client.post(
			INTERNAL_RELOAD_PATH,
			headers={INTERNAL_TOKEN_HEADER: "secret-token"},
		)

	assert forbidden.status_code == 403
	assert response.status_code == 200
	assert app.render_sessions.values_calls == 1
	assert len(emitted) == 1
	assert emitted[0][0] == "message"
	assert emitted[0][2] == "socket-1"
	assert emitted[0][1][-1] == {"type": "reload"}
	assert response.json() == {
		"deployment_id": "prod-260402-120000",
		"connected_render_count": 1,
		"reloaded_socket_count": 1,
	}
