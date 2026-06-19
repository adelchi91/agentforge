#!/usr/bin/env python3
"""Codex hook: block destructive Bash commands and enforce STORY references."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any, Iterable


DESTRUCTIVE = re.compile(
    r"rm\s+-rf|git\s+push\s+--force|drop\s+table|truncate",
    re.IGNORECASE,
)
STORY = re.compile(r"STORY-\d{3,}")


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


def latest_commit_subject() -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return ""
    return result.stdout.strip()


def block(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    payload = load_payload()
    text = "\n".join(strings(payload))
    if not text:
        return 0

    if DESTRUCTIVE.search(text):
        block("Destructive command blocked by Codex pre-tool hook.")

    if re.search(r"\bgit\s+commit\b", text) and not STORY.search(text):
        block("Commit command must reference a STORY-XXX.")

    if re.search(r"\bgit\s+push\b", text) and "--force" not in text:
        subject = latest_commit_subject()
        if subject and not STORY.search(subject):
            block("Latest commit does not reference a STORY-XXX. Push blocked.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
