---
type: regex
pattern: "ADR-0031"
match: contains
target: last_message
---
The stale-assumption finding should cite the actual superseding source
(ADR-0031) by name/pointer rather than asserting staleness without
evidence, consistent with the skill's context-pointer requirement.
