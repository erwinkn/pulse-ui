# AWS ECS Deployment Scripts

These scripts orchestrate the full deployment workflow for the minimal server to AWS ECS.

## Prerequisites

- AWS credentials configured (`aws configure` or environment variables)
- Docker installed and running
- Domain name with DNS access (for ACM certificate validation)

## Scripts

### 1. `deploy.py` - Deploy Application to ECS

Orchestrates the complete deployment workflow:

- Ensures ACM certificate exists and is validated
- Ensures baseline infrastructure exists (VPC, ALB, ECS cluster, etc.)
- Builds and pushes Docker image to ECR
- Registers ECS task definition
- Creates ECS service and ALB target group
- Installs listener rules for header-based routing
- Switches default traffic to the new deployment

**Usage:**

```bash
# From repository root
cd packages/pulse-aws
uv run python scripts/deploy.py
```

**What it does:**

1. **Phase 1: ACM Certificate**

   - Requests/validates certificate for your domain
   - Displays DNS validation records (add these to your DNS provider)
   - Waits for certificate to be ISSUED before continuing

2. **Phase 2: Baseline Infrastructure**

   - Deploys CloudFormation stack with VPC, ALB, ECS cluster, ECR repository
   - Reuses existing stack if already deployed
   - Takes ~5-10 minutes on first run, seconds on subsequent runs

3. **Phase 3: Deploy Application**
   - Generates unique deployment ID (e.g., `test-20251027-183000Z`)
   - Generates drain secret for later use
   - Builds Docker image with deployment ID and drain secret
   - Pushes to ECR
   - Creates ECS service with 2 tasks
   - Creates ALB target group with health checks
   - Installs header-based routing rule for sticky sessions
   - Switches default traffic to new deployment

**Output:**

The script outputs:

- Deployment ID
- Drain secret (save this!)
- Service ARN
- Target group ARN
- Instructions for verification and draining

### 2. `verify.py` - Verify Deployments

Tests all active deployments to ensure they're working correctly.

**Usage:**

```bash
# From repository root
cd packages/pulse-aws
uv run python scripts/verify.py
```

**What it tests:**

1. **Discovery**

   - Lists all active ECS services in the cluster
   - Shows running/desired task counts for each deployment

2. **Default Endpoint**

   - Tests `http://<alb>/ ` without affinity header
   - Should route to newest deployment
   - Verifies response and `X-Pulse-Render-Affinity` header

3. **Health Endpoint**

   - Tests `http://<alb>/_health`
   - Verifies 200 OK response

4. **Header-Based Affinity** (if multiple deployments exist)
   - Tests each deployment with `X-Pulse-Render-Affinity: <deployment-id>` header
   - Verifies requests route to the correct deployment

**Output:**

```
🔍 Verifying deployments for: test
📋 Loading baseline stack outputs...
✓ ALB DNS: test-baseline-alb-123456.us-east-1.elb.amazonaws.com
✓ Cluster: test-baseline-cluster

🔎 Discovering active deployments...
✓ Found 2 active service(s)

   1. test-20251027-183000Z
      Tasks: 2/2 running
   2. test-20251027-190000Z
      Tasks: 2/2 running

🧪 Testing Endpoints
Base URL: http://test-baseline-alb-123456.us-east-1.elb.amazonaws.com

1️⃣  Testing default endpoint (no affinity header)...
   ✓ Status: 200
   ✓ Response: {'deployment_id': 'test-20251027-190000Z', 'ok': True}
   ✓ Affinity header: test-20251027-190000Z

2️⃣  Testing health endpoint...
   ✓ Status: 200
   ✓ Response: {'status': 'ok'}

3️⃣  Testing header-based affinity...
   Testing affinity to: test-20251027-183000Z
      ✓ Routed correctly to test-20251027-183000Z
   Testing affinity to: test-20251027-190000Z
      ✓ Routed correctly to test-20251027-190000Z
```

### 3. `teardown.py` - Teardown Infrastructure

Safely deletes baseline CloudFormation stack.

**Usage:**

```bash
# From repository root
cd packages/pulse-aws
uv run python scripts/teardown.py
```

**What it does:**

- Checks for active ECS services (blocks deletion unless `--force`)
- Deletes CloudFormation stack
- Waits for deletion to complete
- Handles various failure modes

## Typical Workflow

### First Deployment

```bash
# 1. Deploy baseline + first version
cd packages/pulse-aws
uv run python scripts/deploy.py

# Output will show DNS records to add to your DNS provider
# Add the CNAME record, then wait for DNS propagation

# 2. Verify deployment
uv run python scripts/verify.py

# 3. Test via domain
curl https://test.stoneware.rocks/
curl https://test.stoneware.rocks/_health
```

### Deploying a New Version

```bash
# Deploy new version (old version keeps running)
uv run python scripts/deploy.py

# Verify both versions are running
uv run python scripts/verify.py

# Test sticky sessions
curl https://test.stoneware.rocks/
curl -H 'X-Pulse-Render-Affinity: test-20251027-183000Z' \
  https://test.stoneware.rocks/
```

### Draining an Old Version

```bash
# Use the drain secret from deploy.py output
curl -X POST -H 'Authorization: Bearer <drain-secret>' \
  https://test.stoneware.rocks/drain

# After 120 seconds (default), health check fails and ECS drains the service
# Verify health is failing
curl https://test.stoneware.rocks/_health
```

## Configuration

All scripts currently use hardcoded configuration:

- **Domain**: `test.stoneware.rocks`
- **Deployment name**: `test`
- **Region**: Uses your AWS CLI default region

To change these, edit the scripts directly (at the top of `main()` function).

## Troubleshooting

### Certificate Validation Stuck

If the certificate stays in `PENDING_VALIDATION`:

1. Check DNS records are correct (exact match required)
2. Wait up to 30 minutes for DNS propagation
3. Check CloudWatch logs for ACM validation attempts

### ECS Service Not Starting

Check CloudWatch logs:

```bash
aws logs tail /aws/ecs/test --follow
```

Common issues:

- Image failed to pull from ECR (check IAM roles)
- Container failed to start (check Dockerfile)
- Health checks failing (ensure port 8000 is exposed)

### Traffic Not Routing

Check ALB listener rules:

```bash
aws elbv2 describe-rules --listener-arn <listener-arn>
```

Verify target group health:

```bash
aws elbv2 describe-target-health --target-group-arn <tg-arn>
```

## Clean Up

To remove everything:

```bash
# 1. Delete all ECS services first
aws ecs update-service --cluster test-baseline-cluster \
  --service <service-name> --desired-count 0
aws ecs delete-service --cluster test-baseline-cluster \
  --service <service-name>

# 2. Delete baseline stack
uv run python scripts/teardown.py

# 3. (Optional) Delete ACM certificate
aws acm delete-certificate --certificate-arn <cert-arn>
```
