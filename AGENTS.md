# Repository Guidelines

## Project Structure & Module Organization
- `packages/pulse/`: Python core framework and CLI (`pulse`). Source in `src/pulse/`; tests in `packages/pulse/tests/`.
- `packages/pulse-lucide/`: Python icon set for Pulse; depends on `pulse-framework`.
- `packages/pulse-ui-client/`: TypeScript React client distributed to the web app; source in `src/`.
- `examples/pulse-demo/`: React Router + Vite app wiring the UI client; local dev playground.
- `examples/*.py`: Minimal Python examples (`main.py`, `auth.py`).

## Build, Test, and Development Commands
- Python (workspace managed by `uv`):
  - Format code: `uv format` (use `uv format --check` in CI).
  - Run tests: `uv run pytest -q` (from repo root).
  - Run CLI: `uv run pulse --help`.
- UI Client (TypeScript via Bun):
  - Build: `cd packages/pulse-ui-client && bun install && bun run build`.
- Example Web App (Bun for JS):
  - Dev server: `cd examples/pulse-demo && bun install && bun run dev`.
  - Build: `cd examples/pulse-demo && bun run build`.
  - Tests (Vitest): `cd examples/pulse-demo && bun test`.

## Coding Style & Naming Conventions
- Python: 4‑space indents; type‑annotate public APIs; modules/functions `snake_case`, classes `PascalCase`. Keep files `snake_case.py` (e.g., `react_component.py`).
- TypeScript/React: ES modules; components `PascalCase`; hooks `useX`; test files `*.test.ts(x)`. Keep source file names lowercase and concise (e.g., `renderer.tsx`, `serialize/flatted.test.ts`).
- Formatting/Linting: No repo‑enforced formatter; match existing style, small focused diffs.

## Testing Guidelines
- Python: Place tests under `packages/pulse/tests/` named `test_*.py`. Use `pytest` and `pytest-asyncio` where needed. Aim to cover new behavior and edge cases.
- TypeScript: Co‑locate unit tests as `*.test.ts(x)` near sources. Use `bun test` in JS packages; the demo app uses Vitest.

## Commit & Pull Request Guidelines
- Commits: Prefer Conventional Commits (e.g., `feat:`, `fix:`, `docs:`) with imperative, present‑tense subjects.
- PRs: Clear description, linked issues, reproduction steps, and screenshots for UI changes. Include tests and update docs as applicable. Ensure `uv format --check`, `uv run pytest`, and `bun test` pass.

## Security & Configuration Tips
- Tooling: Python 3.12+ workspace (Pulse supports ≥3.11), Node 20+, Bun 1.0+.
- Secrets: Never commit credentials. Use environment variables and local `.env` files excluded by `.gitignore`.
