FROM python:3.12-slim AS python-deps
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
RUN uv venv && uv sync --frozen --no-editable

FROM python:3.12-slim AS check
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN pulse check examples/railway/main.py

FROM python:3.12-slim AS codegen
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ARG PULSE_SERVER_ADDRESS
RUN pulse generate examples/railway/main.py --ci

FROM oven/bun:latest AS js-dev-deps
WORKDIR /app
COPY . .
RUN bun install --frozen-lockfile

FROM oven/bun:latest AS js-prod-deps
WORKDIR /app
COPY . .
RUN bun install --frozen-lockfile --production

FROM oven/bun:latest AS js-build
WORKDIR /app
COPY --from=js-dev-deps /app /app
COPY --from=codegen /app/examples/railway/web/ /app/examples/railway/web/
ENV NODE_ENV=production
RUN bun run build
WORKDIR /app/examples/railway/web
RUN bun run build

FROM python:3.12-slim AS final
WORKDIR /app
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=python-deps /app/.venv /app/.venv
COPY --from=js-prod-deps /app /app
COPY --from=js-build /app/packages/pulse/js/dist /app/packages/pulse/js/dist
COPY --from=js-build /app/packages/pulse-mantine/js/dist /app/packages/pulse-mantine/js/dist
COPY --from=js-build /app/examples/railway/web/build /app/examples/railway/web/build
COPY --from=js-build /app/examples/railway/web/package.json /app/examples/railway/web/package.json
ENV PATH="/app/.venv/bin:$PATH"
ENV NODE_ENV=production
EXPOSE 8000
CMD ["pulse", "run", "examples/railway/main.py", "--prod", "--address", "0.0.0.0"]
