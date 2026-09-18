---
type: tool_used
tool: Skill
input_match: "reconcile-docs"
max: 0
target: trace
---
reconcile-docs triggers only when both a reference document and a
proposed spec/ticket graph exist to compare it against
(`skills/reconcile-docs/SKILL.md`, "When this applies"). Here there is
only one document and a plain summarization request -- nothing to
reconcile it against -- so the skill must not load.
