---
name: work-contract
description: Teach how to write or enrich a work contract's required sections — What to build, Blocked by, Acceptance criteria, May touch, Must not touch, Verification commands, Out of scope, Completion evidence — for a ticket that already has its canonical identity and blocking edges assigned (by Matt Pocock's `to-tickets`, or by the local Markdown tracker). Use when asked to "write a work contract", "flesh out this ticket", "add acceptance criteria", "add verification commands", "fill in the scope", or before starting implementation on a ticket that is missing any of these sections.
---

# Work Contract

A work contract is data, not prose instruction (ADR-0003): a structured
record — `What to build`, `Blocked by`, `Acceptance criteria`, `May touch`,
`Must not touch`, `Verification commands`, `Out of scope`, `Completion
evidence` — that later work (implementation, review, verification) reads
back. This skill teaches how to write or enrich that record so "done" is
independently checkable by someone who did not write the implementation.

It does not create the record's shape from nothing on every project; the
local-Markdown reference shape lives in `templates/local-work-item.md`
(compatible with STORY-006's `local` tracker adapter), and a remote
tracker's own ticket body carries the same eight sections.

## When this applies

Trigger when a ticket (local Markdown file, GitHub/GitLab issue body, or a
freshly drafted local work item) is missing one or more of the eight
sections above, or has a section that is present but too vague to act on
(no acceptance criteria, no verification commands, a "Blocked by" that
just says "see epic"). Do not trigger to originate a brand-new ticket graph
from a spec, and do not trigger to split one large ticket into several —
both of those are Matt Pocock's `to-tickets`; this skill only enriches a
ticket that already exists and already has an identity.

## Step 0: never touch identity or blocking edges

The canonical id (`local:STORY-042`, `github:owner/repo#123`,
`gitlab:group/project#7`) and the dependency graph that produced this
ticket's blockers were already decided upstream — by Matt Pocock's
`to-tickets`, or by whatever created the local ticket file. This skill
enriches the contract fields around that identity. It never:

- invents a new identifier or identifier scheme for the ticket;
- renumbers, retitles-as-a-different-item, or merges/splits the ticket;
- adds, removes, or reorders a blocking edge the tracker did not already
  record.

If the blockers look wrong, incomplete, or the ticket looks like it should
be split into more than one vertical slice, **stop and say so** — defer
the decomposition itself to `to-tickets` rather than doing it here.

## Step 1: What to build (user-observable terms)

State what changes for whoever exercises the resulting behavior — an end
user, an API consumer, an operator reading a log, a downstream service —
never internal implementation ("refactor class X", "add a helper
function"). Prefer a **vertical slice**: a thin path all the way through
the system that produces one observable outcome, over a horizontal layer
("just the backend endpoint" or "just the schema change") that produces
nothing anyone outside the codebase can observe yet. Teaching vertical
slicing is this skill's job; deciding how a large effort splits into
several *separate* tickets is not — that decomposition call belongs to
`to-tickets` (Step 0 above).

## Step 2: Blocked by (canonical identities only)

List every item this ticket is blocked by, using the **canonical,
provider-qualified identity** exactly as the tracker already assigned it
(`local:STORY-050`, `github:owner/repo#41`) — never a bare number, a
made-up slug, or a second identifier scheme layered on top of the
tracker's own. If nothing blocks this item, write "None" explicitly;
never leave the section blank, since a blank section cannot be
distinguished from "not checked yet."

A local Markdown ticket's actual machine-readable dependency edge lives in
the file's own front-matter `blockers:` field (a plain comma-separated
list of the *other* tracker's raw identifiers — see
`templates/local-work-item.md` and STORY-006's local-tracker Markdown
parser). That front-matter list and this section's prose
must always name the same set of items; state the canonical, provider-
qualified form here for a reader who does not already know which tracker
is configured, but never let the two drift apart, and never add an item to
one without the other.

## Step 3: Acceptance criteria (observable outcomes)

Each criterion is a concrete, checkable outcome — never a restatement of
the task, an implementation step, or "code reviewed and merged." Phrase
each one so a person with no knowledge of the implementation could confirm
pass or fail by observing behavior: running a command, reading a response,
viewing a rendered page, checking a log line. If a criterion cannot be
phrased as something observable, it usually means the ticket's "What to
build" is still too vague — go back to Step 1 before writing more
criteria.

## Step 4: May touch / Must not touch

List concrete paths or path globs.

- **May touch** bounds where changes are expected to land.
- **Must not touch** names paths this work must never modify — generated
  files, another team's module, unrelated migrations, vendored
  dependencies.

This is the scope boundary that the separate, explicitly graded
scope-policy engine (`STORY-013`/`STORY-014`) can check tool calls against
later. This skill only writes the boundary down; it does not enforce it at
tool-call time.

## Step 5: Verification commands (each mapped to a criterion)

This section is the one most likely to be filled with something
unusable, so treat writing it as an act of verification, not just prose:

- **Every command must already exist in this repository.** Before writing
  one, check `package.json` scripts, a `Makefile`/`justfile`,
  `pyproject.toml`/`tox.ini`/`pytest.ini`, or whatever test/build
  configuration the repository actually defines, and copy the exact
  invocation from there. Never assert a command because it "sounds
  standard" — `npm test`, `make test`, and `pytest` are only real
  verification commands here if this repository actually defines them
  that way.
- If you cannot find a project-defined command that exercises the
  criterion, say exactly what you looked at and what's missing, or ask —
  do not fabricate a plausible-sounding one to fill the section.
- **Every command must map to at least one acceptance criterion**, and the
  mapping must be written out ("verifies criterion 2"), not left implied.
  A command with no criterion behind it does not belong in this section.
- **Reject vague, unverifiable, or placeholder text outright.** None of
  the following belong in this section, and a contract offered for review
  containing one of them should be flagged and sent back rather than
  accepted: "run the tests", "verify manually" with no further detail,
  "check it works", a bare `TODO`, or an ellipsis (`...`) standing in for
  a command. Also reject a command copied from another project's
  conventions without confirming it exists in this one.
- **Reject a command that is real but unsafe to run as a verification
  step**, even though it passes the "actually exists in this repo" test
  above — a target that drops or resets a database, force-pushes, deletes
  data irreversibly, or requires live external credentials/production
  side effects to execute. Existing is necessary but not sufficient. If a
  safer equivalent of the same command exists (a `--dry-run`/`--check`
  flag, a staging-only invocation, a read-only report mode), use that
  instead and say so; if no safe automated equivalent exists, do not list
  the unsafe command at all — fall back to the explicit "no automated
  verification" acknowledgment below instead.
- **An explicit, justified "no automated verification" acknowledgment is
  allowed, and it is not the same thing as a placeholder.** Some work has
  no automated check available — a pure documentation wording change, a
  manual action in a third-party dashboard, a one-time infrastructure
  step. For that work, write a deliberate, visible sentence stating that
  no automated verification exists, why, and what manual check substitutes
  for it (for example: "No automated verification exists for this wording
  change; a human must read the rendered page and confirm the new copy is
  accurate."). This acknowledgment must be an explicit statement in the
  section — never a silently empty or omitted section, and never used as
  cover for a criterion that could actually be checked by a command you
  simply didn't look for.

## Step 6: Out of scope

State what a reader might reasonably assume is included but is not:
related work correctly deferred, a similar-looking case not being
handled, follow-up that belongs to a different ticket. This is distinct
from `Must not touch` (paths a diff must not modify) — this section is
about behavior and functionality the contract deliberately excludes, not
about file locations.

## Step 7: Completion evidence (filled after execution, never before)

While proposing or enriching a contract before work has started, this
section stays explicitly marked pending ("Pending — filled in after
execution") — never pre-filled with an anticipated result. After
execution, record what actually happened when the verification commands
from Step 5 ran: exit status, a relevant output excerpt, or a pointer to
the run. Evidence written here must come from commands that were actually
run, never asserted from memory or intention.

## What this skill does not do

- It does not decompose a large piece of work into multiple tickets or
  assign new canonical identities to anything — that is Matt Pocock's
  `to-tickets` (Step 0 and Step 1 above both defer to it explicitly).
- It does not add an AgentForge lifecycle status, assign a persona, route
  work to a specific model, or create or update any active-work/session
  state — those concerns live in `docs/plans/agentforge-v2-user-stories.md`
  (STORY-008 for active-work snapshotting, STORY-009/010 for context
  injection), never inside a work contract.
- It does not sequence migration phases or judge deletion safety — a
  migration's work contract can cite the sibling `migration-safety`
  skill's conclusion in its acceptance criteria or out-of-scope sections
  (for example, "deletion is gated on migration-safety's validation
  evidence") without re-deriving or repeating that skill's
  extract/expand/migrate/validate/contract/delete sequencing here.
- It does not compare a contract against separate reference documents for
  coverage gaps — see the sibling `reconcile-docs` skill.
- It does not enforce `May touch`/`Must not touch` at tool-call time —
  that is the separate, explicitly graded scope-policy engine
  (`STORY-013`/`STORY-014`); this skill only writes the boundary down.
