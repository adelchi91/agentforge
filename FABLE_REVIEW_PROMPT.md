# Review & modernize the `project-bootstrap` template — prompt for Claude Fable

> Paste everything below the line into a Claude Fable session opened at the root of
> `claude_code_template/`. It is written to be run by a strong model with repo access,
> web search, and file-edit tools.

---

## Who you are and what I want

You are auditing and upgrading **`project-bootstrap`** — a template/tool that scaffolds a complete
agentic development environment (constitution, agents, skills, hooks, stories, model-routing) for a
software project, targeting **both Claude Code and OpenAI Codex** from a single interview flow.

The methodology is documented in `METHODOLOGY.md` and mirrored in `refs/`. Read those first; they are
the spec this tool is supposed to encode.

My goal: make this **the best-in-class templating tool for launching agentic coding projects on the
latest Claude *and* Codex features**. You are smart and I want your judgment — form **strong opinions**
about what "best" looks like and defend them, but **ask me when a decision is genuinely mine to make**
(scope, packaging strategy, backward-compatibility, anything that changes the product's identity).

## How to work — four phases, with a gate before you edit

**Phase 1 — Audit.** Read every file in the repo (don't skip `steps/`, `templates/claude/`,
`templates/codex/`, `agents/`, `commands/`, `examples/`, `install.sh`). Build a full mental model of how
a `/bootstrap` run flows end to end for each target. Produce a prioritized findings list:
correctness bugs first (things that are broken against current tooling), then staleness, then missing
modern capabilities, then polish. For each finding, cite the exact file/line and say why it matters.

**Phase 2 — Research current best practices.** Do NOT trust your priors on tool APIs — they move fast.
Use web search + fetch the official docs and verify the *current* schema for everything you plan to
change. At minimum confirm against:
- Claude Code: hooks (`code.claude.com/docs/en/hooks` — exact stdin JSON schema, full event list,
  exit codes, `hookSpecificOutput`), subagents (`code.claude.com/docs/en/sub-agents` — frontmatter
  field names), model config, skills (`SKILL.md`), and the **plugin + marketplace** packaging format.
- Codex: `developers.openai.com/codex/` — custom agents TOML schema, `hooks`, `config.toml` keys,
  AGENTS.md discovery order, current models and reasoning-effort values, `sandbox_mode`.
- Current model lineups for both vendors (names change — verify, don't assume).
Summarize what you learned that changes your plan.

**Phase 3 — Plan (STOP for my approval here).** Present a concrete change plan: what you'll edit,
what you'll add/remove, the new model-routing table, the new packaging approach, and any breaking
changes. Flag every open question. **Wait for my explicit approval before editing any file.**

**Phase 4 — Edit.** Implement the approved plan. Keep the five-mechanism separation intact. After
editing, verify: no unfilled `{{TEMPLATE_VARS}}` remain in `examples/`, the examples still cohere with
the templates, hook scripts are syntactically valid, and every story still has runnable verification
commands. Deliver a change log grouped by (a) correctness fixes, (b) modernization, (c) additions,
with before/after for anything non-obvious.

## Confirmed starting checklist (verify each, then go beyond it)

I already audited the repo and confirmed these against current docs. Treat this as a seed, not a
ceiling — independently find what I missed:

**Correctness bugs**
1. **Claude hooks read the wrong input.** `templates/claude/hooks/*.sh` read `CLAUDE_TOOL_NAME` /
   `CLAUDE_TOOL_INPUT` env vars. Claude Code passes hook data as **JSON on stdin** (`tool_name`,
   `tool_input`, `tool_response`, etc.). As written the hooks won't function. Rewrite to parse stdin.
2. **`post-tool-use.sh` reads the wrong key** — `data.get('path')`; the Write tool input key is
   `file_path`. Even after fixing stdin, it won't find the file.
3. **Wrong subagent frontmatter key.** Agent files (`agents/*.md`, `templates/claude/agent.md`) use
   `allowed-tools:`. Claude Code **subagents use `tools:`** — `allowed-tools` is the slash-command key,
   so agents are probably silently inheriting *all* tools. Verify and fix across all agent files and
   the template.

**Staleness**
4. **Stale Claude models.** Routing pins `claude-sonnet-4-6` for judgment and
   `claude-haiku-4-5-20251001` for deterministic work. Current lineup: `claude-opus-4-8`,
   `claude-sonnet-5`, `claude-haiku-4-5`, and `claude-fable-5` (most capable). Rebuild the routing
   table across `METHODOLOGY.md`, `refs/methodology.md`, `refs/model_routing.md`, `steps/04_personas.md`,
   `agents/*.md`, `commands/add-agent.md`, and `.agents/skills/project-bootstrap/SKILL.md`. Decide with
   justification where Fable/Opus vs Sonnet vs Haiku belong, and whether to use aliases
   (`opus`/`sonnet`/`haiku`/`fable`) vs pinned IDs. Verify Codex models (`gpt-5.5`, `gpt-5.4-mini`,
   reasoning-effort values) are still current too.

**Missing modern capability**
5. **Only 3 hook events used** (PreToolUse/PostToolUse/Stop). Claude Code now exposes ~12 lifecycle
   events. Evaluate adding, e.g., `UserPromptSubmit` (inject the active story's scope/constraints),
   `SessionStart` (load `.bootstrap`/story state), `SubagentStop` (enforce the handoff chain), and
   `PreCompact`. Mirror worthwhile ones on the Codex side (`SubagentStart`, `PostCompact`, etc.).
6. **Legacy packaging.** Distribution is `curl | bash` (`install.sh`). Evaluate shipping this as a
   proper **Claude Code plugin with a marketplace manifest** (bundling agents, skills, commands, hooks)
   and the Codex equivalent, while keeping an install path for non-plugin users. This is a product
   decision — give me your recommendation and ask before committing to it.
7. **Unused modern subagent fields:** `permissionMode`, `skills`, `memory`, `mcpServers`, `model`
   aliases. Decide which the template should set by default.
8. **Verify the Codex custom-agent TOML schema** (`developer_instructions` key, `skills.config`,
   `mcp_servers`) against current Codex docs, and confirm `commands/*.md` frontmatter (`agent:` key)
   is a valid slash-command field.

## Constraints
- Preserve the methodology's core: agents ≠ skills ≠ hooks ≠ stories ≠ constitution; safety lives in
  hooks; every story has runnable verification; migrations delete only in the final phase.
- Keep Claude and Codex at feature parity where the platforms allow it; note where they can't match.
- Don't break the `examples/` — update them in lockstep with any template change.
- Every claim about a tool's behavior must be backed by something you verified in Phase 2, not memory.

Start with Phase 1 now.
