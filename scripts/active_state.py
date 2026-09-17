"""AgentForge prepare-work: resolve, validate, and snapshot active work
(STORY-008).

`/agentforge:prepare-work <id>` is a user-invoked skill, never a lifecycle
hook (ADR-0005 / `docs/agents/issue-tracker.md`): it is the one place that
may call STORY-006's `scripts/work_items.py` GitHub/GitLab adapters, and
the one place that writes `.agentforge/active-work.json` — the bounded,
gitignored runtime snapshot that a later lifecycle hook (STORY-009/010)
reads without ever touching the network itself.

This module is organized as three independent, separately testable
pieces, matching the story's three approval gates:

  - **Readiness** (`check_readiness`): resolve every blocker named in the
    work item's `blockers` tuple through the *same* configured tracker
    (`scripts.work_items.resolve_work_item`) and classify each as closed
    or not. GitHub/GitLab items always report zero blockers today
    (`docs/agents/issue-tracker.md`), so remote readiness is trivially
    "ready"; the local adapter's front-matter `blockers:` list is the
    only source of a real blocking edge right now.
  - **Contract completeness** (`check_work_contract`): a *structural*
    check of the eight sections STORY-007's work-contract discipline
    requires (heading present, section non-empty, not an obvious
    placeholder). This module never judges whether a criterion is well
    *written* — that judgment is the `work-contract` skill's job, applied
    by the agent before it ever calls this module's contract-update path.
  - **Snapshot preparation** (`plan_prepare_work` / `apply_prepare_work`):
    a plan/apply pair with the same approval-binding shape
    `scripts/setup.py` already uses for the constitution-file transaction
    (STORY-005) — `plan_*` never writes, `apply_*` recomputes the plan
    immediately before writing and refuses a stale approval.

A fourth pair, `plan_contract_update` / `apply_contract_update`, proposes
and (for the `local` tracker only) writes the missing contract sections
back into the underlying Markdown file, using the same plan/apply/stale
shape. **GitHub and GitLab have no write path** — STORY-006 implemented
fetch-only adapters, so this module can only show the proposed diff and
tell the user to apply it through the tracker's own edit command
(`gh issue edit`, `glab issue update`) before re-running prepare-work.
This is a documented scope boundary, not a placeholder: writing to a
remote tracker item is out of STORY-008's scope, and this module never
pretends to have done it.

Every operation here is "resolve/check/plan, then write" — nothing is
written to `.agentforge/active-work.json` or a local ticket file until an
explicit `apply_*` call with a matching `plan_id`, and every failure mode
(resolution error, unresolved blockers without an explicit override,
incomplete contract, an oversized snapshot that cannot be reduced, a
stale approval, a write failure) returns a structured status and leaves
whatever was already on disk untouched.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

try:
    from . import config as config_module  # imported as scripts.active_state (e.g. tests)
    from . import path_policy as path_policy_module
    from . import work_items as work_items_module
except ImportError:
    import config as config_module  # executed directly: python3 scripts/active_state.py
    import path_policy as path_policy_module
    import work_items as work_items_module

ACTIVE_STATE_SCHEMA_VERSION = 1
ACTIVE_STATE_REL_PARTS = (".agentforge", "active-work.json")
GITIGNORE_ENTRY = ".agentforge/active-work.json"

# The eight required sections (STORY-007), in the exact order
# `templates/local-work-item.md` renders them. "Blocked by" is checked for
# presence like the others, but is never a target of a contract *update*
# proposed by this module (see `_normalize_updates`) -- the blocking edge
# belongs to whatever created the ticket, never to a contract-completion
# pass.
REQUIRED_CONTRACT_SECTIONS = (
    "What to build",
    "Blocked by",
    "Acceptance criteria",
    "May touch",
    "Must not touch",
    "Verification commands",
    "Out of scope",
    "Completion evidence",
)

_IMMUTABLE_SECTIONS = {"blocked by"}

_DEFAULT_COMPLETION_EVIDENCE = "Pending — filled in after execution."

# State strings that count as "this blocker is closed" for readiness
# purposes, checked case-insensitively. Everything else -- including
# "unknown" (no front matter at all) and "open"/"in_progress"/"draft" --
# counts as unresolved. GitHub's `gh issue view --json state` reports
# "OPEN"/"CLOSED" and GitLab's `glab issue view` reports "opened"/"closed";
# both fold onto this same set once lower-cased.
_CLOSED_STATES = frozenset({"closed", "done", "complete", "completed", "merged", "resolved"})

_SECTION_HEADING_RE = re.compile(r"(?m)^##[ \t]+(.+?)[ \t]*$")
_BULLET_RE = re.compile(r"^[-*][ \t]+(.*)$")


# ---------------------------------------------------------------------------
# Small shared helpers (atomic write, diff, path safety) -- mirrors the
# tempfile.mkstemp + os.replace pattern `scripts/setup.py`'s `_write_text`
# already uses, so every file this module ever writes (the runtime
# snapshot, `.gitignore`, a local ticket file) is atomic in isolation and
# never observed half-written by a concurrent reader.
# ---------------------------------------------------------------------------


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _unified_diff(before: str, after: str, path: str) -> Optional[str]:
    if before == after:
        return None
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _active_state_path(project_root: Path) -> Optional[Path]:
    """Resolve the canonical, symlink-safe destination for
    `.agentforge/active-work.json`. Returns None -- never a path outside
    the project root -- if `.agentforge` (or any ancestor) is a symlink
    that escapes `project_root`, or if the project root itself cannot be
    resolved. Every reader/writer in this module goes through this
    function rather than a bare `project_root / ".agentforge" / ...`
    join, so a symlinked `.agentforge` directory can never redirect a
    write outside the project (STORY-008's path-safety requirement)."""
    resolved_root = path_policy_module.resolve_project_root(project_root)
    if resolved_root is None:
        return None
    rel = "/".join(ACTIVE_STATE_REL_PARTS)
    target = path_policy_module.canonicalize_target(project_root, rel)
    if target is None:
        return None
    if not _is_within(target, resolved_root):
        return None
    return target


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Readiness: resolve every blocker through the same configured tracker.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlockerStatus:
    identifier: str
    resolved: bool
    state: Optional[str]
    closed: bool
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.identifier,
            "resolved": self.resolved,
            "state": self.state,
            "closed": self.closed,
            "error": self.error,
        }


