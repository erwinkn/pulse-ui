"""Configuration dataclasses for Pulse Railway deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pulse_railway.constants import (
	DEFAULT_BACKEND_HEALTH_PATH,
	DEFAULT_BACKEND_PORT,
	DEFAULT_DRAIN_GRACE_SECONDS,
	DEFAULT_JANITOR_CRON_SCHEDULE,
	DEFAULT_MAX_DRAIN_AGE_SECONDS,
	DEFAULT_REDIS_PREFIX,
	DEFAULT_REDIS_TEMPLATE_CODE,
	DEFAULT_ROUTER_HEALTH_PATH,
	DEFAULT_ROUTER_PORT,
	DEFAULT_SERVICE_PREFIX,
	DEFAULT_WEBSOCKET_HEARTBEAT_SECONDS,
	DEFAULT_WEBSOCKET_TTL_SECONDS,
)


@dataclass
class DockerBuild:
	"""Docker build configuration."""

	dockerfile_path: Path
	context_path: Path
	build_args: dict[str, str] = field(default_factory=dict)
	platform: str = "linux/amd64"
	image_repository: str | None = None


@dataclass
class RailwayProject:
	"""Railway project configuration."""

	project_id: str
	environment_id: str
	token: str
	service_name: str
	service_prefix: str = DEFAULT_SERVICE_PREFIX
	backend_port: int = DEFAULT_BACKEND_PORT
	backend_replicas: int = 1
	router_port: int = DEFAULT_ROUTER_PORT
	router_replicas: int = 1
	router_image: str | None = None
	server_address: str | None = None
	redis_url: str | None = None
	redis_prefix: str = DEFAULT_REDIS_PREFIX
	redis_service_name: str | None = None
	redis_template_code: str = DEFAULT_REDIS_TEMPLATE_CODE
	janitor_service_name: str | None = None
	janitor_image: str | None = None
	janitor_replicas: int = 1
	janitor_cron_schedule: str = DEFAULT_JANITOR_CRON_SCHEDULE
	drain_grace_seconds: int = DEFAULT_DRAIN_GRACE_SECONDS
	max_drain_age_seconds: int = DEFAULT_MAX_DRAIN_AGE_SECONDS
	websocket_heartbeat_seconds: int = DEFAULT_WEBSOCKET_HEARTBEAT_SECONDS
	websocket_ttl_seconds: int = DEFAULT_WEBSOCKET_TTL_SECONDS
	env_vars: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RailwayInternals:
	"""Resolved runtime state derived from RailwayProject."""

	service_prefix: str
	internal_token: str
	redis_url: str | None = None
	redis_public_url: str | None = None

	@property
	def tracker_url(self) -> str | None:
		return self.redis_public_url or self.redis_url


@dataclass
class ServiceInstanceConfig:
	"""Railway service-instance settings."""

	healthcheck_path: str
	healthcheck_timeout: int = 60
	overlap_seconds: int = 30


DEFAULT_BACKEND_INSTANCE = ServiceInstanceConfig(
	healthcheck_path=DEFAULT_BACKEND_HEALTH_PATH
)
DEFAULT_ROUTER_INSTANCE = ServiceInstanceConfig(
	healthcheck_path=DEFAULT_ROUTER_HEALTH_PATH
)


__all__ = [
	"DEFAULT_BACKEND_INSTANCE",
	"DEFAULT_ROUTER_INSTANCE",
	"DockerBuild",
	"RailwayInternals",
	"RailwayProject",
	"ServiceInstanceConfig",
]
