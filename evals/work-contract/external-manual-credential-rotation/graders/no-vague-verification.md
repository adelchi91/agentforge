---
type: regex
pattern: "(?i)(run the tests|verify manually|check it works|\\bTODO\\b|\\.\\.\\.)"
match: not_contains
target: last_message
---
Even when acknowledging that no automated verification exists for this
entirely external, manual step, the response must still name a concrete
manual check (see names-a-concrete-manual-check.md) rather than falling
back on vague, unactionable phrasing.
