---
name: "setup preserves existing CLAUDE.md prose and Matt Pocock's own block"
tags: [setup, preservation]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
`claude plugin list` in this project shows:

```
mattpocock-skills@claude-plugins-official   enabled
```

This project's `CLAUDE.md` already exists and reads exactly:

```markdown
# Widgets API

## Team conventions

We use trunk-based development. Every PR needs one approving review.
Run `make check` before opening a PR.

<!-- mattpocock:start -->
Grilling and spec/ticket workflow configured by mattpocock-skills.
<!-- mattpocock:end -->
```

Please set up AgentForge in this project.