@dataclass(frozen=True)
class ReadinessResult:
    blockers: tuple
    unresolved: tuple
    ready: bool

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "blockers": [b.to_dict() for b in self.blockers],
            "unresolved": [b.to_dict() for b in self.unresolved],
        }


def _is_closed_state(state: Optional[str]) -> bool:
    return isinstance(state, str) and state.strip().lower() in _CLOSED_STATES


def check_readiness(
    item: "work_items_module.WorkItem",
    config: Optional[dict],
    project_root: Path,
    runner: Callable[..., "subprocess.CompletedProcess"] = subprocess.run,
) -> ReadinessResult:
    """Resolve every entry in `item.blockers` under the same tracker
    `config` names, and classify each as closed or unresolved. A blocker
    that fails to resolve at all (deleted, not found, a CLI error) is
    conservatively treated as unresolved -- this module never treats "I
    could not check" as "must be fine"."""
    statuses = []
    for raw_blocker in item.blockers:
        result = work_items_module.resolve_work_item(
            raw_blocker, config, project_root=project_root, runner=runner
        )
        if result.ok:
            closed = _is_closed_state(result.item.state)
            statuses.append(BlockerStatus(raw_blocker, True, result.item.state, closed))
        else:
            statuses.append(
                BlockerStatus(
                    raw_blocker,
                    False,
                    None,
                    False,
                    error=f"{result.error.kind}: {result.error.message}",
                )
            )
    unresolved = tuple(s for s in statuses if not s.closed)
    return ReadinessResult(tuple(statuses), unresolved, ready=not unresolved)


# ---------------------------------------------------------------------------
# Contract completeness: a structural check of the eight required
# sections, never a semantic judgment of quality (that is the
# `work-contract` skill's job, applied before this module is asked to
# check anything).
# ---------------------------------------------------------------------------


def parse_sections(body: str) -> dict:
    """Split a ticket body into {lowercased heading: content} by scanning
    for `## Heading` lines. Content is everything between one heading and
    the next (or end of body), with leading/trailing blank lines
    stripped."""
    sections: dict = {}
    text = body or ""
    matches = list(_SECTION_HEADING_RE.finditer(text))
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[heading.lower()] = text[start:end].strip("\n").strip()
    return sections


def _looks_like_placeholder(content: str) -> bool:
    stripped = content.strip()
    if not stripped:
        return True
    if stripped in ("...", "…", "-", "*"):
        return True
    if "{{" in stripped and "}}" in stripped:
        return True
    if stripped.lower() in ("todo", "tbd", "n/a", "na"):
        return True
    return False


