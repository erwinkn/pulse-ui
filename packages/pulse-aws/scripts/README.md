# `pulse-aws` Script Wrappers

These scripts are thin wrappers around the `pulse-aws` CLI:

- `deploy.py` -> `pulse-aws deploy`
- `verify.py` -> `pulse-aws verify`
- `teardown.py` -> `pulse-aws teardown`

They do not bundle an application.

For the canonical end-to-end deployment example, use the full Pulse app in `examples/aws-ecs`. From the repository root, deploy it with the workspace sources so the container build exercises the local `pulse-aws` and `pulse-framework` code:

```bash
AWS_PROFILE=brimstone-production AWS_REGION=us-east-2 uv run pulse-aws deploy \
  --deployment-name test \
  --domain test.stoneware.rocks \
  --app-file examples/aws-ecs/main.py \
  --web-root examples/aws-ecs/web \
  --dockerfile examples/Dockerfile \
  --context .
```
