# Railway Pulse Example

Deployable `pulse-railway` smoke test app for shared Redis.

It verifies three things with one app:

- `pulse-railway` deployment tracking uses the stable Railway Redis service
- Pulse server-side sessions use that same shared store
- app code can read and write the same shared store through `ps.store()`

## Local

From the repository root:

```bash
uv run pulse run examples/railway/main.py
```

With a local Redis instead of the default SQLite dev store:

```bash
PULSE_KV_URL=redis://localhost:6379/0 uv run pulse run examples/railway/main.py
```

## Railway Deploy

Deploy from the repository root so Docker uses the local workspace packages:

```bash
set -a; source .env; set +a

uv run pulse-railway deploy \
  --service pulse-router \
  --deployment-name redis-smoke \
  --app-file examples/railway/main.py \
  --web-root examples/railway/web \
  --dockerfile examples/railway/Dockerfile \
  --context .
```

The app exposes Redis through `app.store`. `pulse-railway` reads that config during deploy and reuses the same Redis for router/janitor tracking plus backend app access.

## Verify

Open the page and test:

1. Click `Increment session counter`.
2. Click `Increment shared counter`.
3. Deploy again with a new `--deployment-name`.
4. Confirm the session counter and shared counter are still there.

HTTP probes:

```bash
curl -c /tmp/pulse-railway.cookies -b /tmp/pulse-railway.cookies \
  https://<router-domain>/api/railway-example/session/increment

curl -c /tmp/pulse-railway.cookies -b /tmp/pulse-railway.cookies \
  https://<router-domain>/api/railway-example/session

curl -X POST https://<router-domain>/api/railway-example/shared/increment

curl https://<router-domain>/api/railway-example/shared

curl https://<router-domain>/_pulse/meta
```
