# project-bootstrap

> **v2 status:** a companion governance layer (setup, prepare-work,
> work-contract, reconcile-docs, migration-safety, Git-level traceability,
> graded scope policies, tested Codex parity) has been added alongside
> the interview-based flow described below, and is **not yet declared
> stable** — see [`docs/release-v2.md`](docs/release-v2.md) for
> installation, coexistence, upgrade/uninstall/rollback, the assurance
> and compatibility matrices, and exactly what is still outstanding
> (a real-project pilot) before that changes.

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
> (see `CHANGELOG.md`). The marketplace's `renames` entry is discovery metadata
> only — it does not migrate an existing install automatically (tested in
> STORY-003; see `docs/compatibility.md`). Migrate in this order, which leaves
> no duplicate or orphaned install:
> ```bash
> claude plugin uninstall project-bootstrap@agentforge -y
> claude plugin marketplace update agentforge
> claude plugin install agentforge@agentforge -y
> ```
> Everything else — commands, agents, templates — is unchanged.

Managing the plugin:

```bash
# Update to the latest published version
claude plugin marketplace update agentforge
claude plugin update agentforge

# Uninstall (or use the /plugin menu inside a session to disable/uninstall)
claude plugin uninstall agentforge@agentforge
```

### Using AgentForge alongside mattpocock-skills

