# ECS Draining + Reaper — Implementation plan

## Phase 1 — Deployment script sets SSM params ✅

### What this phase delivers

- For each deployment, writes `/apps/<deployment_name>/<deployment_id>/state` in **SSM Parameter Store** to `active` for the new deployment and `draining` for all previous ones.
- Tag ECS services: `deployment_name`, `deployment_id`, `state`.
- Removed drain secret infrastructure since tasks discover draining state via SSM polling.

**Status: ✅ Complete** (2025-10-28)

**Note:** The original plan included a drain secret and `/drain` endpoint for marking services as draining. This was replaced with a simpler SSM-based approach where tasks poll their state parameter directly, eliminating the need for authenticated HTTP endpoints and secret management.

### Inputs

- `deployment_name` (e.g., `myapp`, `prod`) — stable environment identifier
- `deployment_id` (e.g., `20251028-183000-abc1234`) — unique timestamp + hash (no deployment_name prefix)
- `REGION`, `ACCOUNT_ID`
- ECS cluster/service naming: `svc-<deployment_name>-<deployment_id>`

### Example Script (Python) — idempotent

In practice, integrate the logic into the existing code.

```python
# phase1_set_ssm.py
import boto3, os, re

REGION          = os.environ.get("AWS_REGION", "eu-west-1")
CLUSTER         = os.environ["CLUSTER"]
DEPLOYMENT_NAME = os.environ["DEPLOYMENT_NAME"]
DEPLOYMENT_ID   = os.environ["DEPLOYMENT_ID"]

ecs = boto3.client("ecs", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)

def put_state(deployment_id, state):
    ssm.put_parameter(
        Name=f"/apps/{DEPLOYMENT_NAME}/{deployment_id}/state",
        Value=state,
        Type="String",
        Overwrite=True,
    )

# 1) Mark new deployment active
put_state(DEPLOYMENT_ID, "active")

# 2) Flip older services of this deployment_name to draining
arns = ecs.list_services(cluster=CLUSTER)["serviceArns"]
for i in range(0, len(arns), 10):
    desc = ecs.describe_services(cluster=CLUSTER, services=arns[i:i+10])["services"]
    for svc in desc:
        name = svc["serviceName"]
        # Services are named svc-{deployment_name}-{deployment_id}
        if not name.startswith(f"svc-{DEPLOYMENT_NAME}-"):
            continue
        old_deployment_id = name.split(f"svc-{DEPLOYMENT_NAME}-", 1)[1]
        if old_deployment_id == DEPLOYMENT_ID:
            # keep active tag on the newest
            ecs.tag_resource(resourceArn=svc["serviceArn"], tags=[
                {"key":"deployment_name","value":DEPLOYMENT_NAME},
                {"key":"deployment_id","value":DEPLOYMENT_ID},
                {"key":"state","value":"active"},
            ])
            continue
        put_state(old_deployment_id, "draining")
        ecs.tag_resource(resourceArn=svc["serviceArn"], tags=[{"key":"state","value":"draining"}])
```

**IAM needed for the deployer**

- `ssm:PutParameter` on `arn:aws:ssm:<region>:<acct>:parameter/apps/<deployment_name>/*`
- `ecs:ListServices`, `ecs:DescribeServices`, `ecs:TagResource` on your cluster resources

---

## Phase 2 — App changes: poll SSM + emit EMF "ShutdownReady" ✅

**Status: ✅ Complete** (2025-10-28)

### Behavior

- On startup, discover **task ID** from ECS metadata endpoint (`ECS_CONTAINER_METADATA_URI_V4`).
- Each task polls its **own** param `/apps/<deployment_name>/<deployment_id>/state` every N seconds (configurable).
- When it first sees `draining`, start a grace timer; when timer expires, emit `ShutdownReady=1`.
  Until then, emit `ShutdownReady=0`.
