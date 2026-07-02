---
name: package-extraction
description: >
  How to extract a monorepo module into a standalone pip-installable package for Lagrangia MecAI.
  Auto-load when: extracting a package, writing a pyproject.toml for an extracted module, verifying standalone importability, or checking for cross-package imports.
---

## Package Extraction — Lagrangia MecAI

- Extract as-is: no API changes during extraction. Refactoring happens in later phases.
- Each extracted package gets its own `pyproject.toml` declaring all runtime dependencies,
  its own `tests/`, its own `README.md`, and `.github/workflows/ci.yml` running `pytest tests/`.
- Standalone importability check — run in a clean venv with no other monorepo packages:
  ```bash
  python -m venv /tmp/test-<pkg>
  /tmp/test-<pkg>/bin/pip install -e <pkg>/ --quiet
  /tmp/test-<pkg>/bin/python -c "import <module>; print('PASS: import OK')"
  ```
- Cross-import isolation check:
  ```bash
  grep -rn "from dessiaworker\|from dessia_tools\|from code_explorer\|from dessia_multiagents" <pkg>/ \
    && echo "FAIL: cross-import detected" || echo "PASS: no cross-imports"
  ```
- Nothing is deleted from the monorepo until Phase 5 is validated and final-judge signs off.

<!-- This file contains ONLY knowledge: reference docs, commands, templates.
     It does NOT define a persona. Personas live in agents/*.md -->
