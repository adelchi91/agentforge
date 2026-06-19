---
name: project-bootstrap
description: Bootstrap a software project with the project-bootstrap methodology for Claude Code or Codex. Use when the user asks to bootstrap, scaffold, set up an agentic workflow, define phases, create personas, generate stories, or initialize Claude/Codex project agents.
---

# Project Bootstrap

Run the same six-step methodology as the Claude `/bootstrap` command, but from Codex.
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

## Platform Rules

- Claude judgment agents use `claude-sonnet-4-6`; deterministic/test agents use `claude-haiku-4-5-20251001`.
- Codex judgment agents use `gpt-5.5` with high reasoning; deterministic/test agents use `gpt-5.4-mini` with low or medium reasoning.
- Codex custom agents set `sandbox_mode` to `read-only` for reviewers/testers/final-judge and `workspace-write` for implementation agents.
- Skills are knowledge-only. Agents are persona-only. Hooks hold safety policy. Stories are work contracts with runnable verification commands.
- Use `AGENTS.md` as the Codex constitution and `CLAUDE.md` as the Claude constitution.
