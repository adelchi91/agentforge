#!/usr/bin/env python3
"""Codex hook: append a short session record at Stop."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path


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


subject = git_output(["log", "-1", "--format=%s"], "UNKNOWN")
match = re.search(r"STORY-\d{3,}", subject)
story = match.group(0) if match else "UNKNOWN"
branch = git_output(["branch", "--show-current"], "unknown")
timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

log_file = Path(".codex/session-log.txt")
log_file.parent.mkdir(parents=True, exist_ok=True)
with log_file.open("a", encoding="utf-8") as handle:
    handle.write("----------------------------------------\n")
    handle.write(f"SESSION END: {timestamp}\n")
    handle.write(f"Story:       {story}\n")
    handle.write(f"Branch:      {branch}\n")
    handle.write("----------------------------------------\n")