def _normalize_updates(updates: Optional[dict]) -> dict:
    """Validate a caller-supplied {section name: new content} mapping
    against `REQUIRED_CONTRACT_SECTIONS`, case-insensitively. Silently
    drops anything that is not a recognized section name/string value, and
    -- critically -- always drops "Blocked by" even if a caller supplies
    it: the blocking edge is never something a contract-completion pass
    may rewrite (STORY-008 requirement: "preserve identity and blocking
    edges")."""
    if not updates:
        return {}
    by_lower = {name.lower(): name for name in REQUIRED_CONTRACT_SECTIONS}
    normalized: dict = {}
    for key, value in updates.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        lowered = key.strip().lower()
        if lowered in _IMMUTABLE_SECTIONS:
            continue
        canonical = by_lower.get(lowered)
        if canonical is None:
            continue
        normalized[canonical] = value
    return normalized


@dataclass(frozen=True)
class ContractSectionStatus:
    name: str
    status: str  # "ok" | "missing" | "placeholder"
    content: str


@dataclass(frozen=True)
class ContractCheck:
    sections: tuple
    complete: bool
    missing: tuple

    def to_dict(self) -> dict:
        return {
            "complete": self.complete,
            "missing": list(self.missing),
            "sections": {s.name: s.status for s in self.sections},
        }


def check_work_contract(body: str, updates: Optional[dict] = None) -> ContractCheck:
    """Check whether every required section is present and non-placeholder
    in `body`, optionally layering a caller-supplied `updates` mapping on
    top first (used to preview whether a proposed contract-update would
    make the ticket complete, before anything is written anywhere).

    "Completion evidence" is special: an absent or empty section is
    treated as the deterministic, non-judgmental default ("Pending --
    filled in after execution") rather than reported missing, since no
    model/user judgment is required to know a not-yet-executed ticket has
    no completion evidence yet.
    """
    normalized = _normalize_updates(updates)
    sections = parse_sections(body)
    for name, content in normalized.items():
        sections[name.lower()] = content

    statuses = []
    missing = []
    for name in REQUIRED_CONTRACT_SECTIONS:
        content = sections.get(name.lower())
        if name == "Completion evidence" and (content is None or not content.strip()):
            statuses.append(
                ContractSectionStatus(name, "ok", _DEFAULT_COMPLETION_EVIDENCE)
            )
            continue
        if content is None:
            statuses.append(ContractSectionStatus(name, "missing", ""))
            missing.append(name)
        elif _looks_like_placeholder(content):
            statuses.append(ContractSectionStatus(name, "placeholder", content))
            missing.append(name)
        else:
            statuses.append(ContractSectionStatus(name, "ok", content))
    return ContractCheck(tuple(statuses), not missing, tuple(missing))


def _extract_list_items(text: Optional[str]) -> list:
    """Pull bullet-list lines and fenced-code-block lines out of a
    section's content, in order, for the two path sections (`May touch`/
    `Must not touch`) and `Verification commands`. A section written as an
    explicit "no automated verification" acknowledgment sentence (no
    bullets, no fence) correctly yields an empty list here -- the sentence
    itself lives in the ticket, not duplicated into the bounded runtime
    snapshot."""
    if not text:
        return []
    items: list = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            if line:
                items.append(line)
            continue
        match = _BULLET_RE.match(line)
        if match:
            candidate = match.group(1).strip().strip("`").strip()
            if candidate:
                items.append(candidate)
    return items


# ---------------------------------------------------------------------------
# Snapshot construction and size bounding.
# ---------------------------------------------------------------------------

# Optional/descriptive fields this module may shrink (in this priority
# order) to fit `context.max_bytes`, without ever touching identity
# (`canonical_id`), the source pointer, scope (`allowed_paths`/
# `forbidden_paths`), or `verification_commands` (STORY-008 requirement
# 9). If shrinking every field in this list to empty still does not fit,
# `bound_snapshot` reports failure rather than truncating the JSON into an
# invalid or dishonest state.
_REDUCIBLE_FIELDS_PRIORITY = ("out_of_scope_summary", "title")


