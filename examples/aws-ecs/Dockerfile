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

# Stage 3: JS dev dependencies
FROM oven/bun:latest AS js-dev-deps
WORKDIR /app/web
COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile

# Stage 4: JS prod dependencies
FROM oven/bun:latest AS js-prod-deps
WORKDIR /app/web
COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile --production

# Stage 5: JS build
FROM oven/bun:latest AS js-build
WORKDIR /app/web
COPY --from=js-dev-deps /app/web/node_modules ./node_modules
COPY web/app ./app
COPY web/public ./public
COPY web/react-router.config.ts web/tsconfig.json web/vite.config.ts ./
COPY web/package.json ./
# Copy Python sources so Tailwind can scan them for class names
COPY main.py ../main.py
ENV NODE_ENV=production
RUN bun run build

# Stage 6: Final layer - copy venv, prod node_modules, and build output
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