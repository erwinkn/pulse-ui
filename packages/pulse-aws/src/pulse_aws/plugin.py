"""
AWS ECS Plugin for Pulse applications.

This plugin provides:
- ECS task ID discovery
- SSM-based deployment state polling
- Graceful draining with CloudWatch EMF metrics
- Header-based affinity via directives
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, override

import pulse as ps
import requests

logger = logging.getLogger(__name__)


class AWSECSPlugin(ps.Plugin):
	"""Plugin for AWS ECS deployments with graceful draining support."""

	priority: int = 100  # High priority to run before other plugins
	deployment_name: str
	deployment_id: str
	drain_poll_seconds: int
	drain_grace_seconds: int
	_draining: bool
	_drain_started_at: float | None
	_shutdown_ready: bool
	_task_id: str
	_app: ps.App | None
	_poll_thread: threading.Thread | None

	def __init__(
		self,
		deployment_name: str,
		deployment_id: str,
		*,
		drain_poll_seconds: int = 5,
		drain_grace_seconds: int = 20,
	):
		"""Initialize the AWS ECS plugin.

		Args:
				deployment_name: Stable environment identifier (e.g., "prod", "dev")
				deployment_id: Version-specific deployment ID (e.g., "20251027-183000Z")
				drain_poll_seconds: Seconds between SSM state polls (default: 5)
				drain_grace_seconds: Grace period after draining before shutdown ready (default: 20)
		"""
		self.deployment_name = deployment_name
		self.deployment_id = deployment_id
		self.drain_poll_seconds = drain_poll_seconds
		self.drain_grace_seconds = drain_grace_seconds

		# Draining state
		self._draining = False
		self._drain_started_at = None
		self._shutdown_ready = False
		self._task_id = "unknown"
		self._app = None
		self._poll_thread = None

	@override
	def on_startup(self, app: ps.App) -> None:
		"""Start background polling thread on app startup."""
		self._app = app

		# Discover task ID
		try:
			self._task_id = self._discover_task_id()
			logger.info(
				f"🆔 Task ID: {self._task_id}, Deployment: {self.deployment_name}/{self.deployment_id}"
			)
		except Exception as e:
			logger.warning(f"⚠️  Failed to discover task ID: {e}")
			# Continue without task ID (for local development)

		# Start background polling thread
		self._poll_thread = threading.Thread(target=self._poll_ssm_state, daemon=True)
		self._poll_thread.start()

	@property
	def task_id(self) -> str:
		"""Get the current ECS task ID."""
		return self._task_id

	@override
	def middleware(self) -> list[ps.PulseMiddleware]:
		"""Return middleware that blocks new RenderSession creation when draining and adds directives."""
		return [AWSECSDirectivesMiddleware(self)]

	def _discover_task_id(self) -> str:
		"""Discover ECS task ID from container metadata endpoint."""
		meta_uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
		if not meta_uri:
			# Not running in ECS, use fallback
			task_id = os.environ.get("TASK_ID", "unknown")
			if task_id == "unknown":
				logger.warning(
					"ECS_CONTAINER_METADATA_URI_V4 not set and TASK_ID not provided, using 'unknown'"
				)
			return task_id

		for attempt in range(3):
			try:
				task_resp = requests.get(f"{meta_uri}/task", timeout=2).json()
				task_arn = task_resp["TaskARN"]
				# Extract task ID from ARN (format: arn:aws:ecs:region:account:task/cluster/task-id)
				return task_arn.split("/")[-1]
			except Exception as e:
				if attempt == 2:
					raise RuntimeError(
						f"Failed to discover task ID after 3 attempts: {e}"
					) from e
				time.sleep(0.5)

		raise RuntimeError(
			"Failed to discover task ID (this code should be unreachable)"
		)

	def _emit_emf(self, shutdown_ready_value: int) -> None:
		"""Emit CloudWatch Embedded Metric Format JSON to stdout."""
		payload = {
			"_aws": {
				"Timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
				"CloudWatchMetrics": [
					{
						"Namespace": "App/Drain",
						"Dimensions": [["deployment_name", "deployment_id", "task_id"]],
						"Metrics": [{"Name": "ShutdownReady", "Unit": "Count"}],
					}
				],
			},
			"deployment_name": self.deployment_name,
			"deployment_id": self.deployment_id,
			"task_id": self._task_id,
			"ShutdownReady": shutdown_ready_value,
		}
		print(json.dumps(payload), flush=True)

	def _poll_ssm_state(self) -> None:
		"""Background thread that polls SSM for deployment state and emits EMF metrics."""
		# Import boto3 here to avoid startup overhead if not in AWS
		try:
			import boto3
		except ImportError:
			logger.warning("⚠️  boto3 not available, skipping SSM polling")
			return

		ssm = boto3.client("ssm")
		param_name = f"/apps/{self.deployment_name}/{self.deployment_id}/state"

		logger.info(
			f"🔍 Starting SSM state polling: {param_name} (every {self.drain_poll_seconds}s)"
		)

		while True:
			try:
				# Read SSM parameter
				response = ssm.get_parameter(Name=param_name)
				state = response["Parameter"]["Value"]
				now = time.time()

				if state == "draining":
					if not self._draining:
						# First time seeing draining state
						self._draining = True
						self._drain_started_at = now
						logger.info(
							f"🚨 Deployment marked as DRAINING (grace period: {self.drain_grace_seconds}s)"
						)

					# Check if grace period has elapsed
					elapsed = now - (self._drain_started_at or now)
					if elapsed >= self.drain_grace_seconds:
						# Check active session count
						active_sessions = 0
						if self._app:
							active_sessions = len(self._app.render_sessions)

						if active_sessions == 0:
							if not self._shutdown_ready:
								self._shutdown_ready = True
								logger.info(
									f"✅ Grace period elapsed ({elapsed:.0f}s >= {self.drain_grace_seconds}s) "
									+ "and no active sessions, ShutdownReady=1"
								)
								self._emit_emf(1)
						else:
							# Still have active sessions, emit 0
							if self._shutdown_ready:
								# Reset if sessions reconnect
								self._shutdown_ready = False
								logger.info(
									f"⚠️  Active sessions detected ({active_sessions}), resetting ShutdownReady"
								)
							self._emit_emf(0)
					else:
						# Grace period not elapsed yet, emit 0
						self._emit_emf(0)
				else:
					# Not draining, emit 0
					if self._draining:
						logger.info("✅ Deployment state changed back to active")
						self._draining = False
						self._drain_started_at = None
						self._shutdown_ready = False
					self._emit_emf(0)

			except Exception as e:
				logger.error(f"❌ Error polling SSM state: {e}", exc_info=True)
				# Emit 0 on error to avoid false positives
				self._emit_emf(0)

			time.sleep(self.drain_poll_seconds)


class AWSECSDirectivesMiddleware(ps.PulseMiddleware):
	"""Middleware that adds directives to the prerender response."""

	plugin: AWSECSPlugin

	def __init__(self, plugin: AWSECSPlugin):
		self.plugin = plugin

	@override
	def prerender(
		self,
		*,
		payload: ps.PrerenderPayload,
		result: ps.PrerenderResult,
		request: ps.PulseRequest,
		session: dict[str, Any],
		next: Callable[[], ps.PrerenderResult],
	) -> ps.PrerenderResult:
		"""Add AWS ECS deployment affinity header to prerender directives."""
		res = next()

		directives = res["directives"]
		# Add deployment ID header for ALB affinity routing (HTTP requests)
		directives["headers"]["X-Pulse-Render-Affinity"] = self.plugin.deployment_id
		# Add deployment ID header for Socket.IO connections (WebSocket affinity)
		directives["socketio"]["headers"]["X-Pulse-Render-Affinity"] = (
			self.plugin.deployment_id
		)
		return res


__all__ = ["AWSECSPlugin"]
