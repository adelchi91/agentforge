---
name: python-packaging
description: >
  Packaging and layout conventions for mylib.
  Auto-load when: working on pyproject.toml, src/ layout, package metadata, CI configuration, or install verification.
---

## Python Packaging — mylib

- Use the `src/` layout: package code lives in `src/mylib/`.
- Build system: `hatchling` (declared in `[build-system]` in `pyproject.toml`).
- Dev dependencies go in `[project.optional-dependencies]` under `dev`:
  `dev = ["pytest>=7", "ruff>=0.4"]`.
- Install for development with `pip install -e ".[dev]"` from the repo root.
- Test runner: `pytest tests/ -v --tb=short`. Linter: `ruff check src/mylib/ --quiet`.
- `src/mylib/__init__.py` defines `__version__`; keep it in sync with `pyproject.toml`.

<!-- This file contains ONLY knowledge: reference docs, commands, templates.
     It does NOT define a persona. The persona lives in agents/dev.md -->
