# Model Routing Rules

## Use claude-sonnet-4-6 when:
- The task requires architectural judgment
- The agent writes ADRs, design decisions, or stories
- The agent is the final-judge (approval authority)
- The task involves ambiguous requirements that need reasoning

## Use claude-haiku-4-5-20251001 when:
- The task is deterministic and templated
- The agent runs commands and reads output
- The agent migrates, copies, or restructures files mechanically
- The agent writes PASS/FAIL reports from command output

## Built-in agents (use as-is, do not redefine):
- Explore → Haiku, read-only, codebase traversal
- Plan    → inherits from main conversation, read-only