- Emit EMF with dimensions: `deployment_name`, `deployment_id`, **`task_id`** (unique per running task).
- Keep health checks **passing** (ECS must not restart it).

### Environment variables to add to the **task definition**

- `DEPLOYMENT_NAME` = `<deployment_name>` (e.g., `myapp`, `prod`)
- `DEPLOYMENT_ID` = `<deployment_id>` (e.g., `20251028-183000-abc1234`)
- `DRAIN_PARAM` = `/apps/<deployment_name>/<deployment_id>/state`
- `ECS_CONTAINER_METADATA_URI_V4` = _auto-provided by ECS_
- (Optional) `DRAIN_POLL_SECONDS` = `5` (for testing; production: `5-15`)
- (Optional) `DRAIN_GRACE_SECONDS` = `20` (for testing; production: `30-120`)

### Task Role policy (CloudFormation)

```yaml
AppTaskRolePolicy:
  Type: AWS::IAM::Policy
  Properties:
    PolicyName: !Sub "${DeploymentName}-drain-ssm-read"
    Roles: [!Ref AppTaskRole] # your existing task role
    PolicyDocument:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Action: ["ssm:GetParameter"]
          Resource: !Sub "arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/apps/${DeploymentName}/*"
```

### Example Python helper (drop-in module)

In practice, integrate the logic into the existing code.

```python
# drain_flag.py
import os, time, json, threading, requests
import boto3
from datetime import datetime

PARAM = os.environ["DRAIN_PARAM"]
POLL = int(os.getenv("DRAIN_POLL_SECONDS", "5"))
GRACE = int(os.getenv("DRAIN_GRACE_SECONDS", "30"))

# Discover task ID from ECS metadata endpoint
def _get_task_id():
    meta_uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
    if meta_uri:
        task_resp = requests.get(f"{meta_uri}/task", timeout=2).json()
        task_arn = task_resp["TaskARN"]
        return task_arn.split("/")[-1]  # extract task ID from ARN
    return os.getenv("TASK_ID", "unknown")  # fallback

TASK_ID = _get_task_id()

ssm = boto3.client("ssm")
draining = False
t0 = None  # when draining first observed
shutdown_ready = 0

def _emit_emf(shutdown_ready_value: int):
    # Embedded Metric Format single-line JSON to stdout
    payload = {
        "_aws": {
            "Timestamp": int(datetime.utcnow().timestamp()*1000),
            "CloudWatchMetrics": [{
                "Namespace": "App/Drain",
                "Dimensions": [["deployment_name","deployment_id","task_id"]],
                "Metrics": [{"Name": "ShutdownReady", "Unit": "Count"}]
            }]
        },
        "deployment_name": os.environ["DEPLOYMENT_NAME"],
        "deployment_id": os.environ["DEPLOYMENT_ID"],
        "task_id": TASK_ID,
        "ShutdownReady": shutdown_ready_value
    }
    print(json.dumps(payload), flush=True)

def _poll():
    global draining, t0, shutdown_ready
    while True:
        try:
            v = ssm.get_parameter(Name=PARAM)["Parameter"]["Value"]
            now = time.time()
            if v == "draining":
                if not draining:
                    draining = True
                    t0 = now
                # after GRACE seconds of draining, signal ready
                shutdown_ready = 1 if (now - t0) >= GRACE else 0
            else:
                draining = False
                t0 = None
                shutdown_ready = 0
            _emit_emf(shutdown_ready)
        except Exception:
            # best-effort; keep previous state
            pass
        time.sleep(POLL)

def start_background_polling():
    threading.Thread(target=_poll, daemon=True).start()

def is_draining() -> bool:
    return draining

def is_shutdown_ready() -> bool:
    return shutdown_ready == 1
```

**Use in your app startup**

```python
from drain_flag import start_background_polling, is_draining, is_shutdown_ready
start_background_polling()

# in request path/policy:
# - stop minting new affinity cookies when is_draining()
# - optionally shorten TTLs
```

