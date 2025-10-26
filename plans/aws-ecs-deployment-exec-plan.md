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

## Surprises & Discoveries

- We can rely on CloudFormation to mint ACM certs at deploy time, so `BaselineStack` now only needs domain names (the ARN path remains available for bring-your-own certs).
- ACM’s CloudFormation resource doesn’t surface DNS validation records directly, so we introduced a lightweight `AwsCustomResource` that calls `DescribeCertificate` after creation and publishes the required CNAMEs via `CertificateValidationRecords` output.

## Decision Log

- (2025-10-25 17:41Z) `ensure_baseline_stack` shells out to the CDK CLI (bootstrap → synth → deploy) instead of re-implementing deployment logic; `aws-cdk-lib`/`constructs` are now regular workspace dependencies so `uv run cdk ...` works everywhere, and baseline outputs are persisted as structured JSON for later helpers.

## Outcomes & Retrospective

Implementation has not begun. Populate this section after each phase with a short summary of what shipped, what remains, and any lessons learned relative to the original purpose.

## Context and Orientation

Pulse is a Python-first framework whose server runtime lives in `packages/pulse/python/src/pulse`. The `App` class inside `packages/pulse/python/src/pulse/app.py` wires FastAPI, Socket.IO, middleware, and lifecycle hooks but currently lacks the ability to mark itself as draining, to fail health checks when no RenderSessions remain, or to react to SIGTERM. RenderSessions are managed inside `packages/pulse/python/src/pulse/render_session.py`; they represent a connected UI instance backed by WebSockets and server-side state. Plugins extend the runtime via `packages/pulse/python/src/pulse/plugin.py`, but there is no AWS-specific plugin yet.

The repository currently lacks a Dockerfile, CDK baseline, or AWS orchestration code. The architecture doc in `plans/aws-ecs-deployment.md` specifies the target behavior: weighted ALB target groups with per-RenderSession affinity, an authenticated drain endpoint, health-based cleanup, and automation that spins versioned ECS services up and down. We will deliver these capabilities as reusable helpers that a `deploy.py` script can compose, rather than hard-coding new CLI commands.

The repository root contains `examples/main.py` plus other sample apps that can be reused to prove an ECS deployment. Documentation under `docs/` does not yet cover AWS ECS.

## Implementation Plan

### Phase 1 – Baseline infrastructure

**1.1 CDK stack + deployment helper**  
Build `packages/pulse-aws/cdk/baseline.py` with a `BaselineStack` that provisions the shared VPC (two AZs), public/private subnets, routing tables, security groups, ALB with HTTPS listener (import an existing ACM certificate or request a new DNS-validated one automatically), CloudWatch log group, ECS cluster, execution/task IAM roles, and ECR repository. Implement a Python helper `ensure_baseline_stack(env_name, region, account)` inside `packages/pulse-aws/src/pulse_aws/baseline.py` that synthesizes the stack, auto-runs `cdk bootstrap` if missing, deploys `pulse-<env>-baseline`, waits for CloudFormation success, and writes the outputs (listener ARN, subnet IDs, security groups, cluster name, log group, ECR repo URL, certificate ARN/validation records) to `.pulse/<env>/baseline.json`. Re-running the helper must be idempotent; add tests/mocks to prove it short-circuits when the stack is already healthy.

**1.2 Baseline teardown helper**  
Write `teardown_baseline_stack(env_name, region)` that deletes `pulse-<env>-baseline`, watches the stack to completion, and removes cached artifacts. Protect the command with confirmations plus runtime checks that no active Pulse services exist. Include tests covering failure modes (e.g., stack in `UPDATE_ROLLBACK_FAILED`) to ensure we surface actionable errors.

**1.3 Baseline helpers for deployment scripts**  
Expose async utilities `deploy_baseline(deployment_name: str)` and `teardown_baseline(deployment_name: str)` that wrap the CDK helpers and emit structured logs. These functions are imported inside a standalone `deploy.py` script (run via `python deploy.py <deployment_name>`) instead of a CLI command so users can compose workflows freely. Document how the helpers accept optional AWS profile/region kwargs and cache outputs under `.pulse/<deployment_name>/baseline.json`.

### Phase 2 – Pulse deployment workflow

**2.1 Container image**  
Create `docker/aws-ecs/Dockerfile` that installs the repo and sets `ENTRYPOINT ["uv", "run", "pulse", "run"]` with `CMD ["examples.main:app", "--host", "0.0.0.0", "--port", "8000"]`. No `entrypoint.sh` is needed—the deployment script can override app targets/ports via additional args. Validate locally with `docker run` to ensure logs land on stdout/stderr and the server binds to all interfaces.

