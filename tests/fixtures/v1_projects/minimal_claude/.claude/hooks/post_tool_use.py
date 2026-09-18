#!/usr/bin/env python3
"""Trimmed v1 test fixture PostToolUse hook."""

import sys


def main() -> int:
    sys.stdin.read()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
