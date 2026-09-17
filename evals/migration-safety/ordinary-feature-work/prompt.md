---
name: "migration-safety does not impose migration ceremony on ordinary brownfield feature work"
tags: [migration-safety, not-a-migration]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
Our invoice detail page already exists in production and already has a
working `GET /invoices/:id` endpoint that customer support uses every day.
We want to add a new "Export to PDF" button to that already-existing page,
backed by a brand-new, additive `GET /invoices/:id/pdf` endpoint that
renders the same invoice data support already reads.

Nothing about the existing `GET /invoices/:id` endpoint, its response
shape, or the underlying invoice schema is changing, being renamed, or
being removed. No consumer of the existing endpoint needs to be migrated
to anything, and nothing old needs to coexist with anything new -- we are
only adding a new, independent read path alongside code that already
works and keeps working unchanged.

How should we approach implementing this?
