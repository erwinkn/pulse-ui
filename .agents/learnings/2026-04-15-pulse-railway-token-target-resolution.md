# Pulse Railway Token Target Resolution
Date: 2026-04-15
Session: Live sandbox validation of template-first `pulse-railway init`

## What Changed
- `pulse-railway init` was updated to resolve `projectId` and `environmentId` from a project token when explicit IDs are absent.
- Live validation showed `pulse-railway upgrade` still requires explicit `--project-id` and `--environment-id`.

## Learnings
- The root `.env` may contain only `RAILWAY_TOKEN`; commands should still work when that token is a project token.
- Target resolution should be centralized and reused by `init`, `upgrade`, `deploy`, `delete`, `remove`, and janitor commands.
- Do not treat missing `RAILWAY_PROJECT_ID` as an implicit new-project request until project-token introspection has failed.

## Evidence
- `uv run pulse-railway init --app-file examples/railway/main.py` initially failed with `workspace id is required when creating a new project`.
- `uv run pulse-railway upgrade --app-file examples/railway/main.py` failed with `project id, environment id, and token are required`.
- Relevant code: `packages/pulse-railway/src/pulse_railway/commands/init.py`, `packages/pulse-railway/src/pulse_railway/commands/upgrade.py`.

## Next-Time Checklist
- [ ] Add a shared target resolver that can inspect `projectToken { projectId environmentId }`.
- [ ] Replace per-command ID validation with the shared resolver.
- [ ] Add CLI tests for token-only `.env` behavior across every `pulse-railway` command.
