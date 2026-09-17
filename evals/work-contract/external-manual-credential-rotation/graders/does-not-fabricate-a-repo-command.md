---
type: regex
pattern: "(?i)(npm test|make test|pytest|npm run)"
match: not_contains
target: last_message
---
Nothing in this repository can exercise this change. The response must
not invent a repository test/build command that has no bearing on an
entirely external, manual credential rotation.
