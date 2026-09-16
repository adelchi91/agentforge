# project-bootstrap

## What this is

`project-bootstrap` is a Claude Code command set and Codex bootstrap skill that generates a complete
agentic development environment for any software project in one interview session. It encodes
a proven methodology built around project constitutions, agents, skills, hooks, and stories,
so you can start structured, multi-phase development with human-in-the-loop approval gates
from day one. It works on greenfield projects and existing codebases alike.

## Install

### Claude Code (recommended): plugin install

Inside a Claude Code session:

```
/plugin marketplace add adelchi91/agentforge
/plugin install agentforge@agentforge
```

Or from the terminal:

```bash
claude plugin marketplace add adelchi91/agentforge
claude plugin install agentforge@agentforge
```

The plugin bundles 4 commands (`/bootstrap`, `/story`, `/add-agent`, `/project-review`),
the 3 bootstrap agents (interviewer, planner, scaffolder), and all templates. It installs
at user scope, so the commands work from any project directory. It adds roughly 550
always-on tokens to each session. No files are copied into your repo until you run
`/bootstrap` and type `GO`.

> **Upgrading from `project-bootstrap`?** The plugin was renamed to `agentforge`
> (see `CHANGELOG.md`). Uninstall the old name and install the new one:
> `claude plugin uninstall project-bootstrap@agentforge && claude plugin install agentforge@agentforge`.
> Everything else — commands, agents, templates — is unchanged.

Managing the plugin:

```bash
# Update to the latest published version
claude plugin marketplace update agentforge
claude plugin update agentforge

# Uninstall (or use the /plugin menu inside a session to disable/uninstall)
claude plugin uninstall agentforge@agentforge
```

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

## Commands

| Command | Usage | When to use it |
|---|---|---|
| `/bootstrap` | `/bootstrap` | Scaffold a new or existing project via the 6-step interview. Gates: `OK` advances a step, `BACK` revisits the previous one, `CANCEL` exits cleanly, and `GO` (valid only at the Step 6 checkpoint) writes the scaffold. Nothing touches your repo before that `GO`. Works from any project directory once the plugin is installed. |
| `/story` | `/story [short description of the work]` | Add a story to an existing bootstrapped project — picks the phase, assigns an agent, numbers it sequentially, and writes it after your `GO`. |
| `/add-agent` | `/add-agent [agent role]` | Add a new agent persona — applies the model routing rules, generates the agent file, and updates `scopes.json` so the scope-enforcement hook covers the new agent. |
| `/project-review` | `/project-review` | Revise the roadmap or the agent personas of an already-bootstrapped project. |
| `$project-bootstrap` | (in Codex) | The Codex skill surface — runs the same 6-step flow with the same gates, and can scaffold either the `CLAUDE` or `CODEX` target. |

## Working a bootstrapped project

Day-2 vocabulary, once the scaffold exists:

- `Work on STORY-XXX.` — the assigned agent implements the story within its declared scope
- `Test STORY-XXX.` — the tester runs the story's verification commands and reports PASS/FAIL
- `Review STORY-XXX.` — the final-judge checks acceptance criteria and approves or rejects

The generated hooks enforce the methodology deterministically, regardless of what any
agent is instructed to do: destructive commands are blocked, every `git commit` and push
must reference a STORY-XXX, and each agent may only Write/Edit inside the folders assigned
to it in `.claude/hooks/scopes.json` (or `.codex/hooks/scopes.json`). On the Codex target,
remember to run `/hooks` and trust the generated hooks first — Codex does not run
untrusted project hooks.

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
