from __future__ import annotations

import pulse as ps
import pytest
from pulse_railway import RailwaySessionStore
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
				dockerfile="Dockerfile",
				project="stoneware",
				environment="staging",
				router_service="router",
				janitor_service="janitor",
				redis_service="redis",
				service_prefix="pulse-",
			)
		],
	)

	target = railway_deploy_target_from_app(app)

	assert target == RailwayDeployTarget(
		project="stoneware",
		environment="staging",
		deployment_name=None,
		image_repository=None,
		server_address=None,
		dockerfile="Dockerfile",
		web_root=app.codegen.cfg.web_root,
		uses_railway_session_store=False,
		router_service_name="pulse-router",
		janitor_service_name="pulse-janitor",
		redis_service_name="pulse-redis",
		service_prefix="pulse-",
	)


def test_railway_deploy_target_allows_project_to_come_from_elsewhere() -> None:
	app = ps.App(routes=[], plugins=[RailwayPlugin(dockerfile="Dockerfile")])

	assert railway_deploy_target_from_app(app) == RailwayDeployTarget(
		project=None,
		environment=None,
		deployment_name=None,
		image_repository=None,
		server_address=None,
		dockerfile="Dockerfile",
		web_root=app.codegen.cfg.web_root,
		uses_railway_session_store=False,
		router_service_name="pulse-router",
		janitor_service_name="pulse-janitor",
		redis_service_name="pulse-redis",
		service_prefix=None,
	)


def test_railway_deploy_target_does_not_prefix_stable_services_by_default() -> None:
	app = ps.App(
		routes=[],
		plugins=[RailwayPlugin(dockerfile="Dockerfile", router_service="api")],
	)

	assert railway_deploy_target_from_app(app) == RailwayDeployTarget(
		project=None,
		environment=None,
		deployment_name=None,
		image_repository=None,
		server_address=None,
		dockerfile="Dockerfile",
		web_root=app.codegen.cfg.web_root,
		uses_railway_session_store=False,
		router_service_name="api",
		janitor_service_name="pulse-janitor",
		redis_service_name="pulse-redis",
		service_prefix=None,
	)


def test_railway_deploy_target_preserves_old_prefixing_for_default_service_names() -> (
	None
):
	app = ps.App(
		routes=[],
		plugins=[RailwayPlugin(dockerfile="Dockerfile", service_prefix="foo-")],
	)

	assert railway_deploy_target_from_app(app) == RailwayDeployTarget(
		project=None,
		environment=None,
		deployment_name=None,
		image_repository=None,
		server_address=None,
		dockerfile="Dockerfile",
		web_root=app.codegen.cfg.web_root,
		uses_railway_session_store=False,
		router_service_name="foo-router",
		janitor_service_name="foo-janitor",
		redis_service_name="foo-redis",
		service_prefix="foo-",
	)


def test_railway_deploy_target_exposes_plugin_deployment_name() -> None:
	app = ps.App(
		routes=[],
		plugins=[RailwayPlugin(dockerfile="Dockerfile", deployment_name="staging")],
	)

	assert railway_deploy_target_from_app(app) == RailwayDeployTarget(
		project=None,
		environment=None,
		deployment_name="staging",
		image_repository=None,
		server_address=None,
		dockerfile="Dockerfile",
		web_root=app.codegen.cfg.web_root,
		uses_railway_session_store=False,
		router_service_name="pulse-router",
		janitor_service_name="pulse-janitor",
		redis_service_name="pulse-redis",
		service_prefix=None,
	)


def test_railway_deploy_target_exposes_plugin_image_repository() -> None:
	app = ps.App(
		routes=[],
		plugins=[
			RailwayPlugin(
				dockerfile="Dockerfile", image_repository="ghcr.io/acme/stoneware-v3"
			)
		],
	)

	assert railway_deploy_target_from_app(app) == RailwayDeployTarget(
		project=None,
		environment=None,
		deployment_name=None,
		image_repository="ghcr.io/acme/stoneware-v3",
		server_address=None,
		dockerfile="Dockerfile",
		web_root=app.codegen.cfg.web_root,
		uses_railway_session_store=False,
		router_service_name="pulse-router",
		janitor_service_name="pulse-janitor",
		redis_service_name="pulse-redis",
		service_prefix=None,
	)


def test_railway_deploy_target_exposes_app_server_address(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_ENV", "ci")
	app = ps.App(
		routes=[],
		plugins=[RailwayPlugin(dockerfile="Dockerfile")],
		server_address="https://app.example.com",
	)

	assert railway_deploy_target_from_app(app).server_address == (
		"https://app.example.com"
	)


def test_railway_deploy_target_allows_cli_dockerfile_override() -> None:
	app = ps.App(routes=[], plugins=[RailwayPlugin()])

	assert railway_deploy_target_from_app(app).dockerfile is None


def test_railway_deploy_target_detects_railway_session_store() -> None:
	app = ps.App(
		routes=[],
		plugins=[RailwayPlugin()],
		session_store=RailwaySessionStore(),
	)

	assert railway_deploy_target_from_app(app).uses_railway_session_store is True


def test_railway_deploy_target_requires_plugin() -> None:
	app = ps.App(routes=[])

	with pytest.raises(RailwayDeployTargetError, match="RailwayPlugin not found"):
		railway_deploy_target_from_app(app)
