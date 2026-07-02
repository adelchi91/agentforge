#!/usr/bin/env python3
"""UserPromptSubmit hook (Claude Code + Codex — same stdin JSON contract).

When the user's prompt references a STORY-XXX, injects that story's Scope and
Out of Scope sections as additional context, so scope constraints are loaded
deterministically instead of depending on the agent remembering to read them.

Emits `hookSpecificOutput.additionalContext` JSON on stdout. Always exits 0.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STORY = re.compile(r"STORY-\d{3,}")
STORY_DIRS = (Path(".claude/stories"), Path(".agents/stories"))
SECTIONS = ("Scope", "Out of Scope", "Handoff")


def extract_section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=\n## |\n---|\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def story_context(story_id: str) -> str:
    for directory in STORY_DIRS:
        story_file = directory / f"{story_id}.md"
        if not story_file.is_file():
            continue
        text = story_file.read_text(encoding="utf-8", errors="replace")
        parts = [f"Constraints for {story_id} (from {story_file.as_posix()}):"]
        for heading in SECTIONS:
            body = extract_section(text, heading)
            if body:
                parts.append(f"### {heading}\n{body}")
        if len(parts) > 1:
            return "\n\n".join(parts)
    return ""


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0

    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str):
        return 0

    match = STORY.search(prompt)
    if not match:
        return 0

    context = story_context(match.group(0))
    if context:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