**2.2 Client directives**  
Add a `directives` object to the prerender payload (and Socket.IO handshake) that can carry `headers` and `wsAuth` instructions. `AWSECS` will supply a unique deployment ID per release by registering a prerender middleware that injects `{"headers": {"X-Pulse-Render-Affinity": deployment_id}}` into the outgoing payload, and the serializer will merge it into the JSON sent to the browser. Update `packages/pulse/python/src/pulse/codegen/templates/layout.py` so the generated `clientLoader` reads `directives.headers` from `sessionStorage` (persisted alongside `renderId`) and attaches them to every fetch call; do the same in `packages/pulse/js/src/client.tsx` so the `PulseClient` always sets those headers and Socket.IO auth params when connecting. Replace bespoke `renderId` handling: the prerender route now inspects the `X-Pulse-Render-Id` header (populated by the loader via directives) to look up existing sessions through `session_middleware`, and renderId travels via the directives mechanism instead of being embedded in request bodies.

**2.3 Deployment helpers**  
Ship the primitives that user-land `deploy.py` scripts compose:
- `AWSECSPlugin(secret: str | Callable[[], str])` registers the authenticated `/_pulse/admin/drain` endpoint and exposes middleware hooks so prerender directives (affinity header + render id) are always present.
- `generate_deployment_id(deployment_name: str, app: App) -> str` returns a monotonically increasing or timestamped identifier (e.g., `pulse-prod-v124-20241105-1830Z`). The helper should pull any app-level version metadata but never rely on it, ensuring each run produces a fresh ID.
- `deploy_app(deployment_name: str, deployment_id: str, dockerfile_path: Path, baseline: BaselineOutputs)` builds/tags the Docker image, pushes it to the baseline’s ECR repo, registers an ECS task definition, creates a target group + service named after `deployment_id`, and installs the ALB listener rule keyed off `X-Pulse-Render-Affinity`. If the deployment ID already exists (healthy or draining), raise an error instructing the operator to choose a new ID. All helpers are async so they can be orchestrated with `asyncio.run` inside `deploy.py`.

**2.4 Draining + health coordination**  
Enhance the `App` class so draining forbids new WebSocket connections and RenderSessions and flips health to HTTP 503 once sessions hit zero. Build async orchestration helpers:
- `wait_until_healthy(deployment_name: str, deployment_id: str)` polls ELB/ECS/health endpoints until the new service reports healthy and the `/ _pulse/health` route returns 200 with `draining=false`.
- `drain_previous_deployments(deployment_name: str, deployment_id: str)` enumerates older services/target groups, issues HTTP POSTs to their drain endpoint (no SIGTERM), watches for each to return HTTP 503, and then sets listener weights to zero / lowers ECS desired counts.

These functions guarantee new connections land on the latest version while sticky tabs keep working until they disconnect.

**2.5 Cleanup of drained versions**  
Implement `cleanup(deployment_name: str)` that loads the cached baseline outputs for the given deployment, inspects the AWS account for ECS services/target groups tied to that name, detects which are idle (desired/running count zero and no registered targets), and removes their ALB listener rules, target groups, and services. Run this helper at the end of every `python deploy.py` invocation so CI/CD pipelines automatically garbage-collect stale resources. Emit logs whenever cleanup occurs so operators can trace what was removed.

**2.6 Deployment script orchestration**  
Provide a reference `deploy.py` that composes the helpers in this order:
1. `deployment_name = os.environ["PULSE_DEPLOYMENT"]`; `deployment_id = generate_deployment_id(deployment_name, app)`.
2. `baseline = await deploy_baseline(deployment_name)`.
3. `await deploy_app(deployment_name, deployment_id, dockerfile_path, baseline)`.
4. `await wait_until_healthy(deployment_name, deployment_id)`.
5. `await drain_previous_deployments(deployment_name, deployment_id)`.
6. `await cleanup(deployment_name)`.

CI runs `python deploy.py --deployment pulse-prod --dockerfile docker/aws-ecs/Dockerfile` (plus AWS profile/region flags). Because the workflow is purely script-based, we can evolve the API without touching the CLI; once the API stabilizes we can add optional Typer commands that simply call into these helpers.

### Phase 3 – Runtime guarantees, docs, and example app

