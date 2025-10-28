# ECS Draining + Reaper — Implementation Plan

## 0) Goals (what this delivers)

* Allow **multiple deployments** to run concurrently.
* New traffic (no affinity header) always goes to the **newest deployment**.
* Older deployments are **marked “draining”** by CI.
* Each task **knows** it’s draining (shorten TTL, stop minting cookies).
* A small **Lambda reaper** periodically retires drained deployments once they hit **zero traffic/sessions**, and cleans up LB/TG cruft.
* Guardrails: **max lifetime** and **max history** of old deployments.

---

## 1) Architecture (high level)

* **One ECS Service per deployment**
  Naming: `svc-<app>-<deploy_id>`
* **One Target Group per service**
  Naming: `tg-<app>-<deploy_id>`
* **ALB Listener** routes:

  * No affinity header → newest TG (weight 100)
  * With affinity header → routed by your ALB logic to the correct TG
* **State signal:** SSM Parameter per deployment
  `/apps/<app>/<deploy_id>/state = active|draining`
* **CI**:

  * Creates new service/TG, points listener weights to it
  * Marks all older deployments `draining` (SSM + ECS tag)
* **Lambda reaper (EventBridge 5 min)**:

  * Lists services tagged `state=draining`
  * Checks “zero activity” for their TG (or app metric)
  * Scales to 0 → deletes service/TG/listener rule
  * Enforces max lifetime and “keep last N” cap

---

## 2) Naming, tags & conventions

* `deploy_id`: monotonically increasing unique id (e.g., `YYYYMMDD-HHMM-<sha7>`)
* ECS Service: `svc-<app>-<deploy_id>`
* TG: `tg-<app>-<deploy_id>`
* ECS tags:

  * `app=<app>`
  * `deploy_id=<deploy_id>`
  * `state=active|draining`
* SSM parameter: `/apps/<app>/<deploy_id>/state`

---

## 3) IAM (scoped)

