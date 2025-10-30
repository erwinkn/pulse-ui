# AWS ECS Multi-Version Deployment ExecPlan

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be updated as implementation proceeds. Maintain this document in accordance with `.agent/PLANS.md` so that any contributor can succeed with only the working tree and this file.

The plan translates the architecture captured in `plans/aws-ecs-deployment.md` into actionable engineering steps that make Pulse applications deployable on AWS ECS behind an Application Load Balancer (ALB) while supporting multiple live versions, per-RenderSession stickiness, graceful draining, and automated cleanup.

## Purpose / Big Picture

After completing this work, a Pulse developer can push a new application version to AWS ECS, run it alongside existing versions, switch traffic with zero downtime, and retire older versions only after every active RenderSession has closed. They can verify the rollout end to end by calling a well-defined health endpoint, issuing a signed drain request, watching ECS move traffic via ALB weighted target groups, and observing CloudWatch logs that confirm graceful shutdown. No AWS specialist knowledge is required; the repository will supply the plugin, runtime guarantees, container image, CDK-managed baseline stack, deployment helpers, and documentation needed to complete a production deployment in under five minutes (with an optional Terraform reference arriving later for teams that prefer separate infrastructure lifecycles).

## Progress

- [x] (2025-10-24 21:40Z) Authored the initial ExecPlan derived from `plans/aws-ecs-deployment.md` and `.agent/PLANS.md`.
- [x] (2025-10-24 22:15Z) Updated the ExecPlan to reflect the simplified deployment API (App `deploy` kwarg, `Deployment` base class, single `python deploy.py` command, minimal health/drain responses, code-first configuration).
- [x] (2025-10-25 17:41Z) Implemented Phase 1.1: added the CDK `BaselineStack`, app scaffolding, and `ensure_baseline_stack` helper plus tests that cache CloudFormation outputs under `.pulse/<env>/baseline.json`.
- [x] (2025-10-26 12:21Z) Upgraded the `BaselineStack` to mint ACM certificates automatically (when no ARN is provided), emit DNS validation records via CloudFormation outputs, and added CDK assertions to guarantee the new behavior.
- [x] (2025-10-27) Implemented Phase 1.2: added `teardown_baseline_stack` helper that safely deletes baseline CloudFormation stacks with checks for active ECS services, handles various stack states (DELETE_IN_PROGRESS, failed states), supports forced deletion, and includes comprehensive test coverage for all failure modes.
- [x] (2025-10-27) Implemented Phase 2.1: created minimal FastAPI server (`aws_minimal_server.py`) with deployment info endpoint, health check, and authenticated drain endpoint, plus Dockerfile for containerization. Verified all endpoints work correctly via local Docker testing.
- [x] (2025-10-27) Implemented Phase 2.2: created deployment helpers in `pulse_aws/deployment.py` including `generate_deployment_id`, `build_and_push_image`, `register_task_definition`, `create_service_and_target_group`, and `install_listener_rules_and_switch_traffic`. All helpers are async-friendly, include proper error handling for duplicate deployments, and support the full ECS deployment workflow with header-based ALB routing for sticky sessions.
- [x] (2025-10-27) Implemented Phase 2.3 & 2.4: added `drain_previous_deployments` helper that calls the /drain endpoint on all previous deployments using header-based affinity, waits for targets to become unhealthy (with configurable timeout), and tracks drain status. Added `cleanup_inactive_deployments` helper that finds services with 0 running tasks, scales them to 0, and deletes the ECS service, listener rule, and target group. Integrated both functions into deploy.py for zero-downtime deployments with automatic cleanup.
- [x] (2025-10-27) Implemented stable drain secret caching at the script level: added `get_or_create_drain_secret()` function in deploy.py and verify.py that generates and caches drain secrets in `.pulse/<deployment_name>/secrets.json`. This keeps drain secret management as operational logic (script-level) rather than infrastructure logic (library-level). Added `.pulse/` to .gitignore to prevent committing secrets.
- [x] (2025-10-28) Implemented Phase 1 of the reaper plan: added `set_deployment_state()` helper to write deployment state to SSM Parameter Store (`/apps/<deployment_name>/<deployment_id>/state`), added `mark_previous_deployments_as_draining()` to mark all previous deployments as "draining" in SSM and service tags, integrated state management into the deploy workflow so new deployments are marked as "active" and previous ones as "draining", and updated the baseline task role to grant SSM:GetParameter permissions for reading deployment state.
- [x] (2025-10-28) Removed drain secret infrastructure: eliminated the `/drain` endpoint, drain secret generation/caching, and `drain_previous_deployments()` function since tasks now discover draining state via SSM polling instead of being told via HTTP POST. Simplified `DrainConfig` to be a placeholder for backward compatibility, removed `DRAIN_SECRET` from Dockerfile and environment variables, and updated deploy script to remove all drain secret logic. The deployment workflow is now fully automated via SSM state management and reaper Lambda orchestration.
- [x] (2025-10-28) Implemented Phase 2 of the reaper plan: updated `aws_minimal_server.py` to discover task ID from ECS metadata endpoint, poll SSM parameter state every N seconds (configurable via `DRAIN_POLL_SECONDS`), emit CloudWatch EMF metrics (`App/Drain:ShutdownReady` with dimensions `deployment_name`, `deployment_id`, `task_id`), and set `ShutdownReady=1` after a configurable grace period (`DRAIN_GRACE_SECONDS`) when marked as draining. Updated Dockerfile to install boto3 and requests, and updated `register_task_definition()` to pass `DEPLOYMENT_NAME` environment variable. Replaced deprecated FastAPI `on_event` with lifespan context manager.
- [x] (2025-10-28) Implemented Phase 3 of the reaper plan: created Lambda function (`reaper_lambda.py`) that processes draining services, checks CloudWatch metrics for ShutdownReady=1, and cleans up inactive services. Integrated reaper into `BaselineStack` (instead of separate stack) via `_create_reaper()` method that creates Lambda, IAM role (ECS/ALB/CloudWatch permissions), and EventBridge schedule. Set MAX_AGE_HR to 1.0 hour to enable cleanup of older deployments without Phase 2 logic. Reaper runs every 1 minute (configurable) and enforces MIN_AGE (60s) and MAX_AGE (1 hour) backstops. Reaper is now permanent infrastructure deployed alongside VPC/ALB/ECS cluster.
- [x] (2025-10-28) Fixed critical reaper bug: reaper was cleaning up ANY service with runningCount==0, including brand new services that were still spinning up. Updated both `reaper_lambda.py` and `deployment.py` cleanup functions to ONLY clean up services tagged with `state=draining`. Active services are now safe from premature cleanup. Bumped baseline version to 1.3.1.
- [x] (2025-10-28) Refactored reaper_lambda.py to accept AWS clients as function parameters instead of using global variables, making it importable and testable. Updated deployment.py to import and reuse cleanup_inactive_services() from reaper_lambda.py, eliminating code duplication. The reaper remains a single self-contained file that can be inlined in the Lambda while also being importable for manual cleanup operations. Bumped baseline version to 1.3.2.
- [x] (2025-10-29) Completed Phase 3.1: added `packages/pulse-aws/examples/Dockerfile.pulse` that multi-stage builds the Pulse Python environment, compiles the React Router frontend with Bun, wires workspace dependencies (`pulse-framework`, `pulse-ui-client`), and ships a runtime image that runs `pulse run examples/main.py --prod` without re-installing dependencies at startup. The image now exposes build args/env for deployment metadata and keeps Bun available for the single-server proxy.
- [ ] (2025-10-29) Continue Phase 3: adapt `deploy.py` for Pulse apps, add directive-based affinity plumbing in the Pulse runtime and client, implement `AWSECSPlugin`, and validate end-to-end multi-version deployments with graceful draining before landing.

