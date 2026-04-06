ARG APP_FILE=main.py
ARG WEB_ROOT=web
ARG PULSE_INTERNAL_SERVER_ADDRESS=http://127.0.0.1:8000

FROM python:3.12-slim AS python-deps
ARG APP_FILE
ARG WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
RUN uv venv && uv sync --frozen --no-editable

FROM python:3.12-slim AS check
ARG APP_FILE
ARG WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY ${APP_FILE} ./${APP_FILE}
COPY --from=python-deps /app/.venv /app/.venv
COPY ${WEB_ROOT}/package.json ./${WEB_ROOT}/package.json
ENV PATH="/app/.venv/bin:$PATH"
RUN pulse check ${APP_FILE}

FROM python:3.12-slim AS codegen
ARG APP_FILE
ARG WEB_ROOT
ARG PULSE_INTERNAL_SERVER_ADDRESS
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY ${APP_FILE} ./${APP_FILE}
COPY --from=python-deps /app/.venv /app/.venv
COPY ${WEB_ROOT} ./${WEB_ROOT}
ENV PATH="/app/.venv/bin:$PATH"
ARG PULSE_SERVER_ADDRESS
ENV PULSE_SERVER_ADDRESS=${PULSE_SERVER_ADDRESS}
ENV PULSE_INTERNAL_SERVER_ADDRESS=${PULSE_INTERNAL_SERVER_ADDRESS}
RUN pulse generate ${APP_FILE} --ci

FROM oven/bun:latest AS js-dev-deps
ARG WEB_ROOT
WORKDIR /app
COPY package.json bun.lock ./
COPY packages/pulse/js/package.json ./packages/pulse/js/package.json
COPY packages/pulse/js/dist ./packages/pulse/js/dist
COPY packages/pulse-mantine/js/package.json ./packages/pulse-mantine/js/package.json
COPY examples/web/package.json ./examples/web/package.json
COPY examples/pulse-mantine/web/package.json ./examples/pulse-mantine/web/package.json
COPY tutorial/examples/web/package.json ./tutorial/examples/web/package.json
COPY ${WEB_ROOT}/package.json ./${WEB_ROOT}/package.json
RUN bun install --frozen-lockfile

FROM oven/bun:latest AS js-prod-deps
ARG WEB_ROOT
WORKDIR /app
COPY package.json bun.lock ./
COPY packages/pulse/js/package.json ./packages/pulse/js/package.json
COPY packages/pulse/js/dist ./packages/pulse/js/dist
COPY packages/pulse-mantine/js/package.json ./packages/pulse-mantine/js/package.json
COPY examples/web/package.json ./examples/web/package.json
COPY examples/pulse-mantine/web/package.json ./examples/pulse-mantine/web/package.json
COPY tutorial/examples/web/package.json ./tutorial/examples/web/package.json
COPY ${WEB_ROOT}/package.json ./${WEB_ROOT}/package.json
RUN bun install --frozen-lockfile --production

FROM oven/bun:latest AS js-build
ARG APP_FILE
ARG WEB_ROOT
WORKDIR /app
COPY --from=js-dev-deps /app/node_modules ./node_modules
COPY --from=js-dev-deps /app/packages/pulse/js ./packages/pulse/js
COPY --from=js-dev-deps /app/${WEB_ROOT}/node_modules ./${WEB_ROOT}/node_modules
WORKDIR /app/${WEB_ROOT}
COPY --from=codegen /app/${WEB_ROOT}/app ./app
COPY --from=codegen /app/${WEB_ROOT}/public ./public
COPY --from=codegen /app/${WEB_ROOT}/react-router.config.ts ./
COPY --from=codegen /app/${WEB_ROOT}/tsconfig.json ./
COPY --from=codegen /app/${WEB_ROOT}/vite.config.ts ./
COPY --from=codegen /app/${WEB_ROOT}/package.json ./
COPY ${APP_FILE} /app/${APP_FILE}
ENV NODE_ENV=production
RUN bun run build

FROM python:3.12-slim AS final
ARG APP_FILE
ARG WEB_ROOT
ARG PULSE_INTERNAL_SERVER_ADDRESS
WORKDIR /app
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun
COPY --from=python-deps /app/.venv /app/.venv
COPY --from=js-prod-deps /app/node_modules /app/node_modules
COPY --from=js-prod-deps /app/packages/pulse/js /app/packages/pulse/js
COPY --from=js-prod-deps /app/${WEB_ROOT}/node_modules /app/${WEB_ROOT}/node_modules
COPY --from=js-build /app/${WEB_ROOT}/build /app/${WEB_ROOT}/build
COPY --from=js-build /app/${WEB_ROOT}/package.json /app/${WEB_ROOT}/package.json
COPY ${APP_FILE} ./${APP_FILE}
ENV PATH="/app/.venv/bin:$PATH"
ENV PULSE_APP_FILE=${APP_FILE}
ENV PULSE_INTERNAL_SERVER_ADDRESS=${PULSE_INTERNAL_SERVER_ADDRESS}
EXPOSE 8000
CMD ["sh", "-c", "pulse run \"$PULSE_APP_FILE\" --prod --address 0.0.0.0"]
