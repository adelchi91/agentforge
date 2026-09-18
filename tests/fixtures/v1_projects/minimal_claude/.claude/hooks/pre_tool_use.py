#!/usr/bin/env python3
"""PreToolUse guardrail hook (Claude Code + Codex — same stdin JSON contract).

Trimmed v1 test fixture (not the real installed hook). Mirrors the
real v1 template's own claim closely enough for migration-warning
detection tests: this hook is documented (in v1) as enforcing three
deterministic rules — destructive-command blocking, STORY-XXX commit/push
traceability, and per-agent file scopes — entirely via Bash regex
matching, which `tests/test_v1_characterization.py` in the real
AgentForge repository demonstrates is bypassable.
"""

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