## Surprises & Discoveries

- We can rely on CloudFormation to mint ACM certs at deploy time, so `BaselineStack` now only needs domain names (the ARN path remains available for bring-your-own certs).
- ACM's CloudFormation resource doesn't surface DNS validation records directly, so we introduced a lightweight `AwsCustomResource` that calls `DescribeCertificate` after creation and publishes the required CNAMEs via `CertificateValidationRecords` output.
- Terminology has been standardized throughout the codebase: `deployment_name` is used consistently to refer to the stable environment identifier (e.g., `"prod"`, `"dev"`), avoiding confusion between the environment slug and the per-version deployment ID.
- Naming convention: `deployment_name` is a stable identifier (e.g., `prod`, `myapp`) and `deployment_id` is just the timestamp+hash (e.g., `20251027-183000Z`). Resources combine them as needed (e.g., service `svc-{deployment_name}-{deployment_id}`), avoiding redundancy in hierarchical structures like SSM parameters.
- **Drain secret eliminated:** Originally planned to use authenticated HTTP endpoints (`POST /drain` with bearer token) to signal draining, but switched to SSM polling after realizing tasks can discover their state directly via Parameter Store. This eliminated the need for secret management, the `/drain` endpoint, and the `drain_previous_deployments()` HTTP call. Tasks simply poll `/apps/<deployment_name>/<deployment_id>/state` every few seconds.
- The reaper must ONLY clean up services tagged with `state=draining`, not all services with `runningCount==0`. New services take time to spin up their first task, and cleaning them up prematurely causes deployment failures. This was a critical bug caught during testing.

