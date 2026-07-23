# pulse-railway

Railway deployment utilities for Pulse applications.

`pulse-railway` uses one stable public router service plus one Railway service per deployment. The router keeps older deployments alive and forwards HTTP and websocket traffic to the selected deployment based on `pulse_deployment`.

For local CLI usage, prefer `RAILWAY_API_TOKEN` when you are using a user/account/workspace token. Reserve `RAILWAY_TOKEN` for Railway project tokens, especially in CI. If neither is set, `pulse-railway` falls back to the local Railway CLI login session from `~/.railway/config*.json`. CLI login tokens are allowed for local API calls, but `scaffold` and `ensure` will not write them into the long-lived router or janitor services; set `RAILWAY_TOKEN` or `RAILWAY_API_TOKEN` when initializing or repairing runtime credentials.

## Quick Start

```bash
set -a; source .env; set +a

uv run pulse-railway ensure \
  examples/railway/main.py

uv run pulse-railway deploy \
  examples/railway/main.py

uv run pulse-railway deploy \
  examples/railway/main.py \
  --image-repository ghcr.io/<org>/<name>
```

Use the commands like this:

- `pulse-railway scaffold` bootstraps the stable router, env, Redis, and janitor stack into an empty Railway project.
- `pulse-railway ensure` creates the baseline on an empty project or reconciles mutable runtime and canvas config on a complete baseline.
- `pulse-railway deploy` builds and rolls out a new backend service on top of an already-initialized stack.
  By default it uploads source with detached `railway up` and polls the Railway API for the build result. Passing an image repository switches deploy to the local `docker buildx build --push` path.
- `pulse-railway redeploy` redeploys the active backend service. Pass `--deployment-id <id>` to redeploy a specific Pulse deployment.

`scaffold <app-file>` bootstraps the baseline from `RailwayPlugin` config and defaults. Stable router, Redis, janitor, and backend service names come from the app plugin. The baseline also includes a stable env service that acts as the canonical source for user-managed deployment variables.

`ensure` uses the same target/options as `scaffold`, but it is strict about topology. On an empty project it creates the baseline. On a complete baseline it rewrites Pulse-managed runtime config such as images, variables, replica counts, healthchecks, cron, and janitor drain settings. If the router is in a Railway canvas group, it also moves Pulse baseline and deployment services into that group. On a partial baseline it fails; delete the baseline services and rerun `scaffold`.

`deploy` reads app configuration from `RailwayPlugin` on the target app. Provide the Dockerfile with `RailwayPlugin(dockerfile=...)`.

`pulse-railway scaffold` is template-first and fresh-only. On an empty target it deploys the published `pulse-baseline` template so the router, janitor, and Redis land on the Railway canvas with a stable layout, creates the stable env service in the template group, then writes official runtime images, variables, domains, cron, and healthchecks. When you pass `--redis-url`, scaffold removes the managed Redis service created by the template and rewrites the baseline to use the external URL. If any baseline service already exists, delete the baseline services and rerun `pulse-railway scaffold`.

`pulse-railway scaffold <app-file>`, `pulse-railway ensure <app-file>`, and `pulse-railway deploy <app-file>` load the app to read `RailwayPlugin`. For `scaffold` and `ensure`, set `RailwayPlugin(project="...", environment="...")`; if project or environment is omitted, the token must provide enough scope to infer them. CLI target flags override plugin config. Project and environment IDs are resolved internally before Railway API calls.

All local target commands accept Railway target names and IDs:

```bash
uv run pulse-railway scaffold examples/railway/main.py \
  --workspace <workspace-name> \
  --project <project-name> \
  --environment <environment-name>

uv run pulse-railway ensure examples/railway/main.py \
  --workspace <workspace-name> \
  --project <project-name> \
  --environment <environment-name>

uv run pulse-railway deploy examples/railway/main.py \
  --workspace-id <workspace-id> \
  --project-id <project-id> \
  --environment-id <environment-id>
```

Use either the name or ID form for each target, not both. `--workspace` and `--workspace-id` are only needed to disambiguate project lookup by name.

You can also set `deployment_name` on `RailwayPlugin` to provide the default deploy name from app config. Precedence is: `--deployment-name`, then `RailwayPlugin(deployment_name=...)`, then `prod`.

You can also set `image_repository` on `RailwayPlugin` to provide the default backend image registry from app config. Precedence is: `--image-repository`, then `RailwayPlugin(image_repository=...)`. If none is set, deploy uses source mode.

`pulse-railway deploy <app-file>` reads `server_address` and web root from the target `ps.App`, and the Dockerfile path from `RailwayPlugin(dockerfile=...)`. The deploy context is the invocation directory unless `--context` is provided. Dockerfile and web root paths are resolved from that context. `--server-address` and `--web-root` can override app config; Dockerfile is only configured on the plugin.

