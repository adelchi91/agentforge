#!/usr/bin/env python3
"""PostToolUse auto-lint hook (Claude Code + Codex — same stdin JSON contract).

Runs after file-writing tools. Lints the touched file in place:
Python via ruff, JavaScript/TypeScript via eslint — best effort, only when
the linter is installed. Always exits 0 (informational, never blocks).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

PY_SUFFIXES = {".py"}
JS_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}


def load_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def touched_paths(payload: dict[str, Any]) -> set[Path]:
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}

    found: set[Path] = set()
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            path = Path(value)
            if path.suffix in PY_SUFFIXES | JS_SUFFIXES and path.exists():
                found.add(path)
    if found:
        return found

    # Fallback for patch-style tools (e.g. Codex apply_patch): scan input
    # strings for tokens that look like existing source files.
    for value in strings(tool_input):
        for token in value.replace(",", " ").split():
            path = Path(token.strip("'\""))
            if path.suffix in PY_SUFFIXES | JS_SUFFIXES and path.exists():
                found.add(path)
    return found


def run_quiet(command: list[str]) -> None:
    subprocess.run(
        command,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    paths = touched_paths(load_payload())
    if not paths:
        return 0

    ruff = shutil.which("ruff")
    eslint = shutil.which("eslint")

    for path in sorted(paths):
        if path.suffix in PY_SUFFIXES and ruff:
            run_quiet([ruff, "check", str(path), "--fix", "--quiet"])
        elif path.suffix in JS_SUFFIXES and eslint:
            run_quiet([eslint, str(path), "--fix", "--quiet"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
