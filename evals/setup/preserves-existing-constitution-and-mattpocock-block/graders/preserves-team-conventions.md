---
type: regex
pattern: "(?i)(preserve|keep|leave|retain|untouched|unchanged)[^.\\n]{0,80}(team conventions|existing (content|prose|claude\\.md))"
match: contains
target: last_message
---
The response must explicitly say it keeps the existing "Team conventions"
prose in `CLAUDE.md` intact -- not merely stay silent about it. Setup only
owns one small delimited block; it must never imply a wholesale rewrite.
