---
type: llm
criteria: "The response stops after reporting that mattpocock-skills is not installed and telling the user to install it. It does not write, edit, or propose specific edits to CLAUDE.md, .agentforge/config.json, or any other project file, and does not run or describe running the setup planner/apply commands."
target: last_message
---
`skills/setup/SKILL.md` Step 1 requires stopping before any write when
mattpocock-skills is missing -- the user can re-run setup afterward.
