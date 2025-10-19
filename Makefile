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
	@echo "Running Biome linter..."
	@bun run lint
	@echo "Running Ruff linter..."
	@uv run ruff check .

lint-fix:
	@echo "Running Biome linter with auto-fix..."
	@bun run lint:fix
	@echo "Running Ruff linter with auto-fix..."
	@uv run ruff check --fix .

# Formatting
format:
	@echo "Formatting with Biome..."
	@bun run format
	@echo "Formatting with Ruff..."
	@uv run ruff format .

format-check:
	@echo "Checking Biome formatting..."
	@bun run format:check
	@echo "Checking Ruff formatting..."
	@uv run ruff format --check .

# Type checking
typecheck:
	@echo "Running Basedpyright type checker..."
	@uv run basedpyright

# Testing
test:
	@echo "Running Python tests..."
	@uv run pytest
	@echo "Running JS tests..."
	@bun test

# Run everything
all: format lint typecheck test
	@echo "All checks passed!"
