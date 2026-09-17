---
type: llm
criteria: "The response's work contract (in its acceptance criteria and/or out-of-scope sections) makes dropping/deleting the users.legacy_email column conditional on validation evidence (e.g. the reconciliation script reporting no mismatches) existing first -- it must not present deletion as something this ticket can do immediately or unconditionally."
target: last_message
---
Mirrors migration-safety's no-delete-before-validation rule, but as a
work-contract concern (an acceptance criterion / scope boundary), not a
restatement of the migration-safety skill's own phase sequencing.
