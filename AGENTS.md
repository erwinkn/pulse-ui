# Pulse

Full-stack Python framework for interactive web apps. Runs on React with WebSocket-driven UI updates.

## Guidelines

- Be extremely concise. Sacrifice grammar for the sake of concision.
- Read the README.md in the relevant package before starting work
- Always add tests when implementing a new feature. 
- If dependencies are not installed, run `make sync`
- Run `make test` after implementing
- Run `make all` before committing
- Check `examples/` for usage patterns
- Use `make bump` for changing package versions
- When using a framework/library, do not make assumptions, fetch latest docs (using context7 for example)
- Use `bun info ...` to get information about a JS package
- Test examples by running them with `pulse run` in a background task and using the agent-browser CLI for interacting with the UI.
- While debugging, feel free to add debug print statements, spin up test files, modify existing code, or anything else that would improve your feedback loop and accelerate the troubleshooting process. Remove those debug changes after fixing the issue.


## Code Style

- No `getattr`/`setattr` unless necessary
- Fail early over silent failures
- Minimize state and data structures
- No backwards compatibility unless instructed
- Avoid single-use helpers (except for sequential task orchestration)
- Avoid `typing.TYPE_CHECKING` and non-global imports unless avoiding import cycles

## Code Architecture

- Keep one owner per invariant/state machine. Put lifecycle transitions in that owner.
- Avoid pass-through wrappers (`a()` just calls `b()`) unless they enforce a boundary/API.
- If a helper is only called once, inline it unless it substantially improves readability.
- Avoid public/private duplicate pairs with same behavior (`foo` + `_foo`); keep one path.
- Merge duplicated event pipelines into one dispatch helper when logic is same.
- Prefer explicit lifecycle contracts over fallback branches that mask ordering bugs.
- When simplifying, remove old wrapper/compat paths in same change (don’t keep both).

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

## Subagents
- ALWAYS wait for all subagents to complete before yielding.
- Spawn subagents automatically when:
- Parallelizable work (e.g., install + verify, npm test + typecheck, multiple tasks from plan)
- Long-running or blocking tasks where a worker can run independently.
Isolation for risky changes or checks

## Documentation

Before writing or editing docs, read `docs/GUIDELINES.md` for tone, structure, and Pulse conventions. Key points:
- One page, one job (tutorial / how-to / reference / explanation)
- Code first, explain after
- Be conversational—write like you're explaining to a friend
- Update `docs/content/docs/(core)/glossary.mdx` if introducing new terms
- When changing behavior/APIs, update both `docs/` and `skills/` (if the feature is covered there)
