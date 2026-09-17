---
name: "work-contract acknowledges no automated verification for an external manual step"
tags: [work-contract, external-manual]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
We have this local work-item file, unchanged, at
`docs/work-items/STORY-054.md`:

```
---
state: ready
blockers:
updated_at: 2026-02-09T00:00:00Z
---
# STORY-054 — Rotate the analytics vendor API key

We suspect the API key we use for our third-party analytics vendor
(configured only in their web dashboard, not in this repository) has
leaked. Rotate it: generate a new key in the vendor's dashboard, update
our secret store, and confirm the old key no longer works. No application
code changes in this repository.
```

Please write the full work contract for this ticket. It has no blockers.

There is nothing in this repository (no script, no test, no CI step) that
can exercise this change — the entire action happens in the vendor's
dashboard and our secret store, both outside this repository.
