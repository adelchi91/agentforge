---
type: regex
pattern: "(?i)(run the tests|verify manually|check it works|\\bTODO\\b|\\.\\.\\.)"
match: not_contains
target: last_message
---
Even when acknowledging that no automated verification exists, the
response must not fall back on other vague or placeholder phrasing
elsewhere in the contract.
