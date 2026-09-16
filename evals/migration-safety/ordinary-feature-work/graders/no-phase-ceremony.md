---
type: regex
pattern: "(?i)(extract|expand|contract) (phase|step)|extract/expand/migrate|no.?delete.?before.?validation"
match: not_contains
target: last_message
---
This is ordinary greenfield feature work with no existing schema/interface
being replaced and no coexistence window, so the response must not impose
extract/expand/migrate/validate/contract/delete phase sequencing or the
no-delete-before-validation ceremony on it.
