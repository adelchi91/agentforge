---
type: llm
criteria: "The response structures its plan using (or clearly maps onto) the extract, expand, migrate, validate, contract, and delete phases, in that order, for retiring users.legacy_email in favor of users.email_normalized while the three existing consumers (billing, support-tools, notifications worker) keep working throughout."
target: last_message
---
Core check that the classic backward-compatible migration sequencing
appears for genuine migration work.
