from __future__ import annotations

import pulse as ps
import pytest
from pulse_railway.plugin import RailwayPlugin
from pulse_railway.target import (
	RailwayDeployTarget,
	RailwayDeployTargetError,
	railway_deploy_target_from_app,
)


def test_railway_deploy_target_from_app() -> None:
	app = ps.App(
		routes=[],
		plugins=[
			RailwayPlugin(
				project_id="project",
				environment_id="environment",
				router_service="router",
				janitor_service="janitor",
				redis_service="redis",
				service_prefix="pulse-",
			)
		],
	)

	target = railway_deploy_target_from_app(app)

	assert target == RailwayDeployTarget(
		project_id="project",
		environment_id="environment",
		router_service_name="pulse-router",
		janitor_service_name="pulse-janitor",
		redis_service_name="pulse-redis",
		service_prefix="pulse-",
	)


def test_railway_deploy_target_requires_configured_plugin() -> None:
	app = ps.App(routes=[], plugins=[RailwayPlugin()])

	with pytest.raises(RailwayDeployTargetError, match="project_id is required"):
		railway_deploy_target_from_app(app)
