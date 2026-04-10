# AWS ECS Pulse Example

This example is the canonical end-to-end `pulse-aws` smoke test application.

It is a full Pulse app, not a minimal HTTP server. Use it when you want to verify:

- Pulse prerendering and websocket bootstrapping
- `pulse check` and `pulse generate --ci`
- frontend build output under `web/`
- ECS deployment flow through `pulse-aws`

## Local Development

From the repository root:

```bash
uv run pulse run examples/aws-ecs/main.py
```

## AWS Deploy

Deploy from the repository root so the Docker build uses the local workspace versions of `pulse-aws` and `pulse-framework` instead of the published packages locked in `examples/aws-ecs/uv.lock`.

```bash
AWS_PROFILE=brimstone-production AWS_REGION=us-east-2 uv run pulse-aws deploy \
  --deployment-name test \
  --domain test.stoneware.rocks \
  --app-file examples/aws-ecs/main.py \
  --web-root examples/aws-ecs/web \
  --dockerfile examples/Dockerfile \
  --context .
```

The deploy command sets `PULSE_SERVER_ADDRESS` for the ECS task automatically.
