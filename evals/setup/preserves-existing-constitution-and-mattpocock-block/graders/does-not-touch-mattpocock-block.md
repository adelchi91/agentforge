---
type: regex
pattern: "(?i)(remove|delete|replace|overwrite)[^.\\n]{0,60}mattpocock"
match: not_contains
target: last_message
---
Matt Pocock's own `<!-- mattpocock:start -->`/`<!-- mattpocock:end -->`
block belongs to his plugin, not AgentForge. The response must never
propose removing, replacing, or overwriting it.
