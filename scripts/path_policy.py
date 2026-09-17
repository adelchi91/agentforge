"""AgentForge canonical path utilities (STORY-014).

Builds on STORY-013's graded command-policy engine (`scripts/scope_policy.py`)
to close the two v1 path bugs characterized in
`tests/test_v1_characterization.py`:

  - `DotfileNormalizationTests` — v1's `normalise()` used
    `str.lstrip("./")`, which strips leading `.` and `/` *characters* one
    at a time rather than the `"./"` *prefix* as a unit, silently turning
    `.env` into `env`. This module never calls `str.lstrip` (or any other
    character-stripping) on a path; every operation here is segment-aware
    (`pathlib.Path` / `os.path.normpath` semantics), so a leading dot
    component survives untouched.
  - `DotDotScopeEscapeTests` — v1 only called `.resolve()` on the
    *absolute*-path branch of its scope check; a relative escape such as
    `allowed/../../outside/evil.py` was compared as a raw string and let
    through. This module resolves the project root, the target, and every
    allowed root through the same `Path.resolve(strict=False)` (symlink
    resolution plus lexical `..` normalization) *before* any ancestry
    comparison, and compares with `Path.relative_to` (a segment-aware
    check), never a string-prefix/`startswith` comparison — the latter
    would itself be a bug (`"allowed"` is not a safe prefix test against
    `"allowedx/evil.py"`).

This module only answers "is this canonicalized path in scope?" for a
single target against a single agent's allow-list. Deciding *when* to ask
that question (which `scope.mode`, which `agent_type`) is
`scripts/scope_policy.py`'s job — see its `_decide_structured` for how the
two modules are wired together, and `docs/threat-model.md` for the
documented coverage/limitations statement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Tool-input keys that carry the target path across Claude's structured
# write tools (Write/Edit/MultiEdit: "file_path"; NotebookEdit:
# "notebook_path") and Codex's apply_patch-shaped payloads ("path"/"file"),
# checked in this order. Exact, name-based lookup -- never a scan of every
# string value in tool_input hoping to find something path-shaped.
_TARGET_PATH_KEYS = ("file_path", "notebook_path", "path", "file")

# A Windows drive-letter prefix ("C:\", "C:/") or any backslash anywhere in
# the string marks a path shape this module does not understand as
# project-relative POSIX. Rejected outright as unsupported rather than
# silently mismatched against a POSIX allow-list (a backslash is not a
# path separator here, so a naive split-on-"/" would treat the whole
# Windows path as one opaque segment and never recognize it as escaping,
# and a UNC path's "\\server\share" would never collide with any allowed
# root either).
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def looks_like_windows_path(raw: str) -> bool:
    """True for a drive-letter path (`C:\\Users\\...`, `C:/Users/...`), a
    UNC path (`\\\\server\\share`), or any other backslash-separated path.
    This project only understands POSIX-style relative/absolute paths."""
    if not isinstance(raw, str) or not raw:
        return False
    if "\\" in raw:
        return True
    if _WINDOWS_DRIVE_RE.match(raw):
        return True
    return False


@dataclass(frozen=True)
class PathCheckResult:
    """Outcome of checking one target path against one agent's allow-list."""

    allowed: bool
    reason: str


def resolve_project_root(project_root: Path) -> Optional[Path]:
    """Resolve the project root itself through symlinks so every later
    ancestry comparison happens in the same realpath space. Returns None
    if the root cannot be resolved at all (e.g. a permission error walking
    an intermediate symlink)."""
    try:
        return Path(project_root).resolve(strict=False)
    except OSError:
        return None


def canonicalize_target(project_root: Path, raw_target: str) -> Optional[Path]:
    """Resolve `raw_target` to an absolute, symlink-resolved,
    `..`-normalized `Path`, rooted at `project_root` when relative.

    Returns None when `raw_target` is not a string, is empty, or is a
    Windows-shaped path this module does not support -- the caller must
    treat None as "reject, not merely no match" (see
    `docs/plans/agentforge-v2-user-stories.md` STORY-014: "Windows path
    fixtures ... rejected as unsupported/non-project-relative rather than
    silently mismatched or accepted").

    Never uses `str.lstrip("./")` or any other character-stripping --
    `Path` and `os.path.normpath` treat `.`/`..`/leading-dot components as
    whole path segments, which is what preserves a leading dot component
    like `.env` exactly.
    """
    if not isinstance(raw_target, str) or not raw_target:
        return None
    if looks_like_windows_path(raw_target):
        return None

    resolved_root = resolve_project_root(project_root)
    if resolved_root is None:
        return None

    target_path = Path(raw_target)
    combined = target_path if target_path.is_absolute() else resolved_root / target_path

    try:
        return combined.resolve(strict=False)
    except OSError:
        return None


