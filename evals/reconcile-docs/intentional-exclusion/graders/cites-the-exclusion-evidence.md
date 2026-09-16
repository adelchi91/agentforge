---
type: regex
pattern: "(?i)(2026-08-01|product review|out of scope|Notifications v2)"
match: contains
target: last_message
---
The report should point at the actual evidence for the exclusion (the
dated product decision, the "Out of scope" section, or the v2 deferral)
rather than asserting intent without a pointer, consistent with the
skill's context-pointer requirement.
