---
type: regex
pattern: "(?i)no automated verification"
match: contains
target: last_message
---
STORY-007 requires a deliberate, visible acknowledgment when no automated
verification is possible -- this is the canonical case for it: a fully
external, manual step with nothing in the repository to run.
