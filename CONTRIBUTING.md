# Contributing to Pulse

Thank you for your interest in contributing to Pulse! This guide will help you set up your development environment and understand our workflow.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) for Python package management
- [Bun](https://bun.sh/) for JavaScript package management

### Getting Started

1. Clone the repository and install dependencies:

```bash
# Install Python dependencies
uv sync --dev

# Install JavaScript dependencies
bun install
```

2. Set up pre-commit hooks (recommended):

```bash
uv run prek install
```

This will automatically format and lint your code before each commit.

## Available Commands

All development commands are available through the Makefile:

```bash
make format        # Format all code (Biome for JS/TS, Ruff for Python)
make format-check  # Check formatting without modifying files
make lint          # Run all linters
make lint-fix      # Run linters with auto-fix
make typecheck     # Run type checking (Basedpyright + TypeScript)
make test          # Run all tests (pytest + bun test)
make all           # Run format, lint, typecheck, and test
```

## Pre-commit Hooks

Pre-commit hooks run formatting and linting on staged files only, keeping your commits clean. They're fast (~1-3 seconds) and will auto-fix most issues.

The hooks will:
- Format Python code with Ruff
- Lint Python code with Ruff (with auto-fix)
- Format JavaScript/TypeScript code with Biome
- Lint JavaScript/TypeScript code with Biome (with auto-fix)

To run hooks manually on all files:

```bash
uv run prek run --all-files
```

To bypass hooks (not recommended):

```bash
git commit --no-verify
```

## Continuous Integration

All PRs must pass CI checks before merging. The CI pipeline runs:
- Format checking
- Linting
- Type checking
- All tests

You can run the same checks locally with `make all` before pushing.

## Development Workflow

1. Create a new branch for your feature/fix
2. Make your changes
3. Run `make all` to ensure all checks pass locally
4. Commit your changes (pre-commit hooks will run automatically)
5. Push your branch and create a pull request
6. Wait for CI to pass and address any feedback

## Monorepo Structure

This is a monorepo containing multiple packages:

### Python Packages
- `packages/pulse/python` - Core Pulse framework
- `packages/pulse-ag-grid/` - AG Grid integration
- `packages/pulse-lucide/` - Lucide icons
- `packages/pulse-mantine/python/` - Mantine components (Python)
- `packages/pulse-msal/` - Microsoft Authentication Library integration
- `packages/pulse-recharts/` - Recharts integration

### JavaScript Packages
- `packages/pulse/js` - Client-side JavaScript runtime
- `packages/pulse-mantine/js/` - Mantine components (JavaScript)

### Examples and Documentation
- `examples/` - Example applications
- `tutorial/` - Tutorial examples
- `docs/` - Documentation

## Code Quality Standards

- **Formatting**: Code is automatically formatted using Ruff (Python) and Biome (JavaScript/TypeScript)
- **Linting**: We use Ruff for Python and Biome for JavaScript/TypeScript
- **Type Checking**: Python code is type-checked with Basedpyright, TypeScript with tsc
- **Testing**: Write tests for new features and ensure existing tests pass

## Getting Help

If you need help or have questions:
- Check existing issues and discussions
- Create a new issue for bugs or feature requests
- Join our community discussions