Update `packages/pulse/python/src/pulse/app.py` so `AppStatus` adds `draining = 3` and shifts `stopped` to 4. Expose optional constructor kwargs `version: str | None` and `deploy: Deployment | None`, backing them with helpers such as `set_draining` and `is_draining` that flip a boolean flag and timestamp when draining begins. Ensure `create_render`, `/prerender`, and the Socket.IO `connect` handler refuse to create new render sessions after draining starts while still serving existing connections. Simplify the FastAPI health endpoint to respond with only `{"version": <str>, "draining": <bool>}` and switch to HTTP 503 once all sessions close to signal ECS/ALB. This failing health check is what ultimately causes ECS to terminate tasks for drained versions, so the runtime must be deterministic here and should include instrumentation so we can later add an inactivity timeout for stubborn sessions. Implement a `Deployment` base class (a plugin with an async `deploy(app, version)` method) plus a `DeployToECS` plugin that contributes the authenticated `/_pulse/admin/drain` endpoint returning `{ "status": "ok" }` or `{ "status": "already_draining" }`. The plugin should accept either a raw token string or a callable that fetches the secret from services like AWS Secrets Manager, Vault, or Doppler so teams stay flexible in how credentials are issued. Create unit tests (`packages/pulse/python/tests/test_app_draining.py`, `test_deploy_plugin.py`) to cover the new behaviors and keep manual validation instructions limited to the simple health and drain responses.

Author `docs/deployment/aws-ecs.md` detailing prerequisites, the CDK bootstrap flow baked into `python deploy.py`, configuring `ps.App(..., plugins=[AWSECSPlugin(...)])`, and running `python deploy.py --deployment pulse-prod --app examples/aws_ecs_app.py`. Provide `examples/aws_ecs_app.py` showing a realistic configuration (environment name, cluster identifiers, secrets, desired counts) entirely in code. Capture validation evidence (command transcripts, AWS CLI snippets) in the `Artifacts and Notes` section as phases complete, and refresh `README.md` with a pointer to the deployment guide. Call out that an optional Terraform package will ship later for teams that want to provision the baseline stack outside these helpers. This phase also codifies the verification steps: local drain/health testing, CDK stack outputs, `python deploy.py` success, and CloudWatch log checks.


## Example End-State APIs

### Integrated CDK baseline

Rather than asking every team to provision networking/ALB/ECS ahead of time, `python deploy.py` owns that baseline by running an embedded CDK app. Developers provide a stable environment slug (e.g., `pulse-prod` or `pulse-dev`) either through the AWSECSPlugin configuration or script flags. On each deploy, the script:

1. Synthesizes the CDK stack `pulse-<env>-baseline`, which includes the VPC (two AZs), public + private subnets, routing, security groups, ALB with HTTPS listener + ACM certificate import, CloudWatch log group, ECS cluster, task/execution roles, and an ECR repository.
2. Ensures the CDK bootstrap stack exists in the target account/region; if not, it runs `cdk bootstrap` automatically.
3. Calls `cdk deploy --require-approval never pulse-<env>-baseline` and waits for CloudFormation to report success, caching the emitted outputs in `.pulse/<env>/baseline.json` so subsequent deploys can skip redundant lookups.

Because the stack name is deterministic, rerunning `python deploy.py` only updates resources whose definitions change—CloudFormation provides idempotence, rollback, and drift detection. The script reads the CloudFormation outputs (listener ARN, subnet IDs, security groups, cluster name, log group, ECR repo URL) and passes them directly into the helper functions. For teams who prefer to manage infrastructure separately, we will still publish an equivalent Terraform package once the CDK path is solid; consuming it will simply mean disabling the auto-provision step and supplying the outputs manually.

The ALB portion of the CDK stack exposes listener ARNs and security groups but leaves per-version routing up to the deployment helpers; `AWSECS` will create (and later delete) header-based rules of the form `X-Pulse-Render-Version = v124` that forward directly to the matching target group.

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

Pulse cannot rely on ALB cookies because they are shared across browser tabs. Instead, the JavaScript runtime tracks affinity per RenderSession (and therefore per tab). During the first render handshake, the server returns `app.version` and a `render_session_affinity` token. The client stores this data in `sessionStorage` (scoped to the tab) and includes it on every HTTP/WebSocket request via a custom header (e.g., `X-Pulse-Render-Version`) and Socket.IO query param. `AWSECS.deploy` installs one listener rule per active version that matches this header value and forwards traffic to that version’s dedicated target group, ensuring reconnects for that tab keep hitting the original service even after newer versions ship. The listener’s default action (no header present) uses weighted forwarding so that any tab without an affinity token – i.e., a fresh tab – lands on the newest deployment automatically. This mirrors how static assets behave on the web: old tabs continue running old JavaScript, while new tabs immediately receive upgraded code.

## Concrete Steps

While iterating on the runtime and deployment plugin, keep the relevant unit tests green:

    uv run pytest packages/pulse/python/tests/test_app_draining.py packages/pulse/python/tests/test_deploy_plugin.py

Regenerate locks and enforce formatting whenever dependencies or code generation change:

    uv lock
    make format

