---
type: tool_used
tool: Skill
input_match: "migration-safety"
max: 0
target: trace
---
STORY-020 addition: this scenario is additive, read-only, brownfield
feature work with nothing being replaced, renamed, or removed
(`skills/migration-safety/SKILL.md`'s own "Do not use for ordinary
new-feature work" line), so the migration-safety skill itself should not
load at all -- a stronger check than the existing behavioral graders in
this case, which only assert that *if* something loaded, it did not
impose migration ceremony.
