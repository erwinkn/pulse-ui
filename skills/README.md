# Pulse Skills

AI coding assistant skills for Pulse development. These files help AI tools understand Pulse conventions and generate correct code.

## Available Skills

| Skill | Description |
|-------|-------------|
| [pulse](./pulse/SKILL.md) | Complete Pulse framework reference with reactive state, components, routing, queries, channels, and JS interop |
| [pulse-mantine](./pulse-mantine/SKILL.md) | Mantine UI components for Pulse |
| [anti-pattern](./anti-pattern/SKILL.md) | Enforces anti-pattern workflow: add one-line prevention rule to AGENTS.md first, then implement the fix |

### Pulse Skill Structure

The main `pulse` skill includes detailed reference documentation:

```
pulse/
├── SKILL.md                    # Core framework reference (~4k words)
└── references/
    ├── reactive.md             # Signal, Computed, Effect, containers
    ├── queries.md              # Query, mutation, infinite queries
    ├── channels.md             # Real-time bidirectional communication
    ├── middleware.md           # Request middleware, auth patterns
    ├── js-interop.md           # React components, JS execution
    └── dom.md                  # HTML elements and events
```

## Installation

### Claude Code

Add skills to your `CLAUDE.md`:

```markdown
# Skills

Include these skills for Pulse development:
- https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse/SKILL.md
- https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse-mantine/SKILL.md
```

Or copy the SKILL.md contents directly into your `CLAUDE.md`.

For advanced topics, also include reference files:
```markdown
- https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse/references/reactive.md
- https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse/references/queries.md
- https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse/references/channels.md
```

### Codex CLI

Add to your `AGENTS.md` or `codex.md`:

```markdown
# Skills

Include these skills:
@import https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse/SKILL.md
@import https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse-mantine/SKILL.md
```

### Cursor

Add to `.cursorrules`:

```text
# Pulse Framework Skills

[Paste contents of pulse/SKILL.md here]

# Pulse Mantine Skills

[Paste contents of pulse-mantine/SKILL.md here]
```

### OpenCode

Add to `~/.opencode/agents.md` or project-level `AGENTS.md`:

```markdown
# Skills

Include these skills for Pulse development:
@import skills/pulse/SKILL.md
@import skills/pulse-mantine/SKILL.md
```

### Other Tools

Most AI coding assistants support context files. Copy the contents of relevant SKILL.md files into your tool's context configuration:

- **Windsurf**: Add to `.windsurfrules`
- **Aider**: Add to `.aider.conf.yml` under `read`
- **Continue**: Add to `.continuerc.json` context

## Creating Custom Skills

To create project-specific skills:

1. Create a `skills/` folder in your repo
2. Add `SKILL.md` files for each skill area
3. Reference them in your AI tool's config

Example structure:
```
your-project/
├── skills/
│   ├── README.md
│   └── my-domain/
│       ├── SKILL.md
│       └── references/
│           └── api.md
├── CLAUDE.md (or AGENTS.md)
└── ...
```
