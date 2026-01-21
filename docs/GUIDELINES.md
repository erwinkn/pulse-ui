# Documentation style guide

How we write docs for Pulse. Friendly, practical, and focused on helping Python developers ship.

---

## Core principles

**Help people succeed.** Every page should get someone unstuck or teach them something useful.

**One page, one job.** Don't mix learning content with reference content. Keep pages focused.

**Show the happy path first.** Start with what works out of the box. Advanced stuff comes later.

**Make it skimmable.** People scan. Use headings, short paragraphs, and lists.

**Ground every claim.** Don't invent APIs, flags, or outputs. If you can't verify something, say so.

---

## The four doc types

Every page is exactly one of these:

### Tutorials
Teach by doing. Walk someone through building something step-by-step.
- For beginners following along
- Friendly, guided, minimal choices
- Always include "you should now see..." checkpoints

### How-to guides
Help someone accomplish a specific task.
- For builders who need a result
- Direct steps, minimal explanation
- Link to concepts elsewhere

### Reference
Define APIs precisely and completely.
- For experienced users who need exact details
- Parameters, return types, errors, edge cases
- No narrative, no opinions

### Explanation
Build mental models. Answer "why" and "how it works."
- For people who want deeper understanding
- Diagrams welcome, tradeoffs included
- No step-by-step procedures

---

## Writing style

**Be conversational.** Write like you're explaining to a friend. "Good news:", "Just do this:", "This is advanced—if you use it often, consider restructuring." These interjections feel human.

**Talk to "you."** Active voice, present tense. Skip corporate filler like "In this section, we will..."

**Code first, explain after.** Show the code, then add "Let's break this down:" or "Here's what's happening:" Don't front-load theory.

**Show the wrong way too.** When there's a common mistake, show both ✅ and ❌ patterns. "You don't need this... just do this."

**Stay consistent.** Same terms everywhere: "component" not "widget", "state" not "data model", `ps.` prefix always.

**Sentence case headings.** Descriptive and scannable—they're navigation.

---

## Pulse conventions

When writing about Pulse code:

- Always use `ps.` prefix: `ps.div()`, `ps.component`, `ps.State`
- Show the `@ps.component` decorator in component examples
- State classes inherit from `ps.State` with typed fields
- Use `ps.init()` context manager for preserved state
- Keep examples runnable—import what you use

For concepts, simple ASCII diagrams work well:
```
State -> Render -> User interaction -> State update -> Re-render -> ...
```

---

## Page structure

Every page should have:

1. **Title** — Clear and descriptive
2. **Opening line** — 1-2 sentences saying what this is and why it matters
3. **Prerequisites** — If needed (versions, setup, prior knowledge)
4. **Content** — Code examples with explanations
5. **See also** — 3-5 links to related pages (tutorials, concepts, reference)

Use `<Callout type="warn">` for important warnings or early-access notices.

---

## Code examples

**Copy-pasteable.** Examples should work when copied.

**Minimal.** Show the smallest thing that works. Don't dump every config option.

**Verified.** Run your examples. If you can't, mark them as unverified.

**Include checks.** After meaningful steps, show what success looks like:
- CLI output
- A URL to open
- A file to inspect

Use realistic placeholders when needed: `<PROJECT_NAME>`, `<DATABASE_URL>`

---

## Progressive disclosure

Show only what's needed right now. Push optional details into:
- "Advanced" sections at the bottom
- Collapsible callouts
- Separate pages linked as "Learn more"

In examples: first snippet is minimal and works end-to-end. Second adds one concept. Don't show every knob upfront.

---

## For AI agents

When writing or updating docs:

1. **Pick one doc type** and stick to it. If content doesn't fit, split the page.
2. **Check the source.** Look at actual APIs, types, docstrings, and `examples/` before writing.
3. **Run your examples.** If you can't verify something works, mark it as unverified.
4. **Match the existing tone.** Read a few pages in `docs/content/` first—be that friendly.
5. **Update the glossary** if you introduce new terms (`docs/content/docs/(core)/glossary.mdx`).

---

## Quick checklist

- [ ] Page is one doc type (tutorial / how-to / reference / explanation)
- [ ] Has a clear opening line
- [ ] Code examples work when copied
- [ ] Shows what success looks like
- [ ] Has "See also" links
- [ ] Uses correct Pulse conventions (`ps.`, `@ps.component`, etc.)
