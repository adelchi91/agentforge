# ADR-0002: One work-item tracker is the source of truth per project

## Status

Accepted

## Context

v1 stories lived only as generated Markdown files under `.claude/stories/`
or `.agents/stories/`, authored by the `planner` agent during Step 5 of
the bootstrap interview. v2 introduces `/agentforge:prepare-work <id>`
(STORY-008) and tracker adapters (STORY-006) that must resolve a work
item's identity, status, and blockers from *somewhere* — GitHub, GitLab,
or a local Markdown file. Multiple simultaneous notions of "the" status of
a ticket (a stale local snapshot vs. a live tracker vs. a hand-edited
story file) would make active-work context injection (STORY-009,
STORY-010) unreliable, since hooks would have no way to know which source
to trust.

## Decision

Each project configures exactly one tracker as its source of truth via
`tracker.type` (`github`, `gitlab`, or `local`) in the committed
AgentForge config (STORY-004). `scripts/work_items.py` (STORY-006)
resolves a canonical `WorkItem` identity from that one configured
provider only; a bare identifier is rejected as ambiguous rather than
guessed when the provider is unclear. `.agentforge/active-work.json` is a
local, gitignored, size-bounded *snapshot* of that source of truth — never
an independent record that can drift into being authoritative on its own.
Lifecycle hooks read only this snapshot and never make network calls
(ADR-0005); only `/agentforge:prepare-work` refreshes it from the
configured tracker.

## Consequences

- Context-injection hooks (STORY-009, STORY-010) can stay simple and
  network-free: they trust one local file instead of reconciling multiple
  possibly-conflicting sources.
- Switching a project's tracker type is an explicit, visible config change
  (`tracker.type`), not something hooks infer per call.
- A stale snapshot is possible between tracker updates and the next
  `/agentforge:prepare-work` run; this is an accepted, documented latency,
  not a correctness bug, because the snapshot always names its own
  `fetched-at` timestamp.
- Local Markdown remains a fully supported, zero-network tracker type, not
  a fallback bolted on when a remote tracker is unreachable.

## Rejected alternatives

- **Treat the local story file and the remote tracker as co-equal
  sources, reconciled at read time.** Rejected: reconciliation logic
  (whose status wins on conflict?) adds complexity STORY-006/007 do not
  need, and every hook consumer would have to re-implement the same
  tie-breaking.
- **Let hooks fetch the tracker directly for freshness.** Rejected by
  ADR-0005 (no network access inside hooks) independently of this
  decision, but also rejected here because it reintroduces the exact
  multiple-sources problem this ADR avoids.
- **Support multiple simultaneously configured trackers per project.**
  Rejected as unnecessary complexity for the target audience (small teams
  on one GitHub/GitLab org or one local backlog); revisit only if a real
  multi-tracker use case is reported.