## Decision Log

- (2025-10-25 17:41Z) `ensure_baseline_stack` shells out to the CDK CLI (bootstrap → synth → deploy) instead of re-implementing deployment logic; `aws-cdk-lib`/`constructs` are now regular workspace dependencies so `uv run cdk ...` works everywhere, and baseline outputs are persisted as structured JSON for later helpers.
- (2025-10-26 16:00Z) Standardized on `deployment_name` terminology throughout `packages/pulse-aws` to align with the higher-level orchestration API and reduce confusion between the environment identifier and version-specific deployment IDs.
- (2025-10-27) Moved drain secret caching from library (`baseline.py`) to script level (`deploy.py`/`verify.py`) because secret management is operational/deployment logic rather than infrastructure logic. This keeps the library focused on AWS resource provisioning while scripts handle operational concerns like secrets.
- (2025-10-28) Eliminated drain secret infrastructure entirely. Originally planned to use authenticated `/drain` endpoints with bearer tokens, but realized tasks can discover draining state directly via SSM Parameter Store polling. This simplified the architecture by removing secret generation, caching, HTTP authentication, and the `drain_previous_deployments()` function. Tasks now poll `/apps/<deployment_name>/<deployment_id>/state` every few seconds, eliminating the need for push-based notifications.

## Outcomes & Retrospective

Implementation has not begun. Populate this section after each phase with a short summary of what shipped, what remains, and any lessons learned relative to the original purpose.

## Context and Orientation

Pulse is a Python-first framework whose server runtime lives in `packages/pulse/python/src/pulse`. The `App` class inside `packages/pulse/python/src/pulse/app.py` wires FastAPI, Socket.IO, middleware, and lifecycle hooks but currently lacks the ability to mark itself as draining, to fail health checks when no RenderSessions remain, or to react to SIGTERM. RenderSessions are managed inside `packages/pulse/python/src/pulse/render_session.py`; they represent a connected UI instance backed by WebSockets and server-side state. Plugins extend the runtime via `packages/pulse/python/src/pulse/plugin.py`, but there is no AWS-specific plugin yet.

The repository currently lacks a Dockerfile, CDK baseline, or AWS orchestration code. The architecture doc in `plans/aws-ecs-deployment.md` specifies the target behavior: weighted ALB target groups with per-RenderSession affinity, an authenticated drain endpoint, health-based cleanup, and automation that spins versioned ECS services up and down. We will deliver these capabilities as reusable helpers that a `deploy.py` script can compose, rather than hard-coding new CLI commands.

The repository root contains `examples/main.py` plus other sample apps that can be reused to prove an ECS deployment. Documentation under `docs/` does not yet cover AWS ECS.

## Implementation Plan

### Phase 1 – Baseline infrastructure

**1.1 CDK stack + deployment helper**  
Build `packages/pulse-aws/cdk/baseline.py` with a `BaselineStack` that provisions the shared VPC (two AZs), public/private subnets, routing tables, security groups, ALB with HTTPS listener (import an existing ACM certificate or request a new DNS-validated one automatically), CloudWatch log group, ECS cluster, execution/task IAM roles, and ECR repository. Implement a Python helper `ensure_baseline_stack(deployment_name, region, account)` inside `packages/pulse-aws/src/pulse_aws/baseline.py` that synthesizes the stack, auto-runs `cdk bootstrap` if missing, deploys `pulse-<deployment_name>-baseline`, waits for CloudFormation success, and writes the outputs (listener ARN, subnet IDs, security groups, cluster name, log group, ECR repo URL, certificate ARN/validation records) to `.pulse/<deployment_name>/baseline.json`. Re-running the helper must be idempotent; add tests/mocks to prove it short-circuits when the stack is already healthy.

