# Model Routing Rules

Read `.bootstrap/target_platform.md` before assigning models.

## Claude target

Use **aliases**, not pinned model IDs. Aliases (`opus`, `sonnet`, `haiku`, `fable`,
`inherit`) always resolve to the current model in that tier, so generated projects
do not go stale when the model lineup changes. Pin a full ID only when the user
explicitly asks for reproducibility.

Use `opus` (judgment tier) when:
- The task requires architectural judgment
- The agent writes ADRs, design decisions, or stories
- The agent is the final-judge (approval authority)
- The task involves ambiguous requirements that need reasoning

Use `sonnet` (implementation tier) when:
- The agent implements stories: writes code, features, tests, refactors
- The work is bounded by a story but still requires real programming judgment

Use `haiku` (deterministic tier) when:
- The agent runs commands and reads output (tester)
- The agent writes PASS/FAIL reports from command output
- The agent migrates, copies, or restructures files mechanically with no ambiguity

`fable` (Claude Fable 5) is available as an opt-in for the very hardest judgment
work (e.g. approving a high-stakes production migration). It is not the default:
it is priced above the Opus tier, and its safety classifiers can decline
security-adjacent review work — a bad property for an unattended approval agent.
Offer it only when the user asks for maximum capability.

Claude enforcement extras (set by the scaffolder):
- final-judge → `permissionMode: plan` (deterministically read-only)
- architect agents → `memory: project` (accumulate design knowledge across sessions)

## Codex target

Use `gpt-5.5` with `model_reasoning_effort = "high"` when:
- The task requires architectural judgment
- The agent writes ADRs, design decisions, or stories
- The agent is the final-judge (approval authority)

Use `gpt-5.5` with `model_reasoning_effort = "medium"` when:
- The agent implements stories: writes code, features, tests, refactors

Use `gpt-5.4-mini` with `model_reasoning_effort = "low"` or `"medium"` when:
- The task is deterministic and templated
- The agent runs commands and reads output
- The agent migrates, copies, or restructures files mechanically
- The agent writes PASS/FAIL reports from command output

`gpt-5.3-codex-spark` is a fast/cheap alternative to `gpt-5.4-mini` for read-heavy
exploration agents. Valid `model_reasoning_effort` values: `minimal`, `low`,
`medium`, `high`, `xhigh`.

Set `sandbox_mode = "read-only"` for reviewers, testers, and final approval agents.
Set `sandbox_mode = "workspace-write"` for implementation or migration agents.

## Built-in agents (use as-is, do not redefine):

Claude:
- Explore → read-only codebase traversal and fan-out search
- Plan    → inherits from main conversation, read-only planning

Codex:
- explorer → read-heavy codebase traversal
- worker   → implementation-focused work
- default  → general-purpose fallback
