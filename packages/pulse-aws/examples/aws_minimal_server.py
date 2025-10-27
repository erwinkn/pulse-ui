"""
Minimal FastAPI server for proving ECS deployment workflow.

This server reads DEPLOYMENT_ID from environment and exposes:
- GET / → returns deployment info with affinity header
- GET /_health → health check for ECS/ALB
- POST /drain → authenticated endpoint to trigger graceful drain
"""

import os
import time
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse

app = FastAPI()

# Read configuration from environment
DEPLOYMENT_ID = os.environ.get("DEPLOYMENT_ID", "unknown")
DRAIN_SECRET = os.environ.get("DRAIN_SECRET", "")
# Validate authorization
if not DRAIN_SECRET:
	raise HTTPException(status_code=500, detail="DRAIN_SECRET not configured on server")
DRAIN_HEALTH_FAIL_AFTER_SECONDS = int(
	os.environ.get("DRAIN_HEALTH_FAIL_AFTER_SECONDS", "120")
)

# Draining state
_draining = False
_drain_started_at: float | None = None


@app.get("/")
async def root(response: Response) -> dict[str, str | bool]:
	"""
	Root endpoint that returns deployment info and sets affinity header.
	"""
	response.headers["X-Pulse-Render-Affinity"] = DEPLOYMENT_ID
	return {"deployment_id": DEPLOYMENT_ID, "ok": True}


@app.get("/_health")
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


@app.post("/drain")
async def drain(
	authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
	"""
	Authenticated drain endpoint.

	Requires 'Authorization: Bearer <DRAIN_SECRET>' header.
	On first call, marks the server as draining. After DRAIN_HEALTH_FAIL_AFTER_SECONDS,
	/_health will return 503 to simulate graceful drain.
	"""
	global _draining, _drain_started_at

	if not authorization or not authorization.startswith("Bearer "):
		raise HTTPException(
			status_code=401, detail="Missing or invalid Authorization header"
		)

	token = authorization.replace("Bearer ", "", 1)
	if token != DRAIN_SECRET:
		raise HTTPException(status_code=403, detail="Invalid drain secret")

	# Mark as draining
	if _draining:
		return {"status": "already_draining"}

	_draining = True
	_drain_started_at = time.time()
	return {"status": "ok"}
