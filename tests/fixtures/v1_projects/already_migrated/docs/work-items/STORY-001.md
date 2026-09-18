---
state: draft
blockers:
updated_at:
---
# STORY-001 — Initialise Package Structure

## What to build

Create the complete package structure.

## Blocked by

None

## Acceptance criteria

- `pyproject.toml` exists at repo root with correct metadata

## May touch

- `src/mylib/`
- `tests/`

## Must not touch

- Nothing exists to protect — this is greenfield.

## Verification commands

```bash
pytest tests/ -v --tb=short
```

## Out of scope

- Implementing any validation functions.

## Completion evidence

Pending — filled in after execution.
