"""AgentForge lifecycle-hook context injection.

`scripts/context.py` is the shared home for both of AgentForge's
context-injection hooks (execution plan target architecture /
docs/plans/agentforge-v2-user-stories.md STORY-009 and STORY-010):

  - **`SessionStart`** (STORY-009): fires on `startup`, `resume`, `clear`,
    and `compact` and re-injects the active-work snapshot STORY-008's
    `/agentforge:prepare-work` already wrote to
    `.agentforge/active-work.json`, so scope and verification survive
    every context reset without needing a session transcript.
  - **`UserPromptSubmit`** (STORY-010): per-prompt named-work-item
    detection. Detects the project's configured canonical work-item
    identifiers (`identifier.pattern`, STORY-004) in the user's submitted
    prompt text and, depending on what it finds relative to the active-work
    snapshot, injects either the bounded active work contract, a precise
    "prepare this work item first" instruction, or an explicit ambiguity
    report when more than one distinct identifier is detected.

Both hooks are dispatched from the single `main()` entry point below,
purely by the `hook_event_name` field Claude Code (and Codex) always
include on a hook's stdin payload -- there is no CLI subcommand. A payload
naming an event neither hook owns is a deliberate no-op; a payload with no
`hook_event_name` at all (or one that fails to parse) falls back to
`SessionStart` handling, since real payloads always carry the field and
`SessionStart` was this module's first owner.

Design constraints (ADR-0005 "no hook performs a network call"):

  - Reads only the committed `.agentforge/config.json` (STORY-004) and the
    gitignored runtime snapshot `.agentforge/active-work.json` (STORY-008).
    No subprocess, no network client, nothing else on disk. Never imports
    or calls `scripts.work_items`'s GitHub/GitLab network code paths
    (`_resolve_github`/`_resolve_gitlab`) -- only the pure, local,
    already-tested pieces of that module (`classify_identifier_shape`,
    `_known_provider`, `_parse_issue_number`, `_extract_max_bytes`) are
    reused here.
  - A **missing** snapshot (prepare-work has never run, or `--clear`
    removed it) is a normal no-op for `SessionStart`: no additional
    context, no warning, nothing on stderr. For `UserPromptSubmit` it
    means "no active work" -- still not an error.
  - A **malformed** snapshot (invalid JSON/encoding, wrong shape, or
    missing the identity fields a hook cannot safely render around) is a
    visible warning on stderr, never an uncaught exception/traceback, and
    never something written to stdout. `SessionStart` treats it exactly
    like "missing" for injection purposes (skip); `UserPromptSubmit`
    treats it exactly like "no active work" (reports "none" as the active
    id) -- both warn first.
  - The runtime-state path is resolved through `scripts/active_state.py`'s
    symlink-safe `_active_state_path`, so a symlinked `.agentforge`
    escaping the project root is never followed (mirrors STORY-008's own
    write-path safety requirement).
  - stdout carries only the `hookSpecificOutput` JSON envelope Claude
    Code's hook protocol expects (mirrors `scripts/scope_policy.py`'s
    stdin-JSON-in/stdout-JSON-out/diagnostics-on-stderr convention); every
    diagnostic goes to stderr via `_warn`.
  - Both handlers bound their emitted `additionalContext` text to the
    project's configured `context.max_bytes` (STORY-004), truncating the
    most dispensable descriptive content first and never dropping identity
    (`canonical_id`) -- see `bound_context_text` (SessionStart) and
    `_bound_lines` (UserPromptSubmit).

Turn-level de-duplication (`UserPromptSubmit` only): the payload
documented for Claude Code and Codex carries a `session_id` (stable for
the whole session) and no separate per-turn identifier. Re-injecting the
same active-work contract on every matching prompt within one session is
therefore a known, accepted limitation rather than something this module
silently "solves" with the wrong key -- `session_id` would suppress
re-injection across an entire session, including after the user has
legitimately moved on and back, which is a worse failure mode than an
occasionally repeated context block.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
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

# Identity fields a rendered SessionStart context can never safely be
# built without. Missing/wrong-typed values for either of these make a
# snapshot "malformed" rather than merely sparse (requirement: malformed
# state is a visible warning, never a partial/best-effort render).
_REQUIRED_IDENTITY_FIELDS = ("canonical_id", "source")


def _warn(message: str) -> None:
    print(f"agentforge context: {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Hook payload / project config plumbing, shared by both handlers (mirrors
# scripts/scope_policy.py's _project_root / config-loading conventions for
# this same protocol).
# ---------------------------------------------------------------------------


def _project_root(payload: Optional[dict]) -> Path:
    cwd_value = payload.get("cwd") if payload else None
    return Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else Path.cwd()


def _project_config_path(project_root: Path) -> Path:
    return project_root / ".agentforge" / "config.json"


def _load_project_config(project_root: Path) -> tuple[dict, list]:
    """Load `.agentforge/config.json` for context-hook purposes. A missing
    or invalid config falls back to `config_module.DEFAULT_CONFIG` (with an
    empty issues list) rather than blocking a hook whose only job is to add
    helpful context -- the same non-blocking fallback
    `scripts/scope_policy.py` already uses for its own config load. The
    caller decides how to word a warning from a non-empty `issues` list."""
    config_path = _project_config_path(project_root)
    if not config_path.is_file():
        return config_module.DEFAULT_CONFIG, []
    data, issues = config_module.load_for_observation(config_path)
    if data is None:
        return config_module.DEFAULT_CONFIG, issues
    return data, []


# ---------------------------------------------------------------------------
# Reading the runtime snapshot: missing vs. malformed are distinct
# outcomes, shared by both handlers.
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
    """Read `.agentforge/active-work.json` under `project_root`, through
    `scripts.active_state`'s symlink-safe path resolution. Returns:

      - `(None, None)` -- the file does not exist (or the resolved path
        escapes `project_root` via a symlink -- treated the same as "no
        snapshot" rather than a warning, since STORY-008 already refuses
        to *write* through such a path). A normal no-op: STORY-008 has
        never run, or `--clear` removed the snapshot.
      - `(None, warning)` -- the file exists but cannot be trusted (invalid
        JSON/encoding, not a JSON object, or missing an identity field).
        Never raises.
      - `(snapshot, None)` -- a usable snapshot dict, exactly as written by
        `scripts/active_state.py` (whatever extra/optional fields it
        carries are passed through unchanged).
    """
    path = active_state_module._active_state_path(project_root)
    if path is None or not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"{path} is a malformed active-work snapshot: not readable as valid JSON: {exc}"
    reason = _snapshot_shape_error(data)
    if reason:
        return None, f"{path} is a malformed active-work snapshot: {reason}"
    return data, None


# ---------------------------------------------------------------------------
# SessionStart (STORY-009): rendering identity + source pointer + scope +
# verification commands, bounded to context.max_bytes with deterministic,
# priority-ordered truncation. Mirrors scripts/active_state.py's
# bound_snapshot in spirit (shrink/drop the most dispensable fields first,
# identity last) but operates on the rendered text, not the JSON snapshot
# itself.
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
# UserPromptSubmit (STORY-010): identifier detection, gated by STORY-006's
# shape classification so an owner/repo repository identifier, a Markdown
# path, or a bare number under the wrong (or no) tracker never counts as a
# detected work item.
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


def handle_user_prompt_submit(payload: dict, project_root: Path, config: dict) -> Optional[str]:
    """Given one parsed `UserPromptSubmit` hook payload (plus its already-
    resolved `project_root` and loaded `config`), return the
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

    max_bytes = work_items_module._extract_max_bytes(config)

    detected = find_configured_identifiers(prompt, config)
    if not detected:
        return None

    if len(detected) > 1:
        tokens = [token for token, _canonical_id in detected]
        return _bound_lines(_format_ambiguous_notice(tokens), max_bytes)

    token, canonical_id = detected[0]
    active, warning = read_active_work_snapshot(project_root)
    if warning:
        _warn(warning)

    active_canonical = active.get("canonical_id") if isinstance(active, dict) else None
    if active_canonical == canonical_id:
        return _bound_lines(_format_active_work_contract(active), max_bytes)

    return _bound_lines(_format_mismatch_notice(token, active_canonical), max_bytes)


