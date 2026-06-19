# Model Routing Rules

Read `.bootstrap/target_platform.md` before assigning models.

## Claude target

Use `claude-sonnet-4-6` when:
- The task requires architectural judgment
- The agent writes ADRs, design decisions, or stories
- The agent is the final-judge (approval authority)
- The task involves ambiguous requirements that need reasoning

Use `claude-haiku-4-5-20251001` when:
- The task is deterministic and templated
- The agent runs commands and reads output
- The agent migrates, copies, or restructures files mechanically
- The agent writes PASS/FAIL reports from command output

## Codex target

Use `gpt-5.5` with `model_reasoning_effort = "high"` when:
- The task requires architectural judgment
- The agent writes ADRs, design decisions, or stories
- The agent is the final-judge (approval authority)
- The task involves ambiguous requirements that need reasoning

Use `gpt-5.4-mini` with `model_reasoning_effort = "low"` or `"medium"` when:
- The task is deterministic and templated
- The agent runs commands and reads output
- The agent migrates, copies, or restructures files mechanically
- The agent writes PASS/FAIL reports from command output

Set `sandbox_mode = "read-only"` for reviewers, testers, and final approval agents.
Set `sandbox_mode = "workspace-write"` for implementation or migration agents.

## Built-in agents (use as-is, do not redefine):

Claude:
- Explore → Haiku, read-only, codebase traversal
- Plan    → inherits from main conversation, read-only

Codex:
- explorer → read-heavy codebase traversal
- worker   → implementation-focused work
- default  → general-purpose fallback
