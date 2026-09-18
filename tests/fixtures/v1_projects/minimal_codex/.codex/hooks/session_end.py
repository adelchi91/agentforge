#!/usr/bin/env python3
"""Trimmed v1 test fixture Stop/SessionEnd hook (Codex).

Registered on Codex's per-turn "Stop" event in v1's hooks.json because v1's
documentation claimed Codex had no SessionEnd event. Current Codex
documentation contradicts this (see docs/codex-compatibility.md).
"""

import sys


def main() -> int:
    sys.stdin.read()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