# ---------------------------------------------------------------------------
# Hook protocol: stdin JSON in, hookSpecificOutput JSON out (only when
# there is context to inject), diagnostics on stderr, always exit 0 -- this
# module only ever adds context, it never blocks a session start or a
# prompt. Mirrors scripts/scope_policy.py's stdin-JSON-in/stdout-JSON-out
# convention. Dispatch is purely by the payload's `hook_event_name`.
# ---------------------------------------------------------------------------


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


def _response_json(additional_context: str, hook_event_name: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": hook_event_name,
                "additionalContext": additional_context,
            }
        }
    )


def main(argv: Optional[list] = None) -> int:
    raw = sys.stdin.read()
    payload, parse_error = parse_hook_payload(raw)
    if payload is None:
        _warn(f"malformed hook payload; continuing with no additional context: {parse_error}")

    event_name = payload.get("hook_event_name") if payload else None

    if event_name == "UserPromptSubmit":
        project_root = _project_root(payload)
        cfg, cfg_issues = _load_project_config(project_root)
        if cfg_issues:
            _warn(
                f"could not load {_project_config_path(project_root)}, falling back to "
                "the default identifier pattern: "
                + "; ".join(issue.format() for issue in cfg_issues)
            )
        context_text = handle_user_prompt_submit(payload, project_root, cfg)
        if context_text:
            print(_response_json(context_text, "UserPromptSubmit"))
        return 0

    # Any other explicitly-named event is a deliberate no-op -- this
    # module owns exactly SessionStart and UserPromptSubmit. A payload
    # with no hook_event_name at all falls back to SessionStart handling
    # below: real Claude Code/Codex payloads always carry the field, and
    # SessionStart was this module's first owner.
    if event_name is not None and event_name != "SessionStart":
        return 0

    project_root = _project_root(payload)
    cfg, cfg_issues = _load_project_config(project_root)
    if cfg_issues:
        _warn(
            f"could not load {_project_config_path(project_root)}, falling back to "
            "the default context configuration: "
            + "; ".join(issue.format() for issue in cfg_issues)
        )

    result = handle_session_start(project_root, cfg)
    for warning in result.warnings:
        _warn(warning)
    if result.additional_context:
        print(_response_json(result.additional_context, "SessionStart"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
