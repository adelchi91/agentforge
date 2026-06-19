---
name: python-packaging
description: Packaging guidance for calc-kit. Use when working on pyproject.toml, uv setup, package layout, CLI entry points, or install verification.
---

# Python Packaging

- Use `src/` layout for package code.
- Keep runtime dependencies empty unless a story explicitly approves one.
- Use `uv run pytest` as the default verification command.
- Define the CLI entry point in `pyproject.toml`.
