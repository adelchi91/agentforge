---
name: migration-safety
description: Apply extract/expand/migrate/validate/contract/delete sequencing and a no-delete-before-validation policy, but only to work that is actually a migration — replacing, renaming, moving, or removing an existing schema, API, dependency, or code path while something must keep working during the change. Use when work involves cutting over an existing schema/interface/dependency with live consumers, a dual-write or shadow-read window, a backfill, or an explicit "migrate"/"deprecate and replace" request. Do not use for ordinary new-feature work, greenfield code, or bug fixes that touch no existing schema or interface contract.
---

# Migration Safety

A conditional discipline: extract/expand/migrate/validate/contract/delete
sequencing and a hard no-delete-before-validation rule, applied only when
the work at hand is actually a migration. Ordinary feature work never sees
this ceremony.

## Step 1: classify the work first

Before proposing any phase structure, decide whether this is a migration.

**Signals this is a migration** — any one is enough:

- an existing data schema, storage format, table, or column is being
  replaced, renamed, split, merged, or dropped;
- an existing API, interface, or contract has live consumers and is being
  replaced by a new shape while those consumers must keep working;
- a dependency, library, framework, or infrastructure component is being
  swapped for a replacement across code that already exists and works;
- old and new implementations must coexist for a period (a feature flag,
  dual-write, backfill, or shadow-read is involved);
- the request explicitly says "migrate", "cut over", "backfill",
  "deprecate and replace", or equivalent.

**Signals this is ordinary feature work — not a migration:**

- net-new functionality with no existing behavior being replaced;
- a bug fix that does not change a schema or interface contract;
- greenfield code with no prior consumers;
- documentation-only or test-only changes;
- a refactor that preserves the same external contract/schema with no
  coexistence window and none of the signals above.

**If no migration signal applies, stop here.** Do not propose
extract/expand/migrate/validate/contract/delete phases, do not ask the user
to declare a phase, and say plainly that this discipline does not apply
("this isn't a migration, so this doesn't need phase sequencing"). Continue
to Step 2 only for work classified as a migration.

## Step 2: sequence the migration

For work classified as a migration, structure the plan through these
phases, in order. Not every migration needs an elaborate execution of every
phase, but never skip straight to deletion:

1. **Extract** — isolate the code, schema, or interface that will change
   behind a seam (an interface, a column, a module boundary) so both the
   old and new implementation can be addressed through it.
2. **Expand** — add the new schema/interface/dependency alongside the old
   one. Nothing that currently depends on the old path breaks.
3. **Migrate** — move producers and/or consumers to the new path
   incrementally (dual-write, backfill, staged rollout, one consumer at a
   time). The old path keeps working throughout.
4. **Validate** — gather concrete replacement-verification evidence that
   the new path is correct and complete: reconciliation counts, parity
   tests, shadow-read diffing, or a monitored soak period, proportional to
   the migration's risk. State exactly what evidence exists, or that none
   exists yet.
5. **Contract** — once validated, narrow read/write paths to the new
   implementation only (stop dual-write, flip the default) while the old
   path's storage or code still exists but is no longer the active source
   of truth.
6. **Delete** — remove the old schema, interface, dependency, or code path.

## Step 3: enforce no-delete-before-validation

This is the rule this skill exists to enforce, and it is not negotiable:

**Deletion or contraction of the old path may never be recommended,
scheduled, or performed before Step 4's validation evidence exists and is
stated.**

- If asked to plan or perform Contract/Delete and no validation evidence
  has been produced or cited, refuse to sequence it yet and say exactly
  what evidence is missing (for example: "no reconciliation or parity
  check has run yet — validate before contracting or deleting").
- "It looks fine," "should be safe," and time pressure are not validation
  evidence.
- If the user insists on deleting first, state the risk explicitly and
  require an explicit, informed override to be recorded (in the work
  contract's completion evidence, or an ADR) — never silently comply or
  soften the recommendation to avoid friction.

## What this skill does not do

- It does not impose phase ceremony on ordinary feature work, bug fixes,
  or greenfield code — Step 1 must screen those out before Step 2 ever
  runs.
- It does not own the work contract's fields (scope, acceptance criteria,
  verification commands) — see `work-contract`.
- It does not reconcile source documents against a proposal — see the
  sibling `reconcile-docs` skill.
- It does not replace project-specific migration tooling (schema migration
  frameworks, feature-flag systems); it constrains sequencing and evidence,
  not tooling choice.
