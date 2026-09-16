---
type: tool_used
tool: Skill
input_match: "migration-safety"
min: 1
target: trace
---
The scenario matches every migration-safety trigger signal (existing
column with live consumers, coexistence window, explicit "retire the
column" framing), so the skill should load. Marked as an ablation
("with"-only) indicator by the eval runner rather than a hard pass/fail
gate.
