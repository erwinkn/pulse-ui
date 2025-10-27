# Dockerfile for minimal AWS ECS deployment proof
#
# Build from repository root:
#   docker build -f packages/pulse-aws/examples/Dockerfile \
#     --build-arg DEPLOYMENT_ID=test-123 \
#     --build-arg DRAIN_SECRET=mysecret \
#     -t minimal-server:test .
#
# Run locally:
#   docker run --rm -p 8000:8000 minimal-server:test
#
# Build args:
#   DEPLOYMENT_ID - unique identifier for this deployment version
#   DRAIN_SECRET - bearer token for authenticated drain endpoint
#
# Runtime env vars (overridable):
#   DRAIN_HEALTH_FAIL_AFTER_SECONDS - seconds to wait before health fails (default: 120)

FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy the minimal server
COPY packages/pulse-aws/examples/aws_minimal_server.py ./server.py

# Install dependencies (fastapi, uvicorn)
RUN uv pip install --system fastapi uvicorn[standard]

# Build-time arguments
ARG DEPLOYMENT_ID
ARG DRAIN_SECRET

# Environment variables
ENV DEPLOYMENT_ID=${DEPLOYMENT_ID}
ENV DRAIN_SECRET=${DRAIN_SECRET}
ENV DRAIN_HEALTH_FAIL_AFTER_SECONDS=120

# Expose port
EXPOSE 8000

# Run the server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

