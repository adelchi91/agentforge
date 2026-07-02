---
name: project-bootstrap
description: Bootstrap a software project with the project-bootstrap methodology for Claude Code or Codex. Use when the user asks to bootstrap, scaffold, set up an agentic workflow, define phases, create personas, generate stories, or initialize Claude/Codex project agents.
---

# Project Bootstrap

Run the same six-step methodology as `/bootstrap`, but from Codex. The invocation
surface and output target are separate: this skill can scaffold either `CLAUDE` or
`CODEX`, based on the user's target selection.
Prefer the repository's source files when present. If this skill was installed by
`install.sh codex`, use the bundled `bootstrap/` directory next to this `SKILL.md`.

- `commands/bootstrap.md` for orchestration
- `steps/01_documents.md` through `steps/06_scaffold.md` for the step contracts
- `refs/methodology.md`, `refs/decision_framework.md`, and `refs/model_routing.md` for rules
- `templates/claude/`, `templates/codex/`, and `templates/shared/` for generated files

## Workflow

1. Ask which target to scaffold: `CLAUDE` or `CODEX`. Write it to `.bootstrap/target_platform.md`.
2. Run Step 1 through Step 6 exactly as described in `steps/`.
3. Keep all intermediate state in `.bootstrap/`.
4. Do not write target scaffold files until Step 6 and explicit `GO`.
5. For `CLAUDE`, generate `.claude/CLAUDE.md`, `.claude/settings.json`, `.claude/agents`, `.claude/skills`, `.claude/hooks`, and `.claude/stories`.
6. For `CODEX`, generate `AGENTS.md`, `.codex/agents/*.toml`, `.codex/hooks.json`, `.codex/hooks/*`, `.agents/skills`, and `.agents/stories`.

## Validation Gates

- Run the workflow in the active conversation, not as a backgrounded subagent.
- Stop after every step and wait for explicit user validation before continuing.
- `OK` advances to the next step. `BACK` revisits the previous step.
- `GO` is valid only after the Step 6 scaffold checkpoint has been displayed.
- Do not batch Step 2 through Step 6 after reading reference documents.
- Use only the canonical state files: `.bootstrap/target_platform.md`,
  `.bootstrap/00_docs.md`, `.bootstrap/02_context.md`, `.bootstrap/03_roadmap.md`,
  `.bootstrap/04_personas.md`, and `.bootstrap/stories/STORY-XXX.md`.

## Platform Rules

- Claude agents use model aliases: judgment → `opus`, implementation → `sonnet`,
  deterministic/test → `haiku`. Claude agent frontmatter uses the `tools:` key.
- Codex judgment agents use `gpt-5.5` with `model_reasoning_effort = "high"`;
  implementation agents use `gpt-5.5` with `"medium"`; deterministic/test agents use
  `gpt-5.4-mini` with `"low"` or `"medium"`.
- Codex custom agents set `sandbox_mode` to `read-only` for reviewers/testers/final-judge and `workspace-write` for implementation agents.
- Hook scripts are shared between platforms (`templates/shared/hooks/*.py`) — both
  platforms deliver the hook payload as JSON on stdin. Claude registers them in
  `.claude/settings.json`; Codex registers them in `.codex/hooks.json`.
- The Repo Ownership table is compiled into `scopes.json` and enforced by the
  PreToolUse hook — agent scope is a guardrail, not just an instruction.
- After a Codex scaffold, remind the user to trust the generated hooks via `/hooks`
  (Codex does not run untrusted project hooks).
- Skills are knowledge-only. Agents are persona-only. Hooks hold safety policy. Stories are work contracts with runnable verification commands.
- Use `AGENTS.md` as the Codex constitution and `CLAUDE.md` as the Claude constitution.
