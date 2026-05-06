---
name: add-agent
description: >
  Add a new agent to an existing bootstrapped project.
  Triggers on: "add an agent", "new agent", "create an agent", "I need a new agent",
  "/add-agent"
agent: scaffolder
---

## Purpose

Add a new agent to `.claude/agents/` without re-running the full bootstrap.
Use this when a new technical domain is identified or the user requests a specialised persona.

## Procedure

1. Read all existing agents from `.claude/agents/` (list name, model, scope for each)
2. Ask: "What is this agent's role? (one sentence describing what it does)"
3. Ask: "Which folders may it touch? (comma-separated paths, or 'full repo' for read-only)"
4. Ask: "Does this agent make architectural decisions, or does it execute deterministic tasks?"
   - Architectural decisions / judgment calls → `claude-sonnet-4-6`
   - Deterministic execution / templated work → `claude-haiku-4-5-20251001`
5. Apply model routing from `.claude/refs/model_routing.md`
6. Determine a unique color (check `.claude/agents/` for colors already in use)
7. Generate the agent file from `.claude/templates/agent.md` — fill ALL template variable fields
8. Show the complete agent file and ask:

```
Write to .claude/agents/NAME.md? [GO / CANCEL]
```

## On GO

1. Write the agent file to `.claude/agents/NAME.md`
2. If the agent requires tool permissions not already in `settings.json`, show the diff
   and ask: "Update .claude/settings.json to add these permissions? [Y/N]"
3. Display:
```
✓ agents/NAME.md written
[✓ settings.json updated — if applicable]
```

## On CANCEL

Display: "No agent written." and exit cleanly.

## Rules

- Never duplicate an existing agent name — check `.claude/agents/` first
- Color must be unique among existing agents
- No template variable may remain unfilled in the generated file
- The agent file must follow the agent template structure exactly
- Agent files must NOT contain knowledge (commands, templates, reference docs) — those go in skills
