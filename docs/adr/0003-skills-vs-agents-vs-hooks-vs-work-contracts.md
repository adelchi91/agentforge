# ADR-0003: Skills, agents, hooks, and work contracts are four distinct mechanisms

## Status

Accepted

## Context

v1's METHODOLOGY.md already separated constitution/skills/hooks/agents/
stories by nature (deterministic vs. probabilistic vs. contract) and role.
v2 narrows AgentForge's scope (ADR-0001) and adds a new concept, the work
contract (STORY-007), which risks blurring back into agent or skill
territory if its boundary is not stated explicitly: a work contract could
easily be misimplemented as "a kind of skill" or "a kind of agent
instruction," which would put unconditional rules where they can be
argued away (see ADR-0004).

## Decision

Preserve v1's mechanism split and add a fourth explicit category:

- **Skills** (`skills/*/SKILL.md`) define what an agent *knows* —
  reusable disciplines, model-invoked or user-invoked. `work-contract`,
  `reconcile-docs`, and `migration-safety` are skills.
- **Agents** (`agents/*.md`) define who an agent *is* — a bundle of
  tools, permissions, and (optionally) a distinct model. AgentForge ships
  at most two optional agents (`independent-reviewer`, `verifier`; see
  STORY-017) and never a mandatory persona roster.
- **Hooks** (`hooks/hooks.json` + `scripts/*.py`) are deterministic
  guardrails that execute regardless of agent instructions (ADR-0004).
- **Work contracts** are data, not code or prose instructions: a
  structured record (What to build / Blocked by / Acceptance criteria /
  May touch / Must not touch / Verification commands / Out of scope /
  Completion evidence) that skills and hooks both read, but that neither
  a skill nor an agent file is allowed to embed inline as free text.

No AgentForge skill defines a persona, no AgentForge agent file embeds
domain knowledge or verification commands, and no work-contract field is
duplicated as prose inside a skill or agent file — the contract itself is
the single place that data lives.

## Consequences

- Adding a new AgentForge capability requires classifying it against this
  four-way split before writing any file; "it's a bit of everything" is
  treated as a sign the feature needs to be decomposed further.
- Work-contract enrichment (STORY-007) can be tested independently of any
  specific agent, since contracts are plain data validated on their own.
- The optional agents in STORY-017 stay genuinely optional: because
  contracts and hooks do not depend on any specific agent existing, a
  project can adopt AgentForge's governance layer without enabling either
  bundled agent.

## Rejected alternatives

- **Fold work contracts into the `prepare-work` skill's own prose
  output.** Rejected: makes the contract unversioned free text instead of
  a structured record hooks and evals can validate mechanically.
- **Model work contracts as a fifth kind of agent persona** (a "contract
  agent"). Rejected: contracts are not personas — they hold no tools,
  model, or delegation behavior, only structured facts about a unit of
  work.
- **Collapse skills and agents into one file type** (as some early v1
  drafts considered before METHODOLOGY.md's Rule 1). Rejected again here
  for the same reason it was rejected in v1: conflating who an agent is
  with what it knows makes both harder to reuse and test independently.
