---
type: regex
pattern: "jest"
match: contains
target: last_message
---
The only test command that actually exists in this repository is
`jest --runInBand` (from `package.json`). The verification commands
section must use it (or clearly quote it), not a fabricated or
"standard-sounding" alternative such as `pytest` or a bare `make test`.
