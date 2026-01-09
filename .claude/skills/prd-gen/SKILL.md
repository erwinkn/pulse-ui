---
name: prd-gen
description: Convert a spec/architecture document into a PRD JSON file optimized for Ralph agent. Use when you have a design doc and need to create implementable stories.
allowed-tools: Read, Write, Glob, Grep, Task, Bash
---

# PRD Generator for Ralph Agent

Convert spec/architecture documents into a complete Ralph execution folder.

## Input

User provides path to a spec document (e.g., `plans/minimal-react-framework.md`).

## Output Structure

Creates a subfolder in `plans/` with the spec name:

```
plans/<spec-name>/
├── spec.md          # Copy of original spec
├── prd.json         # Features list for Ralph
├── progress.txt     # Learnings log (initialized)
├── prompt.md        # Instructions for each iteration
├── run.sh           # Loop execution script
└── run-once.sh      # Single iteration (for testing)
```

## prd.json Format

```json
{
  "branchName": "feature-name",
  "features": [
    {
      "id": "F-0001",
      "title": "Short imperative title",
      "acceptanceCriteria": [
        "Explicit criterion 1",
        "Explicit criterion 2",
        "typecheck passes",
        "tests pass"
      ],
      "priority": 1,
      "passes": false,
      "notes": "",
      "tests": ["make all"],
      "dependencies": []
    }
  ]
}
```

## Critical Rules

### 1. Story Size - MUST FIT IN ONE CONTEXT WINDOW

Each story must be implementable in a single session. Break down ruthlessly:

```
❌ TOO BIG:
"Implement the router system"

✅ RIGHT SIZE:
"Create route matching algorithm for static paths"
"Add dynamic param matching (:id)"
"Add optional segment matching (:id?)"
"Add catch-all matching (*)"
```

**Heuristics for right-sized stories:**
- Touches 1-3 files max
- Single responsibility
- Can be tested in isolation
- 50-200 lines of code typically

### 2. Explicit Acceptance Criteria - NO VAGUE LANGUAGE

Every criterion must be objectively verifiable:

