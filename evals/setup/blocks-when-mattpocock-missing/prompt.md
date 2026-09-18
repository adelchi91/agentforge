---
name: "setup stops and prints the install command when mattpocock-skills is not installed"
tags: [setup, preservation]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
`claude plugin list` in this project prints nothing -- no plugins are
installed at all. This project's `CLAUDE.md` already exists with several
paragraphs of team-specific prose.

Please set up AgentForge in this project.
