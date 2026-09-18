#!/usr/bin/env python3
"""Trimmed v1 test fixture PreToolUse hook. Claims to enforce destructive
-command blocking, STORY-XXX traceability, and per-agent file scopes via
Bash regex matching."""

import json
import sys


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    json.loads(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