**1.2 Baseline teardown helper**  
Write `teardown_baseline_stack(deployment_name, region)` that deletes `pulse-<deployment_name>-baseline`, watches the stack to completion, and removes cached artifacts. Protect the command with confirmations plus runtime checks that no active Pulse services exist. Include tests covering failure modes (e.g., stack in `UPDATE_ROLLBACK_FAILED`) to ensure we surface actionable errors.

**1.3 Baseline helpers for deployment scripts**  
Expose async utilities `deploy_baseline(deployment_name: str)` and `teardown_baseline(deployment_name: str)` that wrap the CDK helpers and emit structured logs. These functions are imported inside a standalone `deploy.py` script (run via `python deploy.py <deployment_name>`) instead of a CLI command so users can compose workflows freely. Document how the helpers accept optional AWS profile/region kwargs and cache outputs under `.pulse/<deployment_name>/baseline.json`.

### Phase 2 – AWS deployment workflow (minimal non-Pulse server)

Goal: Prove the full ECS deployment path (build → push → task definition → target group → service → ALB rule/traffic switch) and header-based stickiness using a minimal Python server. No Pulse dependencies, and no cleanup of old deployments yet.

**2.1 Minimal server + container image**

- Add `packages/pulse-aws/examples/aws_minimal_server.py`: a tiny FastAPI app that reads a `DEPLOYMENT_ID` at startup (from env or injected at build time). It exposes:
  - `GET /` → returns `{ "deployment_id": <id>, "ok": true }` and sets `X-Pulse-Render-Affinity: <id>` in the response headers.
  - `GET /_health` → returns 200 `{ "status": "ok" }` for ECS/ALB target health.
- - `POST /drain` → requires `Authorization: Bearer <secret>` where `<secret>` is set via `DRAIN_SECRET` at build/runtime; on first call, marks the server as draining and after 120 seconds (configurable via `DRAIN_HEALTH_FAIL_AFTER_SECONDS`) `/_health` begins returning HTTP 503 to simulate graceful drain before termination.
- Create `packages/pulse-aws/examples/Dockerfile` that installs `uv`, copies the minimal server, sets `ARG DEPLOYMENT_ID` and `ENV DEPLOYMENT_ID=$DEPLOYMENT_ID`, and runs `uv run uvicorn examples.aws_minimal_server:app --host 0.0.0.0 --port 8000`.
  - Also set `ARG DRAIN_SECRET` and `ENV DRAIN_SECRET=$DRAIN_SECRET`; optionally set `ENV DRAIN_HEALTH_FAIL_AFTER_SECONDS=120` (overridable at runtime).

**2.2 Baseline-driven deploy helpers (non-Pulse)**  
Implement new helpers in `packages/pulse-aws/src/pulse_aws/helpers.py`:

- `generate_deployment_id() -> str`: timestamped ID (e.g., `20251027-183000Z`).
- `build_and_push_image(dockerfile_path: Path, deployment_id: str, baseline: BaselineOutputs) -> str`: builds and pushes to the baseline ECR repo with the deployment ID as the tag.
- `register_task_definition(image_uri: str, deployment_id: str, baseline: BaselineOutputs) -> str`: Fargate task def with container env `DEPLOYMENT_ID` and port 8000.
- `create_service_and_target_group(deployment_name: str, deployment_id: str, task_def_arn: str, baseline: BaselineOutputs) -> tuple[str, str]`: creates a dedicated target group and ECS service for this ID.
- `install_listener_rules_and_switch_traffic(deployment_name: str, deployment_id: str, target_group_arn: str, baseline: BaselineOutputs)`: adds a header-based rule `X-Pulse-Render-Affinity == <deployment_id>` for sticky requests and sets the listener default action to forward 100% to the new target group. Existing header rules for prior deployments remain so clients sending the old header keep landing on the old version.

All helpers are async-friendly so a single `deploy.py` can orchestrate them.
They should fail with an informative error if a deployment with this ID already
exists.

**2.3 Programmatic verification**  
Add a verification step that:

- Issues a request to the ALB DNS name with no header and asserts the JSON `deployment_id` equals the new ID.
- Issues a request with header `X-Pulse-Render-Affinity: <old_id>` (if any old service exists) and asserts the response still returns `<old_id>`.
- Calls `POST /drain` on the prior deployment with the correct bearer token and waits (≤3 minutes) for `/_health` to flip to HTTP 503.

