# AGENTS.md

## Code style
- Never use `getattr` / `setattr` unless absolutely necessary
- Prioritize agressive programming: code that fails early is better than code that silently accepts an invalid state or broken assumption
- Minimize the amount of state and data structures 
- Do not worry about backwards compatibility unless explicitly instructed to do so
- Avoid single-use helper functions, unless the goal is to have single main function with clear control that performs multiple tasks in sequence by calling helpers
- Avoid use of `if TYPE_CHECKING` unless an actual import cycle is created

## Development Commands
### Running code
- Run Python code: `uv run path/to/script.py`
- Run JavaScript / TypeScript code: `bun path/to/file.ts`

### Formatting
- Format all code: `make format`
- Check formatting: `make format-check`

### Linting
- Run all linters: `make lint`
- Run linters with auto-fix: `make lint-fix`

### Type Checking
- Run type checking: `make typecheck`

### Testing
- Python tests: `uv run pytest`
- JS tests: `bun test`
- All tests: `make test`

### All Checks
- Run everything (format, lint, typecheck, test): `make all`

## Pre-commit Hooks

Pre-commit hooks are set up using prek and will run automatically on `git commit`:

- **Setup**: `uv run prek install`
- **Manual run on all files**: `uv run prek run --all-files`
- **Bypass hooks** (not recommended): `git commit --no-verify`

The hooks run:
- Ruff formatting and linting (Python) with auto-fix
- Biome formatting and linting (JS/TS) with auto-fix

Hooks only run on staged files and are fast (~1-3 seconds).

## CI/CD

GitHub Actions CI runs on all PRs and must pass before merging:
- Format checking
- Linting
- Type checking  
- All tests

Run `make all` locally before pushing to catch issues early.