Test the container locally before publishing to ECR to make sure stdout/stderr logging behaves as expected:

    docker build -f docker/aws-ecs/Dockerfile -t pulse-app:test .
    docker run --rm -p 8000:8000 pulse-app:test uv run uvicorn examples.main:app --host 0.0.0.0 --port 8000

Prime the CDK baseline (or refresh it independently of an application deploy):

    python deploy.py --deployment pulse-dev --baseline-only

This flag should run the CDK bootstrap (if required), deploy the `pulse-dev-baseline` CloudFormation stack, persist its outputs under `.pulse/pulse-dev/baseline.json`, and exit without creating a new application version. Subsequent invocations without `--baseline-only` should automatically detect that the stack already exists.

Deploy a new version by loading the app and letting the deployment helpers drive every AWS call:

    python deploy.py --deployment pulse-prod --app examples/aws_ecs_app.py --dockerfile docker/aws-ecs/Dockerfile

Verify the rollout via AWS CLI once the script returns:

    aws ecs describe-services --cluster pulse-prod --services pulse-app-v124
    aws elbv2 describe-listeners --listener-arns arn:aws:elasticloadbalancing:...

Guard the codebase with the standard quality bar:

    make lint
    make typecheck
    make test

## Validation and Acceptance

Functional validation (local) still starts by running `uv run pulse run examples/main.py --bind-port 8000`, checking `/_pulse/health` for `{"version": "...", "draining": false}`, issuing an authenticated POST to `/_pulse/admin/drain`, and observing that the response is just `{ "status": "ok" }` while new RenderSessions are denied. The unit tests introduced for draining and deployments must pass before merging.

Infrastructure validation (AWS) requires confirming that the `pulse-<env>-baseline` CloudFormation stack is up-to-date (via `aws cloudformation describe-stacks`) and spot-checking the emitted resources with `aws ec2 describe-subnets`, `aws elbv2 describe-load-balancers`, and `aws ecs describe-clusters` to ensure the expected VPC, ALB, and cluster exist with the names referenced inside the `AWSECS` configuration.

Deployment validation is a single script invocation: `python deploy.py --deployment pulse-prod --app examples/aws_ecs_app.py`. Success is demonstrated by AWS CLI output that shows the new ECS service in steady state, ALB listener weights pointing at the new version, and CloudWatch Logs receiving stdout/stderr from the running tasks. Sticky sessions should keep existing browser tabs on their original version even after the new rollout completes.

Drain validation consists of calling the deployment-provided drain endpoint (via a simple `curl -X POST -H "Authorization: Bearer <token>" https://<alb>/_pulse/admin/drain`) and repeatedly checking `/_pulse/health` until it responds with HTTP 503 and `{"version":"v124","draining":true}`. ECS should then scale the drained service down automatically.

Teardown validation runs `python deploy.py --deployment pulse-dev --teardown --force` after ensuring no services remain, then checks that the CloudFormation stack disappears and cached `.pulse/` outputs are removed.

Before landing the work, run `make format-check`, `make lint`, `make typecheck`, and `make test`, and proofread `docs/deployment/aws-ecs.md`.

## Idempotence and Recovery

The drain route is idempotent and safe to call multiple times. The CDK baseline derives its safety from CloudFormation: rerunning the bootstrap/deploy sequence reconciles drift without manual cleanup, and stack locking prevents concurrent writers. Running `python deploy.py --deployment <name> --app <path>` again should short-circuit baseline provisioning yet fail fast if you reuse a previous `deployment_id`. If the script fails halfway (e.g., after pushing the image but before shifting the ALB), rerunning it with the same arguments is safe because each helper checks for pre-existing resources and only mutates what is necessary. Rollbacks are manual for now: rerun the script with the prior code + a new deployment ID, then drain the newer build.

## Artifacts and Notes

Record evidence snippets here as work progresses. Examples to capture:

    $ curl -s https://pulse.example.com/_pulse/health | jq
    {
      "version": "v124",
      "status": "draining"
    }

    $ curl -s -X POST -H "Authorization: Bearer ****" https://pulse.example.com/_pulse/admin/drain
    {
      "status": "ok"
    }

    $ python deploy.py --deployment pulse-prod --app examples/aws_ecs_app.py
    -> Building docker/aws-ecs/Dockerfile as 123456789012.dkr.ecr.us-east-1.amazonaws.com/pulse-app:v125
    -> Pushing image...
    -> Creating target group pulse-prod-v125
    -> Updating listener arn:aws:elasticloadbalancing:... weights (v125=100, v124=0)
    -> Service pulse-app-v125 reached steady state

    $ aws ecs describe-services --cluster pulse-prod --services pulse-app-v125 | jq '.services[0].events[0]'
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
