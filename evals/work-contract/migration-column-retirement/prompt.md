---
name: "work-contract references migration-safety's validation gate without duplicating its phase list"
tags: [work-contract, migration]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
We have this local work-item file, unchanged, at
`docs/work-items/STORY-053.md`:

```
---
state: ready
blockers: STORY-040
updated_at: 2026-02-07T00:00:00Z
---
# STORY-053 — Retire users.legacy_email in favor of users.email_normalized

Three internal services (billing, support-tools, and the notifications
worker) currently read `users.legacy_email` directly. A new
`email-delivery` service reads the new `users.email_normalized` column
instead. We want to retire the old column once it's safe.
```

Please write the full work contract for this ticket. Keep its identity
and its STORY-040 blocker exactly as given.

For reference, this repository already has a reconciliation script:
`scripts/reconcile_email_columns.py --check`, which compares
`legacy_email` against `email_normalized` for every row and exits non-zero
on any mismatch. There is no other test runner or Makefile target relevant
to this change.

Do not re-explain the full extract/expand/migrate/validate/contract/delete
migration sequencing in detail here -- that discipline lives in the
separate `migration-safety` skill. Just make sure this ticket's acceptance
criteria and scope correctly gate deletion on validation evidence.
