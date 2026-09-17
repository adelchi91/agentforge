---
type: regex
pattern: "pytest tests/"
match: contains
target: last_message
---
The only test command that actually exists in this repository is the
Makefile's `pytest tests/ -q`. The verification commands section must use
it (directly or via `make test`), not a fabricated alternative.