```
❌ VAGUE:
- "Works correctly"
- "Handles errors"
- "Users can navigate"

✅ EXPLICIT:
- "Function returns `['a', 'b']` for path `/a/b` with pattern `/*`"
- "Throws `RouteNotFoundError` when no route matches"
- "Link component renders <a> tag with href attribute"
- "`make typecheck` passes"
- "`make test` passes"
```

### 3. Dependencies - TOPOLOGICAL ORDER

Stories must be orderable. Lower priority numbers execute first. Use `dependencies` array for explicit ordering:

```json
{
  "id": "F-0003",
  "title": "Add Link component",
  "dependencies": ["F-0001", "F-0002"],
  "priority": 3
}
```

### 4. Tests/Verification Commands

Always include verification commands. Use project's actual commands:

```json
"tests": ["make all"]
```

For this codebase, standard verification is `make all` (format, lint, typecheck, test).

### 5. Steel Wire First - CRITICAL

**Get one thin vertical slice working end-to-end before expanding horizontally.**

The first 3-5 stories should establish a minimal but complete working system:

```
❌ WRONG (Horizontal Layering):
F-0001: Create all type definitions
F-0002: Create all components
F-0003: Create all utilities
...
F-0015: Build and test everything

✅ RIGHT (Steel Wire / Vertical Slice):
F-0001: Scaffold project
F-0002: Create ONE component with ONE dependency
F-0003: Build and verify chunk exists  ← EARLY VALIDATION
F-0004: Add second component
F-0005: Verify two chunks exist  ← INCREMENTAL VALIDATION
...
```

**Steel wire validates the architecture early.** If the build fails or chunks aren't created, you find out at story 3, not story 15.

### 6. Test Early and Often

**Every 2-3 implementation stories should be followed by a verification story.**

Interleave testing throughout:

```json
[
  { "id": "F-0001", "title": "Scaffold project" },
  { "id": "F-0002", "title": "Create home component with date-fns" },
  { "id": "F-0003", "title": "Build and verify single chunk works" },  // ← TEST
  { "id": "F-0004", "title": "Add dashboard component with lodash" },
  { "id": "F-0005", "title": "Verify two separate chunks in build" },  // ← TEST
  { "id": "F-0006", "title": "Add SSR rendering" },
  { "id": "F-0007", "title": "Verify SSR outputs correct HTML" },      // ← TEST
  ...
]
```

**Benefits:**
- Catch integration issues early
- Smaller debugging surface when tests fail
- Each verified story is a stable checkpoint
- Agent can stop at any green state

### 7. Include Setup Stories

First stories should handle project scaffolding:
- Create new files/directories
- Add dependencies
- Set up test fixtures

### 8. Final Integration Story

Last story should verify all goals together:
- All components work together
- Example app runs successfully
- This should be EASY because everything was tested incrementally

## Workflow

1. **Read the spec document** - Understand the full scope
2. **Identify the steel wire** - What's the minimal end-to-end path?
3. **Plan first 3-5 stories as vertical slice** - Scaffold → minimal impl → verify it works
4. **Interleave verification stories** - After every 2-3 implementation stories, add a test story
5. **Break into atomic stories** - Each story = one focused change
6. **Order by dependencies** - Foundation first, but TEST throughout (not just at the end)
7. **Write explicit criteria** - Testable, specific, measurable
8. **Add verification commands** - How does Ralph know it worked?
9. **Review story sizes** - Split any that seem too large

## Story Decomposition Patterns

### Steel Wire Pattern (PREFERRED)

Use this when building a new system or subsystem:

```
1. Scaffold / setup
2. Implement ONE minimal vertical slice
3. ✓ VERIFY: Build/run and confirm it works
4. Add second feature
5. ✓ VERIFY: Both features work together
6. Add remaining features...
7. ✓ VERIFY: after each major addition
8. Final integration verification
```

### For New Components

```
1. Create file with type stubs / interfaces
2. Implement core logic
3. ✓ VERIFY: typecheck and basic functionality
4. Add error handling
5. Wire into existing system
6. ✓ VERIFY: integration works
```

### For Algorithms

```
1. Implement base case
2. ✓ VERIFY: base case works
3. Add edge case handling
4. Add complex case handling
5. ✓ VERIFY: all cases pass
```

### For UI Components

```
1. Create component skeleton with props/types
2. Add rendering logic
3. ✓ VERIFY: renders correctly
4. Add interactivity
5. ✓ VERIFY: interactions work
```

### For CLI Commands

```
1. Add command registration + minimal implementation
2. ✓ VERIFY: command runs
3. Add options/flags
4. Add error handling
5. ✓ VERIFY: all options work
```

## Example Transformation

**Input (from spec):**
> "Implement route matching algorithm with React Router feature parity"

**Output (PRD features):**

```json
[
  {
    "id": "F-0001",
    "title": "Create route matcher for static paths",
    "acceptanceCriteria": [
      "Create `packages/pulse/js/src/router/match.ts`",
      "`matchPath('/users', '/users')` returns `{ params: {}, matched: true }`",
      "`matchPath('/users', '/posts')` returns `{ matched: false }`",
      "`make typecheck` passes"
    ],
    "priority": 1,
    "passes": false,
    "notes": "",
    "tests": ["make all"],
    "dependencies": []
  },
  {
    "id": "F-0002",
    "title": "Add dynamic param matching to router",
    "acceptanceCriteria": [
      "`matchPath('/users/:id', '/users/123')` returns `{ params: { id: '123' }, matched: true }`",
      "Multiple params work: `/users/:userId/posts/:postId`",
      "`make test` passes for router/match.test.ts"
    ],
    "priority": 2,
    "passes": false,
    "notes": "",
    "tests": ["make all"],
    "dependencies": ["F-0001"]
  },
  {
    "id": "F-0003",
    "title": "Add optional segment matching",
    "acceptanceCriteria": [
      "`matchPath('/users/:id?', '/users')` matches with `id: undefined`",
      "`matchPath('/users/:id?', '/users/123')` matches with `id: '123'`",
      "All permutations of `/a/:b?/:c?` work correctly"
    ],
    "priority": 3,
    "passes": false,
    "notes": "",
    "tests": ["make all"],
    "dependencies": ["F-0002"]
  }
]
```

## Branch Naming

Derive from spec title, kebab-case:
- "Minimal React Framework" → `minimal-react-framework`
- "User Authentication System" → `user-auth-system`

## Notes Field

Use `notes` for Ralph-relevant context:
- "Refer to React Router docs for edge cases"
- "Pattern exists in `examples/web/`"
- "May need to update imports in other files"

## Final Checklist Before Output

- [ ] **Steel wire first**: Stories 1-5 establish a minimal working end-to-end system
- [ ] **Test early and often**: Verification stories appear throughout (not just at end)
- [ ] Every story fits in one context window
- [ ] No vague criteria like "works correctly"
- [ ] Dependencies form a valid DAG
- [ ] First stories are foundational (files, types)
- [ ] Last story is integration verification (should be easy if tested incrementally)
- [ ] All stories have `make all` or specific tests
- [ ] Branch name is kebab-case
- [ ] IDs are sequential: F-0001, F-0002, etc.
- [ ] Priorities match dependency order

## Validation Script

After generating `prd.json`, run the topological order validator:

```bash
python .claude/skills/prd-gen/check_topo.py plans/<spec-name>/prd.json
```

The script checks:
- **No cycles** in dependency graph
- **Priority order** respects dependencies (if A depends on B, A.priority > B.priority)
- **Unknown dependencies** - all referenced IDs exist
- **Shows components** - visualizes disjoint subgraphs
- **Shows execution order** - both topological and by priority

## Available Tasks Script

The agent uses this script to find tasks ready to work on:

```bash
python .claude/skills/prd-gen/available_tasks.py plans/<spec-name>/prd.json
```

A task is available if:
- `passes: false` (not yet completed)
- No dependencies, OR all dependencies have `passes: true`

The script shows all available tasks and suggests the highest-priority one.

## Execute

1. Read the provided spec document
2. Determine the folder name from spec (kebab-case of title)
3. Create `plans/<spec-name>/` folder
4. Copy spec to `plans/<spec-name>/spec.md`
5. Generate `prd.json` following rules above
6. Generate `prompt.md` (see template below)
7. Generate `progress.txt` (initialized with patterns section)
8. Generate `run.sh` and `run-once.sh` (see templates below)
9. Make scripts executable: `chmod +x plans/<spec-name>/*.sh`
10. **Run validation**: `python .claude/skills/prd-gen/check_topo.py plans/<spec-name>/prd.json`
11. Fix any violations (cycles, priority mismatches)
12. Report summary: folder path, total stories, components, critical path

---

## File Templates

### prompt.md

```markdown
# Ralph Agent Instructions

## Your Task

1. Read `{{PLAN_DIR}}/progress.txt` (check Codebase Patterns first)
2. Check you're on the correct branch: `{{BRANCH_NAME}}`
3. Run: `python .claude/skills/prd-gen/available_tasks.py {{PLAN_DIR}}/prd.json`
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
```

### progress.txt

```markdown
# Ralph Progress Log
Started: {{DATE}}

## Codebase Patterns
<!-- Add discovered patterns here -->

## Key Files
<!-- Add important files discovered during implementation -->

---
```

### run.sh

```bash
#!/bin/bash
set -e

MAX_ITERATIONS=${1:-25}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starting Ralph Loop"
echo "Plan: $SCRIPT_DIR"
echo "Max iterations: $MAX_ITERATIONS"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo ""
  echo "═══════════════════════════════════════"
  echo "  Iteration $i of $MAX_ITERATIONS"
  echo "═══════════════════════════════════════"

  OUTPUT=$(claude -p --dangerously-skip-permissions --verbose < "$SCRIPT_DIR/prompt.md" 2>&1 | tee /dev/stderr) || true

  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo ""
    echo "✅ All features complete!"
    exit 0
  fi

  sleep 2
done

echo ""
echo "⚠️ Max iterations reached ($MAX_ITERATIONS)"
echo "Check progress: cat $SCRIPT_DIR/progress.txt"
exit 1
```

### run-once.sh

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔍 Running single iteration (for testing PRD quality)"
echo "Plan: $SCRIPT_DIR"
echo ""

claude -p --dangerously-skip-permissions --verbose < "$SCRIPT_DIR/prompt.md"

echo ""
echo "Single iteration complete."
echo "Check: $SCRIPT_DIR/prd.json and $SCRIPT_DIR/progress.txt"
```
