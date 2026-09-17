---
type: regex
pattern: "(?i)blocked by[\\s\\S]{0,80}\\bnone\\b"
match: contains
target: last_message
---
This ticket has no blockers. STORY-007 requires the `Blocked by` section
to say "None" explicitly rather than being left blank or omitted.