If `--redis-url` is omitted, `pulse-railway scaffold` and an empty-project `pulse-railway ensure` create the stable Redis service in the Railway project. Redis mode is baseline topology; `ensure` does not switch an existing stack between managed and external Redis.

`pulse-railway deploy` is strict. It inspects the stable baseline stack and does not create or repair it. If router, env, Redis, or janitor topology is missing, delete the partial baseline and rerun `pulse-railway scaffold`.

User-managed app variables should live on the stable env service. Each new backend deployment references every non-Pulse-managed variable from `pulse-env`, so users can sync secrets into that service however they want: Railway UI, Shared Variables, Doppler, or another workflow.

By default, `pulse-railway deploy` uses source mode. Image deployments require `--image-repository ghcr.io/<org>/<name>` or `RailwayPlugin(image_repository="ghcr.io/<org>/<name>")`.

## Model

- Stable Railway router service
- Stable Railway env service for user-managed deployment variables
- One Railway backend service per deployment
- Stable Railway Redis service unless you pass `--redis-url`
- Optional Railway cron job for janitor cleanup
- Active deployment stored in Redis
- Explicit affinity via `pulse_deployment` query param or `x-pulse-deployment` header
- Websockets proxied through the router to the selected backend service
- Draining and cleanup state stored in Redis
- Newly deployed backends are registered in Redis before router health checks
- Before janitor deletion, the backend broadcasts Pulse `reload` to connected clients
- Websocket reconnects with stale affinity fall back to the active deployment so the app can trigger a full-page reload
- The router resolves deployments from Redis only; Railway API calls stay in the deploy CLI/control plane
- Deployment control state is mutated by running `pulse-railway control` inside the private router service with `railway ssh`, not through public HTTP routes

## Runtime

Backend services must set `PULSE_DEPLOYMENT_ID`. `RailwayPlugin` injects the affinity query into Pulse prerender and websocket directives and exposes `/_pulse/meta` for verification. Internal janitor endpoints receive `PULSE_RAILWAY_INTERNAL_TOKEN` directly on each service that needs it.

Set `PULSE_RAILWAY_ROUTER_CONNECTION_LIMIT` on the router service to tune its
aiohttp connection pool. The default is `2048`, which keeps outbound backend
connections bounded while leaving headroom for long-lived WebSocket traffic.

If your app opts into `pulse_railway.RailwaySessionStore()`:

- deploy injects `PULSE_RAILWAY_REDIS_URL` into the backend app
- the app session store uses that Redis for server-backed sessions

When the baseline stack has Redis configured:

- deploy registers the new backend deployment in Redis
- deploy performs Redis control-plane writes from inside the router service, where the private Redis URL is available
- deploy verifies the registered backend through the router with explicit affinity
- deploy marks the new deployment `active`
- previous active deployments become `draining`
- the janitor probes draining backends for active Pulse render sessions
- the janitor deletes drained deployments with no render sessions
- after the drain TTL, the janitor signals connected browsers to reload and deletes the deployment anyway

The janitor job runs as a Railway cron service, not a permanent always-on process. Use a cadence of 5 minutes or slower; Railway does not run cron jobs more frequently than that.

`pulse-railway janitor run` is for the deployed janitor service only. It probes `*.railway.internal` backends and now fails fast outside Railway. `scaffold` and `ensure` inject the stable router, janitor, and Redis service names into the janitor runtime so custom service names are preserved.

If you need to trigger cleanup manually, run the command from inside the deployed janitor service:

```bash
pulse-railway janitor run
```

To rerun Railway's build/deploy for the active backend deployment, use:

```bash
pulse-railway redeploy \
  --project <project-name> \
  --environment production \
  --token <project-token>
```

To redeploy a specific Pulse deployment id:

```bash
pulse-railway redeploy \
  --deployment-id prod-260402-120000 \
  --project <project-name> \
  --environment production \
  --token <project-token>
```

To remove a deployment by the original deployment name prefix, use:

```bash
pulse-railway remove \
  --service pulse-router \
  --deployment-name prod \
  --project <project-name> \
  --environment production \
  --token <project-token>
```

If the name matches multiple generated deployment ids, the command fails and prints the matching ids so you can retry with `pulse-railway delete --deployment-id ...`.

## Notes

- Backend services should run with `1` replica. Railway does not provide replica-level sticky routing, so deployment affinity alone is only safe with a single backend replica when sessions are stored in memory.
- The router can run with multiple replicas because routing state lives in the request query/header plus Redis.
- Healthchecks remain for crash recovery only. Deployment cleanup is handled by the janitor cron job, not by failing healthchecks on drained services.
