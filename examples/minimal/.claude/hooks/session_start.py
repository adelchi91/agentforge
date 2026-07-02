#!/usr/bin/env python3
"""SessionStart hook (Claude Code + Codex — same stdin JSON contract).

Injects the project's Golden Rule and the active story (detected from the
current git branch or latest commit) into the session context, so every
session starts grounded in the constitution and the work in progress.

Emits `hookSpecificOutput.additionalContext` JSON on stdout. Always exits 0.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

STORY = re.compile(r"STORY-\d{3,}")
CONSTITUTIONS = (Path(".claude/CLAUDE.md"), Path("AGENTS.md"))
STORY_DIRS = (Path(".claude/stories"), Path(".agents/stories"))


def git_output(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return ""
    return result.stdout.strip()


def golden_rule() -> str:
    for path in CONSTITUTIONS:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^## Golden Rule\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL | re.MULTILINE)
        if match:
            rule = match.group(1).strip()
            if rule:
                return rule
    return ""


def active_story() -> str:
    for source in (git_output(["branch", "--show-current"]), git_output(["log", "-1", "--format=%s"])):
        match = STORY.search(source)
        if match:
            return match.group(0)
    return ""


def story_status(story_id: str) -> str:
    for directory in STORY_DIRS:
        story_file = directory / f"{story_id}.md"
        if story_file.is_file():
            text = story_file.read_text(encoding="utf-8", errors="replace")
            status = re.search(r"^## Status:\s*(.+)$", text, re.MULTILINE)
            title = re.search(r"^# .+?—\s*(.+)$", text, re.MULTILINE)
            parts = [f"Active story: {story_id}"]
            if title:
                parts.append(f"({title.group(1).strip()})")
            if status:
                parts.append(f"— status: {status.group(1).strip()}")
            parts.append(f"— file: {story_file.as_posix()}")
            return " ".join(parts)
    return f"Active story (from git): {story_id} — story file not found."


def main() -> int:
    lines: list[str] = []

    rule = golden_rule()
    if rule:
        lines.append(f"Project Golden Rule (from the constitution — unconditional): {rule}")

    story_id = active_story()
    if story_id:
        lines.append(story_status(story_id))

    if lines:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(lines),
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
