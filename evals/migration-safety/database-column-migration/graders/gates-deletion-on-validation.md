---
type: regex
pattern: "(?i)(delet(e|ion)|drop(ping)? the (old|legacy)? ?column)[^.\\n]{0,200}\\b(valid(ate|ation))\\b|\\b(valid(ate|ation))\\b[^.\\n]{0,200}(delet(e|ion)|drop(ping)? the (old|legacy)? ?column)"
match: contains
target: last_message
---
The answer to "when is it safe to drop the old column" must explicitly tie
deletion to validation evidence (reconciliation, parity checks, a soak
period) existing first -- not just list validation as one unconnected
bullet among many.
