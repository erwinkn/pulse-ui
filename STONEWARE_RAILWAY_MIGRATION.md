# Stoneware Railway Migration

Remaining items after the `pulse-railway` plugin work in this repo.

## Still to do in `apps/stoneware-v3`

1. Replace AWS plugin wiring

- swap `AWSECSPlugin()` for `RailwayPlugin(...)`
- remove the `pulse-aws` dependency
- add the `pulse-railway` dependency
- replace the current AWS deploy wrapper with `pulse-railway init` / `pulse-railway deploy`

2. Switch session store to the Railway session-store contract

- current app code uses a custom `RedisSessionStore`
- `pulse-railway deploy` auto-injects `PULSE_RAILWAY_REDIS_URL` when the app exposes `RailwaySessionStore()` / `RailwayRedisSessionStore()`
- target pattern:
  - use `RailwaySessionStore(...)`
  - do not use `railway_session_store(...)`
  - do not keep a Railway-specific local fallback path
  - do not depend on app-session `REDIS_URL`
  - let deploy reserve and inject `PULSE_RAILWAY_REDIS_URL`

3. Configure a durable backend image repository

- router and janitor now default to official GHCR images
- app backend images still default to `ttl.sh` unless `--image-repository` is passed
- Stoneware deploy wrapper should use a durable registry, e.g. `ghcr.io/<org>/stoneware-v3`

4. Set up the custom domain in Railway UI

- `v3.stoneware.rocks`
- keep the hardcoded public `server_address` if desired
- ensure the domain points at the Railway router service

## Done in `pulse-ui`

- `pulse-railway init` / `upgrade` now default to official package-versioned GHCR router and janitor images
- `pulse-railway` is now included in version bump / audit / stats scripts
- Railway session-store wiring is now strict:
  - `RailwaySessionStore()` reads `PULSE_RAILWAY_REDIS_URL`
  - `pulse-railway deploy` reserves and injects `PULSE_RAILWAY_REDIS_URL`
  - the old helper/fallback contract is gone

## Suggested acceptance check

After migrating Stoneware:

- deploy succeeds with `pulse-railway init` + `pulse-railway deploy`
- app serves through the Railway router URL
- `/_pulse/meta` returns the active deployment id
- session survives a redeploy
- websocket navigation still works through the router
