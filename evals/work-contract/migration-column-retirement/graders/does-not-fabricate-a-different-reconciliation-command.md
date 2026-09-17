---
type: llm
criteria: "The response's verification commands use the repository's actual `reconcile_email_columns.py --check` reconciliation script and do not invent a different, unverified reconciliation, migration, or test command that was never given in the prompt."
target: last_message
---
Complements uses-the-real-reconciliation-command.md (which checks the real
command is present) by separately guarding against fabricating an
additional, plausible-sounding but nonexistent command alongside it.
