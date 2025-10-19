# Linting, Type Checking, and Formatting

This document describes the linting, type checking, and formatting setup for the Pulse monorepo.

## Tools

### JavaScript/TypeScript
- **Biome**: Formatting and linting for JS/TS files
  - Configuration: `biome.json`
  - Fast, modern alternative to ESLint + Prettier

### Python
- **Ruff**: Linting and formatting for Python files
  - Configuration: `pyproject.toml` (under `[tool.ruff]`)
  - Fast, all-in-one Python linter and formatter
  
- **Basedpyright**: Type checking for Python files
  - Configuration: `basedpyright.toml`
  - Fork of Pyright with additional features

## Commands

### Using Makefile (Recommended)

The easiest way to run linting and formatting across the entire monorepo:

```bash
# Show all available commands
make help

# Format all code (JS/TS and Python)
make format

# Check formatting without modifying files
make format-check

# Run all linters
make lint

# Run all linters with auto-fix
make lint-fix

# Run type checking
make typecheck

# Run all tests
make test

# Run everything (format, lint, typecheck, test)
make all
```

### Using npm/bun scripts (JS/TS only)

```bash
# Format JS/TS files
bun run format

# Check JS/TS formatting
bun run format:check

# Lint JS/TS files
bun run lint

# Lint and fix JS/TS files
bun run lint:fix
```

### Using uv directly (Python only)

```bash
# Format Python files
uv run ruff format .

# Check Python formatting
uv run ruff format --check .

# Lint Python files
uv run ruff check .

# Lint and fix Python files
uv run ruff check --fix .

# Type check Python files
uv run basedpyright
```

## Pre-commit Hooks

Pre-commit hooks are configured to automatically run linting and formatting on staged files before each commit.

### Installation

The hooks are automatically installed when you run `uv sync` or you can install them manually:

```bash
uv run pre-commit install
```

### Running manually

You can run the pre-commit hooks manually on all files:

```bash
uv run pre-commit run --all-files
```

### What runs on commit

1. **Biome Check**: Formats and lints JS/TS files with auto-fix
2. **Ruff Lint**: Lints Python files with auto-fix
3. **Ruff Format**: Formats Python files
4. **Basedpyright**: Type checks Python files

If any check fails, the commit will be aborted. Fix the issues and try again.

## Configuration

### Biome (`biome.json`)
- Line width: 100 characters
- Indent style: Tabs
- Quote style: Double quotes
- Import organization: Enabled

### Ruff (`pyproject.toml`)
- Line length: 100 characters
- Target Python version: 3.11
- Selected rules: pycodestyle, pyflakes, isort, flake8-bugbear, flake8-comprehensions, pyupgrade
- Ignores: E501 (line too long), B008 (function calls in defaults), C901 (complexity)

### Basedpyright (`basedpyright.toml`)
- Type checking mode: Standard
- Python version: 3.11
- Includes: All package source directories and examples
- Excludes: Cache directories, node_modules, virtual environments

## CI/CD Integration

Add these commands to your CI/CD pipeline:

```bash
# Check formatting
make format-check

# Run linters
make lint

# Run type checking
make typecheck

# Run tests
make test
```

## Editor Integration

### VS Code

Install the following extensions:
- [Biome](https://marketplace.visualstudio.com/items?itemName=biomejs.biome)
- [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
- [Basedpyright](https://marketplace.visualstudio.com/items?itemName=detachhead.basedpyright)

Add to your `.vscode/settings.json`:

```json
{
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "quickfix.biome": "explicit",
    "source.organizeImports.biome": "explicit"
  },
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.codeActionsOnSave": {
      "source.fixAll": "explicit",
      "source.organizeImports": "explicit"
    }
  },
  "[javascript]": {
    "editor.defaultFormatter": "biomejs.biome"
  },
  "[typescript]": {
    "editor.defaultFormatter": "biomejs.biome"
  },
  "[javascriptreact]": {
    "editor.defaultFormatter": "biomejs.biome"
  },
  "[typescriptreact]": {
    "editor.defaultFormatter": "biomejs.biome"
  },
  "python.analysis.typeCheckingMode": "standard"
}
```

### Other Editors

Biome, Ruff, and Basedpyright have plugins for most popular editors. Check their documentation for setup instructions.
