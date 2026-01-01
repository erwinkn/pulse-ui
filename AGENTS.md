# AGENTS.md

## Code style
- Never use `getattr` / `setattr` unless absolutely necessary
- Prioritize agressive programming: code that fails early is better than code that silently accepts an invalid state or broken assumption
- Minimize the amount of state and data structures 
- Do not worry about backwards compatibility unless explicitly instructed to do so
- Avoid single-use helper functions, unless the goal is to have single main function with clear control that performs multiple tasks in sequence by calling helpers
- Avoid use of `typing.TYPE_CHECKING` and non-global imports unless they are necessary to avoid an import cycle

## Tools
- Always use context7 when I need code generation, setup or configuration steps, or
library/API documentation. This means you should automatically use the Context7 MCP
tools to resolve library id and get library docs without me having to explicitly ask.
- Use 'bd' for task tracking.

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
- Python-only: use `basedpyright` directly

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

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
