---
name: prepare-work
description: Resolve a configured work item, validate its blockers are closed, and snapshot it to local active-work state so lifecycle hooks can restore scope and verification commands without network access. Use when the user asks to "prepare work on", "start work item", "start ticket", or runs `/agentforge:prepare-work <id>`.
---

# AgentForge Prepare Work

**Status: placeholder.** This skill is a stub for STORY-002's plugin
skeleton. It does not yet resolve work items or write any state.

The full behavior — resolving the canonical work item via
`${CLAUDE_PLUGIN_ROOT}/scripts/work_items.py`, checking blockers, and writing
the bounded snapshot to `.agentforge/active-work.json` — is implemented in
STORY-006 through STORY-008 (`docs/plans/agentforge-v2-user-stories.md`).

Until then, if this skill is invoked, tell the user prepare-work is not yet
implemented and point them at the execution plan
(`docs/plans/agentforge-v2-execution-plan.md`) for the target design. Do not
write any file from this skill.
