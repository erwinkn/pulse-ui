ARG PULSE_APP_FILE=main.py
ARG PULSE_WEB_ROOT=web

FROM python:3.12-slim AS python-deps
ARG PULSE_APP_FILE
ARG PULSE_WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
RUN uv venv && uv sync --frozen --no-editable

FROM python:3.12-slim AS check
ARG PULSE_APP_FILE
ARG PULSE_WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN pulse check ${PULSE_APP_FILE}

FROM python:3.12-slim AS codegen
ARG PULSE_APP_FILE
ARG PULSE_WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN pulse generate ${PULSE_APP_FILE} --ci

FROM oven/bun:latest AS js-dev-deps
ARG PULSE_APP_FILE
ARG PULSE_WEB_ROOT
WORKDIR /app
COPY . .
RUN bun install --frozen-lockfile

FROM oven/bun:latest AS js-prod-deps
ARG PULSE_APP_FILE
ARG PULSE_WEB_ROOT
WORKDIR /app
COPY . .
RUN bun install --frozen-lockfile --production

FROM oven/bun:latest AS js-build
ARG PULSE_APP_FILE
ARG PULSE_WEB_ROOT
WORKDIR /app
COPY --from=js-dev-deps /app /app
COPY --from=codegen /app/${PULSE_WEB_ROOT}/ /app/${PULSE_WEB_ROOT}/
ENV NODE_ENV=production
RUN bun run build
WORKDIR /app/${PULSE_WEB_ROOT}
RUN bun run build

FROM python:3.12-slim AS final
ARG PULSE_APP_FILE
ARG PULSE_WEB_ROOT
WORKDIR /app
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=python-deps /app/.venv /app/.venv
COPY --from=js-prod-deps /app /app
COPY --from=js-build /app/packages/pulse/js/dist /app/packages/pulse/js/dist
COPY --from=js-build /app/packages/pulse-mantine/js/dist /app/packages/pulse-mantine/js/dist
COPY --from=js-build /app/${PULSE_WEB_ROOT}/build /app/${PULSE_WEB_ROOT}/build
COPY --from=js-build /app/${PULSE_WEB_ROOT}/package.json /app/${PULSE_WEB_ROOT}/package.json
ENV PATH="/app/.venv/bin:$PATH"
ENV NODE_ENV=production
ENV PULSE_APP_FILE=${PULSE_APP_FILE}
EXPOSE 8000
CMD ["sh", "-c", "pulse run \"$PULSE_APP_FILE\" --prod --address 0.0.0.0"]