def _serialize(snapshot: dict) -> bytes:
    return (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _truncate_marked(text: str, length: int) -> str:
    if length >= len(text):
        return text
    if length <= 0:
        return ""
    if length == 1:
        return "…"
    return text[: length - 1].rstrip() + "…"


def _shrink_field_to_fit(candidate: dict, field_name: str, max_bytes: int) -> dict:
    original = candidate.get(field_name)
    if not isinstance(original, str) or not original:
        return candidate
    lo, hi = 0, len(original)
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        trial = dict(candidate)
        trial[field_name] = _truncate_marked(original, mid)
        if len(_serialize(trial)) <= max_bytes:
            best = trial[field_name]
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return candidate
    result = dict(candidate)
    result[field_name] = best
    return result


def bound_snapshot(snapshot: dict, max_bytes: int) -> tuple:
    """Return (bounded_snapshot, True) if `snapshot` fits within
    `max_bytes` once serialized (shrinking `_REDUCIBLE_FIELDS_PRIORITY`
    fields as needed), or (None, False) if even shrinking every reducible
    field to nothing still does not fit -- callers must reject in that
    case (requirement 9: "reject or deterministically reduce ... never
    truncate into an invalid state")."""
    candidate = dict(snapshot)
    if len(_serialize(candidate)) <= max_bytes:
        return candidate, True
    for field_name in _REDUCIBLE_FIELDS_PRIORITY:
        candidate = _shrink_field_to_fit(candidate, field_name, max_bytes)
        if len(_serialize(candidate)) <= max_bytes:
            return candidate, True
    return None, False


# ---------------------------------------------------------------------------
# Reading/writing the runtime snapshot.
# ---------------------------------------------------------------------------


def read_previous_snapshot(project_root: Path) -> Optional[dict]:
    """Read and parse the existing `.agentforge/active-work.json`, if any.
    Returns None for "does not exist", "not valid JSON", or "not a JSON
    object" alike -- a malformed previous snapshot is never raised as an
    exception; callers treat None as "nothing to compare against, write
    fresh" (STORY-008: malformed previous state must not block a
    successful prepare)."""
    path = _active_state_path(project_root)
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_noop(previous: Optional[dict], new_snapshot: dict) -> bool:
    if not isinstance(previous, dict):
        return False
    for key in ("canonical_id", "content_digest", "blocker_override"):
        if previous.get(key) != new_snapshot.get(key):
            return False
    return True


def write_snapshot_atomic(project_root: Path, snapshot: dict) -> None:
    path = _active_state_path(project_root)
    if path is None:
        raise RuntimeError(
            "refusing to write .agentforge/active-work.json: the destination "
            "resolves outside the project root (symlink escape or "
            "unresolvable project root)"
        )
    _atomic_write_bytes(path, _serialize(snapshot))


# ---------------------------------------------------------------------------
# .gitignore: add only the one runtime-state entry, surgically.
# ---------------------------------------------------------------------------


def update_gitignore(project_root: Path) -> bool:
    """Ensure `.agentforge/active-work.json` (and only that path) is
    listed in the project's `.gitignore`. Returns True if the file was
    created or modified, False if it already listed the entry (a true
    no-op: no write, no mtime change). Preserves every existing byte,
    comment, newline style (CRLF vs LF), and final-newline state; never
    touches `.agentforge/config.json` or any other line."""
    path = Path(project_root) / ".gitignore"
    if not path.exists():
        _atomic_write_bytes(path, (GITIGNORE_ENTRY + "\n").encode("utf-8"))
        return True

    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="surrogateescape")
    existing_lines = text.splitlines()
    if any(line.strip() == GITIGNORE_ENTRY for line in existing_lines):
        return False

    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    entry = GITIGNORE_ENTRY.encode("utf-8")
    if not raw:
        new_raw = entry + newline
    elif raw.endswith(b"\n"):
        new_raw = raw + entry + newline
    else:
        # No trailing newline: insert one to separate the new entry from
        # the last existing line, then mirror the original's "no final
        # newline" state on the newly appended line.
        new_raw = raw + newline + entry

    _atomic_write_bytes(path, new_raw)
    return True


# ---------------------------------------------------------------------------
# Clear: delete only the runtime snapshot, never a tracker item.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClearResult:
    status: str  # "cleared" | "already_clear" | "not_confirmed"
    path: Optional[str] = None

    def to_dict(self) -> dict:
        return {"status": self.status, "path": self.path}


def clear_active_work(project_root: Path, *, confirmed: bool) -> ClearResult:
    """Delete `.agentforge/active-work.json` if, and only if, `confirmed`
    is True. Never touches any tracker item -- there is no code path in
    this function that resolves an identifier or calls a tracker adapter.
    Idempotent: clearing when no snapshot exists reports "already_clear"
    rather than an error."""
    if not confirmed:
        return ClearResult("not_confirmed")
    path = _active_state_path(project_root)
    if path is None or not path.exists():
        return ClearResult("already_clear")
    path.unlink()
    return ClearResult("cleared", path=str(path))


# ---------------------------------------------------------------------------
# Prepare-work plan/apply: the main entry point.
# ---------------------------------------------------------------------------


def _error_to_dict(error: "work_items_module.WorkItemError") -> dict:
    return {
        "kind": error.kind,
        "message": error.message,
        "identifier": error.identifier,
        "provider": error.provider,
    }


