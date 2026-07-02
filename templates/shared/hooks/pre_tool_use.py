#!/usr/bin/env python3
"""PreToolUse guardrail hook (Claude Code + Codex — same stdin JSON contract).

Reads the hook payload as JSON on stdin. Exit codes:
  0 — allow
  2 — hard block (stderr is shown to the agent; cannot be argued away)

Enforces three deterministic rules:
  1. Destructive commands are blocked (rm -rf, force push, DROP/TRUNCATE TABLE).
  2. git commit messages and pushed commits must reference a STORY-XXX.
  3. Per-agent file scopes: agents may only Write/Edit inside the folders they
     own, as declared in scopes.json next to this script (generated at
     scaffold time from the Repo Ownership table).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

DESTRUCTIVE = re.compile(
    r"rm\s+-rf|git\s+push\s+--force|git\s+push\s+-f\b|drop\s+table|truncate\s+table",
    re.IGNORECASE,
)
STORY = re.compile(r"STORY-\d{3,}")
# Tool names that write files, across both platforms.
FILE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "write", "edit", "apply_patch"}
# Paths every agent may always touch (bootstrap state, session infra).
ALWAYS_ALLOWED_PREFIXES = (".bootstrap/",)


def load_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def block(message: str) -> None:
    print(f"BLOCKED by pre_tool_use hook: {message}", file=sys.stderr)
    raise SystemExit(2)


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


def check_bash(command: str) -> None:
    if DESTRUCTIVE.search(command):
        block(f"Destructive command refused. Command: {command}")

    if re.search(r"\bgit\s+commit\b", command) and not STORY.search(command):
        block(
            "Commit message must reference a STORY-XXX. "
            "Example: git commit -m 'STORY-001: add pyproject.toml'"
        )

    if re.search(r"\bgit\s+push\b", command):
        subject = latest_commit_subject()
        if subject and not STORY.search(subject):
            block("Latest commit does not reference a STORY-XXX. Push refused.")


def candidate_file_paths(tool_input: dict[str, Any]) -> Iterable[str]:
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            yield value
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("file_path"), str):
                yield edit["file_path"]


def load_scopes() -> dict[str, Any]:
    scopes_file = Path(__file__).resolve().parent / "scopes.json"
    if not scopes_file.is_file():
        return {}
    try:
        data = json.loads(scopes_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    agents = data.get("agents")
    return agents if isinstance(agents, dict) else {}


def normalise(path: str, cwd: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(cwd.resolve()).as_posix()
        except ValueError:
            return candidate.resolve().as_posix()
    return candidate.as_posix().lstrip("./") or "."


def check_scope(agent: str, tool_input: dict[str, Any], cwd: Path) -> None:
    scopes = load_scopes()
    entry = scopes.get(agent)
    if not isinstance(entry, dict):
        return  # unknown agent or main session: scope not enforced here
    allowed = [p for p in entry.get("allow", []) if isinstance(p, str)]
    if not allowed:
        block(f"Agent '{agent}' is read-only: it may not write any file.")
    for raw_path in candidate_file_paths(tool_input):
        rel = normalise(raw_path, cwd)
        if any(rel == prefix.rstrip("/") or rel.startswith(prefix.rstrip("/") + "/")
               or rel.startswith(prefix) for prefix in ALWAYS_ALLOWED_PREFIXES):
            continue
        ok = False
        for prefix in allowed:
            clean = prefix.rstrip("/")
            if rel == clean or rel.startswith(clean + "/") or (prefix.endswith("/") and rel.startswith(prefix)):
                ok = True
                break
        if not ok:
            block(
                f"Agent '{agent}' may not modify '{rel}'. "
                f"Its scope is limited to: {', '.join(allowed)}"
            )


def main() -> int:
    payload = load_payload()
    if not payload:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}

    command = tool_input.get("command")
    if isinstance(command, str) and command:
        check_bash(command)

    if tool_name in FILE_WRITE_TOOLS:
        agent = payload.get("agent_type") or ""
        cwd = Path(payload.get("cwd") or ".")
        if agent:
            check_scope(str(agent), tool_input, cwd)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
