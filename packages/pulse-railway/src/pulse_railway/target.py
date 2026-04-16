from __future__ import annotations

from dataclasses import dataclass

import pulse as ps

from pulse_railway.plugin import RailwayPlugin


class RailwayDeployTargetError(ValueError):
	pass


@dataclass(slots=True, frozen=True)
class RailwayDeployTarget:
	project_id: str | None
	environment_id: str | None
	deployment_name: str | None
	image_repository: str | None
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
		project_id=plugin.project_id,
		environment_id=plugin.environment_id,
		deployment_name=plugin.deployment_name,
		image_repository=plugin.image_repository,
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
