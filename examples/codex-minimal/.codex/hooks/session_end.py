#!/usr/bin/env python3
"""Session-record hook (Claude Code + Codex — same stdin JSON contract).

Appends a session record to the session log. Register on `SessionEnd` in
Claude Code (fires once when the session ends) and on `Stop` in Codex
(which has no SessionEnd event — Stop fires at end of turn, so records are
per-turn there; a documented parity limitation). Always exits 0.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

STORY = re.compile(r"STORY-\d{3,}")


def git_output(args: list[str], fallback: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return fallback
    return result.stdout.strip() or fallback


def main() -> int:
    sys.stdin.read()  # payload unused; drain stdin

    subject = git_output(["log", "-1", "--format=%s"], "UNKNOWN")
    match = STORY.search(subject)
    story = match.group(0) if match else "UNKNOWN"
    branch = git_output(["branch", "--show-current"], "unknown")
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log = Path(__file__).resolve().parent.parent / "session-log.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write("----------------------------------------\n")
        handle.write(f"SESSION RECORD: {timestamp}\n")
        handle.write(f"Story:          {story}\n")
        handle.write(f"Branch:         {branch}\n")
        handle.write("----------------------------------------\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