def _plan_id_payload(snapshot: dict) -> dict:
    # Excludes "prepared_at": the timestamp is expected to differ between
    # the plan call and the later apply call even when nothing about the
    # underlying work item changed, so it must never be part of the
    # approval-binding digest -- only actual content does.
    payload = dict(snapshot)
    payload.pop("prepared_at", None)
    return payload


def _compute_prepare_plan_id(snapshot: dict) -> str:
    canonical = json.dumps(_plan_id_payload(snapshot), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class PreparePlan:
    status: str
    project_root: str
    canonical_id: Optional[str] = None
    error: Optional[dict] = None
    readiness: Optional[dict] = None
    contract: Optional[dict] = None
    snapshot: Optional[dict] = None
    previous_snapshot: Optional[dict] = None
    diff: Optional[str] = None
    plan_id: Optional[str] = None
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "project_root": self.project_root,
            "canonical_id": self.canonical_id,
            "error": self.error,
            "readiness": self.readiness,
            "contract": self.contract,
            "snapshot": self.snapshot,
            "previous_snapshot": self.previous_snapshot,
            "diff": self.diff,
            "plan_id": self.plan_id,
            "notes": list(self.notes),
        }


def plan_prepare_work(
    identifier: str,
    config: Optional[dict],
    project_root: Path,
    *,
    override_blockers: bool = False,
    runner: Callable[..., "subprocess.CompletedProcess"] = subprocess.run,
    clock: Optional[Callable[[], str]] = None,
) -> PreparePlan:
    """Resolve `identifier`, check readiness and contract completeness,
    and build the exact bounded snapshot `apply_prepare_work` would write
    -- without writing anything. Statuses:

      - "resolve_error": the tracker adapter could not resolve the item.
      - "blocked_by_dependencies": one or more blockers are unresolved and
        `override_blockers` was not set.
      - "incomplete_contract": one or more of the eight required sections
        is missing or a placeholder. Run `plan_contract_update`/
        `apply_contract_update` (local tracker) or edit the tracker item
        directly, then re-run this.
      - "oversized": the snapshot does not fit `context.max_bytes` even
        after shrinking every reducible field.
      - "no_change": a previous valid snapshot already matches this item's
        identity, content digest, and blocker-override state exactly --
        applying this plan would be a true no-op.
      - "ok": ready to write; `apply_prepare_work` with this `plan_id`
        will write it.
    """
    root = Path(project_root)
    result = work_items_module.resolve_work_item(identifier, config, project_root=root, runner=runner)
    if not result.ok:
        return PreparePlan("resolve_error", str(root), error=_error_to_dict(result.error))

    item = result.item
    readiness = check_readiness(item, config, root, runner)
    if not readiness.ready and not override_blockers:
        return PreparePlan(
            "blocked_by_dependencies",
            str(root),
            canonical_id=item.canonical_id,
            readiness=readiness.to_dict(),
        )

    contract = check_work_contract(item.body)
    if not contract.complete:
        return PreparePlan(
            "incomplete_contract",
            str(root),
            canonical_id=item.canonical_id,
            readiness=readiness.to_dict(),
            contract=contract.to_dict(),
        )

    sections = parse_sections(item.body)
    allowed_paths = _extract_list_items(sections.get("may touch"))
    forbidden_paths = _extract_list_items(sections.get("must not touch"))
    verification_commands = _extract_list_items(sections.get("verification commands"))
    out_of_scope_summary = (sections.get("out of scope") or "").strip()

    snapshot: dict = {
        "schema_version": ACTIVE_STATE_SCHEMA_VERSION,
        "canonical_id": item.canonical_id,
        "title": item.title,
        "source": item.source,
        "content_digest": item.content_digest,
        "prepared_at": (clock or _now_iso)(),
        "allowed_paths": allowed_paths,
        "forbidden_paths": forbidden_paths,
        "verification_commands": verification_commands,
        "out_of_scope_summary": out_of_scope_summary,
    }
    if override_blockers and readiness.unresolved:
        snapshot["blocker_override"] = {
            "overridden": True,
            "blockers": [b.to_dict() for b in readiness.unresolved],
        }

    # Reuses work_items's own context.max_bytes extraction (with its same
    # fallback) rather than re-deriving it -- the same already-tested
    # cross-module delegation work_items.py itself uses for config's
    # relative-path check.
    max_bytes = work_items_module._extract_max_bytes(config)
    bounded, fits = bound_snapshot(snapshot, max_bytes)
    if not fits:
        return PreparePlan(
            "oversized",
            str(root),
            canonical_id=item.canonical_id,
            readiness=readiness.to_dict(),
            contract=contract.to_dict(),
            notes=[
                f"serialized snapshot exceeds context.max_bytes ({max_bytes}) "
                "even after reducing title/out_of_scope_summary"
            ],
        )

    previous = read_previous_snapshot(root)
    no_op = _is_noop(previous, bounded)
    diff = None
    if not no_op:
        before_text = json.dumps(previous, indent=2, sort_keys=True) if previous is not None else ""
        after_text = json.dumps(bounded, indent=2, sort_keys=True)
        diff = _unified_diff(before_text, after_text, "/".join(ACTIVE_STATE_REL_PARTS))

    return PreparePlan(
        "no_change" if no_op else "ok",
        str(root),
        canonical_id=item.canonical_id,
        readiness=readiness.to_dict(),
        contract=contract.to_dict(),
        snapshot=bounded,
        previous_snapshot=previous,
        diff=diff,
        plan_id=_compute_prepare_plan_id(bounded),
    )


