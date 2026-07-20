from __future__ import annotations

import pulse as ps
import pytest
from pulse_railway import RailwaySessionStore
from pulse_railway.config import RailwayProject
from pulse_railway.plugin import RailwayPlugin, RailwayPluginError


def test_railway_plugin_from_app() -> None:
	plugin = RailwayPlugin(
		dockerfile="Dockerfile",
		project="stoneware",
		environment="staging",
		router_service="router",
		janitor_service="janitor",
		redis_service="redis",
		service_prefix="pulse-",
	)
	app = ps.App(
		routes=[],
		plugins=[plugin],
	)

	assert RailwayPlugin.from_app(app) is plugin
	assert plugin.app is app
	assert plugin.project == "stoneware"
	assert plugin.environment == "staging"
	assert plugin.dockerfile == "Dockerfile"
	assert plugin.web_root == app.codegen.cfg.web_root
	assert plugin.uses_railway_session_store is False
	assert plugin.router_service_name == "pulse-router"
	assert plugin.janitor_service_name == "pulse-janitor"
	assert plugin.redis_service_name == "pulse-redis"
	assert plugin.service_prefix == "pulse-"


def test_railway_plugin_allows_project_to_come_from_elsewhere() -> None:
	plugin = RailwayPlugin(dockerfile="Dockerfile")
	app = ps.App(routes=[], plugins=[plugin])

	assert RailwayPlugin.from_app(app) is plugin
	assert plugin.project is None
	assert plugin.environment is None
	assert plugin.dockerfile == "Dockerfile"
	assert plugin.web_root == app.codegen.cfg.web_root
	assert plugin.uses_railway_session_store is False
	assert plugin.router_service_name == "pulse-router"
	assert plugin.janitor_service_name == "pulse-janitor"
	assert plugin.redis_service_name == "pulse-redis"
	assert plugin.service_prefix is None


def test_railway_plugin_does_not_prefix_stable_services_by_default() -> None:
	plugin = RailwayPlugin(dockerfile="Dockerfile", router_service="api")
	ps.App(routes=[], plugins=[plugin])

	assert plugin.router_service_name == "api"
	assert plugin.janitor_service_name == "pulse-janitor"
	assert plugin.redis_service_name == "pulse-redis"
	assert plugin.service_prefix is None


def test_railway_plugin_preserves_old_prefixing_for_default_service_names() -> None:
	plugin = RailwayPlugin(dockerfile="Dockerfile", service_prefix="foo-")
	ps.App(routes=[], plugins=[plugin])

	assert plugin.router_service_name == "foo-router"
	assert plugin.janitor_service_name == "foo-janitor"
	assert plugin.redis_service_name == "foo-redis"
	assert plugin.service_prefix == "foo-"


def test_railway_project_resolves_default_service_names() -> None:
	project = RailwayProject(
		project_id="project",
		environment_id="env",
		token="token",
		service_name="Pulse Router",
	)

	assert project.service_name == "pulse-router"
	assert project.janitor_service_name == "pulse-router-janitor"
	assert project.redis_service_name == "pulse-router-redis"
	assert project.env_service_name == "pulse-env"


def test_railway_project_preserves_explicit_service_names() -> None:
	project = RailwayProject(
		project_id="project",
		environment_id="env",
		token="token",
		service_name="api",
		janitor_service_name="pulse-janitor",
		redis_service_name="pulse-redis",
		env_service_name="pulse-env",
	)

	assert project.service_name == "api"
	assert project.janitor_service_name == "pulse-janitor"
	assert project.redis_service_name == "pulse-redis"
	assert project.env_service_name == "pulse-env"


def test_railway_project_omits_redis_service_for_external_redis() -> None:
	project = RailwayProject(
		project_id="project",
		environment_id="env",
		token="token",
		redis_url="redis://external.example:6379",
	)

	assert project.redis_service_name is None


def test_railway_project_normalizes_public_origin() -> None:
	project = RailwayProject(
		project_id="project",
		environment_id="env",
		token="token",
		public_origin="HTTPS://APP.EXAMPLE.COM:443/",
	)

	assert project.public_origin == "https://app.example.com"


@pytest.mark.parametrize(
	"public_origin",
	[
		"http://app.example.com",
		"app.example.com",
		"https://app.example.com/path",
		"https://app.example.com?preview=true",
	],
)
def test_railway_project_rejects_invalid_public_origin(public_origin: str) -> None:
	with pytest.raises(ValueError, match="public_origin"):
		RailwayProject(
			project_id="project",
			environment_id="env",
			token="token",
			public_origin=public_origin,
		)


def test_railway_plugin_exposes_plugin_deployment_name() -> None:
	plugin = RailwayPlugin(dockerfile="Dockerfile", deployment_name="staging")
	ps.App(routes=[], plugins=[plugin])

	assert plugin.deployment_name == "staging"


def test_railway_plugin_exposes_plugin_image_repository() -> None:
	plugin = RailwayPlugin(
		dockerfile="Dockerfile", image_repository="ghcr.io/acme/stoneware-v3"
	)
	ps.App(routes=[], plugins=[plugin])

	assert plugin.image_repository == "ghcr.io/acme/stoneware-v3"


def test_railway_plugin_exposes_app_public_origin(monkeypatch) -> None:
	monkeypatch.setenv("PULSE_ENV", "ci")
	plugin = RailwayPlugin(dockerfile="Dockerfile")
	app = ps.App(
		routes=[],
		plugins=[plugin],
		public_origin="https://app.example.com",
	)

	RailwayPlugin.from_app(app)

	assert plugin.public_origin == "https://app.example.com"


def test_railway_plugin_allows_cli_dockerfile_override() -> None:
	plugin = RailwayPlugin()
	ps.App(routes=[], plugins=[plugin])

	assert plugin.dockerfile is None


def test_railway_plugin_detects_railway_session_store() -> None:
	plugin = RailwayPlugin()
	app = ps.App(
		routes=[],
		plugins=[plugin],
		session_store=RailwaySessionStore(),
	)

	RailwayPlugin.from_app(app)

	assert plugin.uses_railway_session_store is True


def test_railway_plugin_requires_plugin() -> None:
	app = ps.App(routes=[])

	with pytest.raises(RailwayPluginError, match="RailwayPlugin not found"):
		RailwayPlugin.from_app(app)


def test_railway_plugin_app_properties_require_app() -> None:
	plugin = RailwayPlugin()

	with pytest.raises(RailwayPluginError, match="not attached"):
		_ = plugin.public_origin
	with pytest.raises(RailwayPluginError, match="not attached"):
		_ = plugin.web_root
	with pytest.raises(RailwayPluginError, match="not attached"):
		_ = plugin.uses_railway_session_store


def test_railway_plugin_rejects_multiple_apps() -> None:
	plugin = RailwayPlugin()
	first_app = ps.App(routes=[], plugins=[plugin])
	second_app = ps.App(routes=[], plugins=[plugin])
	RailwayPlugin.from_app(first_app)

	with pytest.raises(RailwayPluginError, match="already attached"):
		RailwayPlugin.from_app(second_app)
