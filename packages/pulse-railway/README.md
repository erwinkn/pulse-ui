# pulse-railway

Railway deployment utilities for Pulse applications.

`pulse-railway` uses one stable public router service plus one Railway service per deployment. The router keeps older deployments alive and forwards HTTP and websocket traffic to the selected deployment based on `pulse_deployment`.

For local CLI usage, prefer `RAILWAY_API_TOKEN` when you are using a user/account/workspace token. Reserve `RAILWAY_TOKEN` for Railway project tokens, especially in CI.

## Quick Start

```bash
set -a; source .env; set +a

uv run pulse-railway init \
  --app-file examples/railway/main.py

uv run pulse-railway deploy \
  --deployment-name prod \
  --app-file examples/railway/main.py \
  --web-root examples/railway/web \
  --dockerfile examples/Dockerfile \
  --context .

uv run pulse-railway deploy \
  --deployment-name prod \
  --app-file examples/railway/main.py \
  --web-root examples/railway/web \
  --dockerfile examples/Dockerfile \
  --context . \
  --image-repository ghcr.io/<org>/<name>
```

Use the commands like this:

- `pulse-railway init` bootstraps the stable router, env, Redis, and janitor stack into an empty Railway project.
- `pulse-railway upgrade` is currently a no-op placeholder.
- `pulse-railway deploy` builds and rolls out a new backend service on top of an already-initialized stack.
  By default it uploads source and uses `railway up` to build on Railway. Passing an image repository switches deploy to the local `docker buildx build --push` path.

`init` and `deploy` read the stable router, Redis, and janitor service names from `RailwayPlugin` on the target app. By default those are `pulse-router`, `pulse-redis`, and `pulse-janitor` without extra prefixing. The baseline also includes a stable env service named `pulse-env` that acts as the canonical source for user-managed deployment variables. Backend deployment services also default to no prefix, so their Railway service names match the generated deployment id unless you pass `--service-prefix`.

`pulse-railway init` is template-first and fresh-only. On an empty target it deploys the published `pulse-baseline` template so the router, janitor, and Redis land on the Railway canvas with a stable layout, creates the stable env service in the template group, then writes runtime images, variables, domains, cron, and healthchecks. Router and janitor services use the official GHCR images for the installed `pulse-railway` version unless you pass explicit image overrides: `ghcr.io/erwinkn/pulse-railway-router:<version>` and `ghcr.io/erwinkn/pulse-railway-janitor:<version>`. When you pass `--redis-url`, init removes the managed Redis service plus any template-created Redis references, then rewrites the baseline to use the external URL. If any baseline service already exists, including partial leftovers from a failed run, delete those services and rerun init. A future `pulse-railway update` command will handle explicit stack reconciliation.

If you omit `--project-id`, `pulse-railway init` creates a new Railway project first. That flow requires an account/workspace-capable Railway token plus `--workspace-id` (or `RAILWAY_WORKSPACE_ID`). The new project name defaults to the app file stem and can be overridden with `--project-name`.

You can also set `deployment_name` on `RailwayPlugin` to provide the default deploy name from app config. Precedence is: `--deployment-name`, then `PULSE_RAILWAY_DEPLOYMENT_NAME`, then `RailwayPlugin(deployment_name=...)`, then `prod`.

You can also set `image_repository` on `RailwayPlugin` to provide the default backend image registry from app config. Precedence is: `--image-repository`, then `PULSE_RAILWAY_IMAGE_REPOSITORY`, then `RailwayPlugin(image_repository=...)`. If none is set, deploy uses source mode.

If `--redis-url` is omitted, `pulse-railway init` creates the stable Redis service configured by `RailwayPlugin` in the Railway project.

`pulse-railway deploy` is now strict. It does not create or repair the stable baseline stack. If the router, env, Redis, or janitor baseline is missing or outdated, run `pulse-railway init` first.

User-managed app variables should live on the stable env service. Each new backend deployment references every non-Pulse-managed variable from `pulse-env`, so users can sync secrets into that service however they want: Railway UI, Shared Variables, Doppler, or another workflow.

By default, `pulse-railway deploy` uses source mode. Image deployments require `--image-repository ghcr.io/<org>/<name>`, `PULSE_RAILWAY_IMAGE_REPOSITORY`, or `RailwayPlugin(image_repository="ghcr.io/<org>/<name>")`.

## Model

- Stable Railway router service
- Stable Railway env service for user-managed deployment variables
- One Railway backend service per deployment
- Stable Railway Redis service unless you pass `--redis-url`
- Optional Railway cron job for janitor cleanup
- Active deployment stored in `PULSE_ACTIVE_DEPLOYMENT`
- Explicit affinity via `pulse_deployment` query param or `x-pulse-deployment` header
- Websockets proxied through the router to the selected backend service
- Draining and cleanup state stored in Redis
- Before janitor deletion, the backend broadcasts Pulse `reload` to connected clients
- Websocket reconnects with stale affinity fall back to the active deployment so the app can trigger a full-page reload

## Runtime

Backend services must set `PULSE_DEPLOYMENT_ID`. `RailwayPlugin` injects the affinity query into Pulse prerender and websocket directives and exposes `/_pulse/meta` for verification.

If your app opts into `pulse_railway.RailwaySessionStore()`:

- deploy injects `PULSE_RAILWAY_REDIS_URL` into the backend app
- the app session store uses that Redis for server-backed sessions

When the baseline stack has Redis configured:

- deploy marks the new deployment `active`
- previous active deployments become `draining`
- the router records HTTP activity and websocket leases in Redis
- the janitor signals connected browsers to reload before deleting a drained deployment
- the janitor cron job deletes drained deployments after they are idle

The janitor job runs as a Railway cron service, not a permanent always-on process. Use a cadence of 5 minutes or slower; Railway does not run cron jobs more frequently than that.

`pulse-railway janitor run` is for the deployed janitor service only. It probes `*.railway.internal` backends and now fails fast outside Railway.

If you need to trigger cleanup manually, run the command from inside the deployed janitor service:

```bash
pulse-railway janitor run
```

To remove a deployment by the original deployment name prefix, use:

```bash
pulse-railway remove \
  --service pulse-router \
  --deployment-name prod \
  --project-id <project-id> \
  --environment-id <environment-id> \
  --token <project-token>
```

If the name matches multiple generated deployment ids, the command fails and prints the matching ids so you can retry with `pulse-railway delete --deployment-id ...`.

## Notes

- Backend services should run with `1` replica. Railway does not provide replica-level sticky routing, so deployment affinity alone is only safe with a single backend replica when sessions are stored in memory.
- The router can run with multiple replicas because routing state lives in the request query/header plus the active deployment variable.
- Healthchecks remain for crash recovery only. Deployment cleanup is handled by the janitor cron job, not by failing healthchecks on drained services.
