# ADR-0006: Runtime hook/policy code stays in the plugin, never copied into projects

## Status

Accepted

## Context

v1's `install.sh` and scaffolder copy `templates/shared/hooks/*.py`
directly into each generated project (`.claude/hooks/` or
`.codex/hooks/`). This means every bootstrapped project freezes its own
copy of the hook suite at scaffold time: fixing a bug in v1's hooks (the
seven characterized in this story) does nothing for a project already
generated — the fix never reaches it without a separate, unspecified
re-sync step. The target v2 architecture instead references scripts via
`${CLAUDE_PLUGIN_ROOT}` and stores only project-specific state
(`.agentforge/config.json`, `.agentforge/active-work.json`) inside the
project.

## Decision

AgentForge v2's runtime scripts (`scripts/*.py`, hook entry points) live
only inside the plugin and are referenced from `hooks/hooks.json` through
`${CLAUDE_PLUGIN_ROOT}`. Nothing under `scripts/` or the hook entry points
is copied into a generated or `/agentforge:setup`-configured project.
Project state written into a project is limited to committed
configuration (`.agentforge/config.json`) and gitignored runtime state
(`.agentforge/active-work.json`) — data, never code. A project's Git-level
enforcement (`commit-msg`, `pre-push`; STORY-011/012) is the one
deliberate exception, because those must exist inside `.git/hooks` (or a
chained dispatcher) of the project's own repository to run at commit/push
time at all — even there, the installed script is a thin dispatcher that
still delegates policy logic to `scripts/git_policy.py` inside the plugin
where the environment supports it, rather than embedding the policy
itself.

## Consequences

- A plugin update (bug fix, new policy mode) reaches every project using
  it the next time the plugin runs, without any per-project migration
  step for the Claude/Codex-side hooks.
- `/agentforge:setup` and the STORY-019 migration skill must never write
  a copy of `scripts/*.py` into a project; a migration fixture containing
  a copied v1 hook script is a case STORY-019's tests must specifically
  cover and archive, not preserve as the new pattern.
- Git-hook installation (STORY-011) must detect and report its one
  necessary exception clearly, so `${CLAUDE_PLUGIN_ROOT}`-only policy
  does not create a false expectation that *nothing* is ever written
  into a project's `.git/`.

## Rejected alternatives

- **Keep copying hooks into each project, as v1 does, and fix the
  characterized bugs in the copied version.** Rejected: perpetuates the
  exact problem this ADR addresses — every existing project would still
  need a manual re-copy to receive any future fix, indefinitely.
- **Copy hooks into the project but add a version marker and an update
  command.** Rejected as unnecessary complexity: `${CLAUDE_PLUGIN_ROOT}`
  referencing already solves "the project always runs the current
  version" with no extra moving parts, for every hook except the
  Git-level ones that must live in `.git/`.
