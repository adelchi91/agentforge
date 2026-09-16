---
type: llm
criteria: "The response treats this as ordinary feature-addition work on an already-existing, already-shipped system (e.g. plain design/build/test guidance for the new PDF export button and endpoint) and does not frame it as a migration or apply migration phase sequencing (extract/expand/migrate/validate/contract/delete) or a no-delete-before-validation gate, even though the invoice page and its existing endpoint are pre-existing, in-production, brownfield code. It is acceptable for the response to explicitly note that this isn't a migration."
target: last_message
---
Holistic check that migration ceremony stays conditional/opt-in and is not
forced onto ordinary brownfield feature work -- i.e. work that touches an
existing, already-shipped system without replacing anything in it, which
is the actual discriminator ADR-0007 and STORY-016 call for (a purely
greenfield/net-new scenario would be a much easier, less meaningful test).