> EMF goes via stdout to CloudWatch Logs; CloudWatch auto-creates metric `App/Drain:ShutdownReady{deployment_name=myapp,deployment_id=20251028-183000-abc1234,task_id=<tid>}` **per task**.

---

## Phase 3 — Reaper (Lambda + EventBridge, via CDK) ✅

**Status: ✅ Complete** (2025-10-28)

### Behavior

- Every N minutes (configurable; 1 minute for testing, 5 minutes for production):

  1. Enumerate **ECS services** tagged `state=draining` (and `deployment_name=<name>` if set).
  2. For each draining service:

     - List all **running tasks** (`ListTasks` + `DescribeTasks` → extract `task_id`s).
     - For **each task**, read **CloudWatch metric**
       `Namespace=App/Drain, MetricName=ShutdownReady, Dimensions={deployment_name,deployment_id,task_id}`
     - If **ALL tasks** report `ShutdownReady == 1` for K consecutive periods OR service has `runningCount==0`, **mark for cleanup**:

       - `UpdateService(desiredCount=0)` (if not already 0)
       - **Continue immediately** — don't wait for tasks to drain

  3. Clean up **any service** with `runningCount==0` (regardless of draining state):

     - Delete ALB listener rules referencing its TG
     - Delete TG
     - `DeleteService(force=True)`

  4. Backstops:

     - **MinAge** (e.g., don't retire in the first 2 minutes)
     - **MaxLifetime** (force retire after X hours even if metric never flips; **set to 1 hour** for testing old deployments)

### CDK Implementation (permanent infra)

Implemented in `packages/pulse-aws/src/pulse_aws/`:

- **`reaper_lambda.py`** - Lambda handler code with all reaper logic
- **`cdk/baseline.py`** - Reaper is now part of the `BaselineStack` (created in `_create_reaper()` method):
  - Lambda function with Python 3.12 runtime
  - IAM role with ECS, ALB, and CloudWatch permissions
  - EventBridge rule for scheduled invocation

**Why part of baseline?** The reaper is permanent infrastructure needed for the deployment environment to function properly, so it makes sense to deploy it alongside the VPC, ALB, and ECS cluster rather than as a separate stack.

**Environment variables** (set via CDK):

- `CLUSTER` - ECS cluster name (from baseline)
- `DEPLOYMENT_NAME` - Deployment environment name
- `LISTENER_ARN` - ALB listener ARN (from baseline)
- `CONSEC: "2"` - consecutive periods with ShutdownReady==1 (testing: 2; production: 3)
- `PERIOD: "60"` - period duration in seconds (testing: 60s; production: 300s)
- `MIN_AGE_SEC: "60"` - min service age before retirement (testing: 60s; production: 120s)
- `MAX_AGE_HR: "1.0"` - **max age in hours (1 hour for testing old deployments; production: 48)**

**Schedule**: Every 1 minute for testing (configurable, 5 minutes for production)

---

## Testing (via deployment script; no unit tests)

### Testing Configuration

Use shorter timeouts for faster iteration:

- `DRAIN_POLL_SECONDS` = 30 (task polls SSM every 30s)
- `DRAIN_GRACE_SECONDS` = 20 (20s from draining → ShutdownReady)
- Reaper schedule = 1 minute
- `PERIOD` = 60 (1-minute CloudWatch periods)
- `CONSEC` = 2 (2 consecutive periods = 2 minutes)
- `MIN_AGE_SEC` = 60 (services must be at least 1 minute old)

### Phase 1: Test with ShutdownReady logic

1. **Deploy version A**

   - Run `packages/pulse-aws/scripts/deploy.py` once
   - Verify service `svc-test-<deployment_id>` is created and healthy
   - Verify EMF metric `App/Drain:ShutdownReady{deployment_name=test,deployment_id=<id>,task_id=<tid>}` exists for each task and shows `0`

2. **Deploy version B**

   - Run `deploy.py` again (new deployment_id)
   - Observe that version A is tagged `state=draining`
   - Within ~20s, verify EMF shows `1` for **all task IDs** of version A

3. **Watch reaper clean up A**

   - Reaper runs every 1 minute
   - After 2 consecutive periods (2 minutes), reaper sets A's `desiredCount=0`
   - Next reaper run (1 minute later) sees `runningCount==0` and cleans up:
     - Deletes ALB listener rules
     - Deletes target group
     - Deletes ECS service
   - Total time: ~3-4 minutes from deployment B → cleanup of A

4. **Deploy version C and verify**

   - Run `deploy.py` again
   - Verify B is drained and cleaned up within ~3-4 minutes
   - Verify C is active and healthy

### Phase 2: Test MAX_AGE forced cleanup

**Configuration for 1 hour MAX_AGE**:

- `MAX_AGE_HR` = `1.0` (1 hour)
- Old deployments without Phase 2 logic won't emit `ShutdownReady=1`

1. **Initial state**

   - You have older deployments (without Phase 2 SSM polling) running
   - These deployments are marked `state=draining` when new deployment happens
   - They won't emit `ShutdownReady=1` because they don't have the polling logic

2. **Deploy a new version**

   - Run `deploy.py` once (this marks old deployments as draining)
   - Old deployments are now tagged `state=draining`

3. **Verify forced cleanup**

   - Wait for deployments to reach 1 hour age
   - Reaper should force-retire them via `MAX_AGE_HR` backstop
   - Even without `ShutdownReady=1`, services get cleaned up after 1 hour
   - Check CloudWatch Logs for reaper invocations showing "MAX_AGE exceeded"

4. **Monitor progress**

   - Every 1 minute, reaper checks ages
   - When deployment age >= 1 hour, sets `desiredCount=0`
   - Next reaper run (1 minute later) sees `runningCount==0` and cleans up

### Success Criteria

- ✅ Multiple deploys work correctly
- ✅ Old deployments are tagged `state=draining`
- ✅ Tasks emit `ShutdownReady=1` after grace period
- ✅ Reaper sets `desiredCount=0` when all tasks ready
- ✅ Reaper cleans up services with `runningCount==0`
- ✅ No dangling target groups or listener rules
- ✅ MAX_AGE backstop works without ShutdownReady

---

## Notes & gotchas

- **Per-task metrics**: Each running task emits its own `ShutdownReady` with a unique `task_id` dimension. The reaper checks **all** tasks.
- **Task ID discovery**: Tasks discover their ID from the ECS metadata endpoint (`ECS_CONTAINER_METADATA_URI_V4`).
- **EMF creation delay**: first metric datapoint appears only after the log hits CW; give it ~1–2 minutes on cold start.
- **Two-step cleanup**: Reaper sets `desiredCount=0` when ready, then cleans up on next run when `runningCount==0`. This keeps invocations fast.
- **Granularity**: With testing config (PERIOD=60, CONSEC=2), retirement takes ~3-4 minutes. With production config (PERIOD=300, CONSEC=3), it takes ~15-20 minutes.
- **Listener cleanup**: the sample deletes rules referencing the TG; adapt to your header-based routing structure.
- **CW metric limit**: GetMetricData is limited to 500 queries; if you have >500 tasks, batch or sum differently.

---

## Done criteria

- Each task discovers its unique ID and sets `ShutdownReady=1` after grace period (20s for testing, configurable).
- Reaper sets `desiredCount=0` when all tasks report ready or MAX_AGE exceeded.
- Reaper cleans up services with `runningCount==0` efficiently (no waiting).
- Testing: Multiple `deploy.py` runs result in old deployments being cleaned up within ~3-4 minutes.
- Phase 2 testing: MAX_AGE backstop works even without ShutdownReady.
- No dangling TGs or listener rules.
- CloudFormation owns all **permanent** bits (Lambda, IAM, EventBridge).
