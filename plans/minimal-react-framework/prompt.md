# Ralph Agent Instructions

## Your Task

1. Read `plans/minimal-react-framework/progress.txt` (check Codebase Patterns first)
2. Check you're on the correct branch: `minimal-react-framework`
3. Run: `python .claude/skills/prd-gen/available_tasks.py plans/minimal-react-framework/prd.json`
4. Pick any task from the available list (all shown tasks have satisfied dependencies)
5. Implement that ONE feature
6. Run typecheck and tests: `make all`
7. Update AGENTS.md files with learnings (if discovered reusable patterns)
8. Commit: `feat: [ID] - [Title]`
9. Update prd.json: `passes: true`
10. Append learnings to progress.txt
11. Stop after implementing this single feature

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
- Migrations: Use IF NOT EXISTS
- React: useRef<Timeout | null>(null)
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