**2.4. Automated cleanup**
Add a helper:

- `cleanup_inactive_deployments(deployment_name) -> None` that finds all
  deployments with no active services, deletes them and their corresponding ALB
  rule.

**Out of scope for Phase 2**  
No Pulse integration or runtime changes

### Phase 3 – Pulse integration (Dockerfile, deployment, runtime affinity, plugin)

Integrate Pulse apps with the ECS deployment workflow, implement header-based affinity for RenderSession stickiness, and add AWS plugin for graceful draining.

**3.1 Pulse app Dockerfile**

- Create `packages/pulse-aws/examples/Dockerfile.pulse` that:
  - Installs `uv` for Python dependency management
  - Installs `bun` for JavaScript tooling
  - Copies the Pulse app Python file (e.g., `examples/main.py`)
  - Copies the React Router web project (`examples/web/`)
  - Installs Python dependencies via `uv sync`
  - Installs JavaScript dependencies via `bun install`
  - Accepts build args: `DEPLOYMENT_ID`, `DEPLOYMENT_NAME`, `DRAIN_POLL_SECONDS`, `DRAIN_GRACE_SECONDS`
  - Sets environment variables from build args
  - Runs `uv run pulse run <app_file>` in single-server mode
- Verify locally: build image, run container, fetch a page to confirm the Pulse app works

**3.2 Adapt deploy.py for Pulse apps**

- Update `packages/pulse-aws/scripts/deploy.py` to accept a `--pulse-app` flag pointing to a Pulse app file
- When `--pulse-app` is provided, use `Dockerfile.pulse` instead of the minimal server Dockerfile
- Pass `DEPLOYMENT_NAME` and `DEPLOYMENT_ID` as build args
- Pass drain configuration (`DRAIN_POLL_SECONDS`, `DRAIN_GRACE_SECONDS`) as build args
- Run a single deploy and verify the Pulse app is accessible at the ALB URL

**3.3 Pulse runtime changes for affinity and draining**

Implement general-purpose header/auth propagation mechanism:

- In `packages/pulse/python/src/pulse/app.py`, add a `directives` field to prerender responses that can specify arbitrary headers and Socket.IO auth values to attach to subsequent requests
- Update the layout template (`packages/pulse/python/src/pulse/codegen/templates/layout.py`) to:
  - Store `directives` from prerender response in `sessionStorage` (similar to how `renderId` is stored)
  - In `clientLoader`, read directives from `sessionStorage` and apply them as headers to the prerender fetch
- Update `packages/pulse/js/src/client.tsx` to read `directives` from `sessionStorage` and attach them to Socket.IO connections
- Replace the current special-case render ID with this general mechanism (renderId becomes part of directives)

Implement AWSECSPlugin:

- Create `packages/pulse-aws/src/pulse_aws/plugin.py` with `AWSECSPlugin(deployment_name: str, deployment_id: str)`
- Plugin behavior:
  - Discovers task ID from ECS metadata endpoint (`ECS_CONTAINER_METADATA_URI_V4`)
  - Polls SSM parameter `/apps/<deployment_name>/<deployment_id>/state` every N seconds (configurable via `DRAIN_POLL_SECONDS`)
  - When state changes to `draining`:
    - Blocks new RenderSession creation (returns error/redirect for prerender requests without a valid renderId)
    - Does NOT block WebSocket connections (existing sessions can reconnect)
    - Starts a grace period timer (configurable via `DRAIN_GRACE_SECONDS`)
  - Periodically checks `len(app.render_sessions)` to count active sessions
  - After grace period expires AND active sessions reach zero, emits CloudWatch EMF metric `App/Drain:ShutdownReady=1` with dimensions `deployment_name`, `deployment_id`, `task_id`
  - Until shutdown ready, emits `App/Drain:ShutdownReady=0`
- Injects `X-Pulse-Render-Affinity: <deployment_id>` header into the prerender `directives` so client includes it on all subsequent requests and WebSocket connections
- Keeps health checks passing throughout drain process; reaper handles cleanup based on metrics

**3.4 End-to-end deployment verification**

