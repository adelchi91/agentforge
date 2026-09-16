---
name: reconcile-docs
description: Compare reference documents (PRDs, specs, existing docs, ADRs, prior tickets) against a proposed spec or ticket graph and report what it covers, omits, contradicts, or deliberately excludes. Use when the user asks to "reconcile this spec against the PRD", "check ticket coverage", "did we miss anything from the doc", "does this contradict the spec", or when a spec/ticket graph is being finalized against known reference material.
---

# Reconcile Docs

A reusable comparison discipline: given one or more reference documents and
a proposed spec or ticket graph, report where the proposal stands relative
to the reference material. This skill only compares and reports — it never
elicits new requirements and never creates or edits tickets.

## When this applies

Trigger only when both of these exist:

- one or more **reference documents** (a PRD, spec, existing documentation,
  ADR, or prior ticket set) that describe what should be true, and
- a **proposal** (a new spec, a ticket graph, or a set of tickets) that is
  supposed to satisfy them.

If there is no proposal yet — the user wants to gather requirements from
scratch — defer to Matt Pocock's `grilling`/`to-spec`. If the proposal
exists but needs to be broken into tickets, defer to his `to-tickets`. This
skill does not perform either job; it only checks an existing proposal
against existing reference material.

## Step 1: identify inputs by pointer, not by copy

List the reference documents and the proposal as file paths or other stable
references (URLs, ticket IDs, commit SHAs). Read them, but do not restate
their full text in your own working notes or in the final report. When you
need to justify a finding, quote the minimal phrase that supports it (a
sentence or a bullet, not a section), and otherwise cite `path:line` or a
section heading. The report must remain useful without the reader having
the source text open, but it is a set of pointers plus short justifying
quotes — not a copy of the source documents.

## Step 2: walk every discrete requirement or claim

For each discrete requirement or claim in the reference documents, classify
what the proposal does with it into exactly one of four categories. These
categories are not interchangeable — the discriminator between the two
"missing" categories is whether the proposal (or material accompanying it)
contains an explicit statement that the item is deferred, rejected, or out
of scope:

1. **Covered** — some part of the proposal addresses the requirement. Cite
   the specific ticket/section that does.
2. **Omission** — nothing in the proposal addresses the requirement, and
   nothing in the proposal or its accompanying material states a reason it
   was left out. Treat silence as an omission, never as an implied
   exclusion.
3. **Intentional exclusion** — nothing in the proposal implements the
   requirement, but the proposal or its accompanying material (an "out of
   scope" section, a linked ADR, a dated product decision) explicitly says
   so. Cite exactly where that statement lives.
4. **Contradiction** — the proposal states something incompatible with the
   reference document (a different behavior, a different value, a
   different actor). Cite both the reference claim and the conflicting
   proposal statement.

**Never conflate omission and intentional exclusion.** If you are unsure
whether an absence is deliberate, default to reporting it as an omission
and say explicitly that you found no exclusion statement — do not infer
intent that isn't written down anywhere.

## Step 3: look for stale assumptions

Separately from the requirement walk, check whether the reference documents
state something as current fact that a newer source (later commits, newer
docs, the current codebase) has superseded, and the proposal is relying on
the stale version. Flag each as a **stale assumption**: the original claim,
its pointer, and the pointer to what supersedes it.

## Step 4: report in four sections

Produce a report with exactly these four section headings, each present
even when empty (state "none found" rather than omitting a section):

- **Omissions** — requirement, reference pointer, and why it looks
  unaddressed (i.e., that no exclusion statement was found).
- **Contradictions** — requirement, reference pointer, proposal pointer,
  and the nature of the conflict.
- **Stale assumptions** — the assumption, its original pointer, and the
  pointer to what supersedes it.
- **Intentional exclusions** — requirement, reference pointer, and the
  exact pointer to where the exclusion is declared.

Do not add a combined "missing" bucket that merges omissions and
intentional exclusions — a reader must be able to tell, from the section
alone, whether something needs a decision (omission) or was already
decided (intentional exclusion).

## What this skill does not do

- It does not interview the user or elicit new requirements — that is
  Matt Pocock's `grilling` and `to-spec`.
- It does not create, edit, or decompose tickets — that is Matt Pocock's
  `to-tickets`.
- It does not decide migration sequencing or deletion safety — see the
  sibling `migration-safety` skill for that.
- It does not copy whole source documents into its output; it cites
  pointers and short justifying quotes only.
