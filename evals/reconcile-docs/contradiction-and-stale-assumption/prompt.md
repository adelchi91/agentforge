---
name: "reconcile-docs identifies a contradiction and a stale assumption"
tags: [reconcile-docs, contradiction, stale-assumption]
plugins: ["agentforge"]
runs: 3
max_turns: 6
timeout_seconds: 120
---
We drafted a spec from our PRD and want it checked before we start
building. Don't ask clarifying questions and don't create or edit any
tickets — just report coverage against the reference material.

Reference PRD, full text (treat this as `docs/reference/PRD-billing-refunds.md`):

```
# PRD: Billing Refunds v1

1. Refunds must be processed within 5 business days of approval.
2. Only finance-admins (not support agents) may approve a refund over $500.
3. All refund amounts must be stored in USD cents (see ADR-0012, "Currency
   handling").
```

Reference ADR, full text (treat this as `docs/reference/ADR-0031-currency-storage.md`,
dated 2026-06-01, which supersedes the ADR-0012 referenced by PRD item 3
above):

```
# ADR-0031: Store amounts in the customer's local currency, not USD cents

## Status
Accepted (supersedes ADR-0012)

## Decision
All monetary amounts, including refunds, are stored in the ISO 4217 minor
unit of the customer's local currency, not USD cents. ADR-0012 no longer
applies to any new work.
```

Proposed spec, full text (treat this as `docs/reference/spec-billing-refunds.md`):

```
# Billing Refunds v1 -- spec

- Refunds are processed within 10 business days of approval.
- Support agents may approve refunds up to $2,000 without finance-admin
  review.
- Refund amounts are stored in USD cents, per ADR-0012.
```

Compare the spec against the reference material. Tell us what's covered,
what's missing, what's contradicted, what relies on a stale assumption,
and what's deliberately excluded, with evidence for each finding.
