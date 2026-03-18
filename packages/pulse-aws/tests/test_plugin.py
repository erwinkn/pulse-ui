from __future__ import annotations

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