AgentForge v2 is a thin governance companion to
[Matt Pocock's engineering skills](https://github.com/mattpocock/skills)
(grilling, spec/ticket flows, TDD, code review, and more) — see
`docs/adr/0001-companion-not-fork.md`. It never vendors or forks his
plugin. Install both as two independent steps:

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install mattpocock-skills@claude-plugins-official --scope user

claude plugin marketplace add adelchi91/agentforge
claude plugin install agentforge@agentforge --scope user
```

Order doesn't matter, and each plugin can be uninstalled, updated, or
reinstalled independently — AgentForge's manifest declares no dependency
on `mattpocock-skills`. `docs/compatibility.md` records the empirical
testing behind that decision (cross-marketplace dependency resolution was
tried and found unreliable) and the full 8-scenario coexistence test
matrix.

Then, inside your project, run:

```
/agentforge:setup
```

This plans a small, delimited pointer block in your `CLAUDE.md`/`AGENTS.md`
plus a committed `.agentforge/config.json`, shows you the exact diff, and
writes nothing until you approve it. If `mattpocock-skills` isn't detected
as installed and enabled, it prints the install command above and stops —
it never scaffolds around a missing companion plugin.

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

## Using AgentForge v2 with Matt's skills

AgentForge and `mattpocock-skills` split the work cleanly, so you only
ever need one command surface for a given concern:

| | Owns |
|---|---|
| **`mattpocock-skills`** | clarification/grilling, specs, ticket decomposition, TDD, bug diagnosis, code review, architecture, research, prototypes |
| **AgentForge** | project setup, work-contract quality, active-work context that survives a restart/compaction, Git-level commit/push traceability, graded scope guardrails, migration safety |
| **Git/CI/branch protection** | merge authorization, immutable history, code quality gates |

AgentForge never wraps or renames Matt's commands — call his skills
directly. The recommended flow for a piece of work, once both plugins are
installed and `/agentforge:setup` has run once:

```
/mattpocock-skills:grill-with-docs      # sharpen the plan/design (optional for small tasks)
          ↓
/mattpocock-skills:to-spec              # turn the conversation into a spec
          ↓
/mattpocock-skills:to-tickets           # break the spec into tracer-bullet tickets
          ↓
/agentforge:prepare-work <ticket-id>    # resolve the ticket, check blockers/contract, snapshot active work
          ↓
/mattpocock-skills:implement            # implement against the snapshotted contract
          ↓
/mattpocock-skills:code-review          # two-axis review: standards + spec
          ↓
git commit / push                       # enforced by AgentForge's commit-msg + pre-push hooks
```

For a small task, skip the grill/spec/tickets steps and just run
`/agentforge:prepare-work <id>` — it accepts or creates one local work
contract directly (`templates/local-work-item.md`) rather than requiring
the full spec/ticket ceremony.

`/agentforge:prepare-work` is what makes this durable: it snapshots the
ticket's identity, scope, exclusions, and verification commands to
`.agentforge/active-work.json` (gitignored, never the network), and a
lifecycle hook restores that same context automatically after a session
restart, `/clear`, or a context compaction — so a long `implement` session
never silently loses track of what it was allowed to touch or how to
verify it.

See [`docs/release-v2.md`](docs/release-v2.md) for the full picture:
installation, upgrade/uninstall/rollback, the assurance-mode table (what
each scope-policy setting actually enforces versus merely observes), the
compatibility matrix, and exactly what's still outstanding before v2 is
declared stable.

## Migrating an existing v1 project to v2

If a project already has a v1 `project-bootstrap` scaffold (`.claude/`
and/or `.codex/` from the original 6-step interview) and you want to
bring it to the v2 companion layer instead of starting fresh, use
`/agentforge:migrate-v1`. It never deletes a v1 file — superseded
content moves to a timestamped
`.agentforge/migration-archive/<timestamp>/`, and every applied
migration comes with exact rollback steps. Full detail:
[`docs/migration-v1-to-v2.md`](docs/migration-v1-to-v2.md) and
`skills/migrate-v1/SKILL.md`.

```bash
# 1. Dry run — writes nothing, prints a full classification report
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_v1.py plan --project-root .

# 2. Review the report: every v1 artifact is classified as retained /
#    transformed / archived / manual_review / obsolete, with a reason.
#    Read every warning, especially anything about v1's Bash-blocking
#    hooks never being a real security boundary — v2 starts scope.mode
#    at "observe" after migration for exactly that reason.

# 3. Apply, once you approve the plan_id from step 1
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_v1.py apply --project-root . \
  --approved-plan-id <plan_id> [--v2-hooks-validated]

# 4. Rollback, if needed — restores every file to its exact
#    pre-migration state and moves archived files back
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_v1.py rollback --project-root . \
  --timestamp <timestamp-from-the-archive-directory-name>
```

Pass `--v2-hooks-validated` in step 3 only once AgentForge v2 is
confirmed installed and enabled for the project (`claude plugin list`)
— otherwise the v1 hooks stay registered rather than leaving the
project with neither the old nor the new one active. A v1 story tracked
on a remote issue tracker (GitHub/GitLab) is reported as
`manual_review` rather than auto-converted — AgentForge's tracker
adapters are fetch-only. Re-running `plan` after a completed migration
reports `"no_change"` — the migration is idempotent.

## Temporary: connecting Jira via the Atlassian MCP connector

> **Status: temporary, pilot-specific.** This section exists to support
> the AgentForge v2 pilot (`docs/pilot-report-template.md`) while a work
> item needs real Jira tickets. It documents a manual bridge, not a
> supported AgentForge feature — remove or replace it once the pilot
> concludes and its findings inform a real design.

Neither Matt Pocock's `to-tickets` skill nor AgentForge's own
`/agentforge:prepare-work` has a native Jira integration:

- `to-tickets`'s setup skill (`setup-matt-pocock-skills`) offers "Other
  (Jira, Linear, etc.)" as a tracker option, but only records your
  described workflow as freeform prose in `docs/agents/issue-tracker.md`
  — there's no bundled Jira API/CLI wrapper the way there is for GitHub
  (`gh`) or GitLab (`glab`).
- AgentForge's own tracker adapters (`scripts/work_items.py`, STORY-006)
  only implement `local`, `github`, and `gitlab` — no `jira` provider
  exists, so `/agentforge:prepare-work` cannot resolve a Jira ticket by
  ID.

Instead, a separate `claude.ai Atlassian` MCP connector may be available
in your Claude Code environment, independent of either plugin:

1. Run `/mcp` inside a Claude Code session and select **"claude.ai
   Atlassian"** to start the OAuth flow.
2. Approve the authorization request in your browser against your work
   account.
3. Once authenticated, real Jira tools (search, create issue, etc.)
   become available to Claude directly in that session.

This is a **manual bridge**, not an automated pipeline: `to-tickets`
still produces the ticket breakdown as usual, and Claude then creates
the corresponding Jira issues one at a time using the authenticated
Atlassian tools, rather than either skill doing it end-to-end on its
own.

**Not yet verified**: whether the connected Atlassian account actually
resolves to your company's specific Jira instance — that depends on
what's linked to your account. Confirm with one test ticket before
relying on it for real pilot work items.

## Usage: the v1 bootstrap interview

The original `project-bootstrap` flow, unchanged and still supported
alongside AgentForge v2 above — use it when you want the full generated
scaffold (constitution, personas, hooks, stories) from a structured
interview rather than v2's lighter companion layer.

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
│   ├── post_tool_use.py       ← off by default; reports (never mutates) ruff/eslint findings on Write/Edit/MultiEdit only when `.agentforge/config.json`'s `quality.post_edit` is `"report"`
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
    ├── post_tool_use.py        ← off by default; reports (never mutates) ruff/eslint findings when opted in
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
