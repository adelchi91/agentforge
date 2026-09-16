# ADR-0001: AgentForge is a companion plugin, not a fork of mattpocock/skills

## Status

Accepted

## Context

AgentForge v1 owned a full linear methodology (constitution, agents,
skills, hooks, stories) end to end, including responsibilities — grilling,
spec writing, ticket decomposition, TDD, diagnosis, code review — that
overlap with Matt Pocock's independently maintained `mattpocock/skills`
plugin. Rebuilding v2 requires deciding how AgentForge relates to that
upstream project.

## Decision

Keep `adelchi91/agentforge` an independent repository and plugin. Users
install Matt's official plugin separately (or via a manifest
`dependencies` entry, see STORY-003) and load both plugins together;
Claude Code plugin skills are namespaced, so both sets of commands remain
usable side by side. AgentForge never vendors, periodically copies, or
wraps Matt's `skills/` directory, and never merges his Git history into
this repository. AgentForge's skills are named distinctly (`setup`,
`prepare-work`, `work-contract`, `reconcile-docs`, `migration-safety`) and
never shadow Matt's namespaced skill names.

## Consequences

- AgentForge's install instructions must document installing Matt's
  plugin as a separate step; setup cannot silently provide his
  functionality if he is missing.
- AgentForge cannot control the pace of Matt's changes; STORY-003 and
  STORY-020 must test against both a pinned known-good release and the
  current released plugin, and treat drift as a compatibility signal, not
  a build failure to suppress.
- If Matt renames or removes a skill AgentForge's flow diagrams reference
  (`grill-with-docs`, `to-spec`, `to-tickets`, `implement`, `code-review`),
  AgentForge's documentation goes stale until updated — there is no
  vendored copy to fall back on.
- A temporary fork of `mattpocock/skills` is permitted only to prepare an
  upstream pull request, and must be deleted once that contribution is
  submitted; it is never a long-lived AgentForge dependency.

## Rejected alternatives

- **Fork `mattpocock/skills` and add AgentForge fields to his files.**
  Rejected: creates permanent merge conflicts against upstream, and
  couples AgentForge's release cadence to manually re-applying patches
  onto every upstream update.
- **Vendor a copy of his skills into AgentForge's `skills/`.** Rejected:
  duplicates content that immediately goes stale, and creates the
  appearance that AgentForge owns work (grilling, TDD, code review) that
  the product boundary explicitly assigns to Matt's plugin.
- **Wrap every Matt command with an AgentForge-namespaced passthrough.**
  Rejected: adds indirection with no behavioral benefit and doubles the
  surface area to keep in sync with upstream changes.