def apply_prepare_work(
    identifier: str,
    config: Optional[dict],
    project_root: Path,
    *,
    approved_plan_id: Optional[str],
    override_blockers: bool = False,
    runner: Callable[..., "subprocess.CompletedProcess"] = subprocess.run,
    clock: Optional[Callable[[], str]] = None,
) -> PreparePlan:
    """Recompute the plan fresh, then write `.agentforge/active-work.json`
    (and surgically update `.gitignore`) only if the fresh status is "ok"
    and its `plan_id` matches `approved_plan_id` exactly -- the same
    TOCTOU-safe approval-binding shape `scripts/setup.py`'s `apply_setup`
    uses. Any other fresh status (including "no_change", where there is
    nothing to write) is returned unchanged, and a fresh "ok" whose
    `plan_id` does not match `approved_plan_id` becomes "stale" rather
    than being written anyway."""
    plan = plan_prepare_work(
        identifier,
        config,
        project_root,
        override_blockers=override_blockers,
        runner=runner,
        clock=clock,
    )
    if plan.status != "ok":
        return plan

    if not approved_plan_id or approved_plan_id != plan.plan_id:
        return PreparePlan(
            "stale",
            plan.project_root,
            canonical_id=plan.canonical_id,
            readiness=plan.readiness,
            contract=plan.contract,
            snapshot=plan.snapshot,
            previous_snapshot=plan.previous_snapshot,
            diff=plan.diff,
            plan_id=plan.plan_id,
        )

    try:
        write_snapshot_atomic(Path(project_root), plan.snapshot)
    except (OSError, RuntimeError) as exc:
        return PreparePlan(
            "write_error",
            plan.project_root,
            canonical_id=plan.canonical_id,
            readiness=plan.readiness,
            contract=plan.contract,
            snapshot=plan.snapshot,
            previous_snapshot=plan.previous_snapshot,
            plan_id=plan.plan_id,
            notes=[f"failed to write .agentforge/active-work.json: {exc}"],
        )

    gitignore_changed = update_gitignore(Path(project_root))
    plan.notes = list(plan.notes) + (
        ["updated .gitignore"] if gitignore_changed else ["gitignore already up to date"]
    )
    return plan


# ---------------------------------------------------------------------------
# Contract-update plan/apply: propose (and, for `local` only, write) the
# missing sections back into the ticket itself.
# ---------------------------------------------------------------------------


def _split_local_markdown(text: str) -> tuple:
    """Return (preamble, body): `preamble` is the front matter plus the
    first `#` heading line, verbatim; `body` is everything after it. This
    mirrors `work_items._parse_local_markdown`'s own scan exactly so a
    contract update never touches the front matter (`state`, `blockers`,
    `updated_at`) or the title heading -- identity and blocking edges stay
    untouched by construction, not by convention."""
    match = work_items_module._FRONT_MATTER_RE.match(text)
    body_start = match.end() if match else 0
    lines = text[body_start:].splitlines(keepends=True)
    heading_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("#"):
            heading_idx = i
            break
    if heading_idx is None:
        return text[:body_start], "".join(lines)
    preamble = text[:body_start] + "".join(lines[: heading_idx + 1])
    return preamble, "".join(lines[heading_idx + 1 :])


def _rebuild_body(existing_sections: dict, updates: dict) -> str:
    parts = []
    for name in REQUIRED_CONTRACT_SECTIONS:
        content = updates.get(name)
        if content is None:
            content = existing_sections.get(name.lower(), "")
        if name == "Completion evidence" and not content.strip():
            content = _DEFAULT_COMPLETION_EVIDENCE
        parts.append(f"## {name}\n\n{content.strip()}\n")
    return "\n".join(parts) + "\n"


