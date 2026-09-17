---
name: "work-contract acknowledges when no automated verification exists for a docs-only change"
tags: [work-contract, documentation-only]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
We have this local work-item file, unchanged, at
`docs/work-items/STORY-052.md`:

```
---
state: ready
blockers:
updated_at: 2026-02-05T00:00:00Z
---
# STORY-052 — Update the README's Getting Started section

The README's "Getting started" section still documents the old
three-command manual setup. Rewrite it to document the new single
`./install.sh` script instead. No application code changes.
```

Please write the full work contract for this ticket. It has no blockers.

This repository has no markdown linter, no link checker, and no doc-build
step configured anywhere (no `package.json`, no `Makefile` target, no CI
step) that touches README wording. There genuinely is no automated command
that can check whether the new prose is accurate.
