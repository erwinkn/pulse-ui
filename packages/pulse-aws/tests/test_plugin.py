from __future__ import annotations

import httpx
import pulse as ps
import pytest
from pulse_aws.constants import AFFINITY_QUERY_PARAM
from pulse_aws.plugin import AWSECSDirectivesMiddleware, AWSECSPlugin


@pytest.mark.asyncio
async def test_prerender_adds_affinity_query_directives():
	plugin = AWSECSPlugin()
	plugin.enabled = True
	plugin.deployment_id = "test-20260306-150000Z"

	middleware = AWSECSDirectivesMiddleware(plugin)
	result = await middleware.prerender(
		payload={"paths": ["/"], "routeInfo": {}},
		request=object(),
		session={},
		next=lambda: _ok_prerender(),
	)

	assert isinstance(result, ps.Ok)
	assert result.payload["directives"]["query"][AFFINITY_QUERY_PARAM] == (
		"test-20260306-150000Z"
	)
	assert result.payload["directives"]["socketio"]["query"] == {
		AFFINITY_QUERY_PARAM: "test-20260306-150000Z"
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
async def test_plugin_exposes_deployment_metadata_endpoint():
	plugin = AWSECSPlugin()
	plugin.enabled = True
	plugin.deployment_name = "prod"
	plugin.deployment_id = "prod-20260306-150000Z"

	app = ps.App(routes=[], plugins=[plugin], mode="subdomains")
	app.setup("https://app.example.com")

	transport = httpx.ASGITransport(app=app.fastapi)
	async with httpx.AsyncClient(
		transport=transport, base_url="https://app.example.com"
	) as client:
		response = await client.get("/_pulse/deployment")

	assert response.status_code == 200
	assert response.json() == {
		"status": "ok",
		"deployment_name": "prod",
		"deployment_id": "prod-20260306-150000Z",
	}
