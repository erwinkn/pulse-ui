"""
AWS ECS Plugin for Pulse applications.

This plugin provides:
- ECS task ID discovery
- SSM-based deployment state polling
- Graceful draining with SSM task readiness state
- Header-based affinity via directives
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any, override

import pulse as ps
import requests

logger = logging.getLogger(__name__)


class AWSECSPlugin(ps.Plugin):
	"""Plugin for AWS ECS deployments with graceful draining support.

	This plugin reads configuration from environment variables at app startup:
	- PULSE_AWS_DEPLOYMENT_NAME: Stable environment identifier (e.g., "prod", "dev") - Required
	- PULSE_AWS_DEPLOYMENT_ID: Version-specific deployment ID (e.g., "20251027-183000Z") - Required
	- PULSE_AWS_DRAIN_POLL_SECONDS: Seconds between SSM state polls - Required
	- PULSE_AWS_DRAIN_GRACE_SECONDS: Grace period after draining before shutdown ready - Required

	The plugin can be instantiated without environment variables present (e.g., during local development).
	Environment variables are validated when the app starts up.
	"""

	priority: int = 100  # High priority to run before other plugins
	deployment_name: str
	deployment_id: str
	drain_poll_seconds: int
	drain_grace_seconds: int
	_draining: bool
	_drain_started_at: float | None
	_shutdown_ready: bool
	_last_written_state: bool | None
	_task_id: str
	_app: ps.App | None
	_poll_thread: threading.Thread | None

	def __init__(self) -> None:
		"""Initialize the AWS ECS plugin.

		Environment variables are read and validated on app startup (on_startup hook).
		"""
		# Draining state
		self._draining = False
		self._drain_started_at = None
		self._shutdown_ready = False
		self._last_written_state = None
		self._task_id = "unknown"
		self._app = None
		self._poll_thread = None

		# Will be set from environment variables in on_startup
		self.deployment_name = ""
		self.deployment_id = ""
		self.drain_poll_seconds = 0
		self.drain_grace_seconds = 0

	@override
	def on_startup(self, app: ps.App) -> None:
		"""Start background polling thread on app startup.

		Reads and validates required environment variables:
		- PULSE_AWS_DEPLOYMENT_NAME: Required, stable environment identifier
		- PULSE_AWS_DEPLOYMENT_ID: Required, version-specific deployment ID
		- PULSE_AWS_DRAIN_POLL_SECONDS: Required, seconds between SSM state polls
		- PULSE_AWS_DRAIN_GRACE_SECONDS: Required, grace period before marking task as draining
		"""
		deployment_name = os.environ.get("PULSE_AWS_DEPLOYMENT_NAME")
		deployment_id = os.environ.get("PULSE_AWS_DEPLOYMENT_ID")
		drain_poll_seconds = os.environ.get("PULSE_AWS_DRAIN_POLL_SECONDS")
		drain_grace_seconds = os.environ.get("PULSE_AWS_DRAIN_GRACE_SECONDS")

		if not deployment_name:
			raise ValueError(
				"PULSE_AWS_DEPLOYMENT_NAME environment variable is required"
			)
		if not deployment_id:
			raise ValueError("PULSE_AWS_DEPLOYMENT_ID environment variable is required")
		if not drain_poll_seconds:
			raise ValueError(
				"PULSE_AWS_DRAIN_POLL_SECONDS environment variable is required"
			)
		if not drain_grace_seconds:
			raise ValueError(
				"PULSE_AWS_DRAIN_GRACE_SECONDS environment variable is required"
			)

		self.deployment_name = deployment_name
		self.deployment_id = deployment_id
		self.drain_poll_seconds = int(drain_poll_seconds)
		self.drain_grace_seconds = int(drain_grace_seconds)

		self._app = app

		# Discover task ID
		try:
			self._task_id = self._discover_task_id()
			print(
				f"🆔 Task ID: {self._task_id}, Deployment: {self.deployment_name}/{self.deployment_id}",
				flush=True,
			)
		except Exception as e:
			logger.warning(f"⚠️  Failed to discover task ID: {e}")
			# Continue without task ID (for local development)

		# Mark task as healthy on startup
		try:
			import boto3

			ssm = boto3.client("ssm")
			self._update_task_state(ssm, draining=False)
		except Exception as e:
			logger.warning(f"⚠️  Failed to mark task as healthy on startup: {e}")

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
			task_id = os.environ.get("PULSE_AWS_TASK_ID", "unknown")
			if task_id == "unknown":
				logger.warning(
					"ECS_CONTAINER_METADATA_URI_V4 not set and PULSE_AWS_TASK_ID not provided, using 'unknown'"
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

	def _update_task_state(self, ssm: Any, draining: bool) -> None:
		"""Update SSM parameter with task state.

		Only writes when state changes to avoid unnecessary SSM calls.
		"""
		if draining == self._last_written_state:
			# State hasn't changed, skip write
			return

		task_param_name = (
			f"/apps/{self.deployment_name}/{self.deployment_id}/tasks/{self._task_id}"
		)
		value = "draining" if draining else "healthy"

		try:
			ssm.put_parameter(
				Name=task_param_name,
				Value=value,
				Type="String",
				Overwrite=True,
			)
			self._last_written_state = draining
			print(
				f"✅ Task state updated: {task_param_name} = {value}",
				flush=True,
			)
		except Exception as e:
			logger.warning(f"⚠️  Failed to update task state in SSM: {e}")

	def _poll_ssm_state(self) -> None:
		"""Background thread that polls SSM for deployment state and updates task state."""
		# Import boto3 here to avoid startup overhead if not in AWS
		try:
			import boto3
		except ImportError:
			logger.warning("⚠️  boto3 not available, skipping SSM polling")
			return

		ssm = boto3.client("ssm")
		param_name = f"/apps/{self.deployment_name}/{self.deployment_id}/state"

		print(
			f"🔍 Starting SSM state polling: {param_name} (every {self.drain_poll_seconds}s)",
			flush=True,
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
						print(
							f"🚨 Deployment marked as DRAINING (grace period: {self.drain_grace_seconds}s)",
							flush=True,
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
								print(
									f"✅ Grace period elapsed ({elapsed:.0f}s >= {self.drain_grace_seconds}s) "
									+ "and no active sessions, marking task as draining",
									flush=True,
								)
							# Update SSM only when state changes
							self._update_task_state(ssm, draining=True)
						else:
							# Still have active sessions
							if self._shutdown_ready:
								# Reset if sessions reconnect
								self._shutdown_ready = False
								print(
									f"⚠️  Active sessions detected ({active_sessions}), marking task as healthy",
									flush=True,
								)
							self._update_task_state(ssm, draining=False)
					else:
						# Grace period not elapsed yet
						self._update_task_state(ssm, draining=False)
				else:
					# Not draining
					if self._draining:
						print("✅ Deployment state changed back to active", flush=True)
						self._draining = False
						self._drain_started_at = None
						self._shutdown_ready = False
					self._update_task_state(ssm, draining=False)

			except Exception as e:
				logger.error(f"❌ Error polling SSM state: {e}", exc_info=True)

			time.sleep(self.drain_poll_seconds)


class AWSECSDirectivesMiddleware(ps.PulseMiddleware):
	"""Middleware that adds directives to the prerender response."""

	plugin: AWSECSPlugin

	def __init__(self, plugin: AWSECSPlugin):
		self.plugin = plugin

	@override
	async def prerender(
		self,
		*,
		payload: ps.PrerenderPayload,
		request: ps.PulseRequest,
		session: dict[str, Any],
		next: Callable[[], Awaitable[ps.PrerenderResponse]],
	) -> ps.PrerenderResponse:
		"""Add AWS ECS deployment affinity header to prerender directives."""
		res = await next()

		# Only modify directives if we have an Ok result
		if isinstance(res, ps.Ok):
			directives = res.payload["directives"]
			# Add deployment ID header for ALB affinity routing (HTTP requests)
			directives["headers"]["X-Pulse-Render-Affinity"] = self.plugin.deployment_id
			# Add deployment ID header for Socket.IO connections (WebSocket affinity)
			directives["socketio"]["headers"]["X-Pulse-Render-Affinity"] = (
				self.plugin.deployment_id
			)
		# For Redirect or NotFound, just pass through
		return res


__all__ = ["AWSECSPlugin"]
