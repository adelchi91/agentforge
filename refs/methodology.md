# Methodology Reference

Injected as context into bootstrap agents. Dense and precise — not explanatory.

---

## The Five Mechanisms

| Mechanism | Location | Nature | Role |
|---|---|---|---|
| CLAUDE.md | project root | Deterministic | Project constitution — loaded in every session |
| Skills | `.claude/skills/` | Probabilistic | Knowledge chunks — injected on demand by trigger |
| Hooks | `.claude/hooks/` | Deterministic | Guardrails — enforced unconditionally at runtime |
| Agents | `.claude/agents/` | Probabilistic | Personas — isolated context + model assignment |
| Stories | `.claude/stories/` | Contract | Units of work — acceptance criteria + verification |

**Deterministic:** always executes regardless of agent reasoning.
**Probabilistic:** loaded by Claude Code when content matches trigger conditions.

---

## Core Rules

1. Agents and skills are always separate files. A skill never defines a persona. An agent never contains knowledge (commands, templates, field definitions, reference docs).
2. Safety rules go in hooks, not in agent instructions. Any rule that must hold unconditionally belongs in a hook with `exit 2`.
3. `exit 2` is the only hard stop in Claude Code. `exit 1` is a soft warning (Claude may continue). `exit 0` allows. Only `exit 2` unconditionally blocks.
4. Model assignment is mandatory per agent. No agent file may omit the `model:` frontmatter field.
5. Every story must have runnable verification commands. No prose descriptions. Real shell commands that produce a pass/fail signal.
6. The golden rule for migrations: if a project has existing code, nothing is deleted until the final phase is fully validated and final-judge has approved.

---

## Model Routing Table

| Task type | Model | Rationale |
|---|---|---|
| Architectural judgment, ADRs, story authoring | `claude-sonnet-4-6` | Requires reasoning over ambiguous requirements |
| Final approval, review decisions | `claude-sonnet-4-6` | Approval requires judgment, not pattern-matching |
| Deterministic implementation, file migration | `claude-haiku-4-5-20251001` | Speed + cost efficiency for templated work |
| Command execution, PASS/FAIL reporting | `claude-haiku-4-5-20251001` | Output is deterministic from command results |
| Mechanical restructuring, copy operations | `claude-haiku-4-5-20251001` | No ambiguity in task definition |

Built-in agents (`Explore`, `Plan`) — use as-is. Do not redefine them.

---

## Decision Framework

When creating a new file or rule, apply these four questions in order:

1. Must this be enforced unconditionally (cannot be argued away by Claude)?
   **YES → Hook (`exit 2`)** | NO → continue

2. Does this define who an agent IS and what it can do?
   **YES → `agents/*.md`** | NO → continue

3. Does this define what an agent KNOWS?
   **YES → `skills/*.md`** | NO → continue

4. Does this apply to every session without exception?
   **YES → `CLAUDE.md`** | NO → story file or inline context

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

1. **Load context.** Read `CLAUDE.md`. Read the assigned story file. Read any referenced skills.
2. **State intent.** Declare the story being worked on and the scope constraints that apply.
3. **Checkpoint.** Before any file modification, display: what will change, risk level (Low / Medium / High), wait for `GO`.
4. **Execute.** Act within scope. Reference the story ID in every git commit message.
5. **Verify.** Run all verification commands from the story file. Record PASS or FAIL explicitly.
6. **Summarise.** Write session summary and hand off to next agent in the handoff chain.

---

## Standard Agent Set

| Agent | Model | Scope | Role |
|---|---|---|---|
| `final-judge` | Sonnet | Full repo (read only) | Human-in-the-loop approval authority |
| `tester` | Haiku | Read + Bash only | Runs verification commands, writes reports |
| `architect` | Sonnet | Read + write docs/stories | Writes ADRs, design decisions, stories |
| `dev` | Haiku | Restricted folder list | Implements stories mechanically |

Additional specialised agents are added per project domain.

---

## Hook Protocol

| Hook | Event | Action |
|---|---|---|
| `pre-tool-use.sh` | Before every Bash call | Blocks destructive commands; enforces STORY-XXX in commit messages |
| `post-tool-use.sh` | After every Write call | Auto-lints Python (ruff) and JS/TS (eslint) |
| `stop.sh` | Session end | Appends record to `.claude/session-log.txt` |

All hooks use `exit 2` for hard blocks. Registered in `settings.json`. Cannot be disabled by agent instructions.

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
