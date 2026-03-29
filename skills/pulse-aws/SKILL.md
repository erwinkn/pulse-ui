---
name: pulse-aws
description: AWS deployment utilities for Pulse applications on ECS Fargate. Use this skill when deploying Pulse apps with pulse-aws, configuring AWSECSPlugin, tuning ECS task settings or health checks, or wiring a repo-specific deploy wrapper around the current pulse-aws CLI and rollout model.
---

# Pulse AWS

Deploys Pulse applications to AWS ECS Fargate behind an ALB. Handles Docker build/push, shared AWS baseline infrastructure, ECS services, target groups, health checks, and Pulse-specific deployment affinity.

## Quick Reference

```python
from pulse_aws import AWSECSPlugin, DockerBuild, TaskConfig, HealthCheckConfig, deploy
```

```bash
pulse-aws deploy \
  --deployment-name my-app \
  --domain app.example.com \
  --app-file apps/my-app/app.py \
  --web-root apps/my-app/web \
  --dockerfile apps/my-app/Dockerfile \
  --context . \
  --cdk-bin apps/my-app/scripts/cdk
```

## Quick Reference Table

| Task | API / CLI | Notes |
|------|-----------|-------|
| Add ECS runtime plugin | `AWSECSPlugin()` | Add to `ps.App(..., plugins=[...])` |
| Deploy app | `pulse-aws deploy` | Main entrypoint |
| Deploy programmatically | `await deploy(...)` | Use for custom orchestration |
| Set Docker inputs | `DockerBuild(...)` or CLI flags | `--app-file`, `--web-root`, `--dockerfile`, `--context` |
| Tune ECS task size | `TaskConfig(...)` or CLI flags | `--task-cpu`, `--task-memory`, `--desired-count` |
| Tune health checks | `HealthCheckConfig(...)` or CLI flags | path, thresholds, intervals |
| Use custom CDK wrapper | `--cdk-bin` | Good for repo-local `scripts/cdk` |
| Use custom CDK app dir | `--cdk-workdir` | Usually unnecessary because the package ships its own CDK app |
| Verify deployment affinity | `/_pulse/meta` | Exposed by `AWSECSPlugin` |

## App Integration

Add the plugin to the Pulse app:

```python
import pulse as ps
from pulse_aws import AWSECSPlugin

app = ps.App(
    routes=[...],
    server_address="https://app.example.com",
    plugins=[AWSECSPlugin()],
)
```

`AWSECSPlugin` provides:

- deployment-aware prerender directives
- deployment-aware Socket.IO directives
- ECS draining integration
- `/_pulse/meta` for deployment inspection

## Deployment Model

`pulse-aws` uses:

- ALB + HTTPS listener
- one ECS service per deployment
- one target group per deployment
- a default listener action for new traffic
- deployment affinity for existing tabs

Affinity is **query-based**, not header-based.

Current routing model:

- old: `X-Pulse-Render-Affinity`
- current: `?pulse_deployment=<deployment-id>`

The plugin and generated Pulse client code propagate that query through prerender and Socket.IO reconnects.

## CLI Usage

Minimum useful deploy:

```bash
pulse-aws deploy \
  --deployment-name stoneware-v3-preview \
  --domain v3.stoneware.rocks \
  --app-file apps/stoneware-v3/app.py \
  --web-root apps/stoneware-v3/web \
  --dockerfile apps/stoneware-v3/Dockerfile \
  --context .
```

Common flags:

- `--deployment-name`: environment / stack prefix
- `--domain`: public hostname
- `--app-file`: Pulse app entry, relative to Docker build context
- `--web-root`: Pulse web directory, relative to Docker build context
- `--dockerfile`: Dockerfile path, resolved from invocation cwd
- `--context`: Docker build context, resolved from invocation cwd
- `--cdk-bin`: alternate CDK executable or wrapper path
- `--cdk-workdir`: alternate CDK app directory
- `--task-env KEY=VALUE`: repeatable task env injection
- `--task-cpu`, `--task-memory`, `--desired-count`: ECS sizing
- `--health-check-path`, `--min-healthy-targets`: rollout and health tuning

## Programmatic Deploy

```python
from pathlib import Path
from pulse_aws import DockerBuild, deploy

result = await deploy(
    domain="app.example.com",
    deployment_name="stoneware-v3-preview",
    docker=DockerBuild(
        dockerfile_path=Path("apps/stoneware-v3/Dockerfile"),
        context_path=Path("."),
    ),
    cdk_bin="apps/stoneware-v3/scripts/cdk",
)
```

Useful when deploy needs extra orchestration or custom reporting.

## Path Rules

Be precise here:

- `--dockerfile`, `--context`, and `--cdk-workdir` resolve from the directory where `pulse-aws deploy` is invoked
- `--app-file` and `--web-root` stay relative to the Docker build context

This matters when adapting older scripts that used `--project-root`. The current CLI does **not** use that flag.

## Repo Wrapper Guidance

Keep repo-specific deploy wrapper logic for:

- secrets / env injection
- deployment naming conventions
- preview vs prod task sizing
- desired count overrides
- convenience `scripts/cdk` wrappers

Do **not** assume the wrapper should mutate the installed `pulse_aws` package. The current package ships its own bundled CDK app and supports `--cdk-bin` / `--cdk-workdir`.

Recommended wrapper shape:

```bash
uv run pulse-aws deploy \
  --deployment-name "${deployment_name}" \
  --domain "${domain}" \
  --app-file "apps/my-app/app.py" \
  --web-root "apps/my-app/web" \
  --dockerfile "apps/my-app/Dockerfile" \
  --context "." \
  --cdk-bin "apps/my-app/scripts/cdk"
```

## Operational Gotchas

- `server_address` on the Pulse app should match the deployed public hostname
- if you use `AWSECSPlugin`, verify deployment behavior through `/_pulse/meta`
- if `cdk` is not globally installed, keep a wrapper such as `scripts/cdk` and pass it via `--cdk-bin`
- if preview environments intentionally run with `desired-count=1`, validate auth/session behavior under single-task operation
- deployment affinity is query-based, so custom tooling should use `pulse_deployment`, not the old header

## Verify / Debug

Useful checks after deploy:

- hit the public app URL
- hit `/_pulse/meta`
- confirm ECS service desired/running counts
- confirm target group health
- confirm the ALB listener presents the expected certificate

If the app behaves oddly across deploys, check:

1. `server_address`
2. `AWSECSPlugin()` presence in `ps.App`
3. Docker build context vs `app.py` / `web/` paths
4. `cdk` executable availability
5. whether a script is still using removed CLI flags like `--project-root`
