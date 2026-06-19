# STORY-001 — Scaffold Python Package

## Status: READY FOR DEVELOPMENT
## Agent: dev (model: gpt-5.4-mini)
## Phase: 1 — Foundation
## Depends on: none
## Estimated effort: S

---

## Context

Create the initial calc-kit package skeleton with test infrastructure and a CLI entry point.

**Architecture reference:** AGENTS.md

---

## Scope

**May touch:**
- `pyproject.toml`
- `src/calc_kit/`
- `tests/`

**Must NOT touch:**
- `.codex/`
- `.agents/`
- `roadmap.md`
- `project_context.md`

---

## Acceptance Criteria

- `pyproject.toml` defines the package metadata and CLI entry point.
- `src/calc_kit/__init__.py` exists.
- A baseline pytest test exists and passes.

---

## Verification Commands

```bash
uv run pytest
uv run calc-kit --help
```

---

## Out of Scope

- Implementing expression parsing or calculator behavior.
- Publishing the package.

---

## Handoff

dev report → tester → final-judge
