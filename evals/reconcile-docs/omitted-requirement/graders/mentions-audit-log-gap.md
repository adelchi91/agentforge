---
type: regex
pattern: "audit log"
flags: "i"
match: contains
target: last_message
---
PRD item 3 (the admin audit log) is the one requirement no ticket
addresses. The final report must name it explicitly rather than silently
dropping it.
