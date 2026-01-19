
Below is a single Markdown document you can copy/paste.

# Documentation authoring guide for <FRAMEWORK_NAME>

Audience: AI agents and humans writing docs for a Python full-stack framework.

This guide optimizes for:
- **Concise, scannable docs** that answer questions fast.
- **Beginner-friendly onboarding** via gradual exposure of complexity.
- **Accurate, maintainable docs** that stay in sync with the codebase.
- **A warm, respectful tone** without fluff.

---

## Table of contents

- [Goals and non-goals](#goals-and-non-goals)
- [Documentation principles](#documentation-principles)
- [Documentation taxonomy](#documentation-taxonomy)
- [Information architecture](#information-architecture)
- [Progressive disclosure](#progressive-disclosure)
- [House style](#house-style)
- [Page anatomy](#page-anatomy)
- [Templates](#templates)
- [Code and examples standards](#code-and-examples-standards)
- [Reference documentation standards](#reference-documentation-standards)
- [Troubleshooting standards](#troubleshooting-standards)
- [Docs-as-code workflow](#docs-as-code-workflow)
- [AI agent workflow](#ai-agent-workflow)
- [Claude Code and Codex recipes](#claude-code-and-codex-recipes)
- [Definition of done](#definition-of-done)
- [Appendix: recommended starter nav](#appendix-recommended-starter-nav)

---

## Goals and non-goals

### Goals
- Help users **succeed quickly**: first working app in minutes, common tasks in hours.
- Make docs **predictable**: users should know where to look.
- Make docs **trustworthy**: never “sound right” if not verified.
- Make docs **easy to maintain**: small pages, clear ownership, automation where possible.

### Non-goals
- Do not write marketing copy.
- Do not teach general Python, HTTP, SQL, Docker, or JS fundamentals (link out if needed).
- Do not duplicate information that can be generated directly from source (prefer reference autogen + human guide layers).

---

## Documentation principles

1. **User goal first**
   - Start from what the reader is trying to do (ship a feature, fix a bug, learn a concept).

2. **One page, one job**
   - Each page should have a clear purpose (tutorial vs how-to vs reference vs explanation).
   - Avoid mixing “learn” content into “do” content.

3. **Make it skimmable**
   - Readers scan; structure pages so they can pick the right section quickly.
   - Use headings, short paragraphs, lists, and “Expected result” checkpoints.

4. **Show the happy path**
   - Default path works with defaults; advanced customizations come later.

5. **Progressive disclosure**
   - Show only what the user needs right now.
   - Offer optional “Advanced” sections and link to deeper explanations.

6. **Every claim should be grounded**
   - Prefer: code, tests, the actual CLI output, config schema, type hints, docstrings.
   - If you can’t verify, label it clearly as an assumption or add a TODO for validation.

7. **Consistency beats cleverness**
   - Same terms for the same concepts everywhere.
   - Same page structure for the same doc types.

---

## Documentation taxonomy

Use these four doc types. Every page must be exactly one of them.

### Tutorials (learning-oriented)
- Goal: teach by doing, step-by-step.
- Reader: beginner, following a path.
- Style: friendly, guided, minimal choices.
- Must include verification points (“You should now see…”).

### How-to guides (task-oriented)
- Goal: help the reader accomplish a specific task.
- Reader: already building something, needs a result.
- Style: direct steps, minimal explanation.
- Link to conceptual background elsewhere.

### Reference (information-oriented)
- Goal: define the API/CLI/config precisely and completely.
- Reader: competent user needs exact behavior, parameters, defaults, edge cases.
- Style: succinct, structured, no narrative.

### Explanation (understanding-oriented)
- Goal: build the mental model; answer “why” and “how it works”.
- Reader: wants clarity, tradeoffs, design rationale.
- Style: conceptual, structured, diagrams welcome, no step-by-step procedures.

---

## Information architecture

### A simple rule
- **Beginner path**: Quickstart → a guided tutorial → a small set of common how-tos.
- **Builder path**: How-tos and troubleshooting.
- **Power-user path**: Reference and deep explanations.

### Keep navigation shallow
- Prefer a few top-level sections with consistent sub-structure.
- Limit nesting depth (readers get lost).

---

## Progressive disclosure

Use progressive disclosure at three levels:

### 1) Within a page
- Put the “happy path” first.
- Push optional details into:
  - “Advanced” sections
  - collapsible callouts (if your doc system supports them)
  - separate explanation pages linked as “Learn more”

### 2) Across the doc set
- A tutorial shouldn’t branch into 10 alternatives.
- Put alternatives in dedicated how-tos (“Use Postgres”, “Use SQLite”, “Deploy to Fly.io”, etc).

### 3) In examples
- First example: minimal, works end-to-end.
- Second example: adds one new concept.
- Avoid showing every knob in the first snippet.

---

## House style

### Voice and tone
- Warm, respectful, and straightforward.
- Address the reader as **“you”**.
- Prefer active voice and present tense.
- Avoid slang, hype, and jokes that may not translate well.
- Keep confidence proportional to evidence:
  - Verified → assertive.
  - Not verified → explicit uncertainty + TODO.

### Language rules
- Prefer short words, short sentences, and concrete nouns.
- Don’t pre-announce: remove “In this section, we will…”.
- Use consistent terminology:
  - Pick one term per concept and stick with it (e.g., “app” vs “project”; “service” vs “module”).

### Headings and formatting
- Use **sentence case** headings.
- Headings should be unique and descriptive (they’re navigation).
- Keep paragraphs short (2–5 lines).
- Use lists for multiple items; use tables for comparisons.

### Links
- Use descriptive link text:
  - Good: “Authentication middleware”
  - Bad: “click here” / “this”
- Link to:
  - “Next step” pages
  - deeper explanation pages
  - reference entries for APIs used in the page

### Accessibility and inclusion
- Avoid culturally specific references and idioms.
- Use inclusive example names and realistic data.
- Prefer code blocks over screenshots for code, unless the UI is the point.

---

## Page anatomy

### Universal page skeleton (use everywhere)
1. **Title**
2. **What you’ll accomplish / what this is**
   - 1–3 sentences. No fluff.
3. **Prerequisites**
   - Versions, OS notes, accounts needed.
4. **Core content**
   - Tutorial steps OR how-to steps OR reference tables OR explanation sections.
5. **Verification**
   - “Expected output”, “Sanity check”, “Run this command…”
6. **Next steps**
   - 3–6 links max.

### Common anti-patterns to avoid
- Giant page that tries to teach everything.
- A tutorial that becomes a reference manual.
- A how-to full of rationale and history.
- Reference pages with “storytelling”.
- Examples that can’t run as written.

---

## Templates

Use these templates verbatim as a starting point.

### Tutorial template

# <Title: build X with <FRAMEWORK_NAME>>

## What you’ll build
- A <thing> that <does something>.
- You’ll learn: <2–4 bullet points>.

## Prerequisites
- Python >= <x.y>
- <FRAMEWORK_NAME> >= <x.y>
- Optional: <db>, <node>, etc.

## Step 1 — <action>
**Goal:** <what this step achieves>

1. <instruction>
2. <instruction>

**Expected result**
- <what the user should see / files created / output snippet>

## Step 2 — <action>
...

## Step N — <action>
...

## Recap
- You built <x>.
- You learned <y>.

## Next steps
- <Link to a how-to that extends this>
- <Link to reference>
- <Link to explanation/concepts>


### How-to template

# <Title: do X>

## When to use this
Use this guide when you want to <goal>.

## Prerequisites
- <versions, setup>
- <existing tutorial completed?>

## Steps

1. <step>
2. <step>
3. <step>

## Verify it worked
- Run: `<command>`
- Expected: `<output>`

## Common issues
- **Symptom:** <...>
  - **Cause:** <...>
  - **Fix:** <...>

## Related
- <Reference entry>
- <Explanation page>


### Reference template

# <Component/API name>

## Summary
1–2 sentences defining what it is.

## Signature (if applicable)
```python
<signature>
````

## Parameters

| Name | Type | Default | Description |
| ---- | ---- | ------- | ----------- |
| ...  | ...  | ...     | ...         |

## Returns

* <type>: <meaning>

## Raises / errors

* `<Exception>`: when <condition>

## Behavior

* Constraints/invariants
* Side effects
* Threading/async notes
* Performance notes (only if true and relevant)

## Examples

Minimal examples only. Prefer multiple small examples over one huge example.

### Explanation template

# <Concept: why/how it works>

## The problem it solves

* <pain point>
* <goal>

## The model

Explain the components and how they interact.

* Diagram encouraged.

## Key decisions and tradeoffs

* <decision> → <benefit> / <cost>
* Alternatives and when to pick them

## How it shows up in the API

Link to relevant reference entries.

## Common misconceptions

* <myth> → <reality>

### Troubleshooting template

# Troubleshooting <area>

## Quick triage

* If you see <symptom>, try <fast check>.

## Errors

### <Error message>

**Cause**

* <...>

**Fix**

* <...>

**Verify**

* <...>

## Diagnostics commands

* `<command>` — what it checks, what “good” looks like.

---

## Code and examples standards

### Examples must be:

* **Copy/pasteable**
* **Minimal**
* **Correct**
* **Version-aware** (call out when behavior differs by version)

### Prefer “golden path” code

* Use default configuration first.
* Avoid showing 12 configuration options in an introductory guide.

### Always include verification

* After a meaningful step, include a quick check:

  * CLI output
  * a URL to open
  * a request to send
  * a file to inspect

### Use realistic placeholders

* Prefer realistic values over `foo/bar/baz` when it improves comprehension.
* When placeholders are necessary, make them obvious:

  * `<PROJECT_NAME>`
  * `<DATABASE_URL>`
  * `<SECRET_KEY>`

### Explain non-obvious lines

* Either inline comments in code or a short bullet list below the snippet.
* Avoid long prose between steps.

---

## Reference documentation standards

Reference docs are where correctness matters most.

Include:

* Full parameter lists with defaults
* Return types and semantics
* Exceptions and error conditions
* Side effects (I/O, DB writes, network)
* Ordering guarantees, idempotency, concurrency/async semantics

Avoid:

* Tutorials embedded into reference
* Opinions (“best”, “simple”, “easy”) unless justified and scoped

---

## Troubleshooting standards

* Organize by:

  * symptom → cause → fix → verify
* Include exact error messages when possible.
* Prefer actionable steps over generic advice.
* If a fix is destructive (data loss, resets), label it clearly.

---

## Docs-as-code workflow

Treat docs like code:

* Store in version control.
* Review changes via PRs.
* Run checks in CI (links, builds, example validation where possible).

Minimum automation to aim for:

* Markdown lint / formatting
* Link checker
* Docs build validation
* “Snippets compile/run” checks for critical examples

Change discipline:

* If a PR changes behavior, it must change docs **in the same PR** or explicitly declare why not.

---

## AI agent workflow

When an AI agent writes or updates docs, follow this exact process.

### 1) Classify the page

Pick one: tutorial / how-to / reference / explanation.
If the content doesn’t fit, split the page.

### 2) Identify ground truth

Prefer in order:

1. Public APIs, types, and docstrings
2. CLI `--help` output
3. Examples in the repo
4. Tests that demonstrate behavior
5. Runtime output from actually running the code

Never invent flags, config keys, module names, or outputs.

### 3) Draft an outline before writing

* Headings first
* Then fill each section
* Keep each section small

### 4) Validate claims

* Run the example.
* Verify imports, commands, and outputs.
* If you can’t run it, reduce claims and add TODOs.

### 5) Make it navigable

* Add “Next steps” links.
* Link to reference entries for APIs used.

### 6) Keep diffs small

Prefer multiple small docs PRs over a huge rewrite.

### 7) Leave breadcrumbs for maintainers

At the bottom of the PR description (or in a short note), include:

* What you verified (commands run)
* What you didn’t verify (and why)
* Any open questions or TODOs

---

## Claude Code and Codex recipes

Goal: make the doc-writing behavior repeatable by encoding it in agent instruction files and reusable prompts.

### Single source of truth: AGENTS.md + CLAUDE.md

* Put durable project instructions in `AGENTS.md`.
* For Claude Code, have `CLAUDE.md` include the same content (or reference it) so both tools follow the same rules.

### Claude Code: recommended setup

#### 1) Create/maintain `CLAUDE.md`

Include:

* “How to build and test”
* key repo paths
* doc style rules (or a pointer to this document)

Keep it concise.

#### 2) Project slash commands (`.claude/commands/`)

Create commands that run the same workflow every time.

Suggested commands:

* `/doc-outline <topic>`
* `/doc-draft <doc-type> <topic>`
* `/doc-review <path>`
* `/doc-verify <path>` (runs local checks if configured)

#### 3) Agent Skills (`.claude/skills/<skill>/SKILL.md`)

Create a “docs-author” Skill that encodes this guide as enforceable rules.

Suggested skills:

* `docs-author` (writes pages using templates + style)
* `docs-linter` (checks for taxonomy violations, vague headings, missing verification)
* `docs-linker` (adds Next steps, See also, reference links)

#### 4) Subagents (`.claude/agents/`)

Create specialized subagents with limited tool permissions.

Suggested subagents:

* `doc-planner` (Read-only tools; outputs outlines and nav placement)
* `doc-writer` (Read + Write; drafts content)
* `doc-reviewer` (Read-only; checks tone, clarity, correctness)
* `example-runner` (Bash only; runs snippet verification commands)

Make tool access restrictive by default; widen only when needed.

---

### Codex: recommended setup

#### 1) Create/maintain `AGENTS.md`

Include:

* build/test commands
* “how we write docs”
* style rules and templates
* “never invent behavior”

Consider nested `AGENTS.md` files in subdirectories if different modules differ.

#### 2) Use `/init` early

Have Codex scaffold `AGENTS.md`, then replace the scaffold with your real rules.

#### 3) Custom prompts (`~/.codex/prompts/`)

Use prompts for your personal workflow (not shared in repo).

Suggested prompts:

* `/prompts:doc-outline TOPIC="..." TYPE=tutorial|howto|reference|explanation`
* `/prompts:doc-review FILES="docs/..."`

#### 4) Repo skills (`.codex/skills/`)

Use skills when you want repo-shared behavior.

Suggested skills:

* `docs-author` (instruction-only; enforces templates + tone)
* `docs-verify` (script-backed; runs doc build/link checks)
* `release-notes-writer` (summarizes changes from git log + PR titles)

---

## Definition of done

A docs change is “done” only if:

### Structure

* [ ] Page is clearly one doc type (tutorial/how-to/reference/explanation)
* [ ] Title is descriptive and sentence case
* [ ] Headings are unique and scannable
* [ ] Includes prerequisites (when relevant)
* [ ] Includes verification (“Expected result” / “Verify it worked”)
* [ ] Includes “Next steps” links

### Content quality

* [ ] No invented APIs/flags/outputs
* [ ] Terminology matches the rest of the docs
* [ ] No pre-announcements (“In this section…”)
* [ ] Minimal but sufficient explanation (especially in how-tos)
* [ ] Advanced content is clearly separated (progressive disclosure)

### Accuracy

* [ ] Examples run as written OR are explicitly marked unverified with TODO
* [ ] Commands are correct for the stated OS/shell (or clearly scoped)
* [ ] Version differences are called out (if relevant)

### Maintenance

* [ ] Links valid
* [ ] Docs build passes (if applicable)
* [ ] Change is located where users will look for it (nav placement makes sense)

---

## Appendix: recommended starter nav

Use this as a default if you don’t already have a structure.

* **Getting started**

  * Installation
  * Quickstart: first app
  * Project layout
* **Tutorials**

  * Build a small full-stack app end-to-end
* **How-to guides**

  * Routing
  * Templates/UI integration
  * Database + migrations
  * Auth + sessions
  * Background jobs / queues
  * Caching
  * Testing
  * Observability (logs/metrics/tracing)
  * Deployment (common targets)
* **Reference**

  * CLI
  * Configuration
  * Python API reference
  * Frontend integration points
* **Explanation**

  * Architecture overview
  * Request lifecycle
  * State management model
  * Security model and boundaries
* **Troubleshooting**

  * Common errors
  * FAQ
* **Release notes**
* **Contributing**
* **Glossary**
