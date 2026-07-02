#!/usr/bin/env python3
"""SubagentStop hook (Claude Code + Codex — same stdin JSON contract).

Appends a handoff-chain record to the session log every time a subagent
finishes, so the dev → tester → final-judge chain leaves a deterministic
audit trail. Always exits 0.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

STORY = re.compile(r"STORY-\d{3,}")


def log_file() -> Path:
    # .claude/hooks/ or .codex/hooks/ → log beside the platform directory root.
    return Path(__file__).resolve().parent.parent / "session-log.txt"


def current_story() -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        match = STORY.search(result.stdout)
        return match.group(0) if match else "UNKNOWN"
    except OSError:
        return "UNKNOWN"


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    agent = payload.get("agent_type") or payload.get("agent_id") or "unknown-agent"
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    path = log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"HANDOFF {timestamp} | agent: {agent} | story: {current_story()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