- Deploy the Pulse app once, verify `X-Pulse-Render-Affinity` header is present in requests
- Deploy a second version with a visual change
- Open a new browser tab, confirm it lands on the new version
- In the original tab (old version), navigate around and confirm affinity is maintained
- Close the old tab, wait for grace period + drain detection
- Verify old deployment emits `ShutdownReady=1` and is cleaned up by reaper
- Confirm no dangling target groups or listener rules remain

### Phase 4 – Finalization and cleanup

Wrap up operational concerns and polish the API.

**4.1 Cleanup of drained/idle versions**  
Implement `cleanup(deployment_name: str)` that finds services/target groups with zero desired/running tasks and no registered targets; remove their listener rules, target groups, and services.

**4.2 Official deploy script for pulse-aws**  
Ship a cohesive `deploy.py` supporting:

- Certificate provisioning
- Baseline provisioning
- Pulse app deployment
- Cleanup of drained/idle versions

**4.2 Official teardown script for pulse-aws**  
Ship a cohesive `teardown.py` that can perform:

- Teardown of a single deployment
- Teardown of all deployments
- Teardown of all deployments + baseline infrastructure

**4.3 API and docs polish**  
Stabilize helper signatures, error messages, and logging. Refresh `README.md` and the deployment guide, and ensure `make all` passes.

## Example End-State APIs

### Integrated CDK baseline

Rather than asking every team to provision networking/ALB/ECS ahead of time, `python deploy.py` owns that baseline by running an embedded CDK app. Developers provide a stable environment slug (e.g., `pulse-prod` or `pulse-dev`) either through the AWSECSPlugin configuration or script flags. On each deploy, the script:

1. Synthesizes the CDK stack `pulse-<env>-baseline`, which includes the VPC (two AZs), public + private subnets, routing, security groups, ALB with HTTPS listener + ACM certificate import, CloudWatch log group, ECS cluster, task/execution roles, and an ECR repository.
2. Ensures the CDK bootstrap stack exists in the target account/region; if not, it runs `cdk bootstrap` automatically.
3. Calls `cdk deploy --require-approval never pulse-<env>-baseline` and waits for CloudFormation to report success, caching the emitted outputs in `.pulse/<env>/baseline.json` so subsequent deploys can skip redundant lookups.

Because the stack name is deterministic, rerunning `python deploy.py` only updates resources whose definitions change—CloudFormation provides idempotence, rollback, and drift detection. The script reads the CloudFormation outputs (listener ARN, subnet IDs, security groups, cluster name, log group, ECR repo URL) and passes them directly into the helper functions. For teams who prefer to manage infrastructure separately, we will still publish an equivalent Terraform package once the CDK path is solid; consuming it will simply mean disabling the auto-provision step and supplying the outputs manually.

The ALB portion of the CDK stack exposes listener ARNs and security groups but leaves per-version routing up to the deployment helpers; `AWSECS` will create (and later delete) header-based rules of the form `X-Pulse-Render-Affinity = 20251027-183000Z` that forward directly to the matching target group.

### GitHub Actions deployment workflow

Because the CDK baseline deploys automatically, the intended CI/CD integration is still a lightweight workflow that runs tests, builds the Docker image, and invokes the single deploy command. A minimal `.github/workflows/deploy.yml`:

```
name: Deploy Pulse App

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version tag to deploy"
        required: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    env:
      AWS_REGION: us-east-1
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: extractions/setup-uv@v1
      - name: Install dependencies
        run: uv pip install -r requirements.txt
      - name: Assume AWS role
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/pulse-deployer
          aws-region: ${{ env.AWS_REGION }}
      - name: Verify version
        run: |
          uv run python -c "import importlib; mod = importlib.import_module('examples.aws_ecs_app'); app = getattr(mod, 'app'); assert app.version == '${{ github.event.inputs.version }}', f'version mismatch: {app.version} != ${{ github.event.inputs.version }}'"
      - name: Deploy
        run: |
          python deploy.py --deployment pulse-prod --app examples/aws_ecs_app.py --region $AWS_REGION --profile default
```

The workflow delegates all environment-specific knowledge to the `AWSECS` deployment object inside `examples/aws_ecs_app.py`, so CI only needs AWS credentials and the desired version string.

### Header-based RenderSession affinity

