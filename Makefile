.PHONY: help init lint lint-fix format format-check typecheck typecheck-py typecheck-ts test all bump

help:
	@echo "Available commands:"
	@echo "  make init          - Initialize environment (sync packages, install deps, build)"
	@echo "  make lint          - Run all linters (Biome for JS/TS, Ruff for Python)"
	@echo "  make lint-fix      - Run all linters with auto-fix"
	@echo "  make format        - Format all code (Biome for JS/TS, Ruff for Python)"
	@echo "  make format-check  - Check formatting without modifying files"
	@echo "  make typecheck     - Run type checking (Basedpyright for Python)"
	@echo "  make test          - Run all tests (pytest for Python, bun test for JS)"
	@echo "  make all           - Run format, lint, typecheck, and test"
	@echo "  make bump          - Bump package version (PKG=name ARGS='--patch|--alpha|...')"

# Initialization
init:
	@echo "Syncing Python packages..."
	@uv sync --all-packages --dev
	@echo "Installing JS dependencies..."
	@bun i
	@echo "Installing docs dependencies..."
	@bun i
	@cd docs && bun i
	@echo "Building JS packages..."
	@bun run build
	@echo "Installing pre-commit hooks"
	@uv run prek install
	@echo "Environment initialized!"

# Linting
lint:
	@echo "Running Ruff linter..."
	@uv run ruff check .
	@echo "Running Biome linter..."
	@bunx biome lint

lint-fix:
	@echo "Running Ruff linter with auto-fix..."
	@uv run ruff check --fix .
	@echo "Running Biome linter with auto-fix..."
	@bunx biome check --write

# Formatting
format:
	@echo "Formatting with Ruff..."
	@uv run ruff format .
	@echo "Formatting with Biome..."
	@bunx biome format --write

format-check:
	@echo "Checking Ruff formatting..."
	@uv run ruff format --check .
	@echo "Checking Biome formatting..."
	@bunx biome format

# Type checking
typecheck: typecheck-py typecheck-ts

typecheck-py:
	@echo "Running basedpyright..."
	@uv run basedpyright

typecheck-ts:
	@echo "Running TypeScript for pulse-ui-client..."
	@bunx tsc --noEmit -p packages/pulse/js/tsconfig.json
	@echo "Running TypeScript for pulse-mantine..."
	@bunx tsc --noEmit -p packages/pulse-mantine/js/tsconfig.json
	@echo "Running TypeScript for docs..."
	@cd docs && bun run types:check

# Testing
test:
	@echo "Running Python tests..."
	@uv run pytest
	@echo "Running JS tests..."
	@bun test

# Run everything
all: format lint typecheck test
	@echo "All checks passed!"

# Version bumping
bump:
ifndef PKG
	@echo "Usage: make bump PKG=<package-name> [ARGS='--patch|--minor|--major|--alpha|--beta|--rc|--version X.Y.Z']"
	@echo "Example: make bump PKG=pulse ARGS='--alpha'"
	@echo "Example: make bump PKG=pulse ARGS='--beta'"
	@python scripts/bump_version.py
else
	@python scripts/bump_version.py $(PKG) $(ARGS)
endif
