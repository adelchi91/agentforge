# STORY-001 — Initialise Package Structure

## Status: READY FOR DEVELOPMENT
## Agent: dev (model: sonnet)
## Phase: 1 — Foundation
## Depends on: none
## Estimated effort: 1 session (1–2 hours)

---

## Context

`mylib` is a new greenfield Python utility library for data validation. This story creates
the complete package structure: `pyproject.toml`, `src/` layout, initial module files,
CI configuration, and import tests.

---

## Scope

**May touch:**
- All files at repo root (`.gitignore`, `pyproject.toml`, `README.md`)
- `src/mylib/` (create entire directory and initial files)
- `tests/` (create, with initial import test)

**Must NOT touch:**
- Nothing exists to protect — this is greenfield.

---

## Acceptance Criteria

- `pyproject.toml` exists at repo root with correct metadata
- `src/mylib/__init__.py` exists and defines `__version__ = "0.1.0"`
- `pytest tests/` runs and passes

---

## Verification Commands

```bash
pip install -e ".[dev]"
pytest tests/ -v --tb=short
```

---

## Out of Scope

- Implementing any validation functions — that is Phase 2 work.
- Publishing to PyPI or TestPyPI — not in scope for this project.

---

## Handoff

dev session summary → tester → final-judge
