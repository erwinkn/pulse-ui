# Pulse Railway control-plane invariants plan

Harden the current Redis-backed Railway control plane. This is a hard cutoff: no migration fallback to legacy `PULSE_ACTIVE_DEPLOYMENT` or service-variable deployment state. If current architecture invariants are missing, fail loudly before mutating Railway services or Redis state.

## Scope

- In: router control endpoints, janitor validation, deployment delete behavior, tests, and internal docs/comments where helpful.
- Out: backwards compatibility for pre-Redis active state, automatic state reconstruction, or migration helpers.

## Finishing criteria

- `pulse-railway janitor run` never marks or deletes deployments when active state is missing or inconsistent.
- Router startup fails if the deployment store cannot be built from current runtime env.
- Router control endpoints reject contradictory promote/delete requests.
- Deleting the active deployment is explicit and cannot silently leave a stale active route.
- Focused tests cover every invalid state below.
- `make test` passes.

## Invariants

- Redis deployment store is required for router and janitor runtime.
- If any backend service with `PULSE_DEPLOYMENT_ID` exists, exactly one active deployment id must exist in Redis.
- The active deployment id must match exactly one backend Railway service.
- Each `PULSE_DEPLOYMENT_ID` may appear on at most one backend Railway service.
- A deployment cannot be active and draining in the same control payload.
- Normal deletion cannot remove the active deployment without an explicit force path.

## Action items

[ ] Add a small validation helper for deployment service records.

- Suggested location: `packages/pulse-railway/src/pulse_railway/deployment.py` or `janitor.py` if it stays janitor-only.
- Input: list of `DeploymentServiceRecord`, active deployment id.
- Validate duplicate deployment ids.
- Validate active id is present when services exist.
- Validate active id matches exactly one service.
- Return the active service record plus non-active service records.
- Raise `DeploymentError` with clear messages.

[ ] Harden `run_janitor`.

- File: `packages/pulse-railway/src/pulse_railway/janitor.py`.
- Fetch Railway deployment services before mutating Redis.
- If no deployment services exist, no active id is required; return a successful empty scan.
- If deployment services exist and Redis active id is missing, raise before `mark_draining`.
- If active id does not match exactly one service, raise before `mark_draining`.
- If duplicate deployment ids exist, raise before `mark_draining`.
- Keep the existing behavior that all non-active services become draining candidates.

[ ] Add janitor tests for invalid state.

- File: `packages/pulse-railway/tests/test_railway_janitor.py`.
- Missing active key + one or more backend services raises and does not call delete.
- Active key points to no listed backend service raises and does not call delete.
- Duplicate `PULSE_DEPLOYMENT_ID` services raises and does not call delete.
- No backend services + missing active key returns empty success.

[ ] Require router deployment store at startup.

- File: `packages/pulse-railway/src/pulse_railway/router.py`.
- In `build_app_from_env()`, if `kv_store_spec_from_env()` returns `None`, raise `RuntimeError`.
- Keep test-only `build_app(..., store=None)` support if existing router unit tests rely on it.
- Do not rely on endpoint-level `503` for deployed router correctness.

[ ] Add router startup tests.

- File: `packages/pulse-railway/tests/test_railway_router.py`.
- `build_app_from_env()` raises when required Railway env is present but no Redis/KV env exists.
- `build_app_from_env()` succeeds when `REDIS_URL` or explicit KV env is present.

[ ] Reject contradictory promote payloads.

- File: `packages/pulse-railway/src/pulse_railway/router.py`.
- In `promote_deployment()`, validate all draining entries before writing any state.
- Reject duplicate draining ids.
- Reject active deployment id appearing in draining list.
- Reject malformed `drain_started_at` values instead of letting `float(...)` raise an unshaped server error.
- Only call `set_active` / `mark_draining` after full payload validation.

[ ] Add promote endpoint tests.

- File: `packages/pulse-railway/tests/test_railway_router.py`.
- Active id also present in `draining` returns `400` and store remains unchanged.
- Duplicate draining deployment ids return `400` and store remains unchanged.
- Invalid `drain_started_at` returns `400` and store remains unchanged.

[ ] Make active lookup distinguish "no app deployed" from invalid deployed state.

- File: `packages/pulse-railway/src/pulse_railway/router.py`.
- Add a store-side way to know whether deployment records exist, or reuse `list_draining_deployments()` plus active record lookup if sufficient.
- For `/active`, return `{"deployment_id": null}` only when the store has no deployment records.
- If deployment records exist but active key is missing, return an internal error.
- Keep `_get_active_deployment_from_router()` treating a non-2xx router response as `DeploymentError`.

[ ] Add active endpoint tests.

- File: `packages/pulse-railway/tests/test_railway_router.py`.
- Empty store returns `{"deployment_id": null}`.
- Store with deployment records but missing active key returns error.
- Store with active key returns the deployment id.

[ ] Guard deletion of active deployments.

- File: `packages/pulse-railway/src/pulse_railway/deployment.py`.
- Before deleting the Railway service, use router active state to determine whether `deployment_id` is active.
- If active, raise before deleting the Railway service. The normal path should be "promote another deployment, then delete old one."
- Remove `--keep-active-variable`; stale or missing active state should not be user-selectable.

[ ] Add delete tests.

- File: `packages/pulse-railway/tests/test_railway_deployment.py` and CLI tests if flags change.
- Deleting non-active deployment deletes Railway service and clears deployment store state.
- Deleting active deployment without force raises before Railway service deletion.
- If force path exists, failed router state delete reports an error and does not pretend delete completed cleanly.

[ ] Update docs/skill notes after behavior changes.

- Files: `packages/pulse-railway/README.md` and `skills/pulse-railway/SKILL.md`.
- Document that Redis active state is mandatory after first deploy.
- Document that janitor fails on inconsistent control-plane state.
- Document the safe active-deployment deletion workflow.

## Verification

[ ] Run focused tests:

```bash
uv run pytest \
  packages/pulse-railway/tests/test_railway_janitor.py \
  packages/pulse-railway/tests/test_railway_router.py \
  packages/pulse-railway/tests/test_railway_deployment.py
```

[ ] Run package-adjacent tests:

```bash
uv run pytest packages/pulse-railway/tests
```

[ ] Run repo test target:

```bash
make test
```

[ ] Before commit, run:

```bash
make all
```

## Open decisions

- Exact exception type for invalid control-plane state: use `DeploymentError` for CLI/deployment paths; router endpoints should surface controlled HTTP errors.
- Whether deletion should have a force flag, and what it should be named.
- Whether to add a general `DeploymentStore.has_deployments()` / `list_deployments()` method to avoid overloading draining-only APIs.
