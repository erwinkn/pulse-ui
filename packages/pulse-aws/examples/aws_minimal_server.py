"""
Minimal FastAPI server for proving ECS deployment workflow.

This server reads DEPLOYMENT_ID from environment and exposes:
- GET / → returns deployment info with affinity header
- GET /_pulse/health → health check for ECS/ALB

For the reaper-based deployment workflow, this server:
- Discovers its ECS task ID from the metadata endpoint
- Polls SSM Parameter Store for deployment state
- Emits CloudWatch EMF metrics (ShutdownReady) to stdout
- Gracefully drains when SSM state transitions to "draining"
"""

import json
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import requests
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Lifespan context manager for startup/shutdown events."""
	global _task_id

	# Startup: Discover task ID and start background SSM polling
	_task_id = _discover_task_id()
	print(f"🆔 Task ID: {_task_id}", flush=True)
	print(f"📦 Deployment: {DEPLOYMENT_NAME}/{DEPLOYMENT_ID}", flush=True)

	# Start background polling thread
	poll_thread = threading.Thread(target=_poll_ssm_state, daemon=True)
	poll_thread.start()

	yield

	# Shutdown (nothing to clean up - daemon thread will exit)


app = FastAPI(lifespan=lifespan)

# Read configuration from environment
DEPLOYMENT_NAME = os.environ.get("DEPLOYMENT_NAME", "unknown")
DEPLOYMENT_ID = os.environ.get("DEPLOYMENT_ID", "unknown")
DRAIN_HEALTH_FAIL_AFTER_SECONDS = int(
	os.environ.get("DRAIN_HEALTH_FAIL_AFTER_SECONDS", "120")
)
DRAIN_POLL_SECONDS = int(os.environ.get("DRAIN_POLL_SECONDS", "5"))
DRAIN_GRACE_SECONDS = int(os.environ.get("DRAIN_GRACE_SECONDS", "20"))

# Draining state
_draining = False
_drain_started_at: float | None = None
_shutdown_ready = False
_task_id = "unknown"


def _discover_task_id() -> str:
	"""Discover ECS task ID from container metadata endpoint."""
	meta_uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
	if not meta_uri:
		# Not running in ECS, use fallback
		raise RuntimeError(
			"ECS_CONTAINER_METADATA_URI_V4 not set and TASK_ID not provided"
		)

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
	raise RuntimeError("Failed to discover task ID (this code should be unreachable)")


def _emit_emf(shutdown_ready_value: int) -> None:
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
		"deployment_name": DEPLOYMENT_NAME,
		"deployment_id": DEPLOYMENT_ID,
		"task_id": _task_id,
		"ShutdownReady": shutdown_ready_value,
	}
	print(json.dumps(payload), flush=True)


def _poll_ssm_state() -> None:
	"""Background thread that polls SSM for deployment state and emits EMF metrics."""
	global _draining, _drain_started_at, _shutdown_ready

	# Import boto3 here to avoid startup overhead if not in AWS
	try:
		import boto3
	except ImportError:
		print("⚠️  boto3 not available, skipping SSM polling", flush=True)
		return

	ssm = boto3.client("ssm")
	param_name = f"/apps/{DEPLOYMENT_NAME}/{DEPLOYMENT_ID}/state"

	print(
		f"🔍 Starting SSM state polling: {param_name} (every {DRAIN_POLL_SECONDS}s)",
		flush=True,
	)

	while True:
		try:
			# Read SSM parameter
			response = ssm.get_parameter(Name=param_name)
			state = response["Parameter"]["Value"]
			now = time.time()

			if state == "draining":
				if not _draining:
					# First time seeing draining state
					_draining = True
					_drain_started_at = now
					print(
						f"🚨 Deployment marked as DRAINING (grace period: {DRAIN_GRACE_SECONDS}s)",
						flush=True,
					)

				# Check if grace period has elapsed
				elapsed = now - (_drain_started_at or now)
				if elapsed >= DRAIN_GRACE_SECONDS:
					if not _shutdown_ready:
						_shutdown_ready = True
						print(
							f"✅ Grace period elapsed ({elapsed:.0f}s >= {DRAIN_GRACE_SECONDS}s), ShutdownReady=1",
							flush=True,
						)
					_emit_emf(1)
				else:
					_emit_emf(0)
			else:
				# State is active or unknown
				if _draining:
					print(
						f"ℹ️  Deployment state changed from draining to {state}",
						flush=True,
					)
				_draining = False
				_drain_started_at = None
				_shutdown_ready = False
				_emit_emf(0)

		except ssm.exceptions.ParameterNotFound:
			# Parameter doesn't exist yet (deployment hasn't set it)
			# This is normal during initial deployment
			_emit_emf(0)
		except Exception as e:
			# Best effort - keep previous state on error
			print(f"⚠️  SSM polling error: {e}", flush=True)

		time.sleep(DRAIN_POLL_SECONDS)


@app.get("/")
async def root(response: Response) -> dict[str, str | bool]:
	"""
	Root endpoint that returns deployment info and sets affinity header.
	"""
	response.headers["X-Pulse-Render-Affinity"] = DEPLOYMENT_ID
	return {"deployment_id": DEPLOYMENT_ID, "ok": True}


@app.get("/_pulse/health")
async def health() -> JSONResponse:
	"""
	Health check endpoint for ECS/ALB target health.

	Returns 200 OK until draining has been active for DRAIN_HEALTH_FAIL_AFTER_SECONDS,
	then returns 503 to trigger deregistration.
	"""
	if _draining and _drain_started_at is not None:
		elapsed = time.time() - _drain_started_at
		if elapsed >= DRAIN_HEALTH_FAIL_AFTER_SECONDS:
			return JSONResponse(
				status_code=503,
				content={"status": "draining", "elapsed_seconds": int(elapsed)},
			)

	return JSONResponse(status_code=200, content={"status": "ok"})
