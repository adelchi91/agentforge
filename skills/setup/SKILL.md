---
name: setup
description: Configure the AgentForge companion layer in the current repository — committed policy config, constitution pointers, and work-contract rules — without overwriting existing CLAUDE.md, AGENTS.md, settings, or Matt Pocock's setup block. Use when the user asks to "set up AgentForge", "configure AgentForge", "install AgentForge in this project", or runs `/agentforge:setup`.
---

# AgentForge Setup

**Status: placeholder, plus one implemented check.** This skill is a stub
for STORY-002's plugin skeleton and does not yet write any project
configuration. STORY-003 adds exactly one piece of real behavior: checking
whether `mattpocock-skills` is installed and telling the user how to get it
if not, before falling through to the placeholder message below. AgentForge
declares no plugin manifest dependency on `mattpocock-skills` — cross-marketplace
dependency resolution was tested and found unreliable; see
`docs/compatibility.md` for the evidence — so this check is the whole of
that fallback.

## Step 1: check for mattpocock-skills

Run `claude plugin list` (plain text is fine; no flags needed). Look for an
entry whose plugin id starts with `mattpocock-skills@` and whose status is
enabled.

- **If it is present and enabled:** continue to "Step 2" below.
- **If it is missing, disabled, or `claude plugin list` reports no plugins
  installed:** tell the user AgentForge works best alongside Matt Pocock's
  engineering skills and that it isn't installed yet. Print this exact
  install command:

  ```bash
  claude plugin marketplace add anthropics/claude-plugins-official
  claude plugin install mattpocock-skills@claude-plugins-official --scope user
  ```

  Then **stop** — do not write, edit, or propose edits to any project file.
  AgentForge setup still requires the user to re-run `/agentforge:setup`
  after installing Matt's plugin, once STORY-005 implements the rest of
  this skill; today there is nothing further to do either way (see Step 2).

## Step 2: placeholder for the rest of setup

The full behavior — inspecting `CLAUDE.md`, `AGENTS.md`, `.agentforge/`, and
existing settings/hooks, then proposing a delimited
`<!-- agentforge:start -->` block for one-shot approval — is implemented in
STORY-005 (`docs/plans/agentforge-v2-user-stories.md`).

Until then, if this skill reaches this step (mattpocock-skills is already
installed, or the user chooses to continue without it), tell the user setup
is not yet implemented and point them at the execution plan
(`docs/plans/agentforge-v2-execution-plan.md`) for the target design. Do not
write, edit, or propose edits to any project file from this skill.