def propose_local_contract_update(file_text: str, updates: dict) -> str:
    """Build the full new file text for a local ticket with `updates`
    (already normalized) layered onto its existing sections. The front
    matter and title heading are copied through byte-for-byte; only the
    body's eight recognized sections are rebuilt, in canonical order."""
    preamble, body = _split_local_markdown(file_text)
    existing_sections = parse_sections(body)
    new_body = _rebuild_body(existing_sections, updates)
    if not preamble.endswith("\n"):
        preamble += "\n"
    return preamble + "\n" + new_body


@dataclass
class ContractUpdatePlan:
    status: str
    project_root: str
    canonical_id: Optional[str] = None
    path: Optional[str] = None
    before: Optional[str] = None
    after: Optional[str] = None
    diff: Optional[str] = None
    contract: Optional[dict] = None
    plan_id: Optional[str] = None
    error: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "project_root": self.project_root,
            "canonical_id": self.canonical_id,
            "path": self.path,
            "diff": self.diff,
            "contract": self.contract,
            "plan_id": self.plan_id,
            "error": self.error,
        }


def _contract_update_plan_id(path: str, before: str, after: str) -> str:
    payload = {
        "path": path,
        "before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def plan_contract_update(
    identifier: str,
    config: Optional[dict],
    project_root: Path,
    updates: Optional[dict],
    *,
    runner: Callable[..., "subprocess.CompletedProcess"] = subprocess.run,
) -> ContractUpdatePlan:
    """Propose filling the ticket's missing/placeholder sections with
    `updates` (agent-drafted text, following the `work-contract` skill's
    discipline). Never writes. Statuses:

      - "resolve_error": the item could not be resolved.
      - "no_change": the contract is already complete; nothing to
        propose.
      - "unsupported_remote": the tracker is `github`/`gitlab` -- this
        module has no write path for a remote tracker item (STORY-006
        implemented fetch-only adapters). The diff is still computed and
        returned so the user can apply it manually via the tracker's own
        edit command, then re-run `/agentforge:prepare-work`.
      - "incomplete_updates": even with `updates` applied, one or more
        required sections is still missing or a placeholder.
      - "ok": `path`/`before`/`after`/`diff`/`plan_id` describe the exact
        local-file write `apply_contract_update` would perform.
    """
    root = Path(project_root)
    result = work_items_module.resolve_work_item(identifier, config, project_root=root, runner=runner)
    if not result.ok:
        return ContractUpdatePlan("resolve_error", str(root), error=_error_to_dict(result.error))

    item = result.item
    original_contract = check_work_contract(item.body)
    normalized = _normalize_updates(updates)
    merged_contract = check_work_contract(item.body, normalized)

    if original_contract.complete:
        return ContractUpdatePlan(
            "no_change", str(root), canonical_id=item.canonical_id, contract=original_contract.to_dict()
        )

    if item.provider != work_items_module.PROVIDER_LOCAL:
        # No write adapter exists for a remote tracker item (STORY-006 is
        # fetch-only), but the proposed merged body text is still useful
        # to the user as something to paste into `gh issue edit`/`glab
        # issue update` themselves -- compute it against the item's body
        # directly (there is no local file to diff against).
        existing_sections = parse_sections(item.body)
        after_text = _rebuild_body(existing_sections, normalized)
        return ContractUpdatePlan(
            "unsupported_remote",
            str(root),
            canonical_id=item.canonical_id,
            before=item.body,
            after=after_text,
            diff=_unified_diff(item.body, after_text, item.canonical_id),
            contract=merged_contract.to_dict(),
        )

    if not merged_contract.complete:
        return ContractUpdatePlan(
            "incomplete_updates",
            str(root),
            canonical_id=item.canonical_id,
            contract=merged_contract.to_dict(),
        )

    file_path = root / item.source
    before_text = file_path.read_text(encoding="utf-8")
    after_text = propose_local_contract_update(before_text, normalized)
    diff = _unified_diff(before_text, after_text, item.source)
    return ContractUpdatePlan(
        "ok",
        str(root),
        canonical_id=item.canonical_id,
        path=item.source,
        before=before_text,
        after=after_text,
        diff=diff,
        contract=merged_contract.to_dict(),
        plan_id=_contract_update_plan_id(item.source, before_text, after_text),
    )


def apply_contract_update(
    identifier: str,
    config: Optional[dict],
    project_root: Path,
    updates: Optional[dict],
    *,
    approved_plan_id: Optional[str],
    runner: Callable[..., "subprocess.CompletedProcess"] = subprocess.run,
) -> ContractUpdatePlan:
    plan = plan_contract_update(identifier, config, project_root, updates, runner=runner)
    if plan.status != "ok":
        return plan
    if not approved_plan_id or approved_plan_id != plan.plan_id:
        return ContractUpdatePlan(
            "stale",
            plan.project_root,
            canonical_id=plan.canonical_id,
            path=plan.path,
            before=plan.before,
            after=plan.after,
            diff=plan.diff,
            contract=plan.contract,
            plan_id=plan.plan_id,
        )
    _atomic_write_bytes(Path(project_root) / plan.path, plan.after.encode("utf-8"))
    return plan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_config_or_exit(project_root: Path) -> Optional[dict]:
    config_path = project_root / ".agentforge" / "config.json"
    try:
        return config_module.load_for_enforcement(config_path)
    except FileNotFoundError:
        print(
            json.dumps(
                {
                    "status": "config_error",
                    "error": f"{config_path} not found; run /agentforge:setup first",
                }
            ),
            file=sys.stderr,
        )
        return None
    except config_module.ConfigValidationError as exc:
        print(
            json.dumps(
                {"status": "config_error", "error": "; ".join(i.format() for i in exc.issues)}
            ),
            file=sys.stderr,
        )
        return None


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="active_state.py",
        description="Resolve, validate, and snapshot AgentForge active work (STORY-008).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_p = subparsers.add_parser(
        "resolve", help="Resolve readiness/contract status only; never writes."
    )
    resolve_p.add_argument("identifier")
    resolve_p.add_argument("--project-root", type=Path, default=Path("."))

    for name in ("prepare-plan", "prepare-apply"):
        sub = subparsers.add_parser(name)
        sub.add_argument("identifier")
        sub.add_argument("--project-root", type=Path, default=Path("."))
        sub.add_argument("--override-blockers", action="store_true")
        if name == "prepare-apply":
            sub.add_argument("--approved-plan-id", required=True)

    for name in ("contract-plan", "contract-apply"):
        sub = subparsers.add_parser(name)
        sub.add_argument("identifier")
        sub.add_argument("--project-root", type=Path, default=Path("."))
        sub.add_argument("--updates-json", type=Path, required=True)
        if name == "contract-apply":
            sub.add_argument("--approved-plan-id", required=True)

    clear_p = subparsers.add_parser("clear")
    clear_p.add_argument("--project-root", type=Path, default=Path("."))
    clear_p.add_argument("--confirm", action="store_true")

    args = parser.parse_args(argv)
    project_root = args.project_root

    if args.command == "clear":
        result = clear_active_work(project_root, confirmed=args.confirm)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.status != "not_confirmed" else 1

    cfg = _load_config_or_exit(project_root)
    if cfg is None:
        return 1

    if args.command == "resolve":
        result = work_items_module.resolve_work_item(
            args.identifier, cfg, project_root=project_root
        )
        if not result.ok:
            print(
                json.dumps(
                    {"status": "resolve_error", "error": _error_to_dict(result.error)}, indent=2
                )
            )
            return 1
        readiness = check_readiness(result.item, cfg, project_root)
        contract = check_work_contract(result.item.body)
        payload = {
            "status": "ok",
            "canonical_id": result.item.canonical_id,
            "title": result.item.title,
            "source": result.item.source,
            "readiness": readiness.to_dict(),
            "contract": contract.to_dict(),
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "prepare-plan":
        plan = plan_prepare_work(
            args.identifier, cfg, project_root, override_blockers=args.override_blockers
        )
        print(json.dumps(plan.to_dict(), indent=2))
        return 0 if plan.status in ("ok", "no_change") else 1

    if args.command == "prepare-apply":
        plan = apply_prepare_work(
            args.identifier,
            cfg,
            project_root,
            approved_plan_id=args.approved_plan_id,
            override_blockers=args.override_blockers,
        )
        print(json.dumps(plan.to_dict(), indent=2))
        return 0 if plan.status in ("ok", "no_change") else 1

    if args.command in ("contract-plan", "contract-apply"):
        try:
            updates = json.loads(args.updates_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(json.dumps({"status": "updates_error", "error": str(exc)}), file=sys.stderr)
            return 1
        if args.command == "contract-plan":
            plan = plan_contract_update(args.identifier, cfg, project_root, updates)
        else:
            plan = apply_contract_update(
                args.identifier, cfg, project_root, updates, approved_plan_id=args.approved_plan_id
            )
        print(json.dumps(plan.to_dict(), indent=2))
        return 0 if plan.status in ("ok", "no_change") else 1

    return 1  # pragma: no cover - argparse enforces a valid subcommand


if __name__ == "__main__":
    sys.exit(main())
