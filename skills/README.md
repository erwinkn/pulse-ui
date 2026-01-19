# Pulse Skills

AI coding assistant skills for Pulse development. These files help AI tools understand Pulse conventions and generate correct code.

## Available Skills

| Skill | Description |
|-------|-------------|
| [pulse-framework](./pulse-framework/SKILL.md) | Core Pulse framework patterns and APIs |
| [pulse-mantine](./pulse-mantine/SKILL.md) | Mantine UI components for Pulse |

## Installation

### Claude Code

Add skills to your `CLAUDE.md`:

```markdown
# Skills

Include these skills for Pulse development:
- https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse-framework/SKILL.md
- https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse-mantine/SKILL.md
```

Or copy the SKILL.md contents directly into your `CLAUDE.md`.

### Codex CLI

Add to your `AGENTS.md` or `codex.md`:

```markdown
# Skills

Include these skills:
@import https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse-framework/SKILL.md
@import https://raw.githubusercontent.com/pulsehq/pulse/main/skills/pulse-mantine/SKILL.md
```

### Cursor

Add to `.cursorrules`:

```text
# Pulse Framework Skills

[Paste contents of pulse-framework/SKILL.md here]

# Pulse Mantine Skills

[Paste contents of pulse-mantine/SKILL.md here]
```

### OpenCode

Add to `~/.opencode/agents.md` or project-level `AGENTS.md`:

```markdown
# Skills

Include these skills for Pulse development:
@import skills/pulse-framework/SKILL.md
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
│       └── SKILL.md
├── CLAUDE.md (or AGENTS.md)
└── ...
```
