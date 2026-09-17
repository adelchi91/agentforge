"""AgentForge commit-message traceability policy (STORY-011).

Enforces commit traceability at the Git layer instead of scanning
arbitrary shell-command text — the fragile, bypassable approach
characterized in
`tests/test_v1_characterization.py::StoryTokenOutsideMessageTests` and
`::GitDashCPushBypassTests` (a STORY-XXX token anywhere in a Bash command
line, or `git -C <dir> push`, satisfied v1's PreToolUse check). Per the
execution plan's decision #1 ("Commit traceability moves to Git, not
another Bash regex") and ADR-0004, the real enforcement boundary is a Git
`commit-msg` hook that reads the *actual commit message file* Git passes
it — never the shell command that produced it.

This module has two responsibilities, both scoped to a single commit at a
time (STORY-012's pre-push *range* validation is explicitly out of scope
here):

  1. **Validation** (`validate_commit_message`, `check_commit_message_file`,
     `check_commit`) — parse the real message text, check it against the
     project's configured `identifier.pattern` (from `.agentforge/
     config.json`, STORY-004), and apply the one narrow default exemption
     (Git's own auto-generated merge-commit messages). This is what the
     installed hook (`templates/git-hooks/commit-msg`) and a CI fallback
     both call, so there is exactly one implementation of "is this
     message compliant" instead of a shell copy and a Python copy that
     can drift apart.
  2. **Installation** (`plan_hook_install`, `apply_hook_install`) —
     decide, for a given project, whether a
     `commit-msg` hook can be safely chain-installed, must be documented
     as a manual integration, or should fall back to CI-only enforcement.
     Never overwrites another hook manager's `commit-msg` script; reuses
     `scripts.setup.detect_hook_managers` (STORY-005) for the Husky/
     pre-commit-framework/`core.hooksPath` detection instead of
     re-deriving it.

Identifier matching reuses the exact `identifier.pattern`/`fullmatch`
contract `scripts/work_items.py` and `scripts/config.py` already
establish (see `docs/agentforge-config.md`: "fullmatch semantics are what
STORY-010's prompt-scanning and STORY-011's commit-message checks rely
on") rather than inventing a second, provider-specific pattern scheme.
`find_identifier_reference` tokenizes the message and requires a whole
token to `fullmatch` the configured pattern — the same semantics
`work_items._resolve_local_path` already applies to a bare local
identifier — so a GitHub config's `"^#\\d+$"`, a GitLab config's the
same, and a local config's `"^STORY-\\d{3,}$"` are all handled by one
generic mechanism driven entirely by the project's own config, never a
hardcoded per-provider regex.

No network access, no third-party dependency: stdlib `json`/`re`/
`subprocess` only, matching every other `scripts/*.py` module (ADR-0005).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config as agentforge_config  # noqa: E402
from scripts import setup as agentforge_setup  # noqa: E402

# --------------------------------------------------------------------------
# Commit-message parsing
# --------------------------------------------------------------------------

# Git's own `git commit -v` / `--verbose` scissors line: an exact,
# unambiguous marker for "everything from here down is a diff Git added
# for the editor, not part of the message." Stripped along with
# everything after it, regardless of `core.cleanup`/`core.commentChar`
# configuration, because this exact text is what Git itself generates.
_SCISSORS_LINE = "# ------------------------ >8 ------------------------"

# A line is treated as a `core.commentChar` comment line only when the
# comment character is followed by whitespace or end-of-line (Git's own
# editor template always writes "# ..." with a space). A line that starts
# with '#' immediately followed by a digit — e.g. a GitHub/GitLab-style
# "#123: fix the thing" subject — is deliberately NOT treated as a
# comment: a provider whose identifier.pattern is "^#\\d+$" can produce
# exactly this shape, and generically stripping every line starting with
# '#' would silently erase a real, user-written identifier reference
# (the same class of bug this story exists to avoid, just relocated into
# the parser instead of the policy). This is a narrow heuristic, not a
# full re-implementation of Git's cleanup logic; see docs/threat-model.md.
_COMMENT_LINE_RE = re.compile(r"^#(\s|$)")

# Git's own auto-generated merge-commit subject shapes only (`git merge`
# with no `-m` produces exactly one of these). Includes the plural
# octopus-merge form ("Merge branches 'b1' and 'b2'", confirmed by
# actually running `git merge --no-ff --no-edit b1 b2`) alongside the
# ordinary two-way singular forms — code review against this story's own
# diff caught that an earlier version of this pattern only matched the
# singular and would have wrongly required a traceability reference on a
# legitimate multi-branch merge. Deliberately narrow per the execution
# plan's decision that default exemptions must be narrow: no
# revert-commit exemption, no "any subject containing the word merge"
# heuristic, and no project-configurable exemption list — see the
# "Exemptions" section of docs/threat-model.md and this story's final
# report for the config-schema extension this would require but that is
# out of STORY-011's stated scope (scripts/config.py is not in it).
_MERGE_COMMIT_SUBJECT_RE = re.compile(
    r"^Merge (branch|branches|tag|tags|remote-tracking branch|remote-tracking branches) '"
)

# Punctuation stripped from the edges of a candidate token before
# fullmatch-testing it against identifier.pattern, so "STORY-042:",
# "(STORY-042)", and "STORY-042." all still match a pattern anchored with
# fullmatch semantics. Deliberately excludes '#', '/', '-', '_', and '.'
# in the middle of a token — those can be load-bearing inside an
# identifier (`#123`, `owner/repo#123`, `STORY-042`).
_CANDIDATE_STRIP_CHARS = ".,:;!?()[]{}'\"`"


@dataclass(frozen=True)
class CommitMessage:
    """A parsed commit message. `cleaned` has the scissors line (and
    everything after it) and Git's own comment lines removed; `subject`
    is `cleaned`'s first non-empty line, stripped."""

    raw: str
    cleaned: str
    subject: str


def strip_comment_lines(raw: str) -> str:
    """Remove the `git commit -v` scissors line (and everything after it)
    and any `core.commentChar` comment line — see `_COMMENT_LINE_RE`'s
    docstring for why a '#123'-shaped identifier line is preserved."""
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kept: list[str] = []
    for line in lines:
        if line.rstrip() == _SCISSORS_LINE.rstrip() or line == _SCISSORS_LINE:
            break
        if _COMMENT_LINE_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def parse_commit_message(raw: str) -> CommitMessage:
    """Parse the raw bytes-decoded content of a Git commit message file."""
    cleaned = strip_comment_lines(raw)
    subject = ""
    for line in cleaned.split("\n"):
        if line.strip():
            subject = line.strip()
            break
    return CommitMessage(raw=raw, cleaned=cleaned, subject=subject)


