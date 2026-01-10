# Ralph Agent Instructions

## Your Task

1. Read `plans/code-splitting-poc/progress.txt`
2. Check you're on the correct branch: `code-splitting-poc`
3. **Check for in-progress work** (see Task Selection below)
4. Implement that ONE feature
5. Run typecheck and tests: `make all` or feature-specific test
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
- Run: `python .claude/skills/prd-gen/available_tasks.py plans/code-splitting-poc/prd.json`
- Pick any task from the available list

## Context Window Management

You may receive warnings about context usage during your work:

**⚠️ Warning (~60% context)**: Start wrapping up. If feature is nearly done, finish it. If not, prepare to save progress.

**🛑 Critical (~80% context)**: STOP IMMEDIATELY. Do not continue implementation.

When stopping due to context limits:

1. **Do NOT mark task as passed** - it's incomplete
2. **Write to progress.txt** under `## In Progress`:
   ```
   ## In Progress
   ### [Feature ID] - [Title]
   **Status**: Incomplete - context limit reached
   **What was done**:
   - List completed steps
   - Files modified: x.py, y.ts
   **Current state**:
   - Describe where you stopped
   - What's working/broken
   **Next steps**:
   - What to try next iteration
   - Hypotheses about the problem
   **Key learnings**:
   - Patterns discovered
   - Gotchas encountered
   ```
3. **Commit partial work** (if any): `wip: [ID] - partial progress`
4. **Stop** - next iteration will continue with fresh context

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
