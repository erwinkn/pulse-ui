import httpx
import pulse as ps
import pytest
from pulse.messages import (
	PrerenderPayload,
	ServerInitMessage,
	ServerNavigateToMessage,
)
from pulse.render_session import RenderSession
from pulse.routing import Route, RouteInfo
from pulse.serializer import deserialize
from pulse.test_helpers import wait_for
from pulse.user_session import UserSession


@ps.component
def prerender_home():
	return ps.div("ok")


@ps.component
def redirect_away():
	ps.redirect("/target")


def _prerender_body(path: str) -> PrerenderPayload:
	return {
		"paths": [path],
		"routeInfo": {
			"pathname": path,
			"hash": "",
			"query": "",
			"queryParams": {},
			"pathParams": {},
			"catchall": [],
		},
	}


@pytest.mark.asyncio
async def test_prerender_normalizes_paths(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[Route("a", prerender_home)])
	app.setup("http://example.com")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		resp = await client.post(
			"/_pulse/prerender",
			json={
				"paths": ["a"],
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
	payload = deserialize(resp.json())
	assert "/a" in payload["views"]
	assert "a" not in payload["views"]
	view = payload["views"]["/a"]
	assert "vdom" in view


@pytest.mark.asyncio
async def test_prerender_unknown_render_id_header_mints_fresh_render(
	monkeypatch: pytest.MonkeyPatch,
):
	"""An unknown X-Pulse-Render-Id never revives an old render: /prerender is
	the only render factory and always mints a server-side id."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[Route("a", prerender_home)])
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
			headers={"X-Pulse-Render-Id": "never-minted"},
		)

	assert resp.status_code == 200
	payload = deserialize(resp.json())
	render_id = payload["directives"]["headers"]["X-Pulse-Render-Id"]
	assert render_id != "never-minted"
	assert render_id in app.render_sessions

	await app.close()


@pytest.mark.asyncio
async def test_prerender_on_render_reaped_mid_request_mints_fresh_render(
	monkeypatch: pytest.MonkeyPatch,
):
	"""If the render resolved by HTTP middleware is closed before the
	prerender handler runs, a fresh render is minted instead of prerendering
	on the dead one."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[Route("a", prerender_home)])
	app.setup("http://example.com")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		resp = await client.post("/_pulse/prerender", json=_prerender_body("/a"))
		render_id = deserialize(resp.json())["directives"]["headers"][
			"X-Pulse-Render-Id"
		]

		# The render dies after the middleware would have resolved it.
		stale = app.render_sessions[render_id]
		app.close_render(render_id)
		assert render_id not in app.render_sessions

		# Pin middleware resolution to the stale object: the handler's identity
		# check is what must detect it.
		def resolve_stale(render_id: str | None, session: UserSession) -> RenderSession:
			return stale

		monkeypatch.setattr(app, "_get_render_for_session", resolve_stale)

		resp = await client.post(
			"/_pulse/prerender",
			json=_prerender_body("/a"),
			headers={"X-Pulse-Render-Id": render_id},
		)

	assert resp.status_code == 200
	payload = deserialize(resp.json())
	new_render_id = payload["directives"]["headers"]["X-Pulse-Render-Id"]
	assert new_render_id != render_id
	assert app.render_sessions[new_render_id] is not stale

	await app.close()


@pytest.mark.asyncio
async def test_prerender_reused_render_is_held_alive_during_request(
	monkeypatch: pytest.MonkeyPatch,
):
	"""A render reused via X-Pulse-Render-Id has its cleanup timer cancelled
	while the prerender runs and rescheduled once it completes."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(routes=[Route("a", prerender_home)], session_timeout=60.0)
	app.setup("http://example.com")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		resp = await client.post("/_pulse/prerender", json=_prerender_body("/a"))
		render_id = deserialize(resp.json())["directives"]["headers"][
			"X-Pulse-Render-Id"
		]
		render = app.render_sessions[render_id]
		assert render_id in app._render_cleanups  # pyright: ignore[reportPrivateUsage]

		# The render's cleanup must be cancelled while its prerender runs.
		cleanup_live_during_prerender: list[bool] = []
		original_prerender = render.prerender

		def spy_prerender(
			paths: list[str], route_info: RouteInfo | None = None
		) -> dict[str, ServerInitMessage | ServerNavigateToMessage]:
			handle = app._render_cleanups.get(render_id)  # pyright: ignore[reportPrivateUsage]
			cleanup_live_during_prerender.append(
				handle is not None and not handle.cancelled()
			)
			return original_prerender(paths, route_info)

		monkeypatch.setattr(render, "prerender", spy_prerender)

		resp = await client.post(
			"/_pulse/prerender",
			json=_prerender_body("/a"),
			headers={"X-Pulse-Render-Id": render_id},
		)

	payload = deserialize(resp.json())
	assert payload["directives"]["headers"]["X-Pulse-Render-Id"] == render_id
	assert cleanup_live_during_prerender == [False]
	assert render_id in app._render_cleanups  # pyright: ignore[reportPrivateUsage]

	await app.close()


@pytest.mark.asyncio
async def test_prerender_redirect_leaves_mountless_render_on_pending_timeout(
	monkeypatch: pytest.MonkeyPatch,
):
	"""A prerender that only redirects disposes its mounts inline, leaving a
	mount-less render. The husk is kept for pending_timeout (a last reuse
	window), not session_timeout."""
	monkeypatch.setenv("PULSE_REACT_SERVER_ADDRESS", "http://localhost:3000")
	app = ps.App(
		routes=[Route("a", redirect_away)],
		session_timeout=60.0,
		pending_timeout=0.05,
	)
	app.setup("http://example.com")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as client:
		resp = await client.post("/_pulse/prerender", json=_prerender_body("/a"))

	assert resp.json() == {"redirect": "/target"}

	# The render survives briefly for reuse, but with no mounts left.
	assert len(app.render_sessions) == 1
	render = next(iter(app.render_sessions.values()))
	assert not render.route_mounts

	# It is reaped on pending_timeout rather than lingering for session_timeout.
	assert await wait_for(lambda: render.id not in app.render_sessions)

	await app.close()
