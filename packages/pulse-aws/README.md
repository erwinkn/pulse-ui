# pulse-aws

AWS deployment utilities for Pulse applications on ECS Fargate.

## Features

- **Zero-downtime deployments** with header-based sticky sessions
- **Automatic ACM certificate management** with DNS validation
- **DNS configuration detection** - automatically detects and guides you through DNS setup
- **Baseline infrastructure** as code using AWS CDK
- **Multi-version support** - run multiple deployments simultaneously

## Quick Start

```bash
# Install
uv add pulse-aws

# Deploy
uv run scripts/deploy.py
```

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for a detailed overview of:

- Infrastructure resources and how they relate
- Traffic routing with sticky sessions
- Zero-downtime deployment workflow
- Security architecture

## Deployment Workflow

The deployment script orchestrates the full workflow:

### 1. ACM Certificate

```python
from pulse_aws import ensure_acm_certificate

cert = await ensure_acm_certificate("api.example.com")
```

- Creates or retrieves an ACM certificate
- Provides DNS validation records if needed
- Waits for certificate to be ISSUED

### 2. Baseline Infrastructure

```python
from pulse_aws import ensure_baseline_stack

outputs = await ensure_baseline_stack(
    "prod",
    certificate_arn=cert.arn,
)
```

Creates shared infrastructure:

- VPC with public/private subnets
- Application Load Balancer with HTTPS listener
- ECS Fargate cluster
- ECR repository
- CloudWatch log group
- Security groups

### 3. DNS Configuration Check

```python
from pulse_aws import check_domain_dns

dns_config = check_domain_dns(domain, alb_dns_name)
if dns_config:
    print(dns_config.format_for_display())
```

Automatically checks if your domain resolves to the ALB:

- ✅ **Already configured**: Silent success
- ✅ **Proxied through Cloudflare**: Treated as configured once records point to Cloudflare
- ⚠️ **Not configured**: Shows exact DNS record to add

Example output:

```
⚠️  Domain DNS Configuration Required
============================================================

🔗 Configure DNS for test.stoneware.rocks

Add the following records to your DNS provider:

  • Type: CNAME
    Name: test.stoneware.rocks
    Value: test-alb-514905529.us-east-2.elb.amazonaws.com
    (Route traffic to Application Load Balancer)

Once the records are added, your domain will be live within a few minutes.
```

### 4. Deploy Application

```python
from pulse_aws import (
    generate_deployment_id,
    build_and_push_image,
    register_task_definition,
    create_service_and_target_group,
    install_listener_rules_and_switch_traffic,
)

deployment_id = generate_deployment_id("prod")
image_uri = await build_and_push_image(...)
task_def_arn = await register_task_definition(...)
service_arn, tg_arn = await create_service_and_target_group(...)
await install_listener_rules_and_switch_traffic(...)  # Waits for health checks
```

- Builds and pushes Docker image to ECR (with correct x86_64 architecture)
- Registers ECS task definition with IAM roles
- Creates target group and attaches to ALB listener
- Creates ECS service with 2 Fargate tasks
- **Waits for targets to pass health checks (zero-downtime)**
- Switches default traffic to new deployment

## Zero-Downtime Deployments

Each deployment gets a unique ID (e.g., `prod-20251027-122112Z`):

1. **New deployment starts** - New tasks spin up alongside old tasks
2. **Header-based routing** - ALB creates a rule: `X-Pulse-Render-Affinity: <deployment-id>` → target group
3. **Default action switches** - New users get new version
4. **Old sessions continue** - Existing users stick to old version via header
5. **Drain old deployment** - When ready, call drain endpoint to shut down gracefully

```bash
# Drain an old deployment
curl -X POST \
  -H "Authorization: Bearer <drain-secret>" \
  https://api.example.com/drain
```

## Configuration

### Environment Variables

- `AWS_PROFILE` - AWS profile to use
- `AWS_REGION` - AWS region (or set in `~/.aws/config`)

### Deployment Settings

```python
# In your deploy script
deployment_name = "prod"  # Used for resource naming
domain = "api.example.com"  # Your domain
dockerfile_path = Path("Dockerfile")  # Path to Dockerfile
```

## Security

**Defense in depth:**

- ALB in public subnets (internet-facing)
- ECS tasks in private subnets (no direct internet access)
- NAT gateway for task outbound internet
- ALB security group: Only 80/443 from internet
- Service security group: Only 8000 from ALB
- IAM roles with least privilege

## Development

```bash
# Run tests
uv run pytest packages/pulse-aws/tests/

# Deploy test environment
AWS_PROFILE=your-profile uv run packages/pulse-aws/scripts/deploy.py
```

## Troubleshooting

### Certificate validation stuck

If certificate stays in `PENDING_VALIDATION`:

1. Check DNS validation records are added correctly
2. Wait 5-10 minutes for DNS propagation
3. Use `dig` to verify: `dig _xxx.yourdomain.com CNAME`

### Domain not accessible after deployment

1. Check DNS record points to ALB: `dig yourdomain.com`
2. Wait for DNS propagation (can take 5-60 minutes)
3. Verify ALB is healthy: Visit ALB DNS directly

### Tasks failing health checks

1. Check logs: `aws logs tail /aws/pulse/{env}/app --follow`
2. Verify tasks are listening on port 8000
3. Check `/_health` endpoint returns 200

## License

MIT
