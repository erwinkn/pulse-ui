from __future__ import annotations

from types import SimpleNamespace

import pulse as ps
import pytest
from pulse.context import PulseContext
from pulse_aws.constants import AFFINITY_COOKIE_NAME
from pulse_aws.plugin import AWSECSDirectivesMiddleware, AWSECSPlugin


class FakeSession:
	def __init__(self) -> None:
		self.cookies: list[dict[str, object]] = []

	def set_cookie(self, **kwargs: object) -> None:
		self.cookies.append(kwargs)


@pytest.mark.asyncio
async def test_prerender_adds_affinity_header_and_cookie():
	plugin = AWSECSPlugin()
	plugin.enabled = True
	plugin.deployment_id = "test-20260306-150000Z"
	plugin._app = SimpleNamespace(
		cookie=SimpleNamespace(
			domain="test.stoneware.rocks",
			secure=True,
			samesite="lax",
			max_age_seconds=3600,
		)
	)

	middleware = AWSECSDirectivesMiddleware(plugin)
	session = FakeSession()

	with PulseContext(app=plugin._app, session=session):
		result = await middleware.prerender(
			payload={"paths": ["/"], "routeInfo": {}},
			request=SimpleNamespace(),
			session={},
			next=lambda: _ok_prerender(),
		)

	assert isinstance(result, ps.Ok)
	assert result.payload["directives"]["headers"]["X-Pulse-Render-Affinity"] == (
		"test-20260306-150000Z"
	)
	assert result.payload["directives"]["socketio"]["headers"] == {
		"X-Pulse-Render-Affinity": "test-20260306-150000Z"
	}
	assert session.cookies == [
		{
			"name": AFFINITY_COOKIE_NAME,
			"value": "test-20260306-150000Z",
			"domain": "test.stoneware.rocks",
			"secure": True,
			"samesite": "lax",
			"max_age_seconds": 3600,
		}
	]


async def _ok_prerender() -> ps.Ok[ps.Prerender]:
	return ps.Ok(
		{
			"views": {},
			"directives": {
				"headers": {"X-Pulse-Render-Id": "render-id"},
				"socketio": {
					"auth": {"render_id": "render-id"},
					"headers": {},
				},
			},
		}
	)
