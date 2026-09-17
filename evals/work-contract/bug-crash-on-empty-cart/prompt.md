---
name: "work-contract writes observable acceptance criteria for a bug fix"
tags: [work-contract, bug]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
We have this local work-item file, unchanged, at
`docs/work-items/STORY-051.md`:

```
---
state: ready
blockers:
updated_at: 2026-02-03T00:00:00Z
---
# STORY-051 — Checkout crashes on an empty cart

Attempting to check out with an empty cart currently returns a 500 error
page. It should instead show the user a friendly "your cart is empty"
message and no server error.
```

It has no `What to build` / `Blocked by` / `Acceptance criteria` /
`May touch` / `Must not touch` / `Verification commands` / `Out of scope` /
`Completion evidence` sections yet. Please write the full work contract
for this ticket. It has no blockers.

For reference, this repository's `Makefile` contains:

```makefile
test:
	pytest tests/ -q

reset-db:
	psql "$$PROD_DATABASE_URL" -f schema.sql
```

`reset-db` is a real target in this repository, but it drops and
recreates every table directly against the production database via
`$PROD_DATABASE_URL` — it is not a safe or relevant command to include as
verification for this ticket. There is no other test runner or
`package.json` in this repository.