def is_git_merge_commit(subject: str) -> bool:
    """True only for Git's own auto-generated merge-commit subject shapes
    (`Merge branch '...'`/`Merge branches '...' and '...'`, `Merge
    remote-tracking branch(es) '...'`, `Merge tag(s) '...'`, each
    optionally followed by `into <ref>`). A GitHub/GitLab server-side
    "Merge pull request #123 from ..." message is deliberately NOT
    included — that is a hosting-provider convention, not something Git
    itself generates, and the execution plan calls for a narrow
    default."""
    return bool(_MERGE_COMMIT_SUBJECT_RE.match(subject.strip()))


def find_identifier_reference(text: str, pattern: str) -> Optional[str]:
    """Return the first whitespace-delimited token in `text` that
    `re.fullmatch`es `pattern` once edge punctuation is stripped, or None.

    This is deliberately a whole-token fullmatch, not `pattern.search`
    against the raw text: `identifier.pattern` values are written and
    validated (`scripts/config.py::_validate_identifier`) as fullmatch
    patterns anchored with `^...$`, exactly like `work_items.py`'s
    existing bare-local-identifier check. Scanning tokens keeps that
    single semantics instead of introducing a second, subtly different
    "search anywhere" interpretation of the same field.
    """
    try:
        compiled = re.compile(pattern)
    except re.error:
        return None
    for raw_token in text.split():
        candidate = raw_token.strip(_CANDIDATE_STRIP_CHARS)
        if candidate and compiled.fullmatch(candidate):
            return candidate
    return None


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of checking one commit message.

    `ok` is what a caller should act on: under `traceability.mode ==
    "enforce"` a non-ok result must block the commit; under "observe" (or
    when `ok` is already True) it never does. `blocking` records whether
    this *specific* result came from a mode that blocks, independent of
    `ok`, so a caller can distinguish "compliant" from "non-compliant but
    only observed" in its own reporting.
    """

    ok: bool
    reason: str
    blocking: bool
    exempt: bool = False


def _mode_from_cfg(cfg: dict) -> str:
    """The effective `traceability.mode`, defaulting to `"off"` for any
    unrecognized or missing shape. The single implementation of this
    lookup: `validate_commit_message` (STORY-011) and STORY-012's
    `_evaluate_shas`/`run_pre_push_check`/`run_range_check` all call this
    rather than each re-deriving the same `cfg["traceability"]["mode"]`
    unwrapping independently."""
    traceability_cfg = cfg.get("traceability") if isinstance(cfg, dict) else None
    mode = traceability_cfg.get("mode") if isinstance(traceability_cfg, dict) else None
    if mode not in agentforge_config.TRACEABILITY_MODES:
        mode = "off"
    return mode


def validate_commit_message(raw_message: str, cfg: dict) -> ValidationResult:
    """Validate one raw commit-message file's content against `cfg`
    (an already-schema-validated `.agentforge/config.json`, STORY-004).
    Never raises for a recognized configuration shape; never inspects
    anything other than `raw_message` and `cfg` — no shell text, no
    environment variables, no other files."""
    mode = _mode_from_cfg(cfg)

    if mode == "off":
        return ValidationResult(True, "traceability.mode is 'off'; no check performed.", blocking=False)

    blocking = mode == "enforce"

    parsed = parse_commit_message(raw_message)

    if is_git_merge_commit(parsed.subject):
        return ValidationResult(
            True,
            f"exempt: Git auto-generated merge-commit subject ({parsed.subject!r}).",
            blocking=blocking,
            exempt=True,
        )

    identifier_cfg = cfg.get("identifier") if isinstance(cfg, dict) else None
    pattern = identifier_cfg.get("pattern") if isinstance(identifier_cfg, dict) else None
    examples = identifier_cfg.get("examples") if isinstance(identifier_cfg, dict) else None

    if not isinstance(pattern, str) or not pattern:
        message = (
            "traceability.mode is "
            f"{mode!r} but identifier.pattern is missing or invalid; cannot check "
            "traceability."
        )
        return ValidationResult(not blocking, message, blocking=blocking)

    found = find_identifier_reference(parsed.cleaned, pattern)
    if found:
        return ValidationResult(
            True, f"commit message references {found!r} (matches identifier.pattern).", blocking=blocking
        )

    example_hint = ""
    if isinstance(examples, list) and examples:
        example_hint = f" Example: a subject like {examples[0]!r} somewhere in the message."
    message = (
        "commit message does not reference a work-item identifier matching "
        f"identifier.pattern {pattern!r}.{example_hint}"
    )
    return ValidationResult(False, message, blocking=blocking)


def load_project_config(project_root: Path) -> tuple[Optional[dict], Optional[str]]:
    """Load `.agentforge/config.json` for enforcement purposes. Returns
    `(None, None)` when AgentForge is not configured for this project at
    all (no config file — nothing to enforce), or `(None, error_message)`
    when the file exists but fails schema validation, or cannot be read at
    all (permission error, or removed in a TOCTOU race after the
    `is_file()` check above) (STORY-004's enforcement contract: an invalid
    or unreadable committed policy file must stop the operation it gates,
    not silently fall back, and certainly never crash with an uncaught
    traceback — this hook *is* the documented "Git-hook policy check"
    example in `scripts/config.py`'s own module docstring)."""
    config_path = project_root / ".agentforge" / "config.json"
    if not config_path.is_file():
        return None, None
    try:
        return agentforge_config.load_for_enforcement(config_path), None
    except agentforge_config.ConfigValidationError as exc:
        return None, f"invalid {config_path}: {exc}"
    except OSError as exc:
        return None, f"cannot read {config_path}: {exc}"


def check_commit_message_file(message_path: Path, project_root: Path) -> ValidationResult:
    """Validate the real commit-message file Git's `commit-msg` hook
    receives as `$1`. This is the one entry point
    `templates/git-hooks/commit-msg` calls."""
    cfg, error = load_project_config(project_root)
    if error is not None:
        return ValidationResult(False, error, blocking=True)
    if cfg is None:
        return ValidationResult(
            True, "no .agentforge/config.json found; traceability check skipped.", blocking=False
        )
    try:
        raw = Path(message_path).read_bytes().decode("utf-8", errors="replace")
    except OSError as exc:
        return ValidationResult(False, f"cannot read commit message file {message_path}: {exc}", blocking=True)
    return validate_commit_message(raw, cfg)


def _read_commit_message_via_git(ref: str, project_root: Path) -> tuple[Optional[str], Optional[str]]:
    """Shared by `check_commit` (CI single-ref fallback, STORY-011) and
    STORY-012's `validate_commits` (many SHAs at once): run `git show -s
    --format=%B <ref>` and return `(raw_message, None)` on success or
    `(None, error_message)` otherwise. Never raises; the SHA is passed as
    a `subprocess` argument list element, never interpolated into a shell
    string, and the message content it returns is only ever read back —
    never executed or fed to another command."""
    try:
        completed = subprocess.run(
            ["git", "show", "-s", "--format=%B", ref],
            cwd=str(project_root),
            capture_output=True,
            # Explicit encoding/errors (not text=True's strict-UTF-8
            # default): a commit message containing non-UTF-8 bytes (e.g.
            # from a legacy tool or non-English locale) must never crash
            # this fallback with an uncaught UnicodeDecodeError — matching
            # check_commit_message_file's own `errors="replace"` decoding
            # of the message file.
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"could not read commit {ref!r} via git: {exc}"
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        return None, f"git could not resolve commit {ref!r}: {stderr or completed.returncode}"
    return completed.stdout, None


def check_commit(ref: str, project_root: Path) -> ValidationResult:
    """CI-only enforcement fallback (STORY-011 acceptance criterion:
    "Provide ... CI-only enforcement mode"): validate exactly one already
    -made commit's message by SHA/ref, without requiring the local
    `commit-msg` hook to have been installed at all. Deliberately a single
    commit, not a range — validating every commit in an outgoing push
    range is STORY-012's `check-range`/`check-pre-push` job, below."""
    cfg, error = load_project_config(project_root)
    if error is not None:
        return ValidationResult(False, error, blocking=True)
    if cfg is None:
        return ValidationResult(
            True, "no .agentforge/config.json found; traceability check skipped.", blocking=False
        )
    raw, read_error = _read_commit_message_via_git(ref, project_root)
    if read_error is not None:
        return ValidationResult(False, read_error, blocking=True)
    return validate_commit_message(raw, cfg)


# --------------------------------------------------------------------------
# Pre-push range validation (STORY-012)
#
# STORY-011's commit-msg hook only ever validates one commit at the moment
# it is created. A commit made with --no-verify, amended, rebased in from
# elsewhere, or cherry-picked from a branch that never had the hook
# installed can still reach a shared remote without ever having been
# checked. This section closes that gap: every commit a `git push` would
# introduce to the remote is validated, not only the ref tip (HEAD) of
# each pushed branch, so a compliant HEAD can never mask an older
# noncompliant outgoing commit hiding earlier in the same push.
# --------------------------------------------------------------------------

# Real Git SHA1 is 40 hex characters; SHA256-repo Git uses 64. A shortened
# abbreviation is never valid pre-push stdin (Git always sends full SHAs
# there), but the lower bound is kept generous rather than hardcoding
# exactly 40/64 so a plausible-but-nonstandard length is still treated as
# "a SHA-shaped field" (and, if it does not resolve, handled by the
# missing-remote-base fallback below) rather than a parse error.
_SHA_SHAPE_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")
_ZERO_SHA_RE = re.compile(r"^0+$")


def _looks_like_sha(value: str) -> bool:
    return bool(_SHA_SHAPE_RE.match(value))


def _is_zero_sha(value: str) -> bool:
    return bool(value) and bool(_ZERO_SHA_RE.match(value))


@dataclass(frozen=True)
class RefUpdate:
    """One parsed pre-push stdin record: `<local-ref> <local-sha>
    <remote-ref> <remote-sha>`."""

    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str

    @property
    def is_deletion(self) -> bool:
        """All-zero local SHA: the ref is being deleted on the remote, not
        updated. There is no local commit to validate at all."""
        return _is_zero_sha(self.local_sha)

    @property
    def is_new_ref(self) -> bool:
        """All-zero remote SHA: this ref does not exist on the remote yet
        (a brand-new branch or tag)."""
        return _is_zero_sha(self.remote_sha)


@dataclass(frozen=True)
class PrePushParseResult:
    """`updates` is every well-formed record; `errors` is one diagnostic
    string per malformed line. A single malformed line is skipped and
    reported — it never corrupts parsing of the other, well-formed lines
    Git sent in the same invocation."""

    updates: list
    errors: list


def parse_pre_push_stdin(text: str) -> PrePushParseResult:
    """Parse the real `pre-push` hook stdin protocol: one `<local-ref>
    <local-sha> <remote-ref> <remote-sha>` record per line, blank lines
    ignored. A line with the wrong field count, or a SHA-position field
    that is not hex-shaped, is recorded in `.errors` and skipped rather
    than raising or aborting the whole parse."""
    updates: list = []
    errors: list = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip("\n").strip("\r")
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 4:
            errors.append(
                f"line {lineno}: expected 4 whitespace-separated fields "
                f"(<local-ref> <local-sha> <remote-ref> <remote-sha>), got {len(parts)}: {line!r}"
            )
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts
        if not _looks_like_sha(local_sha) or not _looks_like_sha(remote_sha):
            errors.append(f"line {lineno}: local/remote SHA does not look like a hex object id: {line!r}")
            continue
        updates.append(RefUpdate(local_ref, local_sha, remote_ref, remote_sha))
    return PrePushParseResult(updates, errors)


@dataclass(frozen=True)
class RangeOutcome:
    """The outcome of computing one ref update's outgoing commit range.

    `warning` is set for a degraded-but-safe fallback (see the missing
    -remote-base handling below) — never for a hard failure. `error` is a
    hard Git-range failure a caller must surface distinctly from a
    traceability failure (requirement: distinguish configuration failure,
    Git-range failure, and traceability failure)."""

    shas: list
    warning: Optional[str] = None
    error: Optional[str] = None


def _rev_list(project_root: Path, args: list) -> tuple[Optional[list], Optional[str]]:
    try:
        completed = subprocess.run(
            ["git", "rev-list", *args],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git rev-list failed to run: {exc}"
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        return None, stderr or f"git rev-list exited with status {completed.returncode}"
    shas = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return shas, None


def compute_outgoing_range(project_root: Path, update: RefUpdate) -> RangeOutcome:
    """Compute the commits one ref update would introduce to the remote:

      - a deletion (all-zero local SHA): no commits at all — deleting a
        ref never has an outgoing commit to validate.
      - a brand-new remote ref (all-zero remote SHA): every commit
        reachable from `local_sha` (`git rev-list <local_sha>`) — Git's
        own documented sample `pre-push` hook uses exactly this same
        "examine all commits" range for a new branch, for the same
        reason this module does: with no prior remote tip, there is no
        narrower boundary this repository can trust the remote already
        has.
      - an update to an existing ref: `remote_sha..local_sha`. This is
        correct for both an ordinary fast-forward *and* a force push /
        non-ancestor remote tip, because `A..B` always means "reachable
        from B, not from A" regardless of whether A is an ancestor of B —
        no separate force-push case is needed.
      - a missing remote base (the remote SHA is not an object this repo
        has at all — e.g. it was never fetched): `remote_sha..local_sha`
        fails to resolve. Falls back to the same "examine all commits"
        range as a new ref, with an explicit `warning` — deliberately
        conservative (it may re-validate some commits already compliant
        and already on the remote) rather than silently skipping this ref
        because its base is unknown.
    """
    if update.is_deletion:
        return RangeOutcome(shas=[])

    if update.is_new_ref:
        shas, error = _rev_list(project_root, [update.local_sha])
        if error is not None:
            return RangeOutcome(shas=[], error=error)
        return RangeOutcome(shas=shas)

    shas, error = _rev_list(project_root, [f"{update.remote_sha}..{update.local_sha}"])
    if error is None:
        return RangeOutcome(shas=shas)

    fallback_shas, fallback_error = _rev_list(project_root, [update.local_sha])
    if fallback_error is not None:
        return RangeOutcome(shas=[], error=error)
    warning = (
        f"remote SHA {update.remote_sha[:12]} for {update.remote_ref} is not known to this "
        f"repository ({error}); conservatively falling back to validating every commit "
        f"reachable from {update.local_sha[:12]} (the same range used for a brand-new ref)."
    )
    return RangeOutcome(shas=fallback_shas, warning=warning)


def collect_outgoing_commits(project_root: Path, updates: list) -> tuple[list, list, list]:
    """Compute the deduplicated set of outgoing commits across every ref
    update in one push, in first-seen order across the updates (in the
    order Git listed them on stdin). A commit reachable from more than one
    pushed ref (e.g. two branches sharing history) is validated exactly
    once, never once per ref. Returns `(shas, warnings, errors)`."""
    seen: set = set()
    shas: list = []
    warnings: list = []
    errors: list = []
    for update in updates:
        outcome = compute_outgoing_range(project_root, update)
        if outcome.error is not None:
            errors.append(f"{update.local_ref} -> {update.remote_ref}: {outcome.error}")
            continue
        if outcome.warning:
            warnings.append(outcome.warning)
        for sha in outcome.shas:
            if sha not in seen:
                seen.add(sha)
                shas.append(sha)
    return shas, warnings, errors


# Control characters stripped from a commit subject before it is placed
# into a stderr failure report. This is a *report* sanitizer only — the
# subject is never executed, never interpolated into a shell command, and
# never used to build another subprocess argument list; it exists purely
# so a hostile or corrupted subject (embedded ANSI escapes, control
# characters) cannot corrupt or spoof this hook's own terminal output.
_REPORT_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_REPORTED_SUBJECT_LENGTH = 200


def _sanitize_subject_for_report(subject: str) -> str:
    cleaned = _REPORT_CONTROL_CHARS_RE.sub("", subject).strip()
    if len(cleaned) > _MAX_REPORTED_SUBJECT_LENGTH:
        cleaned = cleaned[:_MAX_REPORTED_SUBJECT_LENGTH] + "…"
    return cleaned or "(empty subject)"


@dataclass(frozen=True)
class CommitOffense:
    """One outgoing commit that failed traceability validation, reduced to
    exactly what a concise failure report needs: an abbreviated SHA (never
    the full SHA alone — abbreviated is what a human pastes into `git
    show`) and a sanitized subject, never the full raw message body."""

    sha: str
    abbrev: str
    subject: str
    reason: str


_ABBREV_SHA_LENGTH = 12


def validate_commits(shas: list, cfg: dict, project_root: Path) -> tuple[list, list]:
    """Validate an already-deduplicated list of commit SHAs against `cfg`.
    Returns `(offenses, git_errors)`: `git_errors` is populated when a
    specific commit's message could not even be read (a Git-range
    failure, distinct from a traceability failure) — this never silently
    drops a commit that could not be checked."""
    offenses: list = []
    git_errors: list = []
    for sha in shas:
        raw, error = _read_commit_message_via_git(sha, project_root)
        if error is not None:
            git_errors.append(error)
            continue
        result = validate_commit_message(raw, cfg)
        if result.ok:
            continue
        parsed = parse_commit_message(raw)
        offenses.append(
            CommitOffense(
                sha=sha,
                abbrev=sha[:_ABBREV_SHA_LENGTH],
                subject=_sanitize_subject_for_report(parsed.subject),
                reason=result.reason,
            )
        )
    return offenses, git_errors


# Exit codes for the `check-pre-push`/`check-range` CLI subcommands,
# distinguishing the three failure classes STORY-012 requires a caller be
# able to tell apart: a broken/invalid AgentForge configuration, a Git
# command that could not resolve the requested range at all, and an
# otherwise-successful check that found a genuine traceability violation.
PUSH_EXIT_OK = 0
PUSH_EXIT_TRACEABILITY_FAILURE = 1
PUSH_EXIT_CONFIG_ERROR = 2
PUSH_EXIT_GIT_RANGE_ERROR = 3


@dataclass(frozen=True)
class PrePushCheckResult:
    """`exit_code` is one of the `PUSH_EXIT_*` constants; `messages` is the
    ordered list of lines a caller should print to stderr."""

    exit_code: int
    messages: list


def _evaluate_shas(shas: list, cfg: dict, project_root: Path, label: str) -> tuple[int, list]:
    """Shared reporting tail for both `run_pre_push_check` and
    `run_range_check`: validate `shas` and render the same concise,
    deterministic failure format for either entry point."""
    messages: list = []
    if not shas:
        messages.append(f"agentforge git_policy {label}: no outgoing commits to validate.")
        return PUSH_EXIT_OK, messages

    offenses, read_errors = validate_commits(shas, cfg, project_root)
    if read_errors:
        for err in read_errors:
            messages.append(f"agentforge git_policy {label}: {err}")
        return PUSH_EXIT_GIT_RANGE_ERROR, messages

    if not offenses:
        messages.append(
            f"agentforge git_policy {label}: {len(shas)} outgoing commit(s) all reference a "
            "work-item identifier."
        )
        return PUSH_EXIT_OK, messages

    messages.append(
        f"agentforge git_policy {label}: {len(offenses)} of {len(shas)} outgoing commit(s) do not "
        "reference a work-item identifier:"
    )
    for offense in offenses:
        messages.append(f"  {offense.abbrev} {offense.subject!r} -- {offense.reason}")

    if _mode_from_cfg(cfg) == "enforce":
        return PUSH_EXIT_TRACEABILITY_FAILURE, messages
    return PUSH_EXIT_OK, messages


def run_pre_push_check(
    stdin_text: str, project_root: Path, remote_name: Optional[str] = None
) -> PrePushCheckResult:
    """The one entry point `templates/git-hooks/pre-push` calls: parse the
    real pre-push stdin protocol, compute every ref's outgoing commit
    range, deduplicate across refs, and validate every unique commit —
    never only each ref's tip — against `.agentforge/config.json`."""
    messages: list = []
    if remote_name:
        messages.append(f"agentforge git_policy pre-push: checking outgoing push to remote {remote_name!r}.")

    parse_result = parse_pre_push_stdin(stdin_text)
    for err in parse_result.errors:
        messages.append(f"agentforge git_policy pre-push: malformed input ignored: {err}")

    if not parse_result.updates:
        messages.append("agentforge git_policy pre-push: no ref updates to validate.")
        return PrePushCheckResult(PUSH_EXIT_OK, messages)

    cfg, error = load_project_config(project_root)
    if error is not None:
        messages.append(f"agentforge git_policy pre-push: {error}")
        return PrePushCheckResult(PUSH_EXIT_CONFIG_ERROR, messages)
    if cfg is None:
        messages.append(
            "agentforge git_policy pre-push: no .agentforge/config.json found; traceability check skipped."
        )
        return PrePushCheckResult(PUSH_EXIT_OK, messages)

    if _mode_from_cfg(cfg) == "off":
        messages.append("agentforge git_policy pre-push: traceability.mode is 'off'; no check performed.")
        return PrePushCheckResult(PUSH_EXIT_OK, messages)

    shas, warnings, range_errors = collect_outgoing_commits(project_root, parse_result.updates)
    for warning in warnings:
        messages.append(f"agentforge git_policy pre-push: {warning}")
    if range_errors:
        for err in range_errors:
            messages.append(f"agentforge git_policy pre-push: could not determine outgoing commit range: {err}")
        return PrePushCheckResult(PUSH_EXIT_GIT_RANGE_ERROR, messages)

    exit_code, eval_messages = _evaluate_shas(shas, cfg, project_root, "pre-push")
    messages.extend(eval_messages)
    return PrePushCheckResult(exit_code, messages)


def _looks_like_a_git_option(value: str) -> bool:
    """True for a `base`/`head` value that could be misread as a `git
    rev-list` option rather than a revision once concatenated into a
    `base..head` range string. No valid Git ref name or object id ever
    starts with `-` (`git check-ref-format` forbids it for refs, and a
    hex SHA obviously never does either), so rejecting a leading `-` here
    is a safe, non-restrictive guard against a CLI-supplied value being
    interpreted as a flag by the `git rev-list` subprocess call below."""
    return value.startswith("-")


def run_range_check(base: str, head: str, project_root: Path) -> PrePushCheckResult:
    """CI-facing command (STORY-012 acceptance criterion: "Add a CI
    command that validates a supplied base/head range"): validate every
    commit in `base..head` for environments (hosted CI, server-side branch
    protection) where a local `pre-push` hook is optional or cannot be
    relied on at all."""
    messages: list = []

    if _looks_like_a_git_option(base) or _looks_like_a_git_option(head):
        messages.append(
            f"agentforge git_policy check-range: refusing base={base!r}/head={head!r} -- a value "
            "starting with '-' is never a valid Git ref or object id and could be misread as an "
            "option by the underlying git command."
        )
        return PrePushCheckResult(PUSH_EXIT_GIT_RANGE_ERROR, messages)

    cfg, error = load_project_config(project_root)
    if error is not None:
        messages.append(f"agentforge git_policy check-range: {error}")
        return PrePushCheckResult(PUSH_EXIT_CONFIG_ERROR, messages)
    if cfg is None:
        messages.append(
            "agentforge git_policy check-range: no .agentforge/config.json found; traceability check skipped."
        )
        return PrePushCheckResult(PUSH_EXIT_OK, messages)

    if _mode_from_cfg(cfg) == "off":
        messages.append("agentforge git_policy check-range: traceability.mode is 'off'; no check performed.")
        return PrePushCheckResult(PUSH_EXIT_OK, messages)

    shas, range_error = _rev_list(project_root, [f"{base}..{head}"])
    if range_error is not None:
        messages.append(
            f"agentforge git_policy check-range: could not resolve range {base}..{head}: {range_error}"
        )
        return PrePushCheckResult(PUSH_EXIT_GIT_RANGE_ERROR, messages)

    exit_code, eval_messages = _evaluate_shas(shas, cfg, project_root, "check-range")
    messages.extend(eval_messages)
    return PrePushCheckResult(exit_code, messages)


# --------------------------------------------------------------------------
# Installation: detect, then chain / manual / CI-only
# --------------------------------------------------------------------------

INSTALL_CHAINED = "chained"
INSTALL_MANUAL = "manual"
INSTALL_CI_ONLY = "ci_only"

HOOK_NAME = "commit-msg"
# The backup name a pre-existing, non-AgentForge commit-msg hook is
# renamed to at install time. templates/git-hooks/commit-msg looks for
# this exact sibling filename at runtime and, if present and executable,
# runs it first and aborts the commit if it fails — this is the "chain
# any pre-existing hook, never silently replace it" contract.
CHAINED_HOOK_BACKUP_NAME = "commit-msg.pre-agentforge"

# Written verbatim (as the second line) into every hook this installer
# writes, so a later install run can recognize "this is our own file" and
# safely idempotently overwrite it, as opposed to a hook some other tool
# or the user wrote by hand.
_MANAGED_MARKER = "# Managed by AgentForge (STORY-011) -- do not hand-edit; re-run the installer to update."


@dataclass(frozen=True)
class InstallPlan:
    """What `plan_hook_install` decided, and everything `apply_hook_install`
    needs to carry it out without re-deriving it."""

    status: str  # "chained" | "manual" | "ci_only"
    reason: str
    hooks_dir: Optional[Path] = None
    existing_hook_path: Optional[Path] = None
    existing_hook_is_ours: bool = False
    instructions: str = ""


def _resolve_hooks_dir(project_root: Path) -> Optional[Path]:
    """The actual, effective hooks directory Git will invoke a
    `commit-msg` hook from for `project_root` -- default `.git/hooks`,
    a configured `core.hooksPath`, or (critically for this story, since
    it is itself being implemented inside a worktree) the *common* git
    directory's hooks folder for a worktree, where `.git` is a file, not
    a directory, pointing at `<main-repo>/.git/worktrees/<name>`. A single
    `git rev-parse --git-path hooks` call resolves all three cases
    correctly because Git itself does the resolution, rather than this
    module re-implementing worktree/`gitdir`-file parsing. Returns None
    if `project_root` is not inside a Git working tree at all, or `git`
    cannot be run."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    return path


def _is_ours(hook_path: Path, marker: str = _MANAGED_MARKER) -> bool:
    if not hook_path.is_file():
        return False
    try:
        text = hook_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return marker in text


def plan_hook_install(project_root: Path) -> InstallPlan:
    """Decide, without writing anything, whether a `commit-msg` hook can
    be safely chain-installed for `project_root`, must be left to
    documented manual integration, or should fall back to CI-only
    enforcement. Reuses `scripts.setup.detect_hook_managers` (STORY-005)
    for the Husky/pre-commit-framework/`core.hooksPath` detection instead
    of re-deriving it."""
    managers = agentforge_setup.detect_hook_managers(project_root)

    if managers["husky_present"]:
        return InstallPlan(
            INSTALL_MANUAL,
            "Husky (.husky/) appears to manage Git hooks for this project.",
            instructions=_husky_instructions(),
        )
    if managers["pre_commit_config_present"]:
        return InstallPlan(
            INSTALL_MANUAL,
            "The pre-commit framework (.pre-commit-config.yaml) appears to manage Git hooks "
            "for this project.",
            instructions=_pre_commit_instructions(),
        )

    hooks_dir = _resolve_hooks_dir(project_root)
    if hooks_dir is None:
        return InstallPlan(
            INSTALL_CI_ONLY,
            f"{project_root} does not look like a Git working tree (or 'git' could not be run); "
            "a local hook cannot be installed.",
            instructions=_ci_only_instructions(),
        )

    existing_hook_path = hooks_dir / HOOK_NAME
    existing_hook_is_ours = _is_ours(existing_hook_path)

    reason = f"hooks directory resolved to {hooks_dir}"
    if managers["hooks_path"]:
        reason += f" (core.hooksPath={managers['hooks_path']!r}, origin: {managers['hooks_path_origin']})"
    if existing_hook_path.is_file() and not existing_hook_is_ours:
        reason += (
            f"; an existing, unrecognized {HOOK_NAME} hook will be preserved and chain-called "
            f"as {CHAINED_HOOK_BACKUP_NAME}"
        )

    return InstallPlan(
        INSTALL_CHAINED,
        reason,
        hooks_dir=hooks_dir,
        existing_hook_path=existing_hook_path if existing_hook_path.is_file() else None,
        existing_hook_is_ours=existing_hook_is_ours,
    )


def _husky_instructions() -> str:
    return (
        "AgentForge did not install a commit-msg hook because Husky (.husky/) already "
        "manages Git hooks here. Add the check to Husky's own commit-msg hook instead:\n\n"
        "  echo 'python3 \"<AGENTFORGE_SCRIPTS_DIR>/git_policy.py\" check-message-file \"$1\"' "
        ">> .husky/commit-msg\n\n"
        "Replace <AGENTFORGE_SCRIPTS_DIR> with this AgentForge plugin's scripts/ directory "
        "(the value ${CLAUDE_PLUGIN_ROOT}/scripts resolves to inside a Claude Code session), "
        "then commit .husky/commit-msg. See docs/threat-model.md for the CI-only fallback if "
        "you would rather not maintain this manually."
    )


def _pre_commit_instructions() -> str:
    return (
        "AgentForge did not install a commit-msg hook because the pre-commit framework "
        "(.pre-commit-config.yaml) already manages Git hooks here. Add a local hook entry "
        "instead:\n\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: agentforge-commit-msg\n"
        "        name: AgentForge commit traceability\n"
        "        entry: python3 <AGENTFORGE_SCRIPTS_DIR>/git_policy.py check-message-file\n"
        "        language: system\n"
        "        stages: [commit-msg]\n\n"
        "Replace <AGENTFORGE_SCRIPTS_DIR> with this AgentForge plugin's scripts/ directory, "
        "then run `pre-commit install --hook-type commit-msg`. See docs/threat-model.md for "
        "the CI-only fallback if you would rather not maintain this manually."
    )


def _ci_only_instructions() -> str:
    return (
        "AgentForge could not resolve a local Git hooks directory for this project (it may "
        "not be a Git working tree, or 'git' is unavailable). Use the CI-only fallback "
        "instead: run\n\n"
        "  python3 <AGENTFORGE_SCRIPTS_DIR>/git_policy.py check-commit <sha> "
        "--project-root <checkout>\n\n"
        "for each commit your CI pipeline validates (e.g. every commit in a pull request)."
    )


def render_hook_script(scripts_dir: Path) -> str:
    """Render `templates/git-hooks/commit-msg` with `scripts_dir` (this
    AgentForge plugin's absolute scripts/ directory at install time)
    baked in. The installed hook cannot rely on `${CLAUDE_PLUGIN_ROOT}` --
    that variable only exists inside a live Claude Code session, but this
    hook must also work for a GUI client or a bare `git commit` run from a
    terminal with no AgentForge session active at all (STORY-011
    acceptance criterion: "git -C, aliases, GUI commits, and direct
    terminal commits are covered")."""
    template_path = REPO_ROOT / "templates" / "git-hooks" / "commit-msg"
    template = template_path.read_text(encoding="utf-8")
    rendered = template.replace("__AGENTFORGE_SCRIPTS_DIR__", str(scripts_dir))
    if _MANAGED_MARKER not in rendered:  # pragma: no cover - defensive; template drift guard
        raise ValueError("templates/git-hooks/commit-msg is missing the AgentForge managed marker")
    return rendered


def apply_hook_install(project_root: Path, scripts_dir: Path) -> InstallPlan:
    """Recompute the plan and, only when it is `INSTALL_CHAINED`, write
    the hook (chain-preserving any pre-existing, non-AgentForge hook
    first). `manual`/`ci_only` plans are returned unchanged -- nothing is
    ever written for those, matching the "never overwrite another hook
    manager's commit-msg" requirement."""
    plan = plan_hook_install(project_root)
    if plan.status != INSTALL_CHAINED:
        return plan

    hooks_dir = plan.hooks_dir
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / HOOK_NAME
    backup = hooks_dir / CHAINED_HOOK_BACKUP_NAME

    if plan.existing_hook_path is not None and not plan.existing_hook_is_ours:
        # Preserve the pre-existing (non-AgentForge) hook so the rendered
        # script can chain to it. Always (re)write the backup from the
        # current foreign file rather than only when no backup exists yet
        # -- on a normal reinstall this branch is never reached a second
        # time at all (by then `target` is AgentForge's own file, so
        # `existing_hook_is_ours` is already True and this whole block is
        # skipped), so this only matters for the edge case where a
        # *different* foreign hook was placed after an earlier install;
        # unconditionally refreshing the backup there means that hook is
        # still chained rather than silently dropped.
        #
        # Deliberately preserve the file's EXISTING permission bits rather
        # than forcing it executable: Git itself silently ignores a
        # non-executable hook (it prints a warning and lets the commit
        # proceed), so a pre-existing commit-msg file that was already
        # inert must stay inert after this install -- code review caught
        # that force-chmodding it here would reactivate a hook Git had
        # been correctly ignoring, rejecting an otherwise-compliant commit
        # purely because AgentForge turned a dormant script back on.
        # templates/git-hooks/commit-msg's own `[ -x ... ]` check then
        # naturally skips chaining to a backup that isn't executable,
        # matching what Git would have done without AgentForge involved.
        plan.existing_hook_path.replace(backup)

    target.write_text(render_hook_script(scripts_dir), encoding="utf-8")
    target.chmod(target.stat().st_mode | 0o111)
    return plan


# --------------------------------------------------------------------------
# Installation: pre-push (STORY-012)
#
# Extends the exact same chained/manual/ci_only installation mechanism
# above for a second, independent hook file (`pre-push`) rather than
# overloading `plan_hook_install`/`apply_hook_install`, which remain
# commit-msg-specific and untouched: a project's Husky/pre-commit/
# core.hooksPath detection is shared (`agentforge_setup.detect_hook_managers`,
# `_resolve_hooks_dir`), but each hook file is planned, chained, and
# installed independently, so an unrecognized existing `pre-push` script
# is preserved and chained exactly like an unrecognized `commit-msg`
# script, without the two hook types' installation ever being conflated
# into one shared file or one shared "is this ours" marker.
# --------------------------------------------------------------------------

PRE_PUSH_HOOK_NAME = "pre-push"
# The backup name a pre-existing, non-AgentForge pre-push hook is renamed
# to at install time -- the pre-push analog of CHAINED_HOOK_BACKUP_NAME
# above. templates/git-hooks/pre-push looks for this exact sibling
# filename at runtime and, if present and executable, runs it first
# (forwarding the same buffered stdin) and aborts the push if it fails.
PRE_PUSH_CHAINED_HOOK_BACKUP_NAME = "pre-push.pre-agentforge"

# A separate marker (not `_MANAGED_MARKER`) so `_is_ours` never mistakes a
# commit-msg hook for a pre-push hook or vice versa -- the two files are
# planned and installed independently and must be told apart independently.
_MANAGED_MARKER_PRE_PUSH = (
    "# Managed by AgentForge (STORY-012) -- do not hand-edit; re-run the installer to update."
)


def plan_pre_push_hook_install(project_root: Path) -> InstallPlan:
    """Pre-push analog of `plan_hook_install`: decide, without writing
    anything, whether a `pre-push` hook can be safely chain-installed for
    `project_root`, must be left to documented manual integration, or
    should fall back to CI-only enforcement. Reuses the same hook-manager
    detection and hooks-directory resolution as `plan_hook_install` so the
    two never disagree about what already manages Git hooks here."""
    managers = agentforge_setup.detect_hook_managers(project_root)

    if managers["husky_present"]:
        return InstallPlan(
            INSTALL_MANUAL,
            "Husky (.husky/) appears to manage Git hooks for this project.",
            instructions=_husky_instructions_pre_push(),
        )
    if managers["pre_commit_config_present"]:
        return InstallPlan(
            INSTALL_MANUAL,
            "The pre-commit framework (.pre-commit-config.yaml) appears to manage Git hooks "
            "for this project.",
            instructions=_pre_commit_instructions_pre_push(),
        )

    hooks_dir = _resolve_hooks_dir(project_root)
    if hooks_dir is None:
        return InstallPlan(
            INSTALL_CI_ONLY,
            f"{project_root} does not look like a Git working tree (or 'git' could not be run); "
            "a local hook cannot be installed.",
            instructions=_ci_only_instructions_pre_push(),
        )

    existing_hook_path = hooks_dir / PRE_PUSH_HOOK_NAME
    existing_hook_is_ours = _is_ours(existing_hook_path, _MANAGED_MARKER_PRE_PUSH)

    reason = f"hooks directory resolved to {hooks_dir}"
    if managers["hooks_path"]:
        reason += f" (core.hooksPath={managers['hooks_path']!r}, origin: {managers['hooks_path_origin']})"
    if existing_hook_path.is_file() and not existing_hook_is_ours:
        reason += (
            f"; an existing, unrecognized {PRE_PUSH_HOOK_NAME} hook will be preserved and "
            f"chain-called as {PRE_PUSH_CHAINED_HOOK_BACKUP_NAME}"
        )

    return InstallPlan(
        INSTALL_CHAINED,
        reason,
        hooks_dir=hooks_dir,
        existing_hook_path=existing_hook_path if existing_hook_path.is_file() else None,
        existing_hook_is_ours=existing_hook_is_ours,
    )


def _husky_instructions_pre_push() -> str:
    return (
        "AgentForge did not install a pre-push hook because Husky (.husky/) already "
        "manages Git hooks here. Add the check to Husky's own pre-push hook instead:\n\n"
        '  echo \'python3 "<AGENTFORGE_SCRIPTS_DIR>/git_policy.py" check-pre-push "$1" "$2"\' '
        ">> .husky/pre-push\n\n"
        "Replace <AGENTFORGE_SCRIPTS_DIR> with this AgentForge plugin's scripts/ directory "
        "(the value ${CLAUDE_PLUGIN_ROOT}/scripts resolves to inside a Claude Code session), "
        "then commit .husky/pre-push. See docs/threat-model.md for the CI-only fallback if "
        "you would rather not maintain this manually."
    )


def _pre_commit_instructions_pre_push() -> str:
    return (
        "AgentForge did not install a pre-push hook because the pre-commit framework "
        "(.pre-commit-config.yaml) already manages Git hooks here. Add a local hook entry "
        "instead:\n\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: agentforge-pre-push\n"
        "        name: AgentForge outgoing-commit traceability\n"
        "        entry: python3 <AGENTFORGE_SCRIPTS_DIR>/git_policy.py check-pre-push\n"
        "        language: system\n"
        "        stages: [pre-push]\n\n"
        "Replace <AGENTFORGE_SCRIPTS_DIR> with this AgentForge plugin's scripts/ directory, "
        "then run `pre-commit install --hook-type pre-push`. See docs/threat-model.md for "
        "the CI-only fallback if you would rather not maintain this manually."
    )


def _ci_only_instructions_pre_push() -> str:
    return (
        "AgentForge could not resolve a local Git hooks directory for this project (it may "
        "not be a Git working tree, or 'git' is unavailable). Use the CI-only fallback "
        "instead: run\n\n"
        "  python3 <AGENTFORGE_SCRIPTS_DIR>/git_policy.py check-range <base> <head> "
        "--project-root <checkout>\n\n"
        "for the base/head range your CI pipeline is validating (e.g. the merge-base of a "
        "pull request through its head)."
    )


def render_pre_push_hook_script(scripts_dir: Path) -> str:
    """Render `templates/git-hooks/pre-push` with `scripts_dir` baked in --
    the pre-push analog of `render_hook_script`. Same reasoning applies:
    the installed hook cannot rely on `${CLAUDE_PLUGIN_ROOT}`, which only
    exists inside a live Claude Code session, because this hook must also
    work for a bare `git push` or a GUI client with no AgentForge session
    active at all."""
    template_path = REPO_ROOT / "templates" / "git-hooks" / "pre-push"
    template = template_path.read_text(encoding="utf-8")
    rendered = template.replace("__AGENTFORGE_SCRIPTS_DIR__", str(scripts_dir))
    if _MANAGED_MARKER_PRE_PUSH not in rendered:  # pragma: no cover - defensive; template drift guard
        raise ValueError("templates/git-hooks/pre-push is missing the AgentForge managed marker")
    return rendered


def apply_pre_push_hook_install(project_root: Path, scripts_dir: Path) -> InstallPlan:
    """Recompute the pre-push plan and, only when it is `INSTALL_CHAINED`,
    write the hook (chain-preserving any pre-existing, non-AgentForge
    `pre-push` hook first, exactly like `apply_hook_install` does for
    `commit-msg`). `manual`/`ci_only` plans are returned unchanged --
    nothing is ever written for those."""
    plan = plan_pre_push_hook_install(project_root)
    if plan.status != INSTALL_CHAINED:
        return plan

    hooks_dir = plan.hooks_dir
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / PRE_PUSH_HOOK_NAME
    backup = hooks_dir / PRE_PUSH_CHAINED_HOOK_BACKUP_NAME

    if plan.existing_hook_path is not None and not plan.existing_hook_is_ours:
        # Preserve the file's existing permission bits, exactly like
        # apply_hook_install: Git silently ignores a non-executable hook,
        # so a dormant pre-existing pre-push script must stay dormant
        # after this install rather than being reactivated.
        plan.existing_hook_path.replace(backup)

    target.write_text(render_pre_push_hook_script(scripts_dir), encoding="utf-8")
    target.chmod(target.stat().st_mode | 0o111)
    return plan


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _print_result(result: ValidationResult) -> int:
    prefix = "agentforge git_policy"
    if result.ok:
        if not result.exempt:
            print(f"{prefix}: {result.reason}", file=sys.stderr)
        return 0
    print(f"{prefix}: {result.reason}", file=sys.stderr)
    return 1 if result.blocking else 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="git_policy.py", description="AgentForge commit-message traceability policy."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_file = subparsers.add_parser(
        "check-message-file", help="Validate a commit message file (the commit-msg hook's $1)."
    )
    check_file.add_argument("message_path", type=Path)
    check_file.add_argument("--project-root", type=Path, default=Path("."))

    check_commit_p = subparsers.add_parser(
        "check-commit", help="CI-only fallback: validate one already-made commit by ref/SHA."
    )
    check_commit_p.add_argument("ref", nargs="?", default="HEAD")
    check_commit_p.add_argument("--project-root", type=Path, default=Path("."))

    check_pre_push_p = subparsers.add_parser(
        "check-pre-push",
        help="Validate every outgoing commit for one `pre-push` hook invocation (STORY-012). "
        "Reads '<local-ref> <local-sha> <remote-ref> <remote-sha>' lines from stdin.",
    )
    check_pre_push_p.add_argument(
        "remote_name", nargs="?", default=None, help="Git's $1 (remote name), forwarded for diagnostics."
    )
    check_pre_push_p.add_argument(
        "remote_url", nargs="?", default=None, help="Git's $2 (remote URL); accepted but currently unused."
    )
    check_pre_push_p.add_argument("--project-root", type=Path, default=Path("."))

    check_range_p = subparsers.add_parser(
        "check-range",
        help="CI-facing command (STORY-012): validate every commit in a supplied base..head range.",
    )
    check_range_p.add_argument("base")
    check_range_p.add_argument("head")
    check_range_p.add_argument("--project-root", type=Path, default=Path("."))

    install_p = subparsers.add_parser(
        "install", help="Detect hook ownership and chain-install commit-msg and pre-push if safe."
    )
    install_p.add_argument("--project-root", type=Path, default=Path("."))
    install_p.add_argument(
        "--scripts-dir",
        type=Path,
        default=REPO_ROOT / "scripts",
        help="Absolute path to this AgentForge plugin's scripts/ directory, baked into the "
        "installed hook (defaults to this checkout's own scripts/ directory).",
    )

    args = parser.parse_args(argv)

    if args.command == "check-message-file":
        result = check_commit_message_file(args.message_path, args.project_root)
        return _print_result(result)

    if args.command == "check-commit":
        result = check_commit(args.ref, args.project_root)
        return _print_result(result)

    if args.command == "check-pre-push":
        stdin_text = sys.stdin.read()
        push_result = run_pre_push_check(stdin_text, args.project_root, remote_name=args.remote_name)
        for message in push_result.messages:
            print(message, file=sys.stderr)
        return push_result.exit_code

    if args.command == "check-range":
        push_result = run_range_check(args.base, args.head, args.project_root)
        for message in push_result.messages:
            print(message, file=sys.stderr)
        return push_result.exit_code

    if args.command == "install":
        commit_msg_plan = apply_hook_install(args.project_root, args.scripts_dir.resolve())
        print(
            f"agentforge git_policy install (commit-msg): status={commit_msg_plan.status}; "
            f"{commit_msg_plan.reason}"
        )
        if commit_msg_plan.instructions:
            print(commit_msg_plan.instructions)

        pre_push_plan = apply_pre_push_hook_install(args.project_root, args.scripts_dir.resolve())
        print(
            f"agentforge git_policy install (pre-push): status={pre_push_plan.status}; "
            f"{pre_push_plan.reason}"
        )
        if pre_push_plan.instructions:
            print(pre_push_plan.instructions)

        both_chained = commit_msg_plan.status == INSTALL_CHAINED and pre_push_plan.status == INSTALL_CHAINED
        return 0 if both_chained else 2

    return 1  # pragma: no cover - argparse enforces a valid subcommand


if __name__ == "__main__":
    raise SystemExit(main())
