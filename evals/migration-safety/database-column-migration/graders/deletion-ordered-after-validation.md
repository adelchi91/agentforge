---
type: llm
criteria: "In the response's plan, dropping/deleting the old `users.legacy_email` column is sequenced strictly after gathering validation evidence (reconciliation, parity checks, monitoring/soak period, or equivalent) that the new `users.email_normalized` path is correct and complete -- regardless of the specific words, headings, or step numbers used. The plan must not present deletion as an early or immediate step performed before such evidence exists, even if it never uses words like 'now' or 'immediately'."
target: last_message
---
Complements the regex-based no-premature-deletion.md grader, which only
catches explicit temporal markers ("now", "immediately", ...) next to
"drop/delete column". A response that violates the no-delete-before-
validation policy by simply ordering deletion as an early numbered step,
without using any of those words, would slip past the regex grader alone
-- this grader checks the actual sequencing regardless of wording.
