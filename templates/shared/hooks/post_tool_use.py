#!/usr/bin/env python3
"""PostToolUse quality-report hook (Claude Code + Codex — same stdin JSON contract).

STORY-015: this hook never mutates a file. v1 ran `ruff --fix` / `eslint
--fix` silently after every edit, best-effort, whenever the linter was
installed — which meant a "red" test could turn "green" because this hook
silently rewrote the file, not because the agent fixed anything, breaking
TDD's red/green causality and making the visible diff untrustworthy.

v2 behavior:

  - Off by default, and for any missing/unreadable/invalid config. Reads
    the project's own `.agentforge/config.json` `quality.post_edit` field
    (STORY-004's schema, `off` or `report` only — never a mutating mode),
    walking upward from the hook payload's `cwd` the way Git locates `.git`
    from a subdirectory. This hook ships standalone into arbitrary projects
    (copied to `.claude/hooks/` or `.codex/hooks/`) and cannot import the
    AgentForge plugin's own `scripts/config.py`, so it re-reads that one
    field directly and defensively: anything other than the exact string
    `"report"` — a missing file, malformed/undecodable file, an
    unrecognized value, a typo — is treated as `"off"`. A broken config can
    therefore never turn a check ON that the STORY-004 default does not run.
  - When enabled, identifies only the single explicit path a structured
    Write/Edit/MultiEdit tool call names in its own `tool_input` (the
    `file_path` field; lowercase `write`/`edit` tool names are also
    accepted, matching the lowercase Codex variants this hook family
    already handles in `pre_tool_use.py`). It never scans Bash commands,
    apply_patch hunks, or any other free-text tool input for path-shaped
    tokens — that guesswork was v1's `touched_paths` fallback, deleted here
    along with `--fix`.
  - Any other tool name (Bash, apply_patch, NotebookEdit, or anything this
    hook does not recognize as exposing one reliable path) is reported as
    skipped with a diagnostic instead of being guessed at.
  - Runs the check command in NON-MUTATING mode only (`ruff check`, never
    `--fix`; `eslint` with no `--fix`), under a strict timeout, and reports
    the command, exit status, and bounded output back to the agent via
    `hookSpecificOutput.additionalContext`. It never rewrites the file.
  - Always exits 0: PostToolUse cannot undo a completed edit, and a
    quality report is informational, never a hard gate. No exception
    raised by config reading, path resolution, or the subprocess call is
    allowed to propagate out of `main()` — every one of those failure
    modes degrades to "off" or a reported diagnostic instead of a crash.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# Suffix (always lowercased before lookup, so `Script.PY`/`Component.JS`
# are checked like their lowercase equivalents) -> (tool, base arguments,
# not counting the trailing `--` and the file path itself).
TOOL_BY_SUFFIX: dict[str, tuple[str, list[str]]] = {
    ".py": ("ruff", ["check"]),
    ".js": ("eslint", []),
    ".jsx": ("eslint", []),
    ".ts": ("eslint", []),
    ".tsx": ("eslint", []),
}

# Structured tools whose own tool_input carries exactly one, explicit,
# edited-file path under this key. Deliberately not widened to a text/token
# scan of arbitrary tool input — see the module docstring. MultiEdit's
# tool_input still names a single `file_path` even though it applies
# several edits within that one file. Lowercase `write`/`edit` mirror the
# Codex tool-name variants `pre_tool_use.py`'s FILE_WRITE_TOOLS already
# accounts for elsewhere in this hook family.
STRUCTURED_PATH_TOOLS = {
    "Write": "file_path",
    "write": "file_path",
    "Edit": "file_path",
    "edit": "file_path",
    "MultiEdit": "file_path",
}
_SUPPORTED_TOOLS_DESCRIPTION = "Write, Edit, MultiEdit (write/edit also accepted lowercase)"

CONFIG_RELATIVE_PATH = Path(".agentforge") / "config.json"
CHECK_TIMEOUT_SECONDS = 15
MAX_OUTPUT_CHARS = 4000


def load_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_cwd(payload: dict[str, Any]) -> Path:
    """The hook payload's `cwd` is normally a string, but a malformed or
    future payload shape must never crash the hook over it — anything
    other than a non-empty string falls back to `"."`."""
    value = payload.get("cwd")
    if isinstance(value, str) and value:
        return Path(value)
    return Path(".")


def find_agentforge_config(start: Path) -> Optional[Path]:
    """Walk from `start` upward through parent directories looking for
    `.agentforge/config.json`, mirroring how Git locates `.git` from a
    subdirectory (e.g. a monorepo package whose `cwd` is not the repo
    root). Stops at the filesystem root; returns None if no config is
    found anywhere on the way up. Never raises: a `start` that cannot be
    resolved (e.g. it no longer exists) falls back to the path as given."""
    try:
        current = start.resolve()
    except OSError:
        current = start
    for candidate in (current, *current.parents):
        config_path = candidate / CONFIG_RELATIVE_PATH
        if config_path.is_file():
            return config_path
    return None


def quality_post_edit_mode(cwd: Path) -> str:
    """Read `.agentforge/config.json`'s `quality.post_edit` field directly.

    Fails safe to `"off"` (the STORY-004 default) for every problem case:
    no config file found from `cwd` upward, an unreadable or undecodable
    file, malformed JSON, a non-object config or `quality` section, or a
    `post_edit` value other than the literal string `"report"`. Only an
    exact `"report"` enables anything."""
    config_path = find_agentforge_config(cwd)
    if config_path is None:
        return "off"
    try:
        text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "off"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return "off"
    if not isinstance(data, dict):
        return "off"
    quality = data.get("quality")
    if not isinstance(quality, dict):
        return "off"
    mode = quality.get("post_edit")
    return "report" if mode == "report" else "off"


def explicit_edited_path(
    tool_name: str, tool_input: dict[str, Any]
) -> tuple[Optional[Path], Optional[str]]:
    """Returns `(path, skip_reason)`; exactly one of the two is not None.

    Only ever reads the single named field of a known structured tool's own
    `tool_input` — never scans other fields, Bash commands, or patch text
    for path-shaped tokens, and never guesses among multiple candidates for
    a patch-style tool that could touch several files."""
    key = STRUCTURED_PATH_TOOLS.get(tool_name)
    if key is None:
        return None, (
            f"quality check skipped: '{tool_name}' does not expose a single, "
            f"reliable edited-file path in structured tool input (only "
            f"{_SUPPORTED_TOOLS_DESCRIPTION} are supported). Free-text tool "
            "input (Bash commands, apply_patch hunks, and similar) is never "
            "scanned for path-like tokens."
        )
    value = tool_input.get(key)
    if not isinstance(value, str) or not value:
        return None, (
            f"quality check skipped: '{tool_name}' tool_input has no usable '{key}'."
        )
    return Path(value), None


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + "\n... (truncated)"


def run_check(path: Path) -> dict[str, Any]:
    """Runs the non-mutating check command for `path`. Never passes a
    mutating flag (`--fix`/`-fix`) to any tool, and always separates the
    path argument with `--` so a filename that happens to start with `-`
    cannot be misread as an option.

    Returns a report dict tagged by its "kind": "skipped" and "error" carry
    a human-readable "detail" (plus "command" for "error"); "result" carries
    "command", "exit_code", and bounded "output". `format_report` dispatches
    on "kind" and never assumes a key is present without checking it first."""
    suffix = path.suffix.lower()
    if suffix not in TOOL_BY_SUFFIX:
        return {"kind": "skipped", "detail": f"no quality check is configured for suffix {path.suffix!r}."}

    if not path.exists():
        return {"kind": "skipped", "detail": f"{path} no longer exists; quality check skipped."}

    tool_name, base_args = TOOL_BY_SUFFIX[suffix]
    exe = shutil.which(tool_name)
    if not exe:
        return {"kind": "skipped", "detail": f"'{tool_name}' is not installed; quality check skipped."}

    command = [exe, *base_args, "--", str(path)]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=CHECK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "kind": "error",
            "detail": f"command timed out after {CHECK_TIMEOUT_SECONDS}s",
            "command": command,
        }
    except OSError as exc:
        return {"kind": "error", "detail": f"failed to run command: {exc}", "command": command}

    output = _truncate(((completed.stdout or "") + (completed.stderr or "")).strip())
    return {"kind": "result", "command": command, "exit_code": completed.returncode, "output": output}


def format_report(path: Path, report: dict[str, Any]) -> str:
    kind = report.get("kind")
    if kind == "skipped":
        return f"Quality check skipped for {path}: {report['detail']}"
    if kind == "error":
        command = " ".join(report["command"])
        return f"Quality check for {path} did not complete: {report['detail']} (command: {command})"
    if kind == "result":
        command = " ".join(report["command"])
        status = "passed" if report["exit_code"] == 0 else f"failed (exit {report['exit_code']})"
        lines = [f"Quality check for {path}: {status}", f"command: {command}"]
        if report["output"]:
            lines.append(f"output:\n{report['output']}")
        return "\n".join(lines)
    # Defensive: an unrecognized/renamed report shape must never crash the
    # hook (STORY-015's "always exits 0" guarantee extends to this path).
    return f"Quality check for {path} produced an unrecognized report shape: {report!r}"


def emit_context(text: Optional[str]) -> None:
    if not text:
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": text,
                }
            }
        )
    )


def main() -> int:
    payload = load_payload()
    if not payload:
        return 0

    cwd = resolve_cwd(payload)
    if quality_post_edit_mode(cwd) != "report":
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}

    path, skip_reason = explicit_edited_path(str(tool_name), tool_input)
    if path is None:
        emit_context(skip_reason)
        return 0

    report = run_check(path)
    emit_context(format_report(path, report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
