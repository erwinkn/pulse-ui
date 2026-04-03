# pulse-railway

Railway deployment utilities for Pulse applications.

`pulse-railway` uses one stable public router service plus one Railway service per deployment. The router keeps older deployments alive and forwards HTTP and websocket traffic to the selected deployment based on `pulse_deployment`.

## Quick Start

```bash
set -a; source .env; set +a

uv run pulse-railway deploy \
  --service pulse-router \
  --deployment-name prod \
  --app-file examples/aws-ecs/main.py \
  --web-root examples/aws-ecs/web \
  --dockerfile examples/aws-ecs/Dockerfile \
  --context .
```

If `--redis-url` is omitted, `pulse-railway` creates or reuses a stable Redis service in the Railway project. To pin that service name, pass `--redis-service`.

By default, the package builds and pushes both images to `ttl.sh` for a zero-config flow. For longer-lived deployments, pass `--image-repository ghcr.io/<org>/<name>`.

## Model

- Stable Railway router service
- One Railway backend service per deployment
- Stable Railway Redis service unless you pass `--redis-url`
- Optional stable Railway janitor service
- Active deployment stored in `PULSE_ACTIVE_DEPLOYMENT`
- Explicit affinity via `pulse_deployment` query param or `x-pulse-deployment` header
- Websockets proxied through the router to the selected backend service
- Draining and cleanup state stored in Redis

## Runtime

Backend services must set `PULSE_RAILWAY_DEPLOYMENT_ID`. `RailwayPlugin` injects the affinity query into Pulse prerender and websocket directives and exposes `/_pulse/meta` for verification.

When `PULSE_RAILWAY_REDIS_URL` is set:

- deploy marks the new deployment `active`
- previous active deployments become `draining`
- the router records HTTP activity and websocket leases in Redis
- the janitor deletes drained deployments after they are idle

You can run cleanup manually with:

```bash
uv run pulse-railway janitor run \
  --service pulse-router \
  --project-id "$RAILWAY_PROJECT_ID" \
  --environment-id "$RAILWAY_ENVIRONMENT_ID" \
  --token "$RAILWAY_TOKEN" \
  --redis-url "$PULSE_RAILWAY_REDIS_URL"
```

## Notes

- Backend services should run with `1` replica. Railway does not provide replica-level sticky routing, so deployment affinity alone is only safe with a single backend replica when sessions are stored in memory.
- The router can run with multiple replicas because routing state lives in the request query/header plus the active deployment variable.
- Healthchecks remain for crash recovery only. Deployment cleanup is handled by the janitor, not by failing healthchecks on drained services.
