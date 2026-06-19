#!/usr/bin/env python3
"""Codex hook: run best-effort lint fixes for edited Python and JS/TS files."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}


def load_payload() -> Any:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def git_paths(args: list[str]) -> set[Path]:
    try:
        result = subprocess.run(
            ["git", *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return set()
    return {Path(line.strip()) for line in result.stdout.splitlines() if line.strip()}


def candidate_paths(payload: Any) -> set[Path]:
    found: set[Path] = set()
    for value in strings(payload):
        for token in value.replace(",", " ").split():
            path = Path(token.strip("'\""))
            if path.suffix in SUFFIXES and path.exists():
                found.add(path)
    if found:
        return found

    changed = git_paths(["diff", "--name-only"])
    untracked = git_paths(["ls-files", "--others", "--exclude-standard"])
    return {p for p in changed | untracked if p.suffix in SUFFIXES and p.exists()}


def run_quiet(command: list[str]) -> None:
    subprocess.run(
        command,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    paths = candidate_paths(load_payload())
    ruff = shutil.which("ruff")
    eslint = shutil.which("eslint")

    for path in sorted(paths):
        if path.suffix == ".py" and ruff:
            run_quiet([ruff, "check", str(path), "--fix", "--quiet"])
        elif path.suffix in {".js", ".jsx", ".ts", ".tsx"} and eslint:
            run_quiet([eslint, str(path), "--fix", "--quiet"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
