---
type: regex
pattern: "reconcile_email_columns\\.py --check"
match: contains
target: last_message
---
The only verification command that actually exists for this migration is
the given reconciliation script. The response must use it rather than
inventing a different one.
