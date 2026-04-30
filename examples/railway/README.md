# Railway Pulse Example

Deployable `pulse-railway` smoke test app for Railway-backed server sessions.

It verifies two things with one app:

- `pulse-railway` deployment tracking uses the stable Railway Redis service
- Pulse server-side sessions can use that same Redis through `pulse_railway.RailwaySessionStore()`

## Local

From the repository root:

```bash
PULSE_RAILWAY_REDIS_URL=redis://localhost:6379/0 uv run pulse run examples/railway/main.py
```

## Railway Deploy

Deploy from the repository root so the `examples/railway/Dockerfile` can use the local workspace packages:

```bash
set -a; source .env; set +a

uv run pulse-railway ensure \
  examples/railway/main.py \
  --project pulse-sandbox \
  --environment production

uv run pulse-railway deploy \
  examples/railway/main.py \
  --project pulse-sandbox \
  --environment production
```

Passing `--image-repository ghcr.io/<org>/<name>` switches deploy to image mode.

Use `--workspace <name>` or `--workspace-id <id>` when the project name is ambiguous. Every target also has an ID form: `--project-id` and `--environment-id`.

The app opts into `pulse_railway.RailwaySessionStore()`. Local runs can provide `PULSE_RAILWAY_REDIS_URL` directly. On Railway deploy, `pulse-railway` reads the Dockerfile path from `RailwayPlugin` and injects that same env var so the shared Redis service backs deployment tracking and app sessions.

`pulse-railway deploy` assumes the baseline stack already exists. If you skip `ensure`, deploy fails fast and points you back to `ensure`.

## Verify

Open the page and test:

1. Click `Increment session counter`.
2. Deploy again with a new `--deployment-name`.
3. Confirm the session counter is still there.

HTTP probes:

```bash
curl -c /tmp/pulse-railway.cookies -b /tmp/pulse-railway.cookies \
  https://<router-domain>/api/railway-example/session/increment

curl -c /tmp/pulse-railway.cookies -b /tmp/pulse-railway.cookies \
  https://<router-domain>/api/railway-example/session

curl https://<router-domain>/_pulse/meta
```