Pulse cannot rely on ALB cookies because they are shared across browser tabs. Instead, the JavaScript runtime tracks affinity per RenderSession (and therefore per tab). During the first render handshake, the server returns the `deployment_id` and a `render_session_affinity` token. The client stores this data in `sessionStorage` (scoped to the tab) and includes it on every HTTP/WebSocket request via a custom header (e.g., `X-Pulse-Render-Affinity: 20251027-183000Z`) and Socket.IO query param. The deployment process installs one listener rule per active deployment that matches this header value and forwards traffic to that deployment's dedicated target group, ensuring reconnects for that tab keep hitting the original service even after newer deployments ship. The listener's default action (no header present) uses weighted forwarding so that any tab without an affinity token – i.e., a fresh tab – lands on the newest deployment automatically. This mirrors how static assets behave on the web: old tabs continue running old JavaScript, while new tabs immediately receive upgraded code.

## Concrete Steps

While iterating on the runtime and deployment plugin, keep the relevant unit tests green:

    uv run pytest packages/pulse/python/tests/test_app_draining.py packages/pulse/python/tests/test_deploy_plugin.py

Regenerate locks and enforce formatting whenever dependencies or code generation change:

    uv lock
    make format

Test the container locally before publishing to ECR to make sure stdout/stderr logging behaves as expected:

    docker build -f packages/pulse-aws/examples/Dockerfile -t pulse-app:test .
    docker run --rm -p 8000:8000 pulse-app:test uv run uvicorn examples.main:app --host 0.0.0.0 --port 8000

Prime the CDK baseline (or refresh it independently of an application deploy):

    python deploy.py --deployment pulse-dev --baseline-only

This flag should run the CDK bootstrap (if required), deploy the `pulse-dev-baseline` CloudFormation stack, persist its outputs under `.pulse/pulse-dev/baseline.json`, and exit without creating a new application version. Subsequent invocations without `--baseline-only` should automatically detect that the stack already exists.

Deploy a new version by loading the app and letting the deployment helpers drive every AWS call:

    python deploy.py --deployment pulse-prod --app examples/aws_ecs_app.py --dockerfile docker/aws-ecs/Dockerfile

Verify the rollout via AWS CLI once the script returns:

    aws ecs describe-services --cluster pulse-prod --services svc-prod-20251027-183000Z
    aws elbv2 describe-listeners --listener-arns arn:aws:elasticloadbalancing:...

Guard the codebase with the standard quality bar:

    make lint
    make typecheck
    make test

## Validation and Acceptance

Functional validation (local) still starts by running `uv run pulse run examples/main.py --bind-port 8000`, checking `/_pulse/health` for `{"version": "...", "draining": false}`, issuing an authenticated POST to `/_pulse/admin/drain`, and observing that the response is just `{ "status": "ok" }` while new RenderSessions are denied. The unit tests introduced for draining and deployments must pass before merging.

Infrastructure validation (AWS) requires confirming that the `pulse-<env>-baseline` CloudFormation stack is up-to-date (via `aws cloudformation describe-stacks`) and spot-checking the emitted resources with `aws ec2 describe-subnets`, `aws elbv2 describe-load-balancers`, and `aws ecs describe-clusters` to ensure the expected VPC, ALB, and cluster exist with the names referenced inside the `AWSECS` configuration.

Deployment validation is a single script invocation: `python deploy.py --deployment pulse-prod --app examples/aws_ecs_app.py`. Success is demonstrated by AWS CLI output that shows the new ECS service in steady state, ALB listener weights pointing at the new version, and CloudWatch Logs receiving stdout/stderr from the running tasks. Sticky sessions should keep existing browser tabs on their original version even after the new rollout completes.

Drain validation consists of calling the deployment-provided drain endpoint (via a simple `curl -X POST -H "Authorization: Bearer <token>" https://<alb>/_pulse/admin/drain`) and repeatedly checking `/_pulse/health` until it responds with HTTP 503 and `{"version":"20251027-183000Z","draining":true}`. ECS should then scale the drained service down automatically.

Teardown validation runs `python deploy.py --deployment pulse-dev --teardown --force` after ensuring no services remain, then checks that the CloudFormation stack disappears and cached `.pulse/` outputs are removed.

Before landing the work, run `make format-check`, `make lint`, `make typecheck`, and `make test`, and proofread `docs/deployment/aws-ecs.md`.

## Idempotence and Recovery

