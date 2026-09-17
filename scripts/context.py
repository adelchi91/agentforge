"""AgentForge lifecycle-hook context injection.

This module hosts the read-only, network-free context-injection hooks
built on top of STORY-008's `.agentforge/active-work.json` snapshot
(ADR-0005: "no hook performs a network call"). Today it implements only
STORY-010's `UserPromptSubmit` handler:

  - `handle_user_prompt_submit(payload)` -- the STORY-010 entry point.
    Detects the project's configured canonical work-item identifiers
    (`identifier.pattern`, see `docs/agentforge-config.md`) in the user's
    submitted prompt text and, depending on what it finds relative to the
    active-work snapshot, injects either the bounded active work contract,
    a precise "prepare this work item first" instruction, or an explicit
    ambiguity report when more than one distinct identifier is detected.

STORY-009's `SessionStart` handler (lifecycle-boundary restoration for
startup/resume/clear/compact) is a separate story targeting this same
file and `hooks/hooks.json`; it is intentionally not implemented here.
Integrating both is expected to mean adding a `session-start` subcommand
to `main()`'s subparsers below, alongside `user-prompt-submit`, plus
whatever shared helpers the two handlers turn out to want in common --
none of the private helpers below are assumed stable API for that story.

Never imports or calls `scripts.work_items`'s GitHub/GitLab network code
paths (`_resolve_github`/`_resolve_gitlab`) -- only the pure, local,
already-tested pieces of that module (`classify_identifier_shape`,
`_known_provider`, `_parse_issue_number`) and of `scripts.active_state`
(`_active_state_path`, `read_previous_snapshot`) are reused here. This
hook reads only the project's committed `.agentforge/config.json` and the
local `.agentforge/active-work.json` snapshot; it never resolves a work
item through a tracker adapter itself.

Hook protocol (matching `scripts/scope_policy.py`'s established
convention for this repo): JSON on stdin, `hookSpecificOutput` JSON on
stdout when there is context to inject, everything else on stderr, always
exit 0 -- this hook only ever adds context, it never blocks a prompt.

Turn-level de-duplication: the `UserPromptSubmit` payload documented for
Claude Code and Codex carries a `session_id` (stable for the whole
session) and no separate per-turn identifier. Re-injecting the same
active-work contract on every matching prompt within one session is
therefore a known, accepted limitation rather than something this module
silently "solves" with the wrong key -- `session_id` would suppress
re-injection across an entire session, including after the user has
legitimately moved on and back, which is a worse failure mode than an
occasionally repeated context block.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

try:
    from . import active_state as active_state_module  # imported as scripts.context (e.g. tests)
    from . import config as config_module
    from . import work_items as work_items_module
except ImportError:
    import active_state as active_state_module  # executed directly: python3 scripts/context.py
    import config as config_module
    import work_items as work_items_module

PREPARE_WORK_COMMAND = "/agentforge:prepare-work"

# Punctuation commonly found immediately around an identifier mentioned in
# prose ("STORY-010.", "(STORY-010)", "STORY-010,") that must never be
# treated as part of the identifier itself. Deliberately does not include
# "-", "_", "#", "/", or "." in the middle of a token -- those can be
# meaningful parts of a configured identifier.pattern (e.g. "#123",
# "STORY-010").
_TOKEN_RE = re.compile(r"\S+")
_TOKEN_STRIP_CHARS = ".,;:!?()[]{}<>'\"“”‘’*"


def _warn(message: str) -> None:
    print(f"agentforge context: {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Hook payload / project config plumbing (mirrors scripts/scope_policy.py's
# _project_root / config-loading conventions for this same protocol).
# ---------------------------------------------------------------------------


def _project_root(payload: Optional[dict]) -> Path:
    cwd_value = payload.get("cwd") if payload else None
    return Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else Path.cwd()


def _project_config_path(project_root: Path) -> Path:
    return project_root / ".agentforge" / "config.json"


def _load_project_config(project_root: Path) -> dict:
    """Load `.agentforge/config.json` for observation purposes only: a
    missing or invalid config falls back to `config_module.DEFAULT_CONFIG`
    (scope.mode "off"'s sibling default -- `identifier.pattern` matching
    `^STORY-\\d{3,}$`) with a stderr diagnostic, rather than treating a
    problem in this optional governance file as fatal for a hook whose
    only job is to add helpful context (same non-blocking fallback
    `scripts/scope_policy.py` already uses for its own config load)."""
    config_path = _project_config_path(project_root)
    if not config_path.is_file():
        return config_module.DEFAULT_CONFIG
    data, issues = config_module.load_for_observation(config_path)
    if data is None:
        _warn(
            f"could not load {config_path}, falling back to the default identifier "
            "pattern: " + "; ".join(issue.format() for issue in issues)
        )
        return config_module.DEFAULT_CONFIG
    return data


# ---------------------------------------------------------------------------
# Identifier detection: configured identifier.pattern (STORY-004) applied
# with re.fullmatch per token, gated by STORY-006's shape classification so
# an owner/repo repository identifier, a Markdown path, or a bare number
# under the wrong (or no) tracker never counts as a detected work item.
# ---------------------------------------------------------------------------


def _tokenize_prompt(prompt: str) -> list[str]:
    """Split `prompt` into whitespace-separated candidate tokens, stripping
    common surrounding punctuation so "STORY-010." or "(STORY-010)" still
    yields the bare identifier. Every candidate is later checked with
    `re.fullmatch` against the configured pattern (never `re.search` over
    the raw prompt) -- `docs/agentforge-config.md` documents fullmatch as
    the semantics STORY-010's prompt-scanning relies on, which is exactly
    what keeps a digit sequence embedded in a version string, a date, or a
    "line 42" reference from ever matching on its own: the surrounding
    non-identifier characters mean the whole token never fullmatches a
    pattern like `^STORY-\\d{3,}$` or `^#\\d+$`."""
    tokens = []
    for raw in _TOKEN_RE.findall(prompt or ""):
        token = raw.strip(_TOKEN_STRIP_CHARS)
        if token:
            tokens.append(token)
    return tokens


def _compiled_identifier_pattern(config: dict) -> Optional[re.Pattern]:
    identifier_cfg = config.get("identifier") if isinstance(config, dict) else None
    pattern_str = identifier_cfg.get("pattern") if isinstance(identifier_cfg, dict) else None
    if not isinstance(pattern_str, str) or not pattern_str:
        return None
    try:
        return re.compile(pattern_str)
    except re.error:
        return None


def _canonical_id_for_token(token: str, provider: str, config: dict) -> Optional[str]:
    """Build the exact `canonical_id` string `scripts/work_items.py` would
    assign this token under the project's configured tracker, without
    calling a tracker adapter: `local` needs only the token; `github`/
    `gitlab` need the configured `tracker.repository` (already available
    from committed config) and the token's numeric part (already available
    from the prompt text itself via the same regex STORY-006 uses to
    parse an issue number)."""
    if provider == work_items_module.PROVIDER_LOCAL:
        return f"{work_items_module.PROVIDER_LOCAL}:{token}"

    number = work_items_module._parse_issue_number(token)
    if number is None:
        return None
    tracker_cfg = config.get("tracker") if isinstance(config, dict) else None
    repository = tracker_cfg.get("repository") if isinstance(tracker_cfg, dict) else None
    if not isinstance(repository, str) or not repository:
        return None
    return f"{provider}:{repository}#{number}"


def find_configured_identifiers(prompt: str, config: dict) -> list[tuple[str, str]]:
    """Return the distinct `(raw_token, canonical_id)` pairs, in
    first-seen order, for every token in `prompt` that both (a)
    `re.fullmatch`es the project's configured `identifier.pattern`, and
    (b) has a shape STORY-006's `classify_identifier_shape` recognizes as
    an actual work-item identifier for the configured tracker:

      - `tracker.type: "local"` accepts "opaque" (a bare slug like
        `STORY-010`) and "issue_reference" (a bare/hash number) shapes --
        the same two shapes `work_items._resolve_local_path` accepts for a
        bare local ID.
      - `tracker.type: "github"`/`"gitlab"` accepts only "issue_reference"
        (`#123`/`123`) -- the same shape `work_items._resolve_remote`
        requires; an `owner/repo`-shaped ("repository") token is never a
        work-item identifier under any tracker (STORY-006).
      - No known tracker at all (`config.tracker.type` missing/
        unrecognized) never matches anything -- STORY-006 never guesses a
        provider from a bare number's shape alone, and this function
        cannot build a `canonical_id` without one anyway.
      - "path"-shaped tokens (containing `/` or ending in `.md`) are never
        treated as a detected identifier by this hook: resolving a path
        identifier would mean reading an arbitrary local ticket file,
        which is out of this hook's read surface (committed config and
        the active-work snapshot only).
    """
    pattern = _compiled_identifier_pattern(config)
    if pattern is None:
        return []

    provider = work_items_module._known_provider(config)
    if provider is None:
        return []

    if provider == work_items_module.PROVIDER_LOCAL:
        allowed_shapes = ("opaque", "issue_reference")
    else:
        allowed_shapes = ("issue_reference",)

    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for token in _tokenize_prompt(prompt):
        if token in seen or not pattern.fullmatch(token):
            continue
        if work_items_module.classify_identifier_shape(token) not in allowed_shapes:
            continue
        canonical_id = _canonical_id_for_token(token, provider, config)
        if canonical_id is None:
            continue
        seen.add(token)
        found.append((token, canonical_id))
    return found


# ---------------------------------------------------------------------------
# Active-work snapshot lookup: read-only, comparison purposes only. Never
# writes; never raises for a missing or malformed snapshot (ADR-0005 /
# STORY-008's "malformed previous state must not block" contract).
# ---------------------------------------------------------------------------


def _read_active_state(project_root: Path) -> tuple[Optional[dict], bool]:
    """Returns `(data, malformed)`:

      - `(dict, False)` -- a usable snapshot with a non-empty string
        `canonical_id`.
      - `(None, False)` -- no snapshot file exists at all: an entirely
        ordinary "no work prepared yet" state.
      - `(None, True)` -- a snapshot file exists but is not valid JSON, is
        not a JSON object, or has no usable `canonical_id`. The caller
        emits a visible stderr warning for this case but treats it exactly
        like "no active state" for injection purposes -- never an
        exception, never a crash.

    Reuses `scripts.active_state`'s own symlink-safe path resolution and
    malformed-tolerant reader rather than re-deriving either.
    """
    resolved = active_state_module._active_state_path(project_root)
    exists = resolved is not None and resolved.is_file()
    data = active_state_module.read_previous_snapshot(project_root)
    if isinstance(data, dict) and isinstance(data.get("canonical_id"), str) and data["canonical_id"]:
        return data, False
    return None, exists


# ---------------------------------------------------------------------------
# Bounded rendering: deterministic truncation that always keeps whichever
# prefix of lines fits, so identity (always the first line) survives even
# when later, more optional lines do not (STORY-009's requirement, applied
# here too since context.max_bytes is the same configured ceiling).
# ---------------------------------------------------------------------------


def _bound_lines(lines: list[str], max_bytes: int) -> str:
    result = ""
    for line in lines:
        candidate = f"{result}\n{line}" if result else line
        if len(candidate.encode("utf-8")) > max_bytes:
            if not result:
                # Even the very first line alone does not fit: hard-truncate
                # it on a safe UTF-8 character boundary rather than emit
                # nothing at all.
                encoded = line.encode("utf-8")[:max_bytes]
                return encoded.decode("utf-8", errors="ignore")
            break
        result = candidate
    return result


def _format_active_work_contract(active: dict) -> list[str]:
    """Render the bounded work contract for a snapshot that matches the
    detected identifier: identity, source pointer, scope, and verification
    commands -- the exact fields STORY-008 already wrote to
    `.agentforge/active-work.json`, reused verbatim. This hook never reads
    the underlying ticket file to re-derive any of this."""
    lines = [f"Active work: {active.get('canonical_id', 'unknown')}"]
    title = active.get("title")
    if title:
        lines.append(f"Title: {title}")
    source = active.get("source")
    if source:
        lines.append(f"Source: {source}")

    allowed = active.get("allowed_paths") or []
    if allowed:
        lines.append("May touch: " + ", ".join(allowed))

    forbidden = active.get("forbidden_paths") or []
    if forbidden:
        lines.append("Must not touch: " + ", ".join(forbidden))

    verification = active.get("verification_commands") or []
    if verification:
        lines.append("Verification commands:")
        lines.extend(f"  - {cmd}" for cmd in verification)

    out_of_scope = active.get("out_of_scope_summary")
    if out_of_scope:
        lines.append(f"Out of scope: {out_of_scope}")

    return lines


def _format_mismatch_notice(detected_token: str, active_canonical: Optional[str]) -> list[str]:
    return [
        f"Detected work-item reference: {detected_token}",
        f"Active work: {active_canonical or 'none'}",
        f"Run {PREPARE_WORK_COMMAND} {detected_token} before editing further.",
    ]


def _format_ambiguous_notice(detected_tokens: list[str]) -> list[str]:
    return [
        "Multiple work-item references detected in this prompt: " + ", ".join(detected_tokens),
        f"Run {PREPARE_WORK_COMMAND} <id> for the one you intend to work on before editing further.",
    ]


# ---------------------------------------------------------------------------
# STORY-010 entry point.
# ---------------------------------------------------------------------------


def handle_user_prompt_submit(payload: dict) -> Optional[str]:
    """Given one parsed `UserPromptSubmit` hook payload, return the
    `additionalContext` string to inject, or `None` to inject nothing this
    turn. Never raises; never performs a network call or resolves a work
    item through a tracker adapter (ADR-0005) -- reads only the project's
    committed `.agentforge/config.json` and the local
    `.agentforge/active-work.json` snapshot STORY-008 already wrote.

    Behavior:

      - No configured identifier detected in the prompt: `None` (no
        injection at all).
      - Exactly one distinct identifier detected, and it matches the
        active-work snapshot's `canonical_id`: the bounded active work
        contract (identity, scope, verification commands).
      - Exactly one distinct identifier detected, and it does not match
        (including "no active state at all", and "active state exists but
        is malformed"): only the detected id, the current active id (or
        "none"), and the `/agentforge:prepare-work <id>` instruction.
      - More than one distinct identifier detected: an explicit ambiguity
        report listing every detected id -- never silently the first one.

    Every returned string is bounded to the project's configured
    `context.max_bytes` (STORY-004), deterministically truncated so the
    identity line always survives ahead of more optional detail.
    """
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None

    project_root = _project_root(payload)
    config = _load_project_config(project_root)
    max_bytes = work_items_module._extract_max_bytes(config)

    detected = find_configured_identifiers(prompt, config)
    if not detected:
        return None

    if len(detected) > 1:
        tokens = [token for token, _canonical_id in detected]
        return _bound_lines(_format_ambiguous_notice(tokens), max_bytes)

    token, canonical_id = detected[0]
    active, malformed = _read_active_state(project_root)
    if malformed:
        state_path = project_root / ".agentforge" / "active-work.json"
        _warn(
            f"{state_path} exists but is malformed; treating this prompt as if "
            "no work were active"
        )

    active_canonical = active.get("canonical_id") if isinstance(active, dict) else None
    if active_canonical == canonical_id:
        return _bound_lines(_format_active_work_contract(active), max_bytes)

    return _bound_lines(_format_mismatch_notice(token, active_canonical), max_bytes)


# ---------------------------------------------------------------------------
# Hook protocol: stdin JSON in, hookSpecificOutput JSON out (only when
# there is context to inject), diagnostics on stderr, always exit 0 -- this
# hook only ever adds context, it never blocks a prompt.
# ---------------------------------------------------------------------------


def _response_json(context_text: str, hook_event_name: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": hook_event_name,
                "additionalContext": context_text,
            }
        }
    )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="context.py",
        description="AgentForge lifecycle-hook context injection.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "user-prompt-submit",
        help="STORY-010: inject named work context on prompt submission.",
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        _warn("malformed JSON on stdin; emitting no additional context")
        return 0
    if not isinstance(payload, dict):
        _warn("hook payload must be a JSON object; emitting no additional context")
        return 0

    if args.command == "user-prompt-submit":
        context_text = handle_user_prompt_submit(payload)
        if context_text:
            print(_response_json(context_text, "UserPromptSubmit"))
        return 0

    return 1  # pragma: no cover - argparse enforces a valid subcommand


if __name__ == "__main__":
    sys.exit(main())