### Task Role (app containers)

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["ssm:GetParameter"],
    "Resource": "arn:aws:ssm:<region>:<acct>:parameter/apps/<app>/*"
  }]
}
```

### CI Role

* `ecs:*` (Create/Update/Delete service; Describe; Tag)
* `elasticloadbalancing:*` (TG create/attach; listener rules modify)
* `ssm:PutParameter`
* Scope to ARNs for your cluster, ALB, and parameter path.

### Reaper Lambda Role

* ECS: `ListServices`, `DescribeServices`, `ListTagsForResource`, `UpdateService`, `DeleteService`
* ELBv2: `Describe*`, `ModifyListener`, `DeleteTargetGroup`, `DeregisterTargets`
* CloudWatch: `GetMetricData`
* (Optional) `tag:GetResources` if you discover via Tagging API

---

## 4) CI/CD pipeline changes (GitHub Actions example)

```yaml
name: deploy
on: [push]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-region: eu-west-1
          role-to-assume: arn:aws:iam::<acct>:role/gha-deployer
      - name: Build & push image
        run: |
          # build/push image...
      - name: Create TG & Service for new deployment
        run: |
          APP=myapp
          DEPLOY_ID=$(date -u +%Y%m%d-%H%M)-${GITHUB_SHA::7}
          CLUSTER=mycluster
          ALB_ARN=<alb-arn>
          LISTENER_ARN=<listener-arn>
          VPC_ID=<vpc-id>

          # Create TG
          TG_ARN=$(aws elbv2 create-target-group \
            --name tg-${APP}-${DEPLOY_ID} \
            --protocol HTTP --port 80 \
            --vpc-id ${VPC_ID} \
            --target-type ip \
            --query 'TargetGroups[0].TargetGroupArn' --output text)

          # Create/Update ECS Service
          aws ecs create-service \
            --cluster ${CLUSTER} \
            --service-name svc-${APP}-${DEPLOY_ID} \
            --task-definition ${APP} \
            --desired-count 3 \
            --load-balancers targetGroupArn=${TG_ARN},containerName=${APP},containerPort=80 \
            --tags key=app,value=${APP} key=deploy_id,value=${DEPLOY_ID} key=state,value=active

          # Listener rule for newest (no-affinity path, or weight to newest)
          # (Implement your header-based routing here; example below sets weight 100 to newest)
          # aws elbv2 modify-listener --listener-arn ${LISTENER_ARN} --default-actions ...
          
          # SSM param for new deployment = active
          aws ssm put-parameter \
            --name "/apps/${APP}/${DEPLOY_ID}/state" \
            --type String --overwrite --value "active"

          echo "APP=${APP}" >> $GITHUB_ENV
          echo "DEPLOY_ID=${DEPLOY_ID}" >> $GITHUB_ENV
      - name: Mark all previous deployments draining
        run: |
          APP=${APP}
          CLUSTER=mycluster

          NEW_SVC=svc-${APP}-${DEPLOY_ID}
          # tag older ECS services as draining
          aws ecs list-services --cluster ${CLUSTER} --query 'serviceArns[]' --output text | tr '\t' '\n' | while read -r ARN; do
            NAME=${ARN##*/}
            if [[ "$NAME" == svc-${APP}-* && "$NAME" != "$NEW_SVC" ]]; then
              aws ecs tag-resource --resource-arn "$ARN" --tags Key=state,Value=draining
              OLD_DEPLOY_ID=${NAME#svc-${APP}-}
              aws ssm put-parameter \
                --name "/apps/${APP}/${OLD_DEPLOY_ID}/state" \
                --type String --overwrite --value "draining"
            fi
          done
```

> Implement your ALB listener rules to:
>
> 1. Route new, non-affinity traffic to **TG of `DEPLOY_ID`** (weight 100).
> 2. Keep header/cookie routing for stickiness per your app.

---

## 5) App integration (drain-aware behavior)

### Task Definition env vars

* `APP_NAME=<app>`
* `DEPLOY_ID=<deploy_id>`
* `DRAIN_PARAM=/apps/<app>/<deploy_id>/state`
* (Optional) `DRAIN_POLL_SECONDS=60`

### Minimal polling (Node.js)

```js
import { SSMClient, GetParameterCommand } from "@aws-sdk/client-ssm";

const ssm = new SSMClient({});
const PARAM = process.env.DRAIN_PARAM;
const POLL_MS = (process.env.DRAIN_POLL_SECONDS ? Number(process.env.DRAIN_POLL_SECONDS) : 60) * 1000;

let draining = false;

async function refreshDrainFlag() {
  try {
    const out = await ssm.send(new GetParameterCommand({ Name: PARAM }));
    const v = out.Parameter?.Value;
    draining = (v === "draining");
  } catch (_) {}
}
setInterval(refreshDrainFlag, POLL_MS);
refreshDrainFlag();

// hooks
export function shouldMintAffinity() { return !draining; }
export function sessionTtlSeconds() { return draining ? 300 : 3600; } // tune as needed
export function requestHeadersAdjust(res) {
  if (draining) res.setHeader("Connection", "close");
}
```

> Keep health checks **passing** while draining so ECS doesn’t restart tasks.

---

## 6) Reaper Lambda (EventBridge: rate 5 minutes)

### Logic

1. List ECS services with `tag state=draining AND tag app=<app>`.
2. For each:

   * Find its Target Group ARN (from service LB config).
   * Query CloudWatch **ApplicationELB** metrics on that TG:

     * `RequestCount` (Sum) == 0
     * `ActiveConnectionCount` (Max or Average) == 0
     * For **N consecutive periods** (e.g., 3×5m).
   * Check **min age** (e.g., >= 1 hour since deployment) and **max lifetime** backstop (e.g., 48h).
3. If empty & age-ok:

   * `UpdateService(desiredCount=0)`
   * Wait until running tasks == 0
   * Remove listener rule/backend reference
   * `DeleteTargetGroup`
   * `DeleteService`

### Handler (Python, abridged)

```python
import os, time, boto3, datetime as dt

ecs = boto3.client('ecs'); elb = boto3.client('elbv2'); cw = boto3.client('cloudwatch')

CLUSTER = os.environ['CLUSTER']
CONSEC = int(os.environ.get('CONSEC', '3'))
PERIOD = int(os.environ.get('PERIOD', '300'))  # 5m
MIN_AGE_MIN = int(os.environ.get('MIN_AGE_MIN', '60'))
MAX_AGE_HR = int(os.environ.get('MAX_AGE_HR', '48'))

def zero_traffic(tg_arn):
    end = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    start = end - dt.timedelta(seconds=PERIOD*CONSEC)
    def q(metric, stat):
        resp = cw.get_metric_statistics(
            Namespace='AWS/ApplicationELB',
            MetricName=metric,
            Dimensions=[{'Name':'TargetGroup','Value':tg_arn.split('/')[-1]},
                        {'Name':'LoadBalancer','Value':'*'}],  # LB dim can be wildcarded via GetMetricData in prod
            StartTime=start, EndTime=end, Period=PERIOD, Statistics=[stat]
        )
        # build per-period values; if any missing treat as 0
        vals = [p['Sum' if stat=='Sum' else stat] for p in sorted(resp['Datapoints'], key=lambda x: x['Timestamp'])]
        return vals + [0]*(CONSEC-len(vals))
    reqs = q('RequestCount','Sum')
    conns = q('ActiveConnectionCount','Average')
    return all(v == 0 for v in reqs[-CONSEC:]) and all(v == 0 for v in conns[-CONSEC:])

def service_age_minutes(svc):
    created = svc.get('createdAt') or svc.get('createdAt', dt.datetime.utcnow())
    return (dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc) - created).total_seconds() / 60

def handler(event, context):
    arns = ecs.list_services(cluster=CLUSTER)['serviceArns']
    if not arns: return
    # could use Tagging API; for brevity, Describe + filter
    for batch in [arns[i:i+10] for i in range(0,len(arns),10)]:
        desc = ecs.describe_services(cluster=CLUSTER, services=batch)['services']
        for svc in desc:
            tags = ecs.list_tags_for_resource(resourceArn=svc['serviceArn']).get('tags', [])
            tagmap = {t['key']: t['value'] for t in tags}
            if tagmap.get('state') != 'draining': continue

            if service_age_minutes(svc) < MIN_AGE_MIN: continue
            # backstop by deployment time tag if you add one; omitted for brevity
            tg_arn = svc['loadBalancers'][0]['targetGroupArn']

            if zero_traffic(tg_arn):
                # scale down
                ecs.update_service(cluster=CLUSTER, service=svc['serviceName'], desiredCount=0)
                # wait
                while True:
                    cur = ecs.describe_services(cluster=CLUSTER, services=[svc['serviceName']])['services'][0]
                    if cur['runningCount'] == 0: break
                    time.sleep(15)
                # TODO: remove listener rule(s) referencing tg_arn here
                elb.delete_target_group(TargetGroupArn=tg_arn)
                ecs.delete_service(cluster=CLUSTER, service=svc['serviceName'], force=True)
```

> Productionize: switch to `GetMetricData` with explicit LB dimension, handle multiple LB entries, and delete/modify listener rules before deleting the TG.

### EventBridge rule

* `rate(5 minutes)`
* Environment vars: `CLUSTER`, `CONSEC=3`, `PERIOD=300`, `MIN_AGE_MIN=60`, `MAX_AGE_HR=48`

---

## 7) ALB Listener & rules

* Keep a rule (or the default action) that:

  * Sends **new traffic** (no affinity header) to the **newest TG** with weight 100.
* Keep header/cookie routing for sticky users to the correct TG.
* When retiring a deployment, the reaper must:

  * Remove any rule/action entries referencing its TG **before** deleting the TG.

> Implementation detail depends on your current ALB rule set. Prefer deterministic priorities (e.g., priority = epoch of deploy) so cleanup is easy.

---

## 8) Observability

* **CloudWatch Dash**:

  * Per TG: `RequestCount`, `ActiveConnectionCount`
  * Reaper logs (success/decisions)
* **(Optional) EMF Metric from app**: `App/Session ActiveSessions{app,deploy_id}` once/min
  Switch the reaper to use this for precise session emptiness.

---

## 9) Guardrails

* **Max lifetime**: reaper force-retires any draining deployment older than 48h.
* **Max history**: keep only last N (e.g., 10) draining deployments per app.
* **Idempotent cleanup**: TG/Rules may already be partially removed—handle “NotFound” gracefully.

---

## 10) Testing plan

1. **Unit-test app drain flag**

   * Flip SSM param; verify `shouldMintAffinity()` changes within 60–120s.
2. **Deploy two versions**

   * Generate traffic with/without affinity header.
   * Mark old as draining; observe TTL reduction and no new cookies.
3. **Reaper dry-run**

   * Run reaper in “log-only” mode (no deletes). Confirm it identifies zero-traffic TGs correctly.
4. **Full retire**

   * Enable deletes; verify service scales to 0, TG removed, rules cleaned, app remains healthy while draining.
5. **Backstop**

   * Leave a draining deployment with trickle traffic; confirm it remains.
   * After max lifetime, confirm forced retirement.

---

## 11) Rollout

* Ship **app polling** first (no reaper).
* Update **CI** to write SSM + tag ECS.
* Validate manual retire procedure.
* Deploy **reaper** in log-only; inspect decisions for a day.
* Enable retire actions (scale→delete).
* Add alarms on Lambda errors and ALB metric anomalies.

---

## 12) Costs (ballpark, very low)

* **SSM Parameter reads**: one per task per minute → pennies/month.
* **CloudWatch GetMetricData** every 5 min → pennies/month.
* **Lambda**: a few seconds every 5 min → pennies/month.
* **Logs**: minimal if you keep them lean.

---

## 13) Nice-to-haves (later)

* Replace ALB metric heuristic with **app EMF `ActiveSessions`**.
* Emit **deployment_started_at** tag; reaper uses it for age math.
* Terraform modules for:

  * Service+TG+Rule creation
  * Reaper (Lambda, IAM, EventBridge)
* Canary tests to validate stickiness per deployment.

---

## 14) Acceptance criteria

* When a new deployment is live:

  * CI sets `/apps/<app>/<deploy_id>/state=active` (new), and flips all previous to `draining`.
  * Old tasks read `draining=true` within ≤120s; stop minting new affinity cookies; TTL shortens.
  * Reaper retires an old deployment within ≤20 min of last request (given `3×5m` config).
  * No replacement/restarts of retired services.
  * ALB has **no** dangling rules/TGs for retired deployments.

---

> Ping if you want this wrapped as **Terraform** (reaper + IAM + EventBridge + ALB rule helpers) or need a **delete-listener-rules** function for your ALB setup.
