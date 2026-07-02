# project-bootstrap

## What this is

`project-bootstrap` is a Claude Code command set and Codex bootstrap skill that generates a complete
agentic development environment for any software project in one interview session. It encodes
a proven methodology built around project constitutions, agents, skills, hooks, and stories,
so you can start structured, multi-phase development with human-in-the-loop approval gates
from day one. It works on greenfield projects and existing codebases alike.

## Install

### Claude Code (recommended): plugin install

```
/plugin marketplace add adelchi91/agentforge
/plugin install project-bootstrap@agentforge
```

The plugin bundles the `/bootstrap`, `/story`, `/add-agent`, and `/project-review`
commands, the bootstrap agents, and all templates. Plugin installs are versioned and
update through `/plugin` — no files are copied into your repo until you run `/bootstrap`
and type `GO`.

### Script install (Codex, or Claude without plugins)

```bash
# From your project root — Claude bootstrap into .claude/:
curl -sL https://raw.githubusercontent.com/adelchi91/agentforge/main/install.sh | bash

# Codex skill only:
curl -sL https://raw.githubusercontent.com/adelchi91/agentforge/main/install.sh | bash -s -- codex

# Both Claude and Codex:
curl -sL https://raw.githubusercontent.com/adelchi91/agentforge/main/install.sh | bash -s -- both
```

The Codex install adds a repo-scoped skill at `.agents/skills/project-bootstrap/` with the
same bootstrap resources bundled beside it.

Installation chooses the tool surface you start from. The bootstrap flow itself then asks
which output target to generate, so either surface can scaffold `CLAUDE` or `CODEX`.

## Usage

```bash
# In any Claude Code session, from your project root:
/bootstrap

# In any Codex session, from your project root:
$project-bootstrap
```

Both invocations run the same 6-step flow. At the start, choose `CLAUDE` to generate
a Claude Code `.claude/` scaffold or `CODEX` to generate `AGENTS.md`, `.codex/`,
and `.agents/`.

The 6-step flow:
- **Target selection** — Choose `CLAUDE` or `CODEX` before Step 1
- **Step 1** — Optionally share reference documents (PRD, spec, architecture notes) to seed the session
- **Step 2** — Answer questions about your project and stack; existing codebases are scanned automatically
- **Step 3** — Review and approve a phase-based roadmap (cross-checked against your docs if provided)
- **Step 4** — Review and approve the agent personas (model, scope, tools)
- **Step 5** — Review and approve generated story files (one per unit of work)
- **Step 6** — Type `GO` to generate the selected Claude or Codex scaffold

## What it generates for Claude

```
.claude/
├── CLAUDE.md                  ← project constitution
├── settings.json              ← permissions + hook registration
├── agents/                    ← one .md per persona (aliased models, scoped tools)
├── skills/                    ← knowledge chunks per domain (<domain>/SKILL.md)
├── hooks/
│   ├── pre_tool_use.py        ← blocks destructive commands + enforces agent scopes
│   ├── post_tool_use.py       ← auto-lint on Write/Edit (ruff, eslint)
│   ├── session_start.py       ← injects golden rule + active story
│   ├── user_prompt_submit.py  ← injects story scope when STORY-XXX is mentioned
│   ├── subagent_stop.py       ← handoff-chain audit log
│   ├── pre_compact.py         ← preserves story state across compaction
│   ├── session_end.py         ← session record
│   └── scopes.json            ← agent → allowed-folders map
└── stories/
    └── STORY-XXX.md           ← one per unit of work

project_context.md             ← persisted intake answers
roadmap.md                     ← phase plan
```

## What it generates for Codex

```
AGENTS.md                      ← project constitution
.codex/
├── hooks.json                  ← hook registration
├── agents/                     ← one .toml custom agent per persona
└── hooks/                      ← same shared Python hook suite as the Claude target
    ├── pre_tool_use.py         ← safety guardrails + agent scope enforcement
    ├── post_tool_use.py        ← targeted auto-lint
    ├── session_start.py / user_prompt_submit.py / subagent_stop.py / pre_compact.py
    ├── session_end.py          ← session record (registered on Stop)
    └── scopes.json             ← agent → allowed-folders map

.agents/
├── skills/                     ← knowledge chunks per domain (<domain>/SKILL.md)
└── stories/
    └── STORY-XXX.md            ← one per unit of work

project_context.md             ← persisted intake answers
roadmap.md                     ← phase plan
```

After a Codex scaffold, run `/hooks` in Codex and trust the generated hooks —
Codex does not run untrusted project hooks.

## Sub-commands

```
/bootstrap         → start the 6-step flow from Claude Code; choose CLAUDE or CODEX
$project-bootstrap → start the 6-step flow from Codex; choose CLAUDE or CODEX
/story            → add a story to an existing phase
/add-agent        → add a new agent
/project-review   → update roadmap or personas
```

## Examples

A step-by-step walkthrough of a real session is in [`docs/walkthrough-pycalc.md`](docs/walkthrough-pycalc.md) —
a greenfield Python CLI calculator bootstrapped from an empty directory to 12 stories across 4 phases.

Three reference output examples are also included:

- [`examples/lagrangia/`](examples/lagrangia/) — complex existing codebase: monorepo-to-multirepo
  migration with 5 phases, 7 agents, and 16 stories
- [`examples/minimal/`](examples/minimal/) — simple greenfield: 2-phase Python library with
  3 agents and 4 stories
- [`examples/codex-minimal/`](examples/codex-minimal/) — simple greenfield Codex target:
  `AGENTS.md`, `.codex/agents/*.toml`, `.agents/skills/`, and `.agents/stories/`

## The methodology

The methodology encodes five mechanisms — constitution, skills, hooks, agents, and stories —
each with a specific role and platform-native location. They are non-overlapping by design:
agents never contain knowledge, safety rules never live only in agent instructions, and every
story has runnable verification commands. See
[METHODOLOGY.md](METHODOLOGY.md) for the full reference.

## Contributing

Contributions are welcome. Please open an issue before submitting a PR for significant changes.
All PRs must include a reference story or example demonstrating the behaviour change.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Ensure all examples remain coherent (verify no unfilled template variables remain in `examples/`)
5. Smoke-test installer changes from a temporary project directory with
   `AGENTFORGE_SOURCE_DIR=/path/to/agentforge /path/to/agentforge/install.sh [claude|codex|both]`
6. Submit a pull request

## License

MIT — see [LICENSE](LICENSE).
