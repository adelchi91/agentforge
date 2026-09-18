---
type: tool_used
tool: Skill
input_match: "setup"
min: 1
target: trace
---
The scenario is a direct request to set up AgentForge, so the setup skill
should load even though it will stop at Step 1. Marked as an ablation
("with"-only) indicator by the eval runner rather than a hard pass/fail
gate.
