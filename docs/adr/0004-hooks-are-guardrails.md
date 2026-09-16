# ADR-0004: Hooks are guardrails and defense in depth, not a security sandbox

## Status

Accepted

## Context

v1's README and METHODOLOGY.md describe hooks in strong terms ("cannot be
disabled by agent instructions," "hard-block safety-critical actions").
That framing is true as far as it goes — an agent cannot argue a hook out
of firing — but `tests/test_v1_characterization.py` demonstrates that the
actual coverage has real gaps: `git -C <dir> push` and `git -C <dir>
commit` bypass the STORY-XXX and destructive-command checks entirely,
Bash-driven file writes are never scope-checked, a STORY-XXX token
anywhere in the command line satisfies the commit check, and malformed
JSON input fails open rather than closed. Continuing to describe this
layer as a security boundary would be a false claim once v2 users start
relying on it for anything beyond UX nudges.

## Decision

AgentForge stops claiming that lifecycle hooks (Claude/Codex PreToolUse,
PostToolUse, etc.) form a security boundary. Hooks provide context, UX
feedback, audit trail, and defense in depth. Hard enforcement is owned by
native sandboxing/permissions, Git hooks (`commit-msg`, `pre-push`;
STORY-011, STORY-012), CI, and branch protection/human approval — systems
outside the agent's own tool-call loop that cannot be bypassed by a
differently-phrased shell command. AgentForge's config (STORY-004) must
name its own assurance level honestly through explicit policy modes
(`off`/`observe`/`ask`/`deny-structured`/`strict-agent`; ADR text in the
execution plan), and documentation must never call any of them a "secure
sandbox."

## Consequences

- Commit-message traceability moves to a Git `commit-msg`/`pre-push` hook
  as the source of truth (STORY-011, STORY-012); a Claude/Codex
  PreToolUse check on `git commit`/`git push` is retained only as an
  early, explicitly non-authoritative UX warning.
- `scripts/scope_policy.py` (STORY-013, STORY-014) documents, per mode,
  exactly what is and is not covered — e.g. `deny-structured` explicitly
  states that unrestricted Bash is outside its coverage — instead of
  implying blanket protection.
- A threat model document (`docs/threat-model.md`, called for in the
  execution plan's target architecture) is required output, not optional
  polish, because the honesty requirement in this ADR is only meaningful
  if the gaps are written down somewhere a user will read.
- Any future PR that tightens hook coverage must not claim it closes "the
  security gap" — only Git-hook/CI/branch-protection changes get to make
  that claim.

## Rejected alternatives

- **Keep the v1 language and just fix the seven characterized bugs.**
  Rejected: even a perfectly bug-free regex/path-matching layer running
  inside the agent's own tool-call loop cannot classify arbitrary Bash
  reliably (shell indirection, `python -c`, encoded commands), so the
  "hard security boundary" claim would still be false regardless of how
  many specific bugs are fixed.
- **Drop lifecycle hooks entirely and rely only on Git hooks + CI.**
  Rejected: lifecycle hooks still provide real value as immediate,
  same-turn feedback and context injection that Git hooks (which only run
  at commit/push time) and CI (which only runs after push) cannot
  provide.
