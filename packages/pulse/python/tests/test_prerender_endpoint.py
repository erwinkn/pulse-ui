import httpx
import pulse as ps
import pytest
from pulse.routing import Route
from pulse.serializer import deserialize


@ps.component
def prerender_home():
	return ps.div("ok")


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
