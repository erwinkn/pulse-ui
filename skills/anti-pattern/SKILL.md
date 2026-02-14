---
name: anti-pattern
description: Use when asked to remove an anti-pattern. Enforces: first add a one-line prevention rule to AGENTS.md, then fix the anti-pattern in code.
---

# Anti-Pattern Remediation

Use this skill when the user asks to fix an anti-pattern.

## Required Order

1. Identify the anti-pattern from the user request.
2. Add exactly one concise prevention line to `AGENTS.md` (relevant section).
3. Only after that, implement the code fix.

Do not skip step 2.

## Rule Requirements

- One line only.
- Concrete and enforceable.
- Style-level guidance, not task-specific wording.

## Implementation Requirements

- Apply fixes directly; avoid wrapper-only changes.
- Keep behavior unchanged unless user asks otherwise.
- Add/update tests when behavior or contracts are affected.
- Run validation commands expected by repo policy.

## Output Requirements

- State the new `AGENTS.md` rule.
- State what was fixed and where.
- Call out any remaining follow-up work.
