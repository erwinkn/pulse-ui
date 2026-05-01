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
from pulse_railway.railway.client import (
	normalize_service_name,
	normalize_service_prefix,
)


def default_janitor_service_name(service_name: str) -> str:
	return normalize_service_name(f"{service_name}-janitor")


def default_redis_service_name(service_name: str) -> str:
	return normalize_service_name(f"{service_name}-redis")


def default_env_service_name(service_name: str) -> str:
	candidate = service_name.strip().lower()
	if candidate.endswith("-router"):
		candidate = candidate[:-7]
	return normalize_service_name(f"{candidate}-env")


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
	service_name: str = "pulse-router"
	service_prefix: str | None = None
	backend_replicas: int = 1
	router_port: int = DEFAULT_ROUTER_PORT
	router_replicas: int = 1
	server_address: str | None = None
	redis_url: str | None = None
	redis_prefix: str = DEFAULT_REDIS_PREFIX
	redis_service_name: str | None = ""
	redis_template_code: str = DEFAULT_REDIS_TEMPLATE_CODE
	janitor_service_name: str = ""
	env_service_name: str = ""
	janitor_replicas: int = 1
	janitor_cron_schedule: str = DEFAULT_JANITOR_CRON_SCHEDULE
	drain_ttl_seconds: int = DEFAULT_DRAIN_TTL_SECONDS
	env_vars: dict[str, str] = field(default_factory=dict)

	def __post_init__(self) -> None:
		self.service_name = normalize_service_name(self.service_name or "pulse-router")
		self.service_prefix = (
			normalize_service_prefix(self.service_prefix)
			if self.service_prefix is not None and self.service_prefix.strip()
			else None
		)
		self.janitor_service_name = (
			normalize_service_name(self.janitor_service_name)
			if self.janitor_service_name
			else default_janitor_service_name(self.service_name)
		)
		if self.redis_service_name is None:
			self.redis_service_name = None
		elif self.redis_service_name:
			self.redis_service_name = normalize_service_name(self.redis_service_name)
		else:
			self.redis_service_name = (
				None
				if self.redis_url is not None
				else default_redis_service_name(self.service_name)
			)
		self.env_service_name = (
			normalize_service_name(self.env_service_name)
			if self.env_service_name
			else default_env_service_name(self.service_name)
		)


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
	"default_env_service_name",
	"default_janitor_service_name",
	"default_redis_service_name",
]
