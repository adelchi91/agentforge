---
name: "work-contract enriches a feature ticket without changing its identity or blockers"
tags: [work-contract, feature]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
We have this local work-item file, unchanged, at
`docs/work-items/STORY-050.md`:

```
---
state: ready
blockers: STORY-010
updated_at: 2026-02-01T00:00:00Z
---
# STORY-050 — CSV export of the notification log

Admins need to export the notification log as a CSV file from the admin
dashboard, filtered by the date range they currently have selected.
```

It has no `What to build` / `Blocked by` / `Acceptance criteria` /
`May touch` / `Must not touch` / `Verification commands` / `Out of scope` /
`Completion evidence` sections yet. Please write the full work contract for
this ticket.

For reference, this repository's `package.json` contains:

```json
{
  "scripts": {
    "test": "jest --runInBand",
    "build": "tsc -p ."
  }
}
```

There is no other test runner or Makefile in this repository. Do not
change the ticket's identity or its blocker.
