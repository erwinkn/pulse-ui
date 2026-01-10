# Ralph Agent Instructions

## Your Task

1. Read `plans/minimal-react-framework/progress.txt`
2. Check you're on the correct branch: `minimal-react`
3. **Check for in-progress work** (see Task Selection below)
4. Implement that ONE feature
5. Run typecheck and tests: `make all`
6. Update AGENTS.md files with learnings (if discovered reusable patterns)
7. Commit: `feat: [ID] - [Title]`
8. Update prd.json: `passes: true`
9. Append learnings to progress.txt (clear "In Progress" section if completing it)
10. Stop after implementing this single feature

## Task Selection

Check `progress.txt` for an `## In Progress` section:

**If in-progress work exists:**
- You MUST continue that feature (don't start something new)
- Exception: If you discover a missing dependency that must be done first, document this in progress.txt and work on the dependency instead
- Read the in-progress notes carefully - they contain context from the previous iteration

**If no in-progress work:**
- Run: `python .claude/skills/prd-gen/available_tasks.py plans/minimal-react-framework/prd.json`
- Pick any task from the available list

## Context Window Management

After each tool call, the hook reports current context usage as feedback.

**At ~60% context**: Start planning to stop soon.

**At ~80% context**: STOP IMMEDIATELY. Make NO more tool calls. Save your work:

1. **Read progress.txt** to see the format
2. **Write `## In Progress` section** with:
   - What you completed
   - Current working state
   - Exact next steps to try
   - Key learnings
3. **Do NOT mark task as passed** in prd.json
4. **Commit**: `wip: [ID] - partial progress`
5. **Stop the session** - next agent will continue with fresh context

## Progress Format

When completing a feature, APPEND to progress.txt:

---
## [Date] - [Feature ID]
- What was implemented
- Files changed
- **Learnings:**
  - Patterns discovered
  - Gotchas encountered
---

If you completed in-progress work, clear the `## In Progress` section.

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
