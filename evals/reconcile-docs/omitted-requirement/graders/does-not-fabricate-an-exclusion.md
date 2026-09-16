---
type: regex
pattern: "(?i)audit log[^.\\n]{0,120}\\b(intentional(ly)?|deliberate(ly)?|deferred|out of scope|excluded|explicitly (dropped|removed))\\b"
match: not_contains
target: last_message
---
No source document says the audit log was deliberately deferred or
excluded -- that sentence does not exist anywhere in the PRD or the ticket
graph given in this case. The report must not invent an exclusion
rationale for it; it must be reported as an unexplained gap (an omission),
not as a decision that was already made.
