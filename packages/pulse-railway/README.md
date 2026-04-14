# pulse-railway

Railway deployment utilities for Pulse applications.

`pulse-railway` uses one stable public router service plus one Railway service per deployment. The router keeps older deployments alive and forwards HTTP and websocket traffic to the selected deployment based on `pulse_deployment`.

## Quick Start

```bash
set -a; source .env; set +a

uv run pulse-railway deploy \
  --deployment-name prod \
  --app-file examples/railway/main.py \
  --web-root examples/railway/web \
  --dockerfile examples/Dockerfile \
  --context .
```

`pulse-railway deploy` reads the stable router, Redis, and janitor service names from `RailwayPlugin` on the target app. By default those are `pulse-router`, `pulse-redis`, and `pulse-janitor` without extra prefixing. Backend deployment services also default to no prefix, so their Railway service names match the generated deployment id unless you pass `--service-prefix`.

You can also set `deployment_name` on `RailwayPlugin` to provide the default deploy name from app config. Precedence is: `--deployment-name`, then `PULSE_RAILWAY_DEPLOYMENT_NAME`, then `RailwayPlugin(deployment_name=...)`, then `prod`.

If `--redis-url` is omitted, `pulse-railway` creates or reuses the stable Redis service configured by `RailwayPlugin` in the Railway project.

By default, the package builds and pushes both images to `ttl.sh` for a zero-config flow. For longer-lived deployments, pass `--image-repository ghcr.io/<org>/<name>`.

## Model

- Stable Railway router service
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

If your app opts into `pulse_railway.railway_session_store()`:

- deploy injects `PULSE_RAILWAY_REDIS_URL` into the backend app
- the app session store uses that Redis for server-backed sessions

When `PULSE_RAILWAY_REDIS_URL` is set:

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
