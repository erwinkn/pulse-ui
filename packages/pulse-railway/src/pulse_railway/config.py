"""Configuration dataclasses for Pulse Railway deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pulse_railway.constants import (
	DEFAULT_BACKEND_HEALTH_PATH,
	DEFAULT_DRAIN_TTL_SECONDS,
	DEFAULT_JANITOR_CRON_SCHEDULE,
	DEFAULT_REDIS_PREFIX,
	DEFAULT_REDIS_TEMPLATE_CODE,
	DEFAULT_ROUTER_HEALTH_PATH,
	DEFAULT_ROUTER_PORT,
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
	service_prefix: str | None = None
	backend_replicas: int = 1
	router_port: int = DEFAULT_ROUTER_PORT
	router_replicas: int = 1
	server_address: str | None = None
	redis_url: str | None = None
	redis_prefix: str = DEFAULT_REDIS_PREFIX
	redis_service_name: str | None = None
	redis_template_code: str = DEFAULT_REDIS_TEMPLATE_CODE
	janitor_service_name: str | None = None
	janitor_replicas: int = 1
	janitor_cron_schedule: str = DEFAULT_JANITOR_CRON_SCHEDULE
	drain_ttl_seconds: int = DEFAULT_DRAIN_TTL_SECONDS
	env_vars: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RailwayInternals:
	"""Resolved runtime state derived from RailwayProject."""

	service_prefix: str | None
	internal_token: str
	redis_url: str | None = None


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
