# STORY-001 — Initialise Package Structure

## Status: READY FOR DEVELOPMENT
## Agent: dev (model: sonnet)
## Phase: 1 — Foundation
## Depends on: none
## Estimated effort: 1 session

---

## Context

`mylib` is a new greenfield Python utility library for data validation.

---

## Scope

**May touch:**
- `src/mylib/`
- `tests/`

**Must NOT touch:**
- Nothing exists to protect — this is greenfield.

---

## Acceptance Criteria

- `pyproject.toml` exists at repo root with correct metadata
- `pytest tests/` runs and passes

---

## Verification Commands

```bash
pytest tests/ -v --tb=short
```

---

## Out of Scope

- Implementing any validation functions.

---

## Handoff

dev session summary → security-reviewer
