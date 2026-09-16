# ADR-0007: Migration safety is a domain-specific discipline, not a default phase gate

## Status

Accepted

## Context

METHODOLOGY.md's Rule 6 ("golden rule for migrations": nothing is deleted
until the final phase is validated and approved) was, in v1, a global
constitution rule applied uniformly regardless of whether a given project
or story was actually a migration. The v2 execution plan instead scopes
this discipline to a dedicated `migration-safety` skill (STORY-016) that
combines extract/expand/migrate/validate/contract/delete sequencing with
an explicit no-delete-before-validation policy, applied only when the
work at hand is classified as a migration. STORY-019 (v1→v2 migration
itself) is explicitly required to obey this same discipline: v1 assets
must not be deleted before characterization and migration tests exist.

## Decision

Migration safety is a model-invoked skill that activates when the work
item is a migration, not a phase structure forced onto every project or
every story. Ordinary brownfield feature work, bug fixes, and
documentation-only changes are never required to declare extract/expand/
migrate/validate/contract/delete phases. The skill's eval fixtures
(STORY-016's acceptance criteria) must include cases that distinguish
migration work from ordinary brownfield feature work, and migration
deletion may never be recommended before replacement-verification
evidence exists — mirroring the same rule this ADR applies to STORY-019's
own execution: v1 files are archived, never deleted, until v2's
equivalents are validated (see the "Execution protocol" step in the plan
and STORY-019's requirements).

## Consequences

- A project adopting AgentForge v2 for ordinary feature work sees no
  migration ceremony at all; the skill simply never triggers.
- `reconcile-docs` (STORY-016, sibling skill) and `migration-safety` stay
  separable: reconciliation applies to any spec/ticket graph, migration
  sequencing applies only to migrations, and neither may be merged into a
  single always-on discipline.
- This story (STORY-001) itself is bound by the same principle in
  practice: v1's hook scripts, examples, and templates are left
  completely unmodified, and the recovery tag is created explicitly so
  that no later story can restructure v1 assets without a validated
  rollback point.

## Rejected alternatives

- **Keep the global "golden rule" as a constitution-level rule applied to
  every bootstrapped project.** Rejected: forces migration ceremony
  (explicit phase sequencing) onto projects that never touch existing
  code, which the v1 methodology already only intended for the
  monorepo-migration case documented in `examples/lagrangia/`.
- **Fold migration safety into `work-contract` as a mandatory contract
  section.** Rejected: most work contracts describe ordinary feature or
  bug work with no extract/expand/contract/delete structure; forcing the
  section onto every contract would produce placeholder ceremony exactly
  like the ceremony this rebuild is removing elsewhere (STORY-017).
