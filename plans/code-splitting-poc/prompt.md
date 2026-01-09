# Ralph Agent Instructions

## Your Task

1. Read `plans/code-splitting-poc/prd.json`
2. Read `plans/code-splitting-poc/progress.txt` (check Codebase Patterns first)
3. Check you're on the correct branch: `code-splitting-poc`
4. Pick highest priority feature where `passes: false`
5. Implement that ONE feature
6. Run typecheck and tests: `make all` or feature-specific test
7. Update AGENTS.md files with learnings (if discovered reusable patterns)
8. Commit: `feat: [ID] - [Title]`
9. Update prd.json: `passes: true`
10. Append learnings to progress.txt

## Progress Format

APPEND to progress.txt:

---
## [Date] - [Feature ID]
- What was implemented
- Files changed
- **Learnings:**
  - Patterns discovered
  - Gotchas encountered
---

## Codebase Patterns

Add reusable patterns to the TOP of progress.txt under "## Codebase Patterns":

```
## Codebase Patterns
- Vite: Use dynamic import() for code splitting
- Bun SSR: Use require() for synchronous imports
```

## AGENTS.md Updates

Update AGENTS.md in directories with edited files if you discover:
- "When modifying X, also update Y"
- "This module uses pattern Z"
- "Tests require dev server running"

Do NOT add story-specific details or temporary notes.

## Stop Condition

If ALL features pass, reply:
<promise>COMPLETE</promise>

Otherwise end normally.

## POC-Specific Notes

- This is a standalone POC in `poc/` directory
- Uses Bun as package manager and runtime
- Main codebase's `make all` won't apply; use feature-specific tests
- Focus on validating architecture, not production quality
