---
name: "migration-safety sequences a genuine migration and gates deletion on validation"
tags: [migration-safety, is-migration]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
We need to retire the `users.legacy_email` column in favor of a new
`users.email_normalized` column that a new email-delivery service reads.
Three internal services (billing, support-tools, and the notifications
worker) currently read `users.legacy_email` directly, and we can't take
them all down at once.

Plan the safest way to do this end to end, and tell us exactly when it
would be safe to drop the old `legacy_email` column.
