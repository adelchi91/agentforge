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
CI configuration, and import tests. At the end of this story the package must be
installable via `pip install -e ".[dev]"` and importable.

Nothing exists yet. This story creates the repo skeleton from scratch.

**Architecture reference:** Greenfield project. Uses the `src/` layout convention
(`src/mylib/__init__.py`). Build system: `hatchling`. Test runner: `pytest`. Linter: `ruff`.

---

## Scope

**May touch:**
- All files at repo root (`.gitignore`, `pyproject.toml`, `README.md`)
- `src/mylib/` (create entire directory and initial files)
- `tests/` (create, with initial import test)
- `.github/workflows/ci.yml` (create)

**Must NOT touch:**
- Nothing exists to protect — this is greenfield. If any files pre-exist in `src/` or
  `tests/`, stop and ask before overwriting.

---

## Acceptance Criteria

- `pyproject.toml` exists at repo root with correct metadata, `hatchling` build system,
  and `[project.optional-dependencies]` section with `dev = ["pytest>=7", "ruff>=0.4"]`
- `src/mylib/__init__.py` exists and defines `__version__ = "0.1.0"`
- `tests/test_imports.py` exists and imports `mylib` successfully
- `pip install -e ".[dev]"` succeeds from repo root
- `pytest tests/` runs and passes (at least `test_imports.py`)
- `.github/workflows/ci.yml` runs `pytest tests/` on push

---

## Verification Commands

```bash
# Install the package in development mode
pip install -e ".[dev]"

# Verify importability and version
python -c "import mylib; print(mylib.__version__)"

# Run the test suite
pytest tests/ -v --tb=short

# Check package metadata is readable
python -c "
import importlib.metadata
m = importlib.metadata.metadata('mylib')
print(f'Name: {m[\"Name\"]}')
print(f'Version: {m[\"Version\"]}')
print('PASS: metadata readable')
"

# Lint the source
ruff check src/mylib/ --quiet && echo "PASS: ruff clean"
```

---

## Out of Scope

- Implementing any validation functions — that is Phase 2 (STORY-003 and STORY-004) work
- Writing API documentation or docstrings beyond minimal module-level docstring
- Publishing to PyPI or TestPyPI — not in scope for this project

---

## Handoff

dev session summary → tester → final-judge