def resolve_allow_entry(project_root: Path, entry: str) -> Optional[tuple[Path, bool]]:
    """Resolve one `scope.agents.<name>.allow` entry against `project_root`.

    Returns `(resolved_path, is_directory_root)`, where `is_directory_root`
    is True when `entry` ends with a path separator (`"allowed/"`) --
    anything under that directory is in scope -- and False when it names
    exactly one file (`".env"`) -- only that exact path is in scope. These
    are different semantics and must not be conflated: a directory-root
    entry uses ancestry (`Path.relative_to`), an exact-file entry uses
    equality.

    Returns None for an entry this module cannot resolve as a supported
    relative/absolute-within-project path (e.g. Windows-shaped) -- callers
    must skip such an entry rather than let it match everything or
    nothing by accident. In this repository `scripts/config.py` already
    rejects such entries at config-validation time (STORY-004), so this
    is defense in depth, not the primary control.
    """
    if not isinstance(entry, str) or not entry:
        return None
    if looks_like_windows_path(entry):
        return None

    resolved_root = resolve_project_root(project_root)
    if resolved_root is None:
        return None

    is_directory_root = entry.endswith("/")
    combined = resolved_root / entry
    try:
        resolved = combined.resolve(strict=False)
    except OSError:
        return None
    return resolved, is_directory_root


def _is_within(path: Path, root: Path) -> bool:
    """Segment-aware ancestry check (`path == root` counts as within).
    Never a string `startswith`/prefix comparison -- that would wrongly
    match `"allowedx/evil.py"` against an `"allowed"` root."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def check_path(project_root: Path, raw_target: str, allow_entries: list) -> PathCheckResult:
    """Check whether `raw_target` (as reported in a structured tool call's
    `tool_input`) is in scope for an agent whose allow-list is
    `allow_entries` (a list of `scope.agents.<name>.allow` strings).

    Rejects (False):
      - a target that is not a supported path shape at all (Windows-style);
      - a target that resolves outside `project_root` once symlinks and
        `..` are resolved, regardless of how it was spelled (relative
        traversal, absolute path, or a symlink whose real target escapes);
      - a target that resolves inside `project_root` but does not match
        any allow-list entry (directory-root ancestry or exact-file
        equality).

    Accepts (True) only a target that both resolves inside the project
    root and matches at least one allow-list entry.
    """
    resolved_root = resolve_project_root(project_root)
    if resolved_root is None:
        return PathCheckResult(False, f"could not resolve project root {project_root!r}")

    resolved_target = canonicalize_target(project_root, raw_target)
    if resolved_target is None:
        return PathCheckResult(
            False, f"unsupported or non-project-relative path shape: {raw_target!r}"
        )

    if not _is_within(resolved_target, resolved_root):
        return PathCheckResult(
            False,
            f"resolved target {resolved_target} is outside the project root {resolved_root}",
        )

    for entry in allow_entries:
        resolved_entry = resolve_allow_entry(project_root, entry)
        if resolved_entry is None:
            continue
        allowed_path, is_directory_root = resolved_entry
        if not _is_within(allowed_path, resolved_root):
            # A misconfigured allow entry that itself resolves outside the
            # project root (e.g. through a symlinked allowed directory)
            # can never grant access -- it is simply skipped, not treated
            # as "allow everything" or "allow nothing else".
            continue
        if is_directory_root:
            if _is_within(resolved_target, allowed_path):
                return PathCheckResult(
                    True, f"target is under allowed directory root {entry!r}"
                )
        else:
            if resolved_target == allowed_path:
                return PathCheckResult(True, f"target matches exact allowed file {entry!r}")

    return PathCheckResult(
        False, f"target {raw_target!r} does not match any allowed path for this agent"
    )


def extract_target_path(tool_input: dict) -> Optional[str]:
    """Pull the target path string out of a structured tool's `tool_input`,
    checking known field names in order (Write/Edit/MultiEdit:
    `file_path`; NotebookEdit: `notebook_path`; apply_patch-shaped
    payloads: `path`/`file`). Returns None if `tool_input` is not a dict
    or carries none of these keys as a non-empty string -- never guesses
    by scanning arbitrary values."""
    if not isinstance(tool_input, dict):
        return None
    for key in _TARGET_PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None
