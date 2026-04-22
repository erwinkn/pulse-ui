ARG APP_FILE=main.py
ARG WEB_ROOT=web
ARG PULSE_INTERNAL_SERVER_ADDRESS=http://127.0.0.1:8000

FROM python:3.12-slim AS python-deps
ARG APP_FILE
ARG WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
RUN uv venv && uv sync --frozen --no-editable

FROM python:3.12-slim AS check
ARG APP_FILE
ARG WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN pulse check ${APP_FILE}

FROM python:3.12-slim AS codegen
ARG APP_FILE
ARG WEB_ROOT
ARG PULSE_INTERNAL_SERVER_ADDRESS
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ARG PULSE_SERVER_ADDRESS
ENV PULSE_SERVER_ADDRESS=${PULSE_SERVER_ADDRESS}
ENV PULSE_INTERNAL_SERVER_ADDRESS=${PULSE_INTERNAL_SERVER_ADDRESS}
RUN pulse generate ${APP_FILE} --ci

FROM oven/bun:latest AS js-dev-deps
ARG APP_FILE
ARG WEB_ROOT
WORKDIR /app
COPY . .
RUN bun install --frozen-lockfile

FROM oven/bun:latest AS js-prod-deps
ARG APP_FILE
ARG WEB_ROOT
WORKDIR /app
COPY . .
RUN bun install --frozen-lockfile --production

FROM oven/bun:latest AS js-build
ARG APP_FILE
ARG WEB_ROOT
WORKDIR /app
COPY --from=js-dev-deps /app /app
COPY --from=codegen /app/${WEB_ROOT}/ /app/${WEB_ROOT}/
ENV NODE_ENV=production
RUN bun run build
WORKDIR /app/${WEB_ROOT}
RUN bun run build

FROM python:3.12-slim AS final
ARG APP_FILE
ARG WEB_ROOT
ARG PULSE_INTERNAL_SERVER_ADDRESS
WORKDIR /app
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=python-deps /app/.venv /app/.venv
COPY --from=js-prod-deps /app /app
COPY --from=js-build /app/packages/pulse/js/dist /app/packages/pulse/js/dist
COPY --from=js-build /app/packages/pulse-mantine/js/dist /app/packages/pulse-mantine/js/dist
COPY --from=js-build /app/${WEB_ROOT}/build /app/${WEB_ROOT}/build
COPY --from=js-build /app/${WEB_ROOT}/package.json /app/${WEB_ROOT}/package.json
ENV PATH="/app/.venv/bin:$PATH"
ENV NODE_ENV=production
ENV PULSE_APP_FILE=${APP_FILE}
ENV PULSE_INTERNAL_SERVER_ADDRESS=${PULSE_INTERNAL_SERVER_ADDRESS}
EXPOSE 8000
CMD ["sh", "-c", "pulse run \"$PULSE_APP_FILE\" --prod --address 0.0.0.0"]
