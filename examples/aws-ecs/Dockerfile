ARG APP_FILE=main.py
ARG WEB_ROOT=web
ARG APP_RUNTIME_FILE=main.py
ARG WEB_RUNTIME_ROOT=web
ARG PULSE_INTERNAL_SERVER_ADDRESS=http://127.0.0.1:8000

# Stage 1: Python dependency installation using uv
FROM python:3.12-slim AS python-deps
ARG APP_FILE
ARG WEB_ROOT
ARG APP_RUNTIME_FILE
ARG WEB_RUNTIME_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Build from the repository root so workspace packages can be installed locally.
COPY pyproject.toml uv.lock ./
COPY packages ./packages
RUN uv venv && uv sync --frozen --no-editable

# Stage 2: Dependency check - validate web dependencies are in sync
FROM python:3.12-slim AS check
ARG APP_FILE
ARG WEB_ROOT
ARG APP_RUNTIME_FILE
ARG WEB_RUNTIME_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Copy Python application and venv
COPY pyproject.toml uv.lock ./
COPY ${APP_FILE} ./${APP_RUNTIME_FILE}
COPY --from=python-deps /app/.venv /app/.venv
# Copy web package.json for validation
COPY ${WEB_ROOT}/package.json ${WEB_RUNTIME_ROOT}/
# Add venv to PATH and run pulse check
ENV PATH="/app/.venv/bin:$PATH"
RUN pulse check ${APP_RUNTIME_FILE}

# Stage 3: Codegen - generate routes with PULSE_SERVER_ADDRESS
FROM python:3.12-slim AS codegen
ARG APP_FILE
ARG WEB_ROOT
ARG APP_RUNTIME_FILE
ARG WEB_RUNTIME_ROOT
ARG PULSE_INTERNAL_SERVER_ADDRESS
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Copy Python application and venv
COPY pyproject.toml uv.lock ./
COPY ${APP_FILE} ./${APP_RUNTIME_FILE}
COPY --from=python-deps /app/.venv /app/.venv
# Copy web directory (needed for codegen output)
COPY ${WEB_ROOT} ./${WEB_RUNTIME_ROOT}
# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
# Accept build arg for PULSE_SERVER_ADDRESS
ARG PULSE_SERVER_ADDRESS
# Set environment variable for codegen
ENV PULSE_SERVER_ADDRESS=${PULSE_SERVER_ADDRESS}
ENV PULSE_INTERNAL_SERVER_ADDRESS=${PULSE_INTERNAL_SERVER_ADDRESS}
# Generate routes in CI mode
RUN pulse generate ${APP_RUNTIME_FILE} --ci

# Stage 4: JS dev dependencies
FROM oven/bun:latest AS js-dev-deps
ARG WEB_ROOT
ARG WEB_RUNTIME_ROOT
WORKDIR /app/${WEB_RUNTIME_ROOT}
COPY ${WEB_ROOT}/package.json ${WEB_ROOT}/bun.lock ./
RUN bun install --frozen-lockfile

# Stage 5: JS prod dependencies
FROM oven/bun:latest AS js-prod-deps
ARG WEB_ROOT
ARG WEB_RUNTIME_ROOT
WORKDIR /app/${WEB_RUNTIME_ROOT}
COPY ${WEB_ROOT}/package.json ${WEB_ROOT}/bun.lock ./
RUN bun install --frozen-lockfile --production

# Stage 6: JS build
FROM oven/bun:latest AS js-build
ARG APP_FILE
ARG WEB_ROOT
ARG APP_RUNTIME_FILE
ARG WEB_RUNTIME_ROOT
WORKDIR /app/${WEB_RUNTIME_ROOT}
COPY --from=js-dev-deps /app/${WEB_RUNTIME_ROOT}/node_modules ./node_modules
# Copy entire web directory from codegen stage (includes generated routes)
COPY --from=codegen /app/${WEB_RUNTIME_ROOT}/app ./app
COPY --from=codegen /app/${WEB_RUNTIME_ROOT}/public ./public
COPY --from=codegen /app/${WEB_RUNTIME_ROOT}/react-router.config.ts ./
COPY --from=codegen /app/${WEB_RUNTIME_ROOT}/tsconfig.json ./
COPY --from=codegen /app/${WEB_RUNTIME_ROOT}/vite.config.ts ./
COPY --from=codegen /app/${WEB_RUNTIME_ROOT}/package.json ./
# Copy Python sources so Tailwind can scan them for class names
COPY ${APP_FILE} ../${APP_RUNTIME_FILE}
ENV NODE_ENV=production
RUN bun run build

# Stage 7: Final layer - copy venv, prod node_modules, and build output
FROM python:3.12-slim AS final
ARG APP_FILE
ARG WEB_ROOT
ARG APP_RUNTIME_FILE
ARG WEB_RUNTIME_ROOT
ARG PULSE_INTERNAL_SERVER_ADDRESS
WORKDIR /app
# Copy Bun
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun
# Copy Python venv from python-deps stage
COPY --from=python-deps /app/.venv /app/.venv
# Copy prod node_modules from js-prod-deps stage
COPY --from=js-prod-deps /app/${WEB_RUNTIME_ROOT}/node_modules /app/${WEB_RUNTIME_ROOT}/node_modules
# Copy build output from js-build stage
COPY --from=js-build /app/${WEB_RUNTIME_ROOT}/build /app/${WEB_RUNTIME_ROOT}/build
# Copy package.json from js-build stage
COPY --from=js-build /app/${WEB_RUNTIME_ROOT}/package.json /app/${WEB_RUNTIME_ROOT}/package.json
# Copy Python application files
COPY ${APP_FILE} ./${APP_RUNTIME_FILE}
# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PULSE_APP_FILE=${APP_RUNTIME_FILE}
ENV PULSE_INTERNAL_SERVER_ADDRESS=${PULSE_INTERNAL_SERVER_ADDRESS}
# Expose port 8000
EXPOSE 8000
# Run the application in production mode
# Note: PULSE_SERVER_ADDRESS environment variable must be set at runtime
CMD ["sh", "-c", "pulse run \"$PULSE_APP_FILE\" --prod --address 0.0.0.0"]
