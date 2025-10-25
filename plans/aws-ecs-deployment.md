# AWS ECS + ALB Deployment Implementation Plan for Pulse

## Overview

Prepare an exec plan to implement a multi-version deployment strategy for Pulse applications using AWS ECS and Application Load Balancer. The architecture enables:

- Multiple parallel versions running simultaneously
- Sticky sessions ensuring users stay on their version
- Graceful session draining via drain endpoint
- Automatic cleanup when sessions reach zero
- Zero-downtime deployments

## Architecture

```
┌─────────────┐
│   Internet  │
└──────┬──────┘
       │
┌──────▼────────────────────────────────────────────────┐
│            Application Load Balancer                   │
│  - SSL Termination                                     │
│  - WebSocket Support                                   │
│  - Health Checks: /health                              │
│  - Target Groups with sticky sessions                  │
└──────┬────────────────────────────────────────────────┘
       │
       ├──► Target Group v123 (weight=100) ──────────────► ECS Service v123
       │     - Receives all new traffic                     ├─ Task 1 (healthy, active)
       │                                                      └─ Task 2 (healthy, active)
       │
       ├──► Target Group v122 (weight=0) ────────────────► ECS Service v122
       │     - Draining (no new connections)                └─ Task 1 (draining, 2 sessions)
       │     - POST /_pulse/admin/drain was sent                → fails health when 0 sessions
       │
       └──► Target Group v121 (weight=0) ────────────────► ECS Service v121
             - Draining (no new connections)                └─ Task 1 (draining, 0 sessions)
             - Failing health checks                            → ECS will SIGTERM soon
                                                                → graceful shutdown

┌────────────────────────────────────────────────────────┐
│              Supporting Infrastructure                 │
├────────────────────────────────────────────────────────┤
│ ECR: Docker image registry                             │
│ CloudWatch Logs: Application logs (optional)           │
│ Secrets Manager: PULSE_SECRET (optional)               │
└────────────────────────────────────────────────────────┘
```

## Deployment Flow

1. Deploy new version v124
   - Create ECS service v124 with 2 tasks
   - Create target group v124
   - Wait for tasks to be healthy

2. Switch traffic
   - Update ALB listener: v124 weight=100, v123 weight=0
   - New connections → v124, existing sessions → v123 (sticky)

3. Drain old version v123
   - POST /_pulse/admin/drain to v123 tasks
   - v123 stops accepting new WebSocket connections
   - v123 stops creating new RenderSessions
   - Existing sessions continue normally

4. Automatic cleanup
   - v123 has 0 active RenderSessions → /health starts returning 503
   - ALB marks v123 unhealthy
   - ECS sends SIGTERM to v123 tasks
   - v123 executes graceful shutdown (close connections, cleanup)
   - ECS removes v123 service (manual or scripted)

## Core Components

### 1. Pulse Framework Components

#### 1.1 Deployment Plugin (`pulse/deploy/aws.py`)

**Purpose:** Add admin drain endpoint and integrate with App draining state

```python
from fastapi import Request, Response
from typing import Callable

import os

import pulse as ps

class DeployToECS(ps.Plugin):
    """Plugin that enables AWS ECS deployment draining."""

    def __init__(self, secret: str | Callable[[], str]):
        """
        Args:
            drain_token: Secret token for drain endpoint, or factory function
        """
        self._secret: str | Callable[[], str] = secret

    def secret(self):
      if callable(self._secret):
        return self._secret()
      else:
        return self._secret

    def on_setup(self, app: ps.App):
      app.fastapi.post(
        "/_pulse/admin/drain",
        lambda request: self.drain_endpoint(app, request)
      )

    def drain_endpoint(self, app: ps.App, request: Request):
        """Admin endpoint to mark app as draining.

        POST /_pulse/admin/drain
        Authorization: Bearer <PULSE_DRAIN_TOKEN>

        Returns 200 if drain initiated, 401 if unauthorized.
        """
        # Check authorization
        if request.method != "POST":
          return Response("Method not allowed", status_code=405)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return Response("Unauthorized", status_code=401)

        token = auth_header[7:]  # Remove "Bearer " prefix
        if token != self.secret():
            return Response("Unauthorized", status_code=401)

        app.set_draining(True)

        return Response({
            "status": "draining",
        })
```

#### 1.2 Core App Changes (`pulse/app.py`)

- While draining, deny WebSocket connections and prerender requests that would create a new RenderSession
- Fail healthchecks if draining and there are no active render sessions
- On SIGTERM, close and unmount everything + execute lifecycle hooks (ex: plugins)

### 2. Infrastructure Components

- ECS Task definition
- ALB Target Group configuration
- Terraform definitions
- Deployment command
- Rollback command (optional)

## Application Code

### Example Pulse App with AWS Deployment

```python
# app.py
import pulse as ps
from pulse_aws import DeployToECS

@ps.component
def App():
    return ps.div()["Hello Pulse!"]

# The secret can either be a string or a factory (ex: reading from AWS Secrets Manager)
app = ps.App([ps.Route("/", App)], plugins=[DeployToECS(secret=..., timeout=...)])
```

## Success Criteria

- ✅ Deploy new version without dropping active sessions
- ✅ Old versions drain automatically when sessions close
- ✅ Support multiple concurrent versions
- ✅ User-triggerable drain via authenticated endpoint
- ✅ Zero AWS/DevOps expertise required from Pulse developers
- ✅ Deploy in < 5 minutes from git push
- ✅ Clear health check behavior
- ✅ Graceful shutdown on SIGTERM
