---
name: pulse-railway
description: Railway deployment utilities for Pulse applications. Use this skill when deploying Pulse apps with pulse-railway, configuring RailwayPlugin or RailwaySessionStore, running pulse-railway init/deploy/remove, migrating from pulse-aws to Railway, or debugging Railway router/session/deployment affinity behavior.
---

# Pulse Railway

Deploys Pulse applications to Railway with one stable public router service and one backend Railway service per deployment. The router keeps old deployments alive and routes HTTP + websocket traffic by deployment affinity.

## Quick Reference

```python
import pulse as ps
from pulse_railway import RailwayPlugin, RailwaySessionStore

app = ps.App(
    routes=[...],
    plugins=[RailwayPlugin()],
    session_store=RailwaySessionStore(),  # optional Redis-backed server sessions
)
```

```bash
uv run pulse-railway init \
  --app-file apps/my-app/main.py

uv run pulse-railway deploy \
  --deployment-name prod \
  --app-file apps/my-app/main.py \
  --web-root apps/my-app/web \
  --dockerfile Dockerfile \
  --context .
```

## When To Use

- deploying a Pulse app to Railway
- setting up the stable `pulse-router`, `pulse-env`, `pulse-redis`, and `pulse-janitor` baseline
- rolling out new versions with deployment affinity
- preserving server-backed sessions through Railway Redis
- migrating a Pulse app from `pulse-aws` / `AWSECSPlugin`
- debugging `/_pulse/meta`, websocket routing, stale deployment affinity, or drained deployments

## App Integration

Add `RailwayPlugin()` to the app. It injects `pulse_deployment` into prerender and Socket.IO directives and exposes `/_pulse/meta`.

```python
import os
import pulse as ps
from pulse_railway import RailwayPlugin, RailwaySessionStore

app = ps.App(
    routes=[...],
    plugins=[
        RailwayPlugin(
            project_id=os.environ.get("RAILWAY_PROJECT_ID"),
            environment_id=os.environ.get("RAILWAY_ENVIRONMENT_ID"),
            deployment_name="prod",
            # Optional: default image deploy repo.
            # image_repository="ghcr.io/acme/my-app",
        )
    ],
    session_store=RailwaySessionStore(),
    server_address=os.environ.get("PULSE_SERVER_ADDRESS"),
)
```

Use `RailwaySessionStore()` when the app needs server-backed sessions that survive redeploys. Do not read `REDIS_URL` directly for app sessions and do not hand-roll a Railway fallback. `pulse-railway deploy` injects `PULSE_RAILWAY_REDIS_URL` when it detects `RailwaySessionStore()`.

## CLI Workflow

Use `RAILWAY_API_TOKEN` for local user/workspace tokens. Reserve `RAILWAY_TOKEN` for Railway project tokens, especially in CI.

First-time setup:

```bash
set -a; source .env; set +a

uv run pulse-railway init \
  --app-file apps/my-app/main.py \
  --project-id "$RAILWAY_PROJECT_ID" \
  --environment-id "$RAILWAY_ENVIRONMENT_ID"
```

Deploy with Railway source builds by default:

```bash
uv run pulse-railway deploy \
  --deployment-name prod \
  --app-file apps/my-app/main.py \
  --web-root apps/my-app/web \
  --dockerfile Dockerfile \
  --context .
```

Deploy by building and pushing an image locally:

```bash
uv run pulse-railway deploy \
  --deployment-name prod \
  --app-file apps/my-app/main.py \
  --web-root apps/my-app/web \
  --dockerfile Dockerfile \
  --context . \
  --image-repository ghcr.io/acme/my-app
```

`deploy` precedence:

- deployment name: `--deployment-name`, then `PULSE_RAILWAY_DEPLOYMENT_NAME`, then `RailwayPlugin(deployment_name=...)`, then `prod`
- image repository: `--image-repository`, then `PULSE_RAILWAY_IMAGE_REPOSITORY`, then `RailwayPlugin(image_repository=...)`; absent means source deploy

## Path Rules

- `--dockerfile` and `--context` resolve from the shell invocation directory
- `--app-file` and `--web-root` must be relative to the deploy context
- source deploys use `railway up`, so the Railway CLI must be available
- image deploys use `docker buildx build --push`

## Railway Model

`pulse-railway init` creates or configures:

- stable public router service, default `pulse-router`
- stable env service, default `pulse-env`, for user-managed app variables
- stable Redis service, default `pulse-redis`, unless `--redis-url` is supplied
- janitor cron service, default `pulse-janitor`
- official router/janitor GHCR images for the installed `pulse-railway` version

`init` is fresh-only. If baseline services or partial leftovers already exist, delete them and rerun `init`. `deploy` is strict and will not repair missing baseline services.

User-managed variables belong on `pulse-env`. New backend deployments reference every non-Pulse-managed variable from that service.

## Migration From pulse-aws

Typical app migration:

- replace `AWSECSPlugin()` with `RailwayPlugin(...)`
- remove `pulse-aws` dependency and add `pulse-railway`
- replace AWS deploy wrapper with `pulse-railway init` / `pulse-railway deploy`
- if using custom Redis sessions, switch to `RailwaySessionStore()`
- set custom domains in the Railway UI and point them at the router service

## Verification

After deploy:

```bash
curl https://<router-domain>/_pulse/meta
```

Check:

- `/_pulse/meta` returns the active deployment id
- app loads through the Railway router URL or custom domain
- session data survives a redeploy when using `RailwaySessionStore()`
- websocket navigation and actions still work after a redeploy
- old deployment services eventually drain and get deleted by the janitor

For a local repo example, inspect `examples/railway/` and `packages/pulse-railway/README.md`.

## Operational Gotchas

- Keep backend replicas at `1` unless sessions are safe across replicas; Railway does not provide replica-level sticky routing.
- The router can run multiple replicas because routing state lives in request affinity plus Redis.
- `pulse-railway janitor run` is for the deployed janitor service only and fails outside Railway.
- The janitor should run every 5 minutes or slower; Railway cron does not run more frequently.
- `pulse-railway upgrade` is currently a no-op placeholder.
- If a deployment name matches multiple generated ids, `pulse-railway remove` fails and prints matches; retry with `pulse-railway delete --deployment-id ...`.
