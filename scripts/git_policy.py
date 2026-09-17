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


def validate_commit_message(raw_message: str, cfg: dict) -> ValidationResult:
    """Validate one raw commit-message file's content against `cfg`
    (an already-schema-validated `.agentforge/config.json`, STORY-004).
    Never raises for a recognized configuration shape; never inspects
    anything other than `raw_message` and `cfg` — no shell text, no
    environment variables, no other files."""
    traceability_cfg = cfg.get("traceability") if isinstance(cfg, dict) else None
    mode = traceability_cfg.get("mode") if isinstance(traceability_cfg, dict) else None
    if mode not in agentforge_config.TRACEABILITY_MODES:
        mode = "off"

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


def check_commit(ref: str, project_root: Path) -> ValidationResult:
    """CI-only enforcement fallback (STORY-011 acceptance criterion:
    "Provide ... CI-only enforcement mode"): validate exactly one already
    -made commit's message by SHA/ref, without requiring the local
    `commit-msg` hook to have been installed at all. Deliberately a single
    commit, not a range — validating every commit in an outgoing push
    range is STORY-012's explicit scope, not this story's."""
    cfg, error = load_project_config(project_root)
    if error is not None:
        return ValidationResult(False, error, blocking=True)
    if cfg is None:
        return ValidationResult(
            True, "no .agentforge/config.json found; traceability check skipped.", blocking=False
        )
    try:
        completed = subprocess.run(
            ["git", "show", "-s", "--format=%B", ref],
            cwd=str(project_root),
            capture_output=True,
            # Explicit encoding/errors (not text=True's strict-UTF-8
            # default): a commit message containing non-UTF-8 bytes (e.g.
            # from a legacy tool or non-English locale) must never crash
            # this CI-only fallback with an uncaught UnicodeDecodeError —
            # matching check_commit_message_file's own
            # `errors="replace"` decoding of the message file.
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ValidationResult(False, f"could not read commit {ref!r} via git: {exc}", blocking=True)
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        return ValidationResult(
            False, f"git could not resolve commit {ref!r}: {stderr or completed.returncode}", blocking=True
        )
    return validate_commit_message(completed.stdout, cfg)


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


def _is_ours(hook_path: Path) -> bool:
    if not hook_path.is_file():
        return False
    try:
        text = hook_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return _MANAGED_MARKER in text


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

    install_p = subparsers.add_parser(
        "install", help="Detect hook ownership and chain-install commit-msg if safe."
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

    if args.command == "install":
        plan = apply_hook_install(args.project_root, args.scripts_dir.resolve())
        print(f"agentforge git_policy install: status={plan.status}; {plan.reason}")
        if plan.instructions:
            print(plan.instructions)
        return 0 if plan.status == INSTALL_CHAINED else 2

    return 1  # pragma: no cover - argparse enforces a valid subcommand


if __name__ == "__main__":
    raise SystemExit(main())
