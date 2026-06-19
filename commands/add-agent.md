---
name: add-agent
description: >
  Add a new agent to an existing bootstrapped project.
  Triggers on: "add an agent", "new agent", "create an agent", "I need a new agent",
  "/add-agent"
agent: scaffolder
---

## Purpose

Add a new agent without re-running the full bootstrap.
Use this when a new technical domain is identified or the user requests a specialised persona.

## Procedure

1. Detect the scaffold target:
   - Claude if `.claude/CLAUDE.md` exists
   - Codex if `AGENTS.md` and `.codex/agents/` exist
2. Read all existing agents from `.claude/agents/` or `.codex/agents/` (list name, model, scope for each)
3. Ask: "What is this agent's role? (one sentence describing what it does)"
4. Ask: "Which folders may it touch? (comma-separated paths, or 'full repo' for read-only)"
5. Ask: "Does this agent make architectural decisions, or does it execute deterministic tasks?"
   - Claude architectural decisions / judgment calls → `claude-sonnet-4-6`
   - Claude deterministic execution / templated work → `claude-haiku-4-5-20251001`
   - Codex architectural decisions / judgment calls → `gpt-5.5`, reasoning `high`
   - Codex deterministic execution / templated work → `gpt-5.4-mini`, reasoning `low` or `medium`
6. Apply model routing from the installed refs/model_routing.md
7. For Codex, set `sandbox_mode = "read-only"` for reviewer/tester/final-judge style agents and `sandbox_mode = "workspace-write"` for implementation agents.
8. For Claude, determine a unique color by checking `.claude/agents/` for colors already in use. For Codex, do not add a color field unless the Codex template defines one.
9. Generate the agent file from `templates/claude/agent.md` or `templates/codex/agent.toml` — fill ALL template variable fields
10. Show the complete agent file and ask:

```
Write to [agent directory]/NAME.[md or toml]? [GO / CANCEL]
```

## On GO

1. Write the agent file to `.claude/agents/NAME.md` for Claude or `.codex/agents/NAME.toml` for Codex
2. If a Claude agent requires tool permissions not already in `settings.json`, show the diff
   and ask: "Update .claude/settings.json to add these permissions? [Y/N]"
3. Display:
```
✓ agent written
[✓ settings.json updated — if applicable]
```

## On CANCEL

Display: "No agent written." and exit cleanly.

## Rules

- Never duplicate an existing agent name in the selected platform's agent directory
- Claude agent colors must be unique among existing Claude agents
- No template variable may remain unfilled in the generated file
- The agent file must follow the selected platform template structure exactly
- Agent files must NOT contain knowledge (commands, templates, reference docs) — those go in skills
