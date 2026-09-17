"""AgentForge lifecycle context restoration (STORY-009).

`scripts/context.py` is the shared home for both of AgentForge's context-
injection hooks (execution plan target architecture / user-stories STORY-009
and STORY-010):

  - **`SessionStart`** (this story): fires on `startup`, `resume`, `clear`,
    and `compact` and re-injects the active-work snapshot STORY-008's
    `/agentforge:prepare-work` already wrote to
    `.agentforge/active-work.json`, so scope and verification survive every
    context reset without needing a session transcript.
  - **`UserPromptSubmit`** (STORY-010, not implemented here): per-prompt
    named-work-item detection. `handle_session_start` below is a
    self-contained entry point; a later change adds a sibling
    `handle_user_prompt_submit` and wires `main()`'s dispatch (see the
    "hook_event_name dispatch" section) to call it. Nothing in this module
    assumes anything about that handler's shape.

Design constraints (ADR-0005 "no hook performs a network call"):

  - Reads only the committed `.agentforge/config.json` (STORY-004) and the
    gitignored runtime snapshot `.agentforge/active-work.json` (STORY-008).
    No subprocess, no network client, nothing else on disk.
  - A **missing** snapshot (prepare-work has never run, or `--clear` removed
    it) is a normal no-op: no additional context, no warning, nothing on
    stderr.
  - A **malformed** snapshot (invalid JSON/encoding, wrong shape, or missing
    the identity fields a hook cannot safely render around) is a visible
    warning on stderr, never an uncaught exception/traceback, and never
    something written to stdout.
  - stdout carries only the `hookSpecificOutput` JSON envelope Claude
    Code's `SessionStart` hook protocol expects (mirrors
    `scripts/scope_policy.py`'s stdin-JSON-in/stdout-JSON-out/diagnostics-
    on-stderr convention); every diagnostic goes to stderr via `_warn`.
  - The emitted `additionalContext` text is bounded to the project's
    configured `context.max_bytes` (STORY-004), truncating the most
    dispensable descriptive content first and never dropping identity
    (`canonical_id`) or the source pointer -- see `bound_context_text`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from . import config as config_module  # imported as scripts.context (e.g. tests)
    from . import work_items as work_items_module
except ImportError:
    import config as config_module  # executed directly: python3 scripts/context.py
    import work_items as work_items_module

# Mirrors scripts/active_state.py's ACTIVE_STATE_REL_PARTS -- duplicated as
# a plain literal rather than imported, so this module never needs to
# import scripts.active_state (which pulls in work_items/path_policy write
# machinery this read-only hook has no use for). Both constants must keep
# naming the same path; tests/test_context_hooks.py pins this.
ACTIVE_STATE_REL_PARTS = (".agentforge", "active-work.json")

# Identity fields a rendered context can never safely be built without.
# Missing/wrong-typed values for either of these make a snapshot
# "malformed" rather than merely sparse (requirement: malformed state is a
# visible warning, never a partial/best-effort render).
_REQUIRED_IDENTITY_FIELDS = ("canonical_id", "source")


# ---------------------------------------------------------------------------
# Reading the runtime snapshot: missing vs. malformed are distinct outcomes.
# ---------------------------------------------------------------------------


def _snapshot_shape_error(data: object) -> Optional[str]:
    """Return a human-readable reason `data` cannot be trusted as an
    active-work snapshot, or None if it looks usable. A structural check
    only -- this never judges the *quality* of scope/verification content,
    only whether the fields a rendered context depends on are present and
    the right type."""
    if not isinstance(data, dict):
        return "does not contain a JSON object"
    for field_name in _REQUIRED_IDENTITY_FIELDS:
        value = data.get(field_name)
        if not isinstance(value, str) or not value.strip():
            return f"missing required field {field_name!r}"
    return None


def read_active_work_snapshot(project_root: Path) -> tuple[Optional[dict], Optional[str]]:
    """Read `.agentforge/active-work.json` under `project_root`. Returns:

      - `(None, None)` -- the file does not exist. A normal no-op: STORY-008
        has never run, or `--clear` removed the snapshot.
      - `(None, warning)` -- the file exists but cannot be trusted (invalid
        JSON/encoding, not a JSON object, or missing an identity field).
        Never raises.
      - `(snapshot, None)` -- a usable snapshot dict, exactly as written by
        `scripts/active_state.py` (whatever extra/optional fields it
        carries are passed through unchanged).
    """
    path = Path(project_root).joinpath(*ACTIVE_STATE_REL_PARTS)
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"{path} is not readable as valid JSON: {exc}"
    reason = _snapshot_shape_error(data)
    if reason:
        return None, f"{path} is not a usable active-work snapshot: {reason}"
    return data, None


# ---------------------------------------------------------------------------
# Rendering: identity + source pointer + scope + verification commands,
# bounded to context.max_bytes with deterministic, priority-ordered
# truncation. Mirrors scripts/active_state.py's bound_snapshot in spirit
# (shrink/drop the most dispensable fields first, identity last) but
# operates on the rendered text, not the JSON snapshot itself.
# ---------------------------------------------------------------------------


def _text_bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _truncate_marked(text: str, length: int) -> str:
    """Shorten `text` to at most `length` bytes-as-chars, marking a real cut
    with a trailing ellipsis. Mirrors scripts/active_state.py's
    `_truncate_marked` helper (same shape, kept local rather than imported
    so this read-only hook module has no write-path dependency)."""
    if length >= len(text):
        return text
    if length <= 0:
        return ""
    if length == 1:
        return "…"
    return text[: length - 1].rstrip() + "…"


def _shrink_text_to_fit(text: str, max_bytes: int) -> str:
    """Binary-search the longest prefix of `text` (ellipsis-marked if cut)
    whose UTF-8 encoding is at most `max_bytes`."""
    if _text_bytes(text) <= max_bytes:
        return text
    lo, hi = 0, len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = _truncate_marked(text, mid)
        if _text_bytes(candidate) <= max_bytes:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _format_list_block(heading: str, items: list) -> list:
    if not items:
        return []
    lines = [f"{heading}:"]
    lines.extend(f"  - {item}" for item in items if isinstance(item, str) and item)
    return lines


def _essential_lines(snapshot: dict) -> list:
    canonical_id = str(snapshot.get("canonical_id", ""))
    title = snapshot.get("title")
    source = str(snapshot.get("source", ""))
    identity = f"Active work: {canonical_id}"
    if isinstance(title, str) and title.strip():
        identity += f" — {title.strip()}"
    return [identity, f"Source: {source}"]


# Optional content blocks, keyed by name, in the order they are dropped
# under byte pressure -- most dispensable (purely descriptive) first,
# scope/verification content last. Never includes identity or the source
# pointer: those two lines are produced by `_essential_lines` and are
# never removed by this priority list.
_OPTIONAL_BLOCKS_DROP_PRIORITY = (
    "out_of_scope_summary",
    "verification_commands",
    "forbidden_paths",
    "allowed_paths",
)


def _optional_blocks(snapshot: dict) -> dict:
    out_of_scope = snapshot.get("out_of_scope_summary")
    blocks = {
        "out_of_scope_summary": (
            [f"Out of scope: {out_of_scope.strip()}"]
            if isinstance(out_of_scope, str) and out_of_scope.strip()
            else []
        ),
        "verification_commands": _format_list_block(
            "Verification commands", snapshot.get("verification_commands") or []
        ),
        "forbidden_paths": _format_list_block(
            "Forbidden paths (must not touch)", snapshot.get("forbidden_paths") or []
        ),
        "allowed_paths": _format_list_block(
            "Allowed paths (may touch)", snapshot.get("allowed_paths") or []
        ),
    }
    return blocks


# Fixed display order (top to bottom), independent of drop priority above.
_BLOCKS_DISPLAY_ORDER = ("allowed_paths", "forbidden_paths", "verification_commands", "out_of_scope_summary")


def _assemble(essential: list, blocks: dict) -> str:
    lines = list(essential)
    for name in _BLOCKS_DISPLAY_ORDER:
        lines.extend(blocks.get(name, []))
    return "\n".join(lines)


def bound_context_text(snapshot: dict, max_bytes: int) -> str:
    """Render `snapshot` into the SessionStart `additionalContext` text,
    reducing it to fit `max_bytes` (UTF-8) if necessary.

    Deterministic reduction order, most dispensable first:

      1. Drop the `out_of_scope_summary` line entirely.
      2. Drop `verification_commands` entries from the end, one at a time.
      3. Drop `forbidden_paths` entries from the end, one at a time.
      4. Drop `allowed_paths` entries from the end, one at a time.

    Identity (`canonical_id`/title) and the source pointer are never
    dropped by this loop -- they come from `_essential_lines`, which is
    untouched throughout. Only if the two bare essential lines themselves
    exceed `max_bytes` (an effectively pathological config, since
    `context.max_bytes` is validated > 0 and this repo's default is 8000)
    does this function fall back to shrinking the title first, then the
    source text, while still never truncating `canonical_id` -- see the
    tail of this function.
    """
    essential = _essential_lines(snapshot)
    blocks = _optional_blocks(snapshot)

    text = _assemble(essential, blocks)
    if _text_bytes(text) <= max_bytes:
        return text

    for name in _OPTIONAL_BLOCKS_DROP_PRIORITY:
        while blocks.get(name):
            if name == "out_of_scope_summary":
                blocks[name] = []
            else:
                # Drop the last bullet line; keep the heading line (index 0)
                # until the whole block empties out.
                if len(blocks[name]) <= 1:
                    blocks[name] = []
                else:
                    blocks[name] = blocks[name][:-1]
            text = _assemble(essential, blocks)
            if _text_bytes(text) <= max_bytes:
                return text

    # Every optional block is gone; only the two essential lines remain.
    # If they still do not fit, shrink title first (keep canonical_id
    # whole), then the source line, as an explicit, deterministic last
    # resort -- never raise, never silently exceed max_bytes.
    canonical_id = str(snapshot.get("canonical_id", ""))
    source = str(snapshot.get("source", ""))
    identity_no_title = f"Active work: {canonical_id}"
    source_line = f"Source: {source}"
    text = identity_no_title + "\n" + source_line
    if _text_bytes(text) <= max_bytes:
        return text

    # Still too big: shrink the source line, reserving room for the
    # identity line and the separating newline.
    reserved = _text_bytes(identity_no_title) + 1  # + "\n"
    remaining = max(max_bytes - reserved, 0)
    return identity_no_title + "\n" + _shrink_text_to_fit(source_line, remaining)


def render_active_work_context(snapshot: dict, config: Optional[dict]) -> str:
    max_bytes = work_items_module._extract_max_bytes(config)
    return bound_context_text(snapshot, max_bytes)


# ---------------------------------------------------------------------------
# handle_session_start: the SessionStart entry point.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionStartResult:
    """Outcome of handling one SessionStart invocation.

    `additional_context` is exactly the string to place in the hook
    protocol's `hookSpecificOutput.additionalContext` field, or None for a
    normal no-op (nothing to inject: no snapshot, or a malformed one).
    `warnings` are diagnostics for stderr only -- never stdout.
    """

    additional_context: Optional[str] = None
    warnings: tuple = field(default_factory=tuple)


def handle_session_start(project_root: Path, config: Optional[dict]) -> SessionStartResult:
    """Build the SessionStart response for `project_root`, for any of the
    four lifecycle sources (`startup`/`resume`/`clear`/`compact`) alike --
    the restored context depends only on the current active-work snapshot
    and config, never on which source triggered the call, so all four
    produce equivalent context by construction."""
    snapshot, warning = read_active_work_snapshot(project_root)
    if warning:
        return SessionStartResult(additional_context=None, warnings=(warning,))
    if snapshot is None:
        return SessionStartResult(additional_context=None, warnings=())
    context_text = render_active_work_context(snapshot, config)
    return SessionStartResult(additional_context=context_text, warnings=())


# ---------------------------------------------------------------------------
# Hook protocol: stdin JSON in, stdout JSON out, diagnostics on stderr.
# Mirrors scripts/scope_policy.py's main()/_warn/_project_root conventions.
# ---------------------------------------------------------------------------


def _warn(message: str) -> None:
    print(f"agentforge context: {message}", file=sys.stderr)


def parse_hook_payload(raw: str) -> tuple[Optional[dict], Optional[str]]:
    """Parse the hook stdin payload. Returns (payload, None) on success or
    (None, error_message) on any parse/shape problem -- never raises."""
    if not raw or not raw.strip():
        return None, "empty stdin"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON on stdin: {exc.msg} at line {exc.lineno} column {exc.colno}"
    if not isinstance(data, dict):
        return None, "hook payload must be a JSON object"
    return data, None


def _project_root(payload: Optional[dict]) -> Path:
    cwd_value = payload.get("cwd") if payload else None
    return Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else Path.cwd()


def _project_config_path(payload: Optional[dict]) -> Path:
    return _project_root(payload) / ".agentforge" / "config.json"


def _load_context_config(config_path: Path) -> tuple[dict, list]:
    """Load the project config for context-hook purposes. A missing or
    invalid config falls back to DEFAULT_CONFIG (context.max_bytes: 8000)
    rather than blocking the hook -- see docs/adr and scripts/scope_policy's
    `_load_scope_config` for the identical rationale: a broken *optional*
    governance file must never freeze/crash an otherwise-working hook."""
    if not config_path.is_file():
        return config_module.DEFAULT_CONFIG, []
    data, issues = config_module.load_for_observation(config_path)
    if data is None:
        return config_module.DEFAULT_CONFIG, issues
    return data, []


def _response_json(additional_context: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": additional_context,
            }
        }
    )


def main(argv: Optional[list] = None) -> int:
    raw = sys.stdin.read()
    payload, parse_error = parse_hook_payload(raw)
    if payload is None:
        _warn(f"malformed SessionStart payload; continuing with no additional context: {parse_error}")

    # hook_event_name dispatch: this module is the shared home for both
    # SessionStart (STORY-009, implemented below) and UserPromptSubmit
    # (STORY-010, not yet present). A payload naming any other event, or
    # naming none at all in a context this build does not recognize, is a
    # deliberate no-op rather than a guess at behavior this story does not
    # own. A future change adds an `elif` branch here calling its own
    # `handle_user_prompt_submit`.
    event_name = payload.get("hook_event_name") if payload else None
    if event_name is not None and event_name != "SessionStart":
        return 0

    config_path = _project_config_path(payload)
    cfg, cfg_issues = _load_context_config(config_path)
    if cfg_issues:
        _warn(
            f"could not load {config_path}, falling back to default context config: "
            + "; ".join(issue.format() for issue in cfg_issues)
        )

    result = handle_session_start(_project_root(payload), cfg)
    for warning in result.warnings:
        _warn(warning)
    if result.additional_context:
        print(_response_json(result.additional_context))
    return 0


if __name__ == "__main__":
    sys.exit(main())
