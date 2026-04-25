from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pulse as ps

from pulse_railway.plugin import RailwayPlugin
from pulse_railway.session import RailwayRedisSessionStore


class RailwayDeployTargetError(ValueError):
	pass


@dataclass(slots=True, frozen=True)
class RailwayDeployTarget:
	project: str | None
	environment: str | None
	deployment_name: str | None
	image_repository: str | None
	server_address: str | None
	dockerfile: str | None
	web_root: Path
	uses_railway_session_store: bool
	router_service_name: str
	janitor_service_name: str
	redis_service_name: str
	service_prefix: str | None


def railway_deploy_target_from_app(app: ps.App) -> RailwayDeployTarget:
	plugins = [plugin for plugin in app.plugins if isinstance(plugin, RailwayPlugin)]
	if not plugins:
		raise RailwayDeployTargetError("RailwayPlugin not found on app")
	if len(plugins) > 1:
		raise RailwayDeployTargetError("expected exactly one RailwayPlugin on app")
	plugin = plugins[0]
	return RailwayDeployTarget(
		project=plugin.project,
		environment=plugin.environment,
		deployment_name=plugin.deployment_name,
		image_repository=plugin.image_repository,
		server_address=app.server_address,
		dockerfile=plugin.dockerfile,
		web_root=app.codegen.cfg.web_root,
		uses_railway_session_store=isinstance(
			app.session_store, RailwayRedisSessionStore
		),
		router_service_name=plugin.router_service_name,
		janitor_service_name=plugin.janitor_service_name,
		redis_service_name=plugin.redis_service_name,
		service_prefix=plugin.service_prefix,
	)


__all__ = [
	"RailwayDeployTarget",
	"RailwayDeployTargetError",
	"railway_deploy_target_from_app",
]
