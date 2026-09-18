# STORY-001 — Extract dessia-memory package

## Status: DONE
## Agent: dev-memory (model: sonnet)
## Phase: 1 — Extract dessia-memory
## Depends on: none
## Estimated effort: 1 session

---

## Context

Extract the ChromaDB-backed memory layer into a standalone `dessia-memory` package,
importable independently of the monorepo.

---

## Scope

**May touch:**
- `dessia-memory/` (all files)

**Must NOT touch:**
- `dessiaworker/`
- `dessia-tools/`

---

## Acceptance Criteria

- `dessia-memory` is importable as a standalone package
- All existing memory tests pass unchanged

---

## Verification Commands

```bash
cd dessia-memory && python -m pytest tests/ -v
```

---

## Out of Scope

- Extracting `dessia-tools` — that is STORY-002.

---

## Handoff

dev-memory session summary → tester → final-judge
