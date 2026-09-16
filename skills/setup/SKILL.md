---
name: setup
description: Configure the AgentForge companion layer in the current repository — committed policy config, constitution pointers, and work-contract rules — without overwriting existing CLAUDE.md, AGENTS.md, settings, or Matt Pocock's setup block. Use when the user asks to "set up AgentForge", "configure AgentForge", "install AgentForge in this project", or runs `/agentforge:setup`.
---

# AgentForge Setup

**Status: placeholder.** This skill is a stub for STORY-002's plugin
skeleton. It does not yet write any configuration.

The full behavior — inspecting `CLAUDE.md`, `AGENTS.md`, `.agentforge/`, and
existing settings/hooks, then proposing a delimited
`<!-- agentforge:start -->` block for one-shot approval — is implemented in
STORY-005 (`docs/plans/agentforge-v2-user-stories.md`).

Until then, if this skill is invoked, tell the user setup is not yet
implemented and point them at the execution plan
(`docs/plans/agentforge-v2-execution-plan.md`) for the target design. Do not
write, edit, or propose edits to any project file from this skill.
