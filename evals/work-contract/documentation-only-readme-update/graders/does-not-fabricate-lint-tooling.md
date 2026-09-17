---
type: regex
pattern: "(?i)(markdownlint|textlint|npm run lint|make lint)"
match: not_contains
target: last_message
---
No linter or doc-build tooling is configured in this repository. The
response must not invent a plausible-sounding lint/build command that
does not actually exist here.
