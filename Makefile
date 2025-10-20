.PHONY: help lint lint-fix format format-check typecheck test all

help:
	@echo "Available commands:"
	@echo "  make lint          - Run all linters (Biome for JS/TS, Ruff for Python)"
	@echo "  make lint-fix      - Run all linters with auto-fix"
	@echo "  make format        - Format all code (Biome for JS/TS, Ruff for Python)"
	@echo "  make format-check  - Check formatting without modifying files"
	@echo "  make typecheck     - Run type checking (Basedpyright for Python)"
	@echo "  make test          - Run all tests (pytest for Python, bun test for JS)"
	@echo "  make all           - Run format, lint, typecheck, and test"

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
typecheck:
	@echo "Running basedpyright..."
	@uv run basedpyright
	@echo "Running TypeScript for pulse-ui-client..."
	@bunx tsc --noEmit -p packages/pulse-ui-client/tsconfig.json
	@echo "Running TypeScript for pulse-mantine..."
	@bunx tsc --noEmit -p packages/pulse-mantine/js/tsconfig.json

# Testing
test:
	@echo "Running Python tests..."
	@uv run pytest
	@echo "Running JS tests..."
	@bun test

# Run everything
all: format lint typecheck test
	@echo "All checks passed!"
