---
name: bootstrap
description: >
  Scaffold a complete Claude Code or Codex agentic development environment for this project.
  Runs a 6-step interview to generate agents, skills, hooks, stories, and a project constitution.
  Invoke at the start of any new or existing project.
  Triggers on: "bootstrap this project", "set up agentic methodology",
  "scaffold my project", "initialise agentic workflow", "/bootstrap"
---

## Welcome

When this skill activates, display the following welcome message exactly:

```
── Project Bootstrap ──────────────────────────────────────────────
  project-bootstrap v1.1.0

  I'll scaffold a complete agentic development environment
  for either Claude Code or Codex in 6 steps:

    Step 1 — Reference documents (optional)
    Step 2 — Project context & codebase scan
    Step 3 — Roadmap planning
    Step 4 — Persona definition
    Step 5 — Story generation
    Step 6 — File scaffolding

  Estimated time: 10–15 minutes.
  I will stop for your validation after every step.
  Nothing is written to the final scaffold until Step 6 and you type GO.

  Type OK to begin, or CANCEL to exit.
───────────────────────────────────────────────────────────────────
```

## Orchestration

This is an interactive main-session command. Do not run the bootstrap interview in a
backgrounded/forked agent. Do not call the `interviewer`, `planner`, or `scaffolder`
agents as Task/Agent subagents for the user-facing flow. Use their files as role
contracts if useful, but keep the live conversation in the main session so the user can
validate every step.

On `OK`: ask the target platform question before Step 1:

```
Which environment should I scaffold?
  - CLAUDE → generate a Claude Code .claude/ scaffold
  - CODEX  → generate a Codex-native AGENTS.md/.codex/.agents scaffold
```

Accept only `CLAUDE` or `CODEX`. Write the uppercase answer to
`.bootstrap/target_platform.md`, then begin Step 1.

Run Steps 1-6 sequentially in the main session using:
- `steps/01_documents.md`
- `steps/02_context.md`
- `steps/03_roadmap.md`
- `steps/04_personas.md`
- `steps/05_stories.md`
- `steps/06_scaffold.md`

## Resource Resolution

The `steps/`, `templates/`, and `refs/` directories ship alongside this command set.
Resolve them from wherever this command file lives:
- Installed as a Claude Code plugin → `${CLAUDE_PLUGIN_ROOT}/steps/`, `${CLAUDE_PLUGIN_ROOT}/templates/`, `${CLAUDE_PLUGIN_ROOT}/refs/`
- Installed via `install.sh` → `.claude/steps/`, `.claude/templates/`, `.claude/refs/`
- Running from the agentforge repository itself → `steps/`, `templates/`, `refs/` at the repo root

Do not guess alternate locations. If none of these paths exist, stop and report it.

Each step has a validation gate. A user response to one step is not permission to
continue into later steps.

## State Management

All intermediate state is written to `.bootstrap/` (hidden, gitignored):
- `.bootstrap/target_platform.md` — selected output target (`CLAUDE` or `CODEX`)
- `.bootstrap/00_docs.md` — Step 1 output (reference documents summary)
- `.bootstrap/02_context.md` — Step 2 output
- `.bootstrap/03_roadmap.md` — Step 3 output
- `.bootstrap/04_personas.md` — Step 4 output
- `.bootstrap/stories/STORY-XXX.md` — Step 5 output

Do not create alternate state filenames such as `.bootstrap/platform.md`,
`.bootstrap/context.md`, `.bootstrap/roadmap.md`, or `.bootstrap/personas.md`.

Nothing is written to the selected target scaffold (`.claude/` for Claude, or
`AGENTS.md`, `.codex/`, and `.agents/` for Codex) until Step 6 and the user types `GO`.

## Step Transitions

Between every step display:
```
✓ Step X complete. [one-sentence summary of what was decided/saved]

Type OK to continue to Step X+1, or BACK to revisit Step X.
```

`BACK` is supported at every transition. It re-runs the previous step using the
existing `.bootstrap/` file as starting context.

Hard rules:
- Stop after each transition message and wait for the user's next message.
- Only `OK` advances to the next step.
- Only Step 6 accepts `GO`; before Step 6, `GO` is invalid and must be treated as
  a request to clarify the current validation gate.
- Never say "I'll run the full bootstrap" or generate multiple remaining steps in one
  pass.
- If a file cannot be read or written because of permissions, stop and report the
  exact blocker. Do not bypass the workflow by using a different agent, a different
  state filename, or an inferred summary.

## On CANCEL

At any point, if the user types `CANCEL`: exit cleanly.
Display: "Bootstrap cancelled. No files written."

## Done

After Step 6 completes successfully, display the Done summary.
The bootstrap session is then complete. The user's project is ready to use.
