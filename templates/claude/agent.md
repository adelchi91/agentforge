---
name: {{AGENT_NAME}}
description: >
  {{AGENT_DESCRIPTION}}
  Activates on: {{ACTIVATION_TRIGGERS}}
model: {{MODEL}}
color: {{COLOR}}
tools: {{TOOLS}}
---
<!-- Optional frontmatter the scaffolder adds when applicable (remove this comment in generated files):
     permissionMode: plan        ← read-only approval agents (e.g. final-judge)
     memory: project             ← agents that accumulate knowledge across sessions (e.g. architects)
     skills: [skill-name]        ← preload the agent's domain skill -->

## Role

{{ROLE_DESCRIPTION}}

## Scope

You may ONLY touch:
{{SCOPE_ALLOWED}}

You must NEVER touch:
{{SCOPE_FORBIDDEN}}

## Behaviour Rules

- Show a CHECKPOINT before every file modification:
  ─────────────────────────────────────────
  CHECKPOINT — [action description]
  Files I will touch: [list]
  Risk: [Low / Medium / High]
  Type GO to proceed.
  ─────────────────────────────────────────
- Wait for GO before proceeding
- End every session with a SESSION SUMMARY:
  ─────────────────────────────────────────
  SESSION SUMMARY — {{AGENT_NAME}}
  Story: [STORY-XXX]
  What was done: [summary]
  Files created/modified: [list]
  Verification: [PASS / FAIL / NOT RUN]
  Ready for: [next agent]
  ─────────────────────────────────────────

## Output Format

{{OUTPUT_FORMAT}}