The drain route is idempotent and safe to call multiple times. The CDK baseline derives its safety from CloudFormation: rerunning the bootstrap/deploy sequence reconciles drift without manual cleanup, and stack locking prevents concurrent writers. Running `python deploy.py --deployment <name> --app <path>` again should short-circuit baseline provisioning yet fail fast if you reuse a previous `deployment_id`. If the script fails halfway (e.g., after pushing the image but before shifting the ALB), rerunning it with the same arguments is safe because each helper checks for pre-existing resources and only mutates what is necessary. Rollbacks are manual for now: rerun the script with the prior code + a new deployment ID, then drain the newer build.

## Artifacts and Notes

Record evidence snippets here as work progresses. Examples to capture:

    $ curl -s https://pulse.example.com/_pulse/health | jq
    {
      "version": "20251027-183000Z",
      "status": "draining"
    }

    $ curl -s -X POST -H "Authorization: Bearer ****" https://pulse.example.com/_pulse/admin/drain
    {
      "status": "ok"
    }

    $ python deploy.py --deployment pulse-prod --app examples/aws_ecs_app.py
    -> Building docker/aws-ecs/Dockerfile as 123456789012.dkr.ecr.us-east-1.amazonaws.com/pulse-app:20251027-183000Z
    -> Pushing image...
    -> Creating target group tg-prod-20251027-183000Z
    -> Updating listener arn:aws:elasticloadbalancing:... weights (20251027-183000Z=100, 20251027-120000Z=0)
    -> Service svc-prod-20251027-183000Z reached steady state

    $ aws ecs describe-services --cluster pulse-prod --services svc-prod-20251027-183000Z | jq '.services[0].events[0]'
    {
      "message": "steady state reached",
      "createdAt": "2025-10-24T22:10:14Z"
    }

Update this section with real outputs, CloudWatch links, and screenshots once AWS testing is performed.

## Interfaces and Dependencies

Expose the following interfaces so that all moving parts are explicit:

- In `packages/pulse/python/src/pulse/app.py`, extend `AppStatus` with `draining = 3` / `stopped = 4`, add helpers such as `set_draining()`, `is_draining()`, and `await wait_for_drain_completion()`, and block WebSocket connections / new RenderSessions once draining starts. The FastAPI health route should emit `{"version": ..., "draining": bool}` and return HTTP 503 once the active session count hits zero.
- Provide `AWSECSPlugin(secret: str | Callable[[], str])` in `packages/pulse-aws/src/pulse_aws/plugin.py`. The plugin registers the `/_pulse/admin/drain` endpoint, injects prerender directives (`X-Pulse-Render-Affinity`, `X-Pulse-Render-Id`), and exposes middleware hooks so other deployment recipes can piggyback on the same mechanism.
- Implement the async helpers described in Phase 2 (`generate_deployment_id`, `deploy_baseline`, `deploy_app`, `wait_until_healthy`, `drain_previous_deployments`, `cleanup`) under `packages/pulse-aws/src/pulse_aws/helpers.py`. Each helper should accept explicit parameters (deployment name, deployment ID, dockerfile path, baseline outputs) and rely only on data supplied by the caller, making them easy to compose inside custom scripts.
- On the client side (see `packages/pulse/js/src/serialize/serializer.ts` and `packages/pulse/js/src/client.tsx`), persist the prerender `directives`, attach their headers to every HTTP fetch, and include them in Socket.IO auth/query params so ALB header rules keep each tab pinned to the correct version.

The CDK app lives under `packages/pulse-aws/src/pulse_aws/cdk/` and exposes a `BaselineStack` whose CloudFormation outputs map one-to-one with the values the helpers expect (listener ARN, subnet IDs, security groups, cluster name, log group, ECR repo URL, certificate ARN, DNS validation records). Store the most recent outputs in `.pulse/<deployment_name>/baseline.json` so deployment scripts can read them without rerunning `cdk synth`. Document the mapping in `docs/deployment/aws-ecs.md`, and note that we will later publish a Terraform equivalent for teams that prefer a different tooling stack.

Update `packages/pulse/python/pyproject.toml` dependencies with `boto3>=1.35.0,<2.0`, `botocore>=1.35.0,<2.0`, and `docker>=7.1.0` so the deployment helpers can interact with AWS and build images; retain `httpx` for drain calls. No new environment variables are introduced because all deployment configuration is code-first via the `AWSECS` plugin, and secrets can be retrieved lazily in code (e.g., `lambda: secretsmanager.get_secret_value(...)`).

## Change Log

No entries yet. Begin recording notable updates once implementation work produces concrete changes worth summarizing.
