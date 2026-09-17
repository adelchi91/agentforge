---
name: "reconcile-docs identifies a deliberate exclusion"
tags: [reconcile-docs, exclusion]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
We drafted a ticket breakdown from our PRD and want it checked before we
start building. Don't ask clarifying questions and don't create or edit any
tickets — just report coverage against the PRD.

Reference PRD, full text (treat this as `docs/reference/PRD-notifications.md`):

```
# PRD: Admin Notifications v1

1. Admins must be able to export the notification log as CSV.
2. Users must be able to reset their password via an emailed link.
3. Every admin action (create, edit, delete) must be written to an audit
   log visible to super-admins.
4. The system must send a daily digest email summarizing unresolved
   notifications.
```

Proposed ticket graph, full text (treat this as
`docs/reference/tickets-notifications.md`):

```
# Notifications v1 -- ticket graph

- TICKET-1: CSV export of the notification log for admins.
- TICKET-2: Password reset via emailed link.
- TICKET-3: Daily digest email of unresolved notifications.

## Out of scope

- Per the 2026-08-01 product review, the admin audit log (PRD item 3) is
  explicitly deferred to Notifications v2 and is intentionally not part of
  this ticket graph.
```

Compare the ticket graph against the PRD. Tell us what's covered, what's
missing, what's contradicted, and what's deliberately excluded, with
evidence for each finding.
