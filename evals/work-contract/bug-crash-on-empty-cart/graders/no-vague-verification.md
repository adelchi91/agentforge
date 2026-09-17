---
type: regex
pattern: "(?i)(run the tests|verify manually|check it works|\\bTODO\\b|\\.\\.\\.)"
match: not_contains
target: last_message
---
The verification commands section must never contain vague, unverifiable,
or placeholder prose.
