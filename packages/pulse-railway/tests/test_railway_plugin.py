from __future__ import annotations

import httpx
import pulse as ps
import pytest
from pulse_railway.constants import AFFINITY_QUERY_PARAM, RAILWAY_DEPLOYMENT_ID_ENV
from pulse_railway.plugin import RailwayDirectivesMiddleware, RailwayPlugin


@pytest.mark.asyncio
async def test_prerender_adds_affinity_query_directives(monkeypatch) -> None:
	monkeypatch.setenv(RAILWAY_DEPLOYMENT_ID_ENV, "prod-260402-120000")
	plugin = RailwayPlugin()
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
		AFFINITY_QUERY_PARAM: "prod-260402-120000"
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
	monkeypatch.setenv(RAILWAY_DEPLOYMENT_ID_ENV, "prod-260402-120000")
	plugin = RailwayPlugin()

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
