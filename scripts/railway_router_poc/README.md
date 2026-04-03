# Railway Router POC

Proof of concept for a Pulse-style deployment-affinity pipeline on Railway.

Pieces:

- `router.py`: stable reverse proxy that routes by `pulse_deployment` query param or `x-pulse-deployment` header
- `demo_backend.py`: tiny HTTP + WebSocket backend for local testing
- `deploy.py`: Railway GraphQL deploy helper that creates one service per deployment and flips the active deployment pointer

Local demo:

```bash
uv run uvicorn scripts.railway_router_poc.demo_backend:app --port 9101
POC_DEPLOYMENT_ID=v2 uv run uvicorn scripts.railway_router_poc.demo_backend:app --port 9102

POC_STATIC_BACKENDS='{"v1":"http://127.0.0.1:9101","v2":"http://127.0.0.1:9102"}' \
POC_ACTIVE_DEPLOYMENT=v2 \
uv run uvicorn scripts.railway_router_poc.router:build_app_from_env --factory --port 9200
```

Then:

```bash
curl http://127.0.0.1:9200/
curl 'http://127.0.0.1:9200/?pulse_deployment=v1'
```

Railway demo:

```bash
uv run python -m scripts.railway_router_poc.deploy deploy \
  --deployment v1 \
  --image traefik/whoami:v1.10 \
  --service-prefix poc- \
  --backend-port 80 \
  --expose-domain
```
