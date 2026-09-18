---
type: llm
criteria: "The response follows a plan-then-approve-then-apply flow: it describes the proposed AgentForge block/config as a plan or diff and asks for one explicit approval before treating any file as written, rather than asserting that CLAUDE.md or .agentforge/config.json have already been created or modified. It does not claim to have silently regenerated the whole CLAUDE.md file."
target: last_message
---
`skills/setup/SKILL.md` requires a plan step and one explicit approval
before any write, and forbids ever describing the constitution file as
wholesale-replaced. This is a holistic check that the response follows
that flow instead of skipping straight to "done".
