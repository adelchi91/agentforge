---
name: bootstrap
description: >
  Scaffold a complete Claude Code agentic development environment for this project.
  Runs a 5-step interview to generate agents, skills, hooks, stories, and CLAUDE.md.
  Invoke at the start of any new or existing project.
  Triggers on: "bootstrap this project", "set up claude methodology",
  "scaffold my project", "initialise agentic workflow", "/bootstrap"
context: fork
agent: interviewer
---

## Welcome

When this skill activates, display the following welcome message exactly:

```
── Project Bootstrap ──────────────────────────────────────────────
  claude-project-bootstrap v1.0.0

  I'll scaffold a complete Claude Code agentic development
  environment for this project in 5 steps:

    Step 1 — Project context & codebase scan
    Step 2 — Roadmap planning
    Step 3 — Persona definition
    Step 4 — Story generation
    Step 5 — File scaffolding

  Estimated time: 10–15 minutes.
  Nothing is written to disk until Step 5 and you type GO.

  Type OK to begin, or CANCEL to exit.
───────────────────────────────────────────────────────────────────
```

## Orchestration

On `OK`: begin Step 1. The `interviewer` agent handles Steps 1–3.

After Step 3 completes and user types `OK`: the `planner` agent handles Step 4.

After Step 4 completes and user types `OK`: the `scaffolder` agent handles Step 5.

## State Management

All intermediate state is written to `.bootstrap/` (hidden, gitignored):
- `.bootstrap/01_context.md` — Step 1 output
- `.bootstrap/02_roadmap.md` — Step 2 output
- `.bootstrap/03_personas.md` — Step 3 output
- `.bootstrap/stories/STORY-XXX.md` — Step 4 output

Nothing is written to `.claude/` until Step 5 and the user types `GO`.

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

After Step 5 completes successfully, the scaffolder agent displays the Done summary.
The bootstrap session is then complete. The user's project is ready to use.
