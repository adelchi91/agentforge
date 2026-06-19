---
name: bootstrap
description: >
  Scaffold a complete Claude Code or Codex agentic development environment for this project.
  Runs a 6-step interview to generate agents, skills, hooks, stories, and a project constitution.
  Invoke at the start of any new or existing project.
  Triggers on: "bootstrap this project", "set up agentic methodology",
  "scaffold my project", "initialise agentic workflow", "/bootstrap"
context: fork
agent: interviewer
---

## Welcome

When this skill activates, display the following welcome message exactly:

```
── Project Bootstrap ──────────────────────────────────────────────
  project-bootstrap v1.0.0

  I'll scaffold a complete agentic development environment
  for either Claude Code or Codex in 6 steps:

    Step 1 — Reference documents (optional)
    Step 2 — Project context & codebase scan
    Step 3 — Roadmap planning
    Step 4 — Persona definition
    Step 5 — Story generation
    Step 6 — File scaffolding

  Estimated time: 10–15 minutes.
  Nothing is written to disk until Step 6 and you type GO.

  Type OK to begin, or CANCEL to exit.
───────────────────────────────────────────────────────────────────
```

## Orchestration

On `OK`: ask the target platform question before Step 1:

```
Which environment should I scaffold?
  - CLAUDE → generate a Claude Code .claude/ scaffold
  - CODEX  → generate a Codex-native AGENTS.md/.codex/.agents scaffold
```

Accept only `CLAUDE` or `CODEX`. Write the uppercase answer to
`.bootstrap/target_platform.md`, then begin Step 1.

The `interviewer` agent handles platform selection and Steps 1–4.

After Step 4 completes and user types `OK`: the `planner` agent handles Step 5.

After Step 5 completes and user types `OK`: the `scaffolder` agent handles Step 6.

## State Management

All intermediate state is written to `.bootstrap/` (hidden, gitignored):
- `.bootstrap/target_platform.md` — selected output target (`CLAUDE` or `CODEX`)
- `.bootstrap/00_docs.md` — Step 1 output (reference documents summary)
- `.bootstrap/02_context.md` — Step 2 output
- `.bootstrap/03_roadmap.md` — Step 3 output
- `.bootstrap/04_personas.md` — Step 4 output
- `.bootstrap/stories/STORY-XXX.md` — Step 5 output

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

## On CANCEL

At any point, if the user types `CANCEL`: exit cleanly.
Display: "Bootstrap cancelled. No files written."

## Done

After Step 6 completes successfully, the scaffolder agent displays the Done summary.
The bootstrap session is then complete. The user's project is ready to use.
