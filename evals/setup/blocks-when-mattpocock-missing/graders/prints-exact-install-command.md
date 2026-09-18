---
type: regex
pattern: "claude plugin install mattpocock-skills@claude-plugins-official"
match: contains
target: last_message
---
`skills/setup/SKILL.md` requires printing this exact install command
verbatim when mattpocock-skills is missing or disabled, so the user can
copy-paste it rather than guess at plugin names.
