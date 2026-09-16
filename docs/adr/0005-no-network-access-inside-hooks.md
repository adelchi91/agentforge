# ADR-0005: No hook performs a network call

## Status

Accepted

## Context

v2 introduces remote tracker adapters (GitHub/GitLab, STORY-006) and
active-work context restoration on every lifecycle boundary — startup,
resume, clear, and compaction (STORY-009), plus per-prompt context
injection (STORY-010). Lifecycle hooks run synchronously and block the
agent's turn while they execute; the execution plan's "Definition of
done" requires the SessionStart hook to complete within 100ms on fixture
data. A hook that reaches out to a remote tracker on every session start,
resume, or keystroke-adjacent prompt submission would be slow, flaky
under network conditions outside AgentForge's control, and would turn a
guardrail into a dependency the whole session stalls on.

## Decision

No AgentForge lifecycle hook (`SessionStart`, `UserPromptSubmit`,
`PreToolUse`, `PostToolUse`, `SubagentStop`, `PreCompact`, `SessionEnd`/
`Stop`) makes a network call, directly or by shelling out to a CLI that
does. Remote work-item fetching happens only inside explicit,
user-invoked skill operations — `/agentforge:setup` and
`/agentforge:prepare-work <id>` — which fetch once, sanitize and
size-bound the result, and write it to the local
`.agentforge/active-work.json` snapshot (ADR-0002). Every hook reads only
that local snapshot and the committed config; a fetch failure during
`prepare-work` must preserve the previous valid snapshot rather than
corrupting it.

## Consequences

- STORY-006's tracker adapters must be structured so their network code
  paths are reachable only from `prepare-work`/`setup`, never imported
  into a hook entry point.
- STORY-009/STORY-010's test suites can assert hook performance and
  correctness using only local fixtures, with no network mocking
  required and no flakiness from external services.
- Users must explicitly re-run `/agentforge:prepare-work` to refresh
  tracker state; hooks will happily operate on a stale snapshot rather
  than silently going stale *and* slow.
- Codex parity (STORY-018) is simpler to verify, since "no network calls"
  is a single cross-cutting property to test once rather than a
  per-platform behavior.

## Rejected alternatives

- **Fetch lazily inside SessionStart only when the snapshot looks
  stale.** Rejected: reintroduces unpredictable per-session latency and
  failure modes (auth prompts, rate limits) into a hook whose contract
  promises a fast, deterministic response.
- **Fetch in a background thread/process from the hook and let the
  session continue.** Rejected: hook processes are short-lived
  request/response scripts under the Claude/Codex hook contract, not
  long-running daemons; a detached background fetch has no reliable way
  to report failure back into the session, undermining ADR-0002's "never
  corrupt existing state on failure" guarantee.
