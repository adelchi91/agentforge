# STORY-001 — Extract dessia-memory Package

## Status: READY FOR DEVELOPMENT
## Agent: dev-memory (model: sonnet)
## Phase: 1 — Extract dessia-memory
## Depends on: none
## Estimated effort: 1 session (4–6 hours)

---

## Context

The `dessia-memory/` module in the monorepo provides ChromaDB-based RAG memory for the
Lagrangia system. It must be extracted into a standalone Python package with its own
`pyproject.toml`, independent test suite, and CI configuration so it can be versioned
and deployed separately from the monorepo.

The module is currently importable as `dessia_memory` across the monorepo. After this
story, it must be installable via `pip install dessia-memory` from its own directory and
importable in a clean virtual environment with no other monorepo packages installed.

**Architecture reference:** `dessia-memory/` at monorepo root. Exposes `MemoryManager`
class backed by ChromaDB. No dependency on `dessiaworker`, `dessia-tools`, or
`code-explorer`.

---

## Scope

**May touch:**
- `dessia-memory/` — all files
- `dessia-memory/pyproject.toml` (create if not exists)
- `dessia-memory/tests/` (create or extend)
- `dessia-memory/.github/workflows/ci.yml` (create)
- `dessia-memory/README.md` (create)

**Must NOT touch:**
- `dessiaworker/` — any file
- `dessia-tools/` — any file
- `code-explorer/` — any file
- `dessia-multiagents/` — any file
- Root-level `pyproject.toml` or CI configuration (if any)

---

## Acceptance Criteria

- `dessia-memory/pyproject.toml` exists and declares all runtime dependencies
- `pip install -e dessia-memory/` succeeds from repo root
- `from dessia_memory import MemoryManager` succeeds in a clean virtual environment
  that has no other monorepo packages installed
- All existing memory tests pass with no modifications to test logic
- Package is importable independently of any other monorepo module
- `dessia-memory/.github/workflows/ci.yml` exists and runs `pytest tests/`

---

## Verification Commands

```bash
# Create an isolated virtual environment for testing
python -m venv /tmp/test-dessia-memory
/tmp/test-dessia-memory/bin/pip install -e dessia-memory/ --quiet

# Verify standalone importability
/tmp/test-dessia-memory/bin/python -c "from dessia_memory import MemoryManager; print('PASS: import OK')"

# Run the test suite
cd dessia-memory && python -m pytest tests/ -v --tb=short

# Verify no cross-module imports leaked into the extracted package
grep -rn "from dessiaworker\|from dessia_tools\|from code_explorer\|from dessia_multiagents" dessia-memory/ \
  && echo "FAIL: cross-import detected" || echo "PASS: no cross-imports"

# Confirm pyproject.toml is valid
cd dessia-memory && python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb')); print('PASS: pyproject.toml valid')"
```

---

## Out of Scope

- Refactoring the `MemoryManager` API — extract as-is, no API changes
- Changing ChromaDB configuration or version — keep existing settings
- Any changes to other monorepo packages that consume `dessia-memory`
- Publishing to PyPI — that is Phase 5 work
- Updating CI for the root monorepo — only `dessia-memory/.github/` is in scope

---

## Handoff

dev-memory session summary → tester → final-judge
