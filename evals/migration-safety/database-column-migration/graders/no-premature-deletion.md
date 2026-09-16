---
type: regex
pattern: "(?i)(drop|delete) (the )?(old |legacy )?(column|`?legacy_email`?) (now|immediately|right away|today|first thing)"
match: not_contains
target: last_message
---
The response must not recommend dropping/deleting the legacy column
immediately or before the other phases -- deletion is only ever the last
step, gated on validation evidence.
