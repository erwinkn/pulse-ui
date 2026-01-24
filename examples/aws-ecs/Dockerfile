ARG APP_FILE=main.py
ARG WEB_ROOT=web

# Stage 1: Python dependency installation using uv
FROM python:3.12-slim AS python-deps
ARG APP_FILE
ARG WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv venv && uv sync --frozen

# Stage 2: Dependency check - validate web dependencies are in sync
FROM python:3.12-slim AS check
ARG APP_FILE
ARG WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Copy Python application and venv
COPY pyproject.toml uv.lock ${APP_FILE} ./
COPY --from=python-deps /app/.venv /app/.venv
# Copy web package.json for validation
COPY ${WEB_ROOT}/package.json ${WEB_ROOT}/
# Add venv to PATH and run pulse check
ENV PATH="/app/.venv/bin:$PATH"
RUN pulse check ${APP_FILE}

# Stage 3: Codegen - generate routes with PULSE_SERVER_ADDRESS
FROM python:3.12-slim AS codegen
ARG APP_FILE
ARG WEB_ROOT
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Copy Python application and venv
COPY pyproject.toml uv.lock ${APP_FILE} ./
COPY --from=python-deps /app/.venv /app/.venv
# Copy web directory (needed for codegen output)
COPY ${WEB_ROOT} ./${WEB_ROOT}
# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
# Accept build arg for PULSE_SERVER_ADDRESS
ARG PULSE_SERVER_ADDRESS
# Set environment variable for codegen
ENV PULSE_SERVER_ADDRESS=${PULSE_SERVER_ADDRESS}
# Generate routes in CI mode
RUN pulse generate ${APP_FILE} --ci

# Stage 4: JS dev dependencies
FROM oven/bun:latest AS js-dev-deps
ARG WEB_ROOT
WORKDIR /app/${WEB_ROOT}
COPY ${WEB_ROOT}/package.json ${WEB_ROOT}/bun.lock ./
RUN bun install --frozen-lockfile

# Stage 5: JS prod dependencies
FROM oven/bun:latest AS js-prod-deps
ARG WEB_ROOT
WORKDIR /app/${WEB_ROOT}
COPY ${WEB_ROOT}/package.json ${WEB_ROOT}/bun.lock ./
RUN bun install --frozen-lockfile --production

# Stage 6: JS build
FROM oven/bun:latest AS js-build
ARG APP_FILE
ARG WEB_ROOT
WORKDIR /app/${WEB_ROOT}
COPY --from=js-dev-deps /app/${WEB_ROOT}/node_modules ./node_modules
# Copy entire web directory from codegen stage (includes generated routes)
COPY --from=codegen /app/${WEB_ROOT}/app ./app
COPY --from=codegen /app/${WEB_ROOT}/public ./public
COPY --from=codegen /app/${WEB_ROOT}/server ./server
COPY --from=codegen /app/${WEB_ROOT}/src ./src
COPY --from=codegen /app/${WEB_ROOT}/tsconfig.json ./
COPY --from=codegen /app/${WEB_ROOT}/vite.config.ts ./
COPY --from=codegen /app/${WEB_ROOT}/package.json ./
COPY --from=codegen /app/${WEB_ROOT}/bun.lock ./
# Copy Python sources so Tailwind can scan them for class names
COPY ${APP_FILE} ../${APP_FILE}
ENV NODE_ENV=production
RUN bun run build

# Stage 7: Final layer - copy venv, prod node_modules, and build output
FROM python:3.12-slim AS final
ARG APP_FILE
ARG WEB_ROOT
# Copy Bun
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun
# Copy Python venv from python-deps stage
COPY --from=python-deps /app/.venv /app/.venv
# Copy prod node_modules from js-prod-deps stage
COPY --from=js-prod-deps /app/${WEB_ROOT}/node_modules /app/${WEB_ROOT}/node_modules
# Copy build output from js-build stage
COPY --from=js-build /app/${WEB_ROOT}/dist /app/${WEB_ROOT}/dist
COPY --from=js-build /app/${WEB_ROOT}/server /app/${WEB_ROOT}/server
# Copy package.json from js-build stage
COPY --from=js-build /app/${WEB_ROOT}/package.json /app/${WEB_ROOT}/package.json
# Copy Python application files
COPY ${APP_FILE} ./${APP_FILE}
# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PULSE_APP_FILE=${APP_FILE}
# Expose port 8000
EXPOSE 8000
WORKDIR /app
# Run the application in production mode
# Note: PULSE_SERVER_ADDRESS environment variable must be set at runtime
CMD ["sh", "-c", "pulse start \"$PULSE_APP_FILE\" --address 0.0.0.0"]
