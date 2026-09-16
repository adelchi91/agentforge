---
type: regex
pattern: "(?i)audit log[^.\\n]{0,160}\\b(intentional(ly)?|deliberate(ly)?|deferred|out of scope|explicitly)\\b|\\b(intentional(ly)?|deliberate(ly)?|deferred|out of scope|explicitly)\\b[^.\\n]{0,160}audit log"
match: contains
target: last_message
---
The ticket graph's "Out of scope" section explicitly defers the audit log
to Notifications v2. The report must classify this as a deliberate/
intentional exclusion, near the audit-log mention, not as a silent gap.
