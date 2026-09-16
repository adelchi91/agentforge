---
type: regex
pattern: "(?i)(old|legacy) (column|schema|endpoint|api|table)"
match: not_contains
target: last_message
---
There is no existing schema/endpoint being replaced in this scenario, so
the response should not invent an "old path" to migrate away from or
describe a deletion/validation gate for something that doesn't exist here.
