---
type: regex
pattern: "(?i)\\b(omission|omitted|missing|uncovered|not covered|gap|unaddressed)\\b"
match: contains
target: last_message
---
The report must characterize the audit-log finding using omission-type
language somewhere (the exact word doesn't matter, but the finding must
read as "nothing addresses this").
