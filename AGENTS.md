# Pulse

Full-stack Python framework for interactive web apps. Runs on React with WebSocket-driven UI updates.

## Code Style

- No `getattr`/`setattr` unless necessary
- Fail early over silent failures
- Minimize state and data structures
- No backwards compatibility unless instructed
- Avoid single-use helpers (except for sequential task orchestration)
- Avoid `typing.TYPE_CHECKING` and non-global imports unless avoiding import cycles

## Commands

```bash
make init          # First-time setup in a new worktree
make all           # Format, lint, typecheck, test
make format        # Biome + Ruff
make lint-fix      # Lint with auto-fix
make typecheck     # Basedpyright + tsc
make test          # pytest + bun test
```

```bash
uv run <script.py>                # Run Python
bun <file.ts>                     # Run JS/TS
uv run pulse run examples/app.py  # Run a Pulse app (dev server on :8000)
```

## Structure

```
packages/
├── pulse/python/src/pulse/   # Core Python (app, state, component, renderer, vdom, hooks/, queries/)
├── pulse/js/src/             # JS client (client.tsx, renderer.tsx, serialize/)
├── pulse-mantine/            # Mantine UI
├── pulse-ag-grid/            # AG Grid
├── pulse-recharts/           # Charts
├── pulse-lucide/             # Icons
├── pulse-msal/               # MS auth
└── pulse-aws/                # AWS deploy
examples/                     # Example apps
```

## Guidelines

- Be extremely concise. Sacrifice grammar for the sake of concision.
- Read the README.md in the relevant package before starting work
- Run `make all` before committing
- Check `examples/` for patterns
- Use `make bump` for changing package versions
- When editing docs, update `docs/content/docs/(core)/glossary.mdx` if introducing new technical terms
