"""Configuration dataclasses for Pulse AWS deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DockerBuild:
	"""Docker build configuration.

	Attributes:
	    dockerfile_path: Path to the Dockerfile
	    context_path: Path to the Docker build context directory
	    build_args: Additional build arguments to pass to docker build
	"""

	dockerfile_path: Path
	context_path: Path
	build_args: dict[str, str] = field(default_factory=dict)


@dataclass
class TaskConfig:
	"""ECS task configuration.

	Attributes:
	    cpu: CPU units (256, 512, 1024, etc.)
	    memory: Memory in MB (512, 1024, 2048, etc.)
	    desired_count: Number of tasks to run
	    env_vars: Additional environment variables for the task
	    drain_poll_seconds: Seconds between SSM state polling (default: 5)
	    drain_grace_seconds: Grace period before ShutdownReady=1 (default: 20)
	    drain_health_fail_after_seconds: Seconds before health fails when draining (default: 120)
	"""

	cpu: str = "256"
	memory: str = "512"
	desired_count: int = 2
	env_vars: dict[str, str] = field(default_factory=dict)
	drain_poll_seconds: int = 5
	drain_grace_seconds: int = 20
	drain_health_fail_after_seconds: int = 120


@dataclass
class ReaperConfig:
	"""Reaper Lambda configuration for automated cleanup.

	Attributes:
	    schedule_minutes: How often the reaper runs (default: 1 for testing, 5 for production)
	    consecutive_periods: Consecutive periods with ShutdownReady=1 before cleanup (default: 2)
	    period_seconds: CloudWatch metric period duration in seconds (default: 60)
	    min_age_seconds: Minimum service age before cleanup (default: 60)
	    max_age_hours: Maximum service age before forced cleanup (default: 1.0)
	"""

	schedule_minutes: int = 1
	consecutive_periods: int = 2
	period_seconds: int = 60
	min_age_seconds: int = 60
	max_age_hours: float = 1.0


@dataclass
class HealthCheckConfig:
	"""ALB health check configuration.

	Attributes:
	    path: Path for ALB health checks
	    interval_seconds: Seconds between health checks
	    timeout_seconds: Health check timeout in seconds
	    healthy_threshold: Consecutive successes to be healthy
	    unhealthy_threshold: Consecutive failures to be unhealthy
	    wait_for_health: Wait for targets to be healthy before switching traffic
	    min_healthy_targets: Minimum healthy targets required before switching
	    task_grace_period_seconds: Grace period per task after exiting initial state (default: 60)
	"""

	path: str = "/_health"
	interval_seconds: int = 30
	timeout_seconds: int = 5
	healthy_threshold: int = 2
	unhealthy_threshold: int = 3
	wait_for_health: bool = True
	min_healthy_targets: int = 2
	task_grace_period_seconds: int = 60


__all__ = [
	"DockerBuild",
	"TaskConfig",
	"ReaperConfig",
	"HealthCheckConfig",
]
