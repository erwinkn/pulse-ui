# Stage 1: Python dependency installation using uv
FROM python:3.12-slim AS python-deps
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv venv && uv sync --frozen

# Stage 2: Dependency check - validate web dependencies are in sync
FROM python:3.12-slim AS check
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Copy Python application and venv
COPY pyproject.toml uv.lock main.py ./
COPY --from=python-deps /app/.venv /app/.venv
# Copy web package.json for validation
COPY web/package.json web/
# Add venv to PATH and run pulse check
ENV PATH="/app/.venv/bin:$PATH"
RUN pulse check main.py

# Stage 3: Codegen - generate routes with PULSE_SERVER_ADDRESS
FROM python:3.12-slim AS codegen
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Copy Python application and venv
COPY pyproject.toml uv.lock main.py ./
COPY --from=python-deps /app/.venv /app/.venv
# Copy web directory (needed for codegen output)
COPY web ./web
# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
# Accept build arg for PULSE_SERVER_ADDRESS
ARG PULSE_SERVER_ADDRESS
# Set environment variable for codegen
ENV PULSE_SERVER_ADDRESS=${PULSE_SERVER_ADDRESS}
# Generate routes in CI mode
RUN pulse generate main.py --ci

# Stage 4: JS dev dependencies
FROM oven/bun:latest AS js-dev-deps
WORKDIR /app/web
COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile

# Stage 5: JS prod dependencies
FROM oven/bun:latest AS js-prod-deps
WORKDIR /app/web
COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile --production

# Stage 6: JS build
FROM oven/bun:latest AS js-build
WORKDIR /app/web
COPY --from=js-dev-deps /app/web/node_modules ./node_modules
# Copy entire web directory from codegen stage (includes generated routes)
COPY --from=codegen /app/web/app ./app
COPY --from=codegen /app/web/public ./public
COPY --from=codegen /app/web/react-router.config.ts ./
COPY --from=codegen /app/web/tsconfig.json ./
COPY --from=codegen /app/web/vite.config.ts ./
COPY --from=codegen /app/web/package.json ./
# Copy Python sources so Tailwind can scan them for class names
COPY main.py ../main.py
ENV NODE_ENV=production
RUN bun run build

# Stage 7: Final layer - copy venv, prod node_modules, and build output
FROM python:3.12-slim AS final
# Copy Bun
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun
# Copy Python venv from python-deps stage
COPY --from=python-deps /app/.venv /app/.venv
# Copy prod node_modules from js-prod-deps stage
COPY --from=js-prod-deps /app/web/node_modules /app/web/node_modules
# Copy build output from js-build stage
COPY --from=js-build /app/web/build /app/web/build
# Copy package.json from js-build stage
COPY --from=js-build /app/web/package.json /app/web/package.json
# Copy Python application files
COPY main.py /app/main.py
# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
# Expose port 8000
EXPOSE 8000
WORKDIR /app
# Run the application in production mode
# Note: PULSE_SERVER_ADDRESS environment variable must be set at runtime
CMD ["pulse", "run", "main.py", "--prod", "--address", "0.0.0.0"]