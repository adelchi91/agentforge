"""AgentForge idempotent, non-destructive project setup (STORY-005).

Plans and applies the one-time-per-change transaction that
`/agentforge:setup` performs on a target project: creating or updating a
single delimited block (`<!-- agentforge:start -->` .. `<!-- agentforge:end
-->`) inside exactly one constitution file (`CLAUDE.md` or `AGENTS.md`), and
creating `.agentforge/config.json` from the validated template
(`scripts/config.py`, STORY-004) when it does not already exist.

Two entry points, matching the story's "separate planning from application"
requirement:

  - `plan_setup(project_root, constitution_target=None)` never writes to
    disk. It returns a `SetupPlan` describing every file that would change,
    as an exact diff, plus informational notes about state this story does
    not touch (existing Claude settings, Git hook management). Its status is
    one of:
      - "ok": `plan.changes` is the exact, ready-to-apply file list, and
        `plan.plan_id` is the approval-binding identifier for exactly this
        proposal (see "Approval binding" below).
      - "needs_choice": neither or both of CLAUDE.md/AGENTS.md exist and no
        `constitution_target` was given; `plan.choices` names the options.
      - "blocked": a malformed AgentForge marker block or an invalid
        existing `.agentforge/config.json` was found; `plan.blocking_issues`
        carries precise diagnostics. Nothing may be written in this state.
  - `apply_setup(project_root, *, approved_plan_id, constitution_target=None)`
    requires the `plan_id` of the exact plan the user approved. It
    recomputes the plan immediately before writing and compares the fresh
    `plan_id` against `approved_plan_id`:
      - if they match and the fresh status is "ok", every non-"none" change
        is written and the (still "ok") plan is returned;
      - if the fresh status is not "ok" (a needs_choice/blocked condition
        newly appeared), that fresh plan is returned unchanged, nothing is
        written;
      - if the fresh status is "ok" but `plan_id` differs from
        `approved_plan_id` — project state changed after the user approved
        the original proposal — status "stale" is returned instead, with
        the newly computed `changes`/`notes`/`plan_id` attached, and nothing
        is written. The caller must present this new plan and obtain a new
        approval before calling `apply_setup` again with the new `plan_id`.
    This is what makes cancellation (never calling apply), a
    blocked/needs_choice plan, and a stale plan all write nothing.

Approval binding (STORY-005 follow-up: approval-binding/TOCTOU fix). A
`plan_id` is a SHA-256 hex digest over a canonical JSON document capturing
everything that could make an approved plan wrong to apply verbatim: the
resolved constitution target, the existence/content hash of every input file
(`CLAUDE.md`, `AGENTS.md`, `.agentforge/config.json`), the proposed action
and output-content hash for every planned change, and the content hash of
this plugin's own templates (`AGENTFORGE_BLOCK`,
`templates/agentforge-config.json`) — so a plugin upgrade between plan and
apply also invalidates a stale approval. See `_compute_plan_id`.

Transaction honesty (requirement 8/9): this is **one approved transaction
with stale-plan protection, not a filesystem-atomic multi-file transaction**.
Each individual file write is atomic in isolation (`_write_text` writes to a
sibling temp file and `os.replace`s it into place, so no reader ever
observes a truncated/partial file), but if a write fails partway through a
multi-file plan (e.g. permission denied creating `.agentforge/`), the files
already written before the failure are **not** rolled back. Re-running setup
afterward is always safe — plan_setup will simply report the remaining
files that still need the change (see `TransactionHonestyTests` in
`tests/test_setup_idempotence.py`).

Byte-for-byte preservation (STORY-005 requirement 14): every read/write in
this module goes through raw bytes decoded/encoded as UTF-8, never through a
text-mode file handle, so no universal-newline translation ever touches a
byte the module did not deliberately place there. Inserting a new block
never rewrites existing bytes — it only appends after them, or (when a
well-formed AgentForge block already exists) replaces exactly the span from
`<!-- agentforge:start -->` through `<!-- agentforge:end -->`, leaving every
byte before and after that span untouched. This is also what makes a second
identical `apply_setup` call idempotent: the recomputed block is byte-equal
to the one already on disk, so its `FileChange.action` is "none".

Marker validation (STORY-005 requirement 10) is a single rule: a file must
contain exactly one `<!-- agentforge:start -->` and exactly one
`<!-- agentforge:end -->`, with the start before the end. Any other count or
order — unmatched, duplicated, or nested — is reported as "blocked" and
never partially repaired.

This module makes no network call and performs no Git or
`.claude/settings*.json` mutation (STORY-005 requirement 15 scope boundary;
STORY-011 through STORY-014 own Git-hook and scope-policy installation). It
may run one local, read-only `git config --show-origin --get
core.hooksPath` subprocess call (never `--add`/`--set`/`--unset`) to report
the *effective* Git hook-path configuration — local, worktree, global, and
system combined — falling back to a direct (repo-local only) parse of
`.git/config` if the `git` executable itself cannot be run at all. See
`_git_effective_hooks_path`.
"""

from __future__ import annotations

import argparse
import configparser
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    from . import config as config_module  # imported as scripts.setup (e.g. tests)
except ImportError:
    import config as config_module  # executed directly: python3 scripts/setup.py

MARKER_START = "<!-- agentforge:start -->"
MARKER_END = "<!-- agentforge:end -->"

# The single source of truth for the managed block's content. Mirrored
# byte-for-byte (plus one trailing newline) by templates/claude-agent-skills-block.md
# and checked equal in tests/test_setup_idempotence.py::TemplateFileTests,
# the same pattern test_config.py::TemplateFileTests uses for
# templates/agentforge-config.json. Kept short per requirement 7: pointers
# only, no duplication of Matt's own setup block content.
AGENTFORGE_BLOCK = (
    "<!-- agentforge:start -->\n"
    "AgentForge companion layer — do not hand-edit; managed by `/agentforge:setup`.\n"
    "\n"
    "- Policy configuration: `.agentforge/config.json` (schema: `docs/agentforge-config.md`).\n"
    "- Tracker and domain documentation: `docs/agents/`, when present.\n"
    "- Work-contract discipline: use the AgentForge `work-contract` skill for What to build / "
    "Blocked by / Acceptance criteria / May touch / Must not touch / Verification commands / "
    "Out of scope / Completion evidence.\n"
    "<!-- agentforge:end -->"
)

_CONFIG_TEMPLATE_PATH = _REPO_ROOT / "templates" / "agentforge-config.json"

_CONSTITUTION_FILE_NAMES = ("CLAUDE.md", "AGENTS.md")


class MarkerScanError(Exception):
    """Raised for a malformed, nested, duplicated, or unmatched marker pair."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NeedsChoice(Exception):
    """Raised when the caller must supply `constitution_target` explicitly."""

    def __init__(self, options: list):
        self.options = list(options)
        super().__init__(f"a constitution target choice is required: {self.options}")


class SetupBlocked(Exception):
    """Raised when the plan cannot proceed without risking data loss."""

    def __init__(self, issues: list):
        self.issues = list(issues)
        super().__init__("; ".join(self.issues))


@dataclass(frozen=True)
class FileChange:
    """One planned (or applied) change to a single project-relative path."""

    path: str
    action: str  # "create" | "update" | "none"
    before: Optional[str]
    after: Optional[str]
    diff: Optional[str]
    reason: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "action": self.action,
            "diff": self.diff,
            "reason": self.reason,
        }


@dataclass
class SetupPlan:
    """The full result of `plan_setup`/`apply_setup`.

    `status` is "ok", "needs_choice", "blocked", or "stale" — see the
    module docstring. `changes` and `blocking_issues`/`choices` are
    mutually populated depending on `status`; `notes` (informational, never
    blocking) is always populated. `plan_id` is populated whenever
    `changes` is (status "ok" or "stale") and is the approval-binding
    identifier `apply_setup` requires — see `_compute_plan_id`.
    """

    status: str
    project_root: str
    choices: list = field(default_factory=list)
    blocking_issues: list = field(default_factory=list)
    changes: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    plan_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "project_root": self.project_root,
            "plan_id": self.plan_id,
            "choices": list(self.choices),
            "blocking_issues": list(self.blocking_issues),
            "changes": [change.to_dict() for change in self.changes],
            "notes": list(self.notes),
        }

    def change_for(self, path: str) -> Optional[FileChange]:
        for change in self.changes:
            if change.path == path:
                return change
        return None


def _read_text(path: Path) -> str:
    """Decode-only read: bytes -> str, no universal-newline translation."""
    return path.read_bytes().decode("utf-8")


def _write_text(path: Path, text: str) -> None:
    """Encode-only write: str -> bytes, no universal-newline translation.

    Writes to a sibling temp file and `os.replace`s it into place, so this
    one file's write is atomic in isolation — no reader ever observes a
    truncated or partially written file. This does NOT make a multi-file
    `apply_setup` transaction atomic as a whole: see the module docstring's
    "Transaction honesty" note.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
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


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hash_record(path: Path) -> dict:
    """Existence + content hash of one input file, for `_compute_plan_id`.
    Never raises for a missing file; a read error on an existing file is
    allowed to propagate (the same failure plan_constitution/
    plan_agentforge_config would already have hit reading that same path)."""
    if not path.exists():
        return {"exists": False, "sha256": None}
    return {"exists": True, "sha256": _sha256_hex(path.read_bytes())}


def _compute_plan_id(root: Path, resolved_target: str, changes: list) -> str:
    """The approval-binding identifier (requirement 1): a SHA-256 digest
    over the complete approved transaction — the resolved constitution
    target, every relevant input file's existence/content hash, every
    proposed change's action and output-content hash, and this plugin's
    own template content hashes. Two calls with identical project state and
    an identical resolved plan always produce the same id; any difference
    in any of those inputs changes it."""
    payload = {
        "constitution_target": resolved_target,
        "inputs": {
            "CLAUDE.md": _file_hash_record(root / "CLAUDE.md"),
            "AGENTS.md": _file_hash_record(root / "AGENTS.md"),
            ".agentforge/config.json": _file_hash_record(root / ".agentforge" / "config.json"),
        },
        "changes": [
            {
                "path": change.path,
                "action": change.action,
                "after_sha256": (
                    _sha256_hex(change.after.encode("utf-8"))
                    if change.after is not None
                    else None
                ),
            }
            for change in changes
        ],
        "template_versions": {
            "agentforge_block_sha256": _sha256_hex(AGENTFORGE_BLOCK.encode("utf-8")),
            "agentforge_config_template_sha256": _sha256_hex(_CONFIG_TEMPLATE_PATH.read_bytes()),
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _sha256_hex(canonical.encode("utf-8"))


def unified_diff(before: str, after: str, path: str) -> Optional[str]:
    if before == after:
        return None
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    diff = difflib.unified_diff(
        before_lines, after_lines, fromfile=f"a/{path}", tofile=f"b/{path}"
    )
    return "".join(diff)


def detect_newline(text: str) -> str:
    """CRLF if any '\\r\\n' is present in the file, else LF. A brand-new
    file (empty text) defaults to LF."""
    return "\r\n" if "\r\n" in text else "\n"


def find_agentforge_block(text: str) -> Optional[tuple]:
    """Return the (start, end) character span of the single well-formed
    AgentForge block in `text` (markers included), or None if no marker is
    present at all.

    Raises `MarkerScanError` for anything else: an unmatched start or end,
    more than one of either (duplicated or nested), or an end that appears
    before its start. A count-based rule catches every one of those shapes
    without needing to special-case "nested" vs. "duplicated" separately —
    both produce more than one start and/or end marker.
    """
    starts = [m.start() for m in re.finditer(re.escape(MARKER_START), text)]
    ends = [m.start() for m in re.finditer(re.escape(MARKER_END), text)]

    if not starts and not ends:
        return None

    if len(starts) != 1 or len(ends) != 1:
        raise MarkerScanError(
            f"found {len(starts)} '{MARKER_START}' marker(s) and {len(ends)} "
            f"'{MARKER_END}' marker(s); expected exactly one matched pair "
            "(malformed, duplicated, or nested AgentForge markers)"
        )

    start, end_start = starts[0], ends[0]
    if start >= end_start:
        raise MarkerScanError(
            f"'{MARKER_END}' appears before '{MARKER_START}'; AgentForge "
            "markers are out of order"
        )
    return start, end_start + len(MARKER_END)


def _plan_block_change(rel_path: str, original_text: str, exists: bool) -> FileChange:
    try:
        span = find_agentforge_block(original_text)
    except MarkerScanError as exc:
        raise SetupBlocked([f"{rel_path}: {exc.message}"]) from exc

    newline = detect_newline(original_text) if original_text else "\n"
    rendered = AGENTFORGE_BLOCK if newline == "\n" else AGENTFORGE_BLOCK.replace("\n", newline)

    if span is not None:
        start, end = span
        existing_block = original_text[start:end]
        if existing_block == rendered:
            return FileChange(
                rel_path,
                "none",
                original_text,
                original_text,
                None,
                "AgentForge block already present and up to date.",
            )
        new_text = original_text[:start] + rendered + original_text[end:]
        return FileChange(
            rel_path,
            "update",
            original_text,
            new_text,
            unified_diff(original_text, new_text, rel_path),
            "AgentForge block content differs from the current template; "
            "refreshing the block only, all surrounding content is left unchanged.",
        )

    if original_text == "":
        new_text = rendered + newline
    else:
        separator = ("" if original_text.endswith(("\n", "\r\n")) else newline) + newline
        new_text = original_text + separator + rendered + newline

    action = "create" if not exists else "update"
    reason = (
        "Creating the constitution file with the AgentForge pointer block."
        if not exists
        else "Appending the AgentForge pointer block; existing content is preserved unchanged above it."
    )
    return FileChange(
        rel_path,
        action,
        original_text if exists else None,
        new_text,
        unified_diff(original_text if exists else "", new_text, rel_path),
        reason,
    )


def _require_valid_target(name: str) -> None:
    if name not in _CONSTITUTION_FILE_NAMES:
        raise SetupBlocked(
            [
                "constitution: --constitution-target must be 'CLAUDE.md' or "
                f"'AGENTS.md' (got: {name!r})"
            ]
        )


def plan_constitution(project_root: Path, target_name: Optional[str]) -> FileChange:
    """Implements requirements 3-6: neither exists -> ask; one exists ->
    edit only that one; both exist -> require an explicit choice, unless
    exactly one of the two already carries a well-formed AgentForge block
    (an unambiguous record of a prior choice), in which case that one is
    reused automatically so a repeat run stays idempotent without the
    caller re-supplying the same answer every time."""
    claude_path = project_root / "CLAUDE.md"
    agents_path = project_root / "AGENTS.md"
    claude_exists = claude_path.exists()
    agents_exists = agents_path.exists()

    if not claude_exists and not agents_exists:
        if target_name is None:
            raise NeedsChoice(list(_CONSTITUTION_FILE_NAMES))
        _require_valid_target(target_name)
        return _plan_block_change(target_name, "", exists=False)

    if claude_exists != agents_exists:
        chosen_rel = "CLAUDE.md" if claude_exists else "AGENTS.md"
        if target_name is not None and target_name != chosen_rel:
            raise SetupBlocked(
                [
                    f"constitution: --constitution-target {target_name} was given, "
                    f"but only {chosen_rel} exists in this project"
                ]
            )
        original_text = _read_text(project_root / chosen_rel)
        return _plan_block_change(chosen_rel, original_text, exists=True)

    # Both exist.
    claude_text = _read_text(claude_path)
    agents_text = _read_text(agents_path)
    try:
        claude_span = find_agentforge_block(claude_text)
    except MarkerScanError as exc:
        raise SetupBlocked([f"CLAUDE.md: {exc.message}"]) from exc
    try:
        agents_span = find_agentforge_block(agents_text)
    except MarkerScanError as exc:
        raise SetupBlocked([f"AGENTS.md: {exc.message}"]) from exc

    resolved = target_name
    if resolved is None:
        if claude_span is not None and agents_span is None:
            resolved = "CLAUDE.md"
        elif agents_span is not None and claude_span is None:
            resolved = "AGENTS.md"
        elif claude_span is not None and agents_span is not None:
            raise SetupBlocked(
                [
                    "Both CLAUDE.md and AGENTS.md already contain an AgentForge "
                    "block; specify --constitution-target to choose which one "
                    "AgentForge should manage."
                ]
            )
        else:
            raise NeedsChoice(list(_CONSTITUTION_FILE_NAMES))

    _require_valid_target(resolved)
    chosen_text = claude_text if resolved == "CLAUDE.md" else agents_text
    return _plan_block_change(resolved, chosen_text, exists=True)


def plan_agentforge_config(project_root: Path) -> FileChange:
    """Implements requirements 8-9: create `.agentforge/config.json` from
    the validated template only when it is absent; an existing, valid
    config is left untouched; an existing, invalid config blocks the whole
    transaction with precise diagnostics rather than being replaced."""
    rel_path = ".agentforge/config.json"
    target = project_root / ".agentforge" / "config.json"

    if not target.exists():
        after = _read_text(_CONFIG_TEMPLATE_PATH)
        return FileChange(
            rel_path,
            "create",
            None,
            after,
            unified_diff("", after, rel_path),
            "AgentForge config does not exist; creating it from the validated template.",
        )

    try:
        config_module.load_for_enforcement(target)
    except config_module.ConfigValidationError as exc:
        raise SetupBlocked([f"{rel_path}: {issue.format()}" for issue in exc.issues]) from exc

    existing_text = _read_text(target)
    return FileChange(
        rel_path,
        "none",
        existing_text,
        existing_text,
        None,
        "Existing AgentForge config is valid; left unchanged.",
    )


def _git_hooks_path(project_root: Path) -> Optional[str]:
    """Local-only fallback (requirement 11): a direct parse of this
    repository's own `.git/config`. Used only when the `git` executable
    cannot be run at all — it does not see worktree, global, or system
    configuration, which is exactly the gap `_git_effective_hooks_path`
    exists to close when Git is available."""
    git_config = project_root / ".git" / "config"
    if not git_config.exists():
        return None
    parser = configparser.ConfigParser(strict=False)
    try:
        parser.read(git_config, encoding="utf-8")
    except configparser.Error:
        return None
    if parser.has_option("core", "hooksPath"):
        return parser.get("core", "hooksPath")
    return None


def _run_git_config_show_origin(project_root: Path) -> subprocess.CompletedProcess:
    """Thin, mockable wrapper around one read-only Git call. Never passes
    `--add`/`--set`/`--unset`/`--replace-all` — `--get` only ever reads."""
    return subprocess.run(
        ["git", "config", "--show-origin", "--get", "core.hooksPath"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=5,
    )


def _git_effective_hooks_path(project_root: Path) -> tuple:
    """Requirement 10: the *effective* `core.hooksPath` — local, worktree,
    global, and system configuration combined, exactly as Git itself would
    resolve it — via a read-only `git config --show-origin --get
    core.hooksPath` call. Returns `(value, origin_description)`, or
    `(None, None)` if nothing is configured anywhere.

    Falls back to `_git_hooks_path` (repo-local `.git/config` only) whenever
    the `git` executable cannot be run to completion at all (requirement
    11) — a missing binary (`OSError`/`FileNotFoundError`), or any other
    `subprocess` failure such as a hung call hitting `timeout=5`
    (`subprocess.TimeoutExpired`, which is a `SubprocessError`, not an
    `OSError` — this call is read-only regardless, so falling back on any
    such failure is always safe) — not when Git runs successfully and
    simply reports nothing configured, which is itself the correct
    effective answer."""
    try:
        result = _run_git_config_show_origin(project_root)
    except (OSError, subprocess.SubprocessError):
        value = _git_hooks_path(project_root)
        if value is None:
            return None, None
        return value, "local .git/config (git executable unavailable)"

    if result.returncode != 0:
        return None, None

    output = result.stdout.strip()
    if not output:
        return None, None
    origin, _, value = output.rpartition("\t")
    if not value:
        return None, None
    return value, (origin or "git")


def _inspect_report(project_root: Path) -> list:
    """Requirement 1/11: inspect (never mutate) docs/agents/, Claude
    settings, and Git-hook management, and surface what was found as
    informational notes. No note here ever becomes a FileChange — STORY-005
    makes no settings or Git-hook writes (requirement 15's scope
    boundary)."""
    notes = []

    docs_agents = project_root / "docs" / "agents"
    notes.append(
        f"docs/agents/ {'present' if docs_agents.is_dir() else 'not present'}; "
        "no changes proposed to it."
    )

    for name in ("settings.json", "settings.local.json"):
        settings_path = project_root / ".claude" / name
        if settings_path.exists():
            notes.append(f".claude/{name} exists; left unchanged (no settings changes in STORY-005).")

    hooks_path, hooks_path_origin = _git_effective_hooks_path(project_root)
    if hooks_path is not None:
        notes.append(
            f"effective git core.hooksPath is {hooks_path!r} (origin: "
            f"{hooks_path_origin}); no Git-hook changes proposed."
        )

    commit_msg_hook = project_root / ".git" / "hooks" / "commit-msg"
    if commit_msg_hook.exists():
        notes.append(".git/hooks/commit-msg already exists; left unchanged.")

    pre_push_hook = project_root / ".git" / "hooks" / "pre-push"
    if pre_push_hook.exists():
        notes.append(".git/hooks/pre-push already exists; left unchanged.")

    husky_dir = project_root / ".husky"
    if husky_dir.is_dir():
        notes.append(".husky/ present; another Git-hook manager appears to own hooks here.")

    pre_commit_config = project_root / ".pre-commit-config.yaml"
    if pre_commit_config.exists():
        notes.append(".pre-commit-config.yaml present; the pre-commit framework appears to own hooks here.")

    any_hook_manager = bool(
        hooks_path or commit_msg_hook.exists() or pre_push_hook.exists()
        or husky_dir.is_dir() or pre_commit_config.exists()
    )
    notes.append(
        "Git-hook commit/push traceability enforcement is not installed by this "
        "story (STORY-011/012). When it is, the available integration modes are: "
        "chained installation alongside the existing hook manager"
        + (" detected above" if any_hook_manager else "")
        + ", documented manual integration, or CI-only enforcement."
    )

    return notes


def plan_setup(project_root: Any, *, constitution_target: Optional[str] = None) -> SetupPlan:
    """Never writes to disk. See the module docstring for `status` meanings."""
    root = Path(project_root)
    notes = _inspect_report(root)
    try:
        constitution_change = plan_constitution(root, constitution_target)
        config_change = plan_agentforge_config(root)
    except NeedsChoice as exc:
        return SetupPlan("needs_choice", str(root), choices=exc.options, notes=notes)
    except SetupBlocked as exc:
        return SetupPlan("blocked", str(root), blocking_issues=exc.issues, notes=notes)

    changes = [constitution_change, config_change]
    plan_id = _compute_plan_id(root, constitution_change.path, changes)
    return SetupPlan("ok", str(root), changes=changes, notes=notes, plan_id=plan_id)


def apply_setup(
    project_root: Any,
    *,
    approved_plan_id: Optional[str] = None,
    constitution_target: Optional[str] = None,
) -> SetupPlan:
    """The caller must supply the `plan_id` of the exact plan the user
    approved (requirement 3) — the CLI's `apply` subcommand enforces this
    with a required `--approved-plan-id` flag; this Python function accepts
    it as an optional keyword so a caller with nothing to approve yet (a
    blocked/needs_choice plan) can still call it without an id and simply
    get that same status back.

    Recomputes the plan immediately before writing (requirement 4):

      - a non-"ok" fresh status (needs_choice/blocked) is returned as-is,
        nothing is written, regardless of `approved_plan_id`;
      - an "ok" fresh status whose `plan_id` does not match
        `approved_plan_id` (including a missing/`None` `approved_plan_id`)
        means there is no valid approval for this exact proposal — project
        state may have changed after approval, or approval was never
        given. Returns status "stale" carrying the fresh
        changes/notes/plan_id, nothing is written (requirement 5);
      - an "ok" fresh status whose `plan_id` matches writes every
        non-"none" change and returns the (still "ok") fresh plan.

    This is what makes cancellation, a blocked/needs_choice result, and a
    stale result all write nothing (requirement 12's guarantee, extended).
    """
    plan = plan_setup(project_root, constitution_target=constitution_target)
    if plan.status != "ok":
        return plan

    if not approved_plan_id or plan.plan_id != approved_plan_id:
        return SetupPlan(
            "stale",
            plan.project_root,
            changes=plan.changes,
            notes=plan.notes,
            plan_id=plan.plan_id,
        )

    root = Path(project_root)
    for change in plan.changes:
        if change.action == "none":
            continue
        _write_text(root / change.path, change.after)
    return plan


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="setup.py", description="Plan or apply AgentForge project setup."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("plan", "apply"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--project-root", type=Path, default=Path("."))
        sub.add_argument(
            "--constitution-target",
            choices=_CONSTITUTION_FILE_NAMES,
            default=None,
        )
        if name == "apply":
            sub.add_argument(
                "--approved-plan-id",
                required=True,
                help="The plan_id printed by a prior 'plan' run that the user approved.",
            )

    args = parser.parse_args(argv)

    if args.command == "plan":
        plan = plan_setup(args.project_root, constitution_target=args.constitution_target)
    else:
        plan = apply_setup(
            args.project_root,
            constitution_target=args.constitution_target,
            approved_plan_id=args.approved_plan_id,
        )

    print(json.dumps(plan.to_dict(), indent=2))
    return 0 if plan.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
