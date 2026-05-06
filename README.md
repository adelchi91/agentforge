# claude-project-bootstrap

## What this is

`claude-project-bootstrap` is a set of Claude Code agents and commands that generates a complete
agentic development environment for any software project in one interview session. It encodes
a proven methodology built around Claude Code's native primitives — agents, commands, hooks,
and stories — so you can start working on structured, multi-phase development
with human-in-the-loop approval gates from day one. It works on greenfield projects
and existing codebases alike.

## Install

```bash
# From your project root:
curl -sL https://raw.githubusercontent.com/adelchi91/agentforge/main/install.sh | bash
```

This copies only the required files (`agents/`, `commands/`, `templates/`, `steps/`, `refs/`) into `.claude/` — nothing else from the repo lands in your project.

## Usage

```bash
# In any Claude Code session, from your project root:
/bootstrap
```

The 5-step flow:
- **Step 1** — Answer questions about your project and stack; existing codebases are scanned automatically
- **Step 2** — Review and approve a phase-based roadmap
- **Step 3** — Review and approve the agent personas (model, scope, tools)
- **Step 4** — Review and approve generated story files (one per unit of work)
- **Step 5** — Type `GO` to generate the complete `.claude/` folder structure

## What it generates

```
.claude/
├── CLAUDE.md                  ← project constitution
├── settings.json              ← agent permissions + hooks
├── agents/                    ← one .md per persona
├── commands/                  ← knowledge chunks per domain
├── hooks/
│   ├── pre-tool-use.sh        ← safety guardrails (blocks destructive commands)
│   ├── post-tool-use.sh       ← auto-lint on Write (ruff, eslint)
│   └── stop.sh                ← session summary on end
└── stories/
    └── STORY-XXX.md           ← one per unit of work

project_context.md             ← persisted intake answers
roadmap.md                     ← phase plan
```

## Sub-commands

```
/bootstrap        → full 5-step initialisation
/story            → add a story to an existing phase
/add-agent        → add a new agent
/project-review   → update roadmap or personas
```

## Examples

Two reference examples are included:

- [`examples/lagrangia/`](examples/lagrangia/) — complex existing codebase: monorepo-to-multirepo
  migration with 5 phases, 7 agents, and 16 stories
- [`examples/minimal/`](examples/minimal/) — simple greenfield: 2-phase Python library with
  3 agents and 4 stories

## The methodology

The methodology encodes five mechanisms — CLAUDE.md (constitution), commands (knowledge), hooks
(guardrails), agents (personas), and stories (work contracts) — each with a specific role and
location. They are non-overlapping by design: agents never contain knowledge, safety rules never
live in agent instructions, and every story has runnable verification commands. See
[METHODOLOGY.md](METHODOLOGY.md) for the full reference.

## Contributing

Contributions are welcome. Please open an issue before submitting a PR for significant changes.
All PRs must include a reference story or example demonstrating the behaviour change.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Ensure all examples remain coherent (verify no unfilled template variables remain in `examples/`)
5. Submit a pull request

## License

MIT — see [LICENSE](LICENSE).
