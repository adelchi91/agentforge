# Methodology Reference

Injected as context into bootstrap agents. Dense and precise — not explanatory.
The methodology is platform-neutral; file locations branch by target platform.

---

## The Five Mechanisms

| Mechanism | Claude target | Codex target | Nature | Role |
|---|---|---|---|---|
| Constitution | `CLAUDE.md` | `AGENTS.md` | Deterministic | Project rules loaded every session |
| Skills | `.claude/skills/` | `.agents/skills/` | Probabilistic | Knowledge chunks loaded on demand |
| Hooks | `.claude/hooks/` + settings.json | `.codex/hooks/` + hooks.json | Deterministic | Guardrails enforced at runtime |
| Agents | `.claude/agents/*.md` | `.codex/agents/*.toml` | Probabilistic | Personas + model assignment |
| Stories | `.claude/stories/` | `.agents/stories/` | Contract | Units of work + verification |

**Deterministic:** always executes regardless of agent reasoning.
**Probabilistic:** loaded by the runtime when content matches trigger conditions or agent use.

---

## Core Rules

1. Agents and skills are always separate files. A skill never defines a persona. An agent never contains knowledge (commands, templates, field definitions, reference docs).
2. Safety rules go in hooks, not in agent instructions. Any rule that must hold unconditionally belongs in a hook. This includes agent write scopes: the Repo Ownership table is compiled into `scopes.json` and enforced by the PreToolUse hook.
3. Hooks block unsafe work; generated hook scripts read the hook payload as JSON on stdin and use `exit 2` for hard blocks.
4. Model assignment is mandatory per agent. Claude agents use frontmatter with model **aliases** (`opus`/`sonnet`/`haiku`, or `inherit`); Codex agents use TOML with model IDs. Codex agents include `sandbox_mode` when scope maps cleanly to `read-only` or `workspace-write`.
5. Every story must have runnable verification commands. No prose descriptions. Real shell commands that produce a pass/fail signal.
6. The golden rule for migrations: if a project has existing code, nothing is deleted until the final phase is fully validated and final-judge has approved.

---

## Model Routing Table

| Task type | Claude model | Codex model | Rationale |
|---|---|---|---|
| Architectural judgment, ADRs, story authoring | `opus` | `gpt-5.5` high reasoning | Requires reasoning over ambiguous requirements |
| Final approval, review decisions | `opus` | `gpt-5.5` high reasoning | Approval requires judgment |
| Story implementation (code, features, refactors) | `sonnet` | `gpt-5.5` medium reasoning | Real coding work at implementation-tier cost |
| Command execution, PASS/FAIL reporting | `haiku` | `gpt-5.4-mini` low/medium reasoning | Output is determined by command results |
| Mechanical restructuring, copy operations | `haiku` | `gpt-5.4-mini` low reasoning | No ambiguity in task definition |

Claude aliases track the current lineup (today: Opus 4.8, Sonnet 5, Haiku 4.5) so
generated projects never pin stale IDs. `fable` (Claude Fable 5) is an opt-in for the
hardest judgment work only — see `refs/model_routing.md`.

Built-in agents — use as-is. Claude: `Explore`, `Plan`. Codex: `explorer`, `worker`, `default`.

---

## Decision Framework

When creating a new file or rule, apply these four questions in order:

1. Must this be enforced unconditionally (cannot be argued away by the agent)?
   **YES → Hook** | NO → continue

2. Does this define who an agent IS and what it can do?
   **YES → Claude `agents/*.md`; Codex `.codex/agents/*.toml`** | NO → continue

3. Does this define what an agent KNOWS?
   **YES → Claude `skills/*.md`; Codex `.agents/skills/*/SKILL.md`** | NO → continue

4. Does this apply to every session without exception?
   **YES → Claude `CLAUDE.md`; Codex `AGENTS.md`** | NO → story file or inline context

---

## Story Lifecycle

Status values in order — no story may skip a status:

| Status | Meaning | Transition trigger |
|---|---|---|
| `READY FOR DEVELOPMENT` | Approved and waiting | Previous story merged |
| `IN PROGRESS` | Dev agent working | Agent picks up the story |
| `READY FOR TESTING` | Dev done, tests not run | Dev writes session summary |
| `TESTING` | Tester running verification | Tester agent picks up |
| `APPROVED` | Tester passed, final-judge approved | final-judge issues approval |
| `MERGED` | PR merged into main | CI green, merge complete |

---

## Session Protocol

Every agent session follows these six steps:

1. **Load context.** Read the constitution (`CLAUDE.md` or `AGENTS.md`). Read the assigned story file. Read any referenced skills.
2. **State intent.** Declare the story being worked on and the scope constraints that apply.
3. **Checkpoint.** Before any file modification, display: what will change, risk level (Low / Medium / High), wait for `GO`.
4. **Execute.** Act within scope. Reference the story ID in every git commit message.
5. **Verify.** Run all verification commands from the story file. Record PASS or FAIL explicitly.
6. **Summarise.** Write session summary and hand off to next agent in the handoff chain.

---

## Standard Agent Set

| Agent | Model class | Scope | Role |
|---|---|---|---|
| `final-judge` | Judgment | Full repo (read only) | Human-in-the-loop approval authority |
| `tester` | Deterministic | Read + Bash only | Runs verification commands, writes reports |
| `architect` | Judgment | Read + write docs/stories | Writes ADRs, design decisions, stories |
| `dev` | Implementation | Restricted folder list | Implements stories within scope |

Additional specialised agents are added per project domain.

---

## Hook Protocol

One shared set of Python hook scripts serves both platforms (Claude Code and Codex use
the same hook stdin-JSON contract). Claude registers them in `.claude/settings.json`;
Codex registers them in `.codex/hooks.json`.

| Event | Script | Action |
|---|---|---|
| SessionStart | `session_start.py` | Injects the Golden Rule and the active story into session context |
| UserPromptSubmit | `user_prompt_submit.py` | Injects the referenced story's Scope / Out of Scope sections |
| PreToolUse | `pre_tool_use.py` | Blocks destructive commands; enforces STORY-XXX in commits/pushes; enforces per-agent write scopes from `scopes.json` |
| PostToolUse | `post_tool_use.py` | Auto-lints Python (ruff) and JS/TS (eslint) on Write/Edit |
| SubagentStop | `subagent_stop.py` | Appends a handoff-chain record to the session log |
| PreCompact | `pre_compact.py` | Records active story + branch so state survives compaction |
| SessionEnd (Claude) / Stop (Codex) | `session_end.py` | Appends a session record |

All generated hook scripts read the hook payload as JSON on stdin and use `exit 2` for
hard blocks. Codex parity notes: Codex has no `SessionEnd` event (the session record is
registered on `Stop`, so it fires per turn there), and Codex requires project hooks to be
reviewed and trusted via `/hooks` before they run.

---

## Story Authoring Rules

1. One story = one agent can complete it in one session.
2. Sequential numbering across all phases: STORY-001, STORY-002, …
3. First story of Phase N depends on last story of Phase N-1.
4. Every story has an explicit `Depends on:` field (`none` for the first story).
5. `Out of scope` section is mandatory on every story.
6. Verification commands are real shell commands — never prose.
7. Each story is assigned to exactly one agent.
8. Story scope constraint (may touch / must not touch) is explicit and exhaustive.
