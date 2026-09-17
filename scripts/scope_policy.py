"""AgentForge graded command-policy engine (STORY-013).

Replaces the v1 `templates/shared/hooks/pre_tool_use.py` regex blocklist
(characterized in `tests/test_v1_characterization.py`) with an honest,
gradeable PreToolUse policy that never claims to parse arbitrary shell
reliably. See `docs/threat-model.md` for the full coverage/limitation
statement and `docs/adr/0004-hooks-are-guardrails.md` for why this is a
guardrail, not a security boundary.

Two independent policies, deliberately kept apart (STORY-013 requirement:
"separate exact structured-tool policy from Bash heuristics"):

  - `classify_structured_tool()` — exact, name-based classification for
    Claude/Codex structured tools (Write/Edit/MultiEdit/NotebookEdit/
    apply_patch vs. everything else). Canonical path/allow-list
    enforcement (STORY-014: "Canonicalize paths and expose honest scope
    modes") lives in `scripts/path_policy.py` and is wired in below, in
    `_decide_structured`, for `deny-structured` and `strict-agent` modes
    only — `observe` and `ask` never gate on path, and `off` never
    evaluates anything at all.
  - `classify_bash_command()` — best-effort static classification of a
    Bash command string into `known-read`, `known-write`,
    `known-destructive`, or `ambiguous`. This can never be complete
    (execution plan risk #4: "Bash cannot be reliably classified with
    regex"). Anything involving shell indirection (pipes, redirection,
    command substitution, backgrounding, `tee`, inline interpreters like
    `python -c`, `base64`, ...) is classified `ambiguous`, never silently
    treated as safe.

Never re-executes or shell-interpolates the command under test: every
classification here is pure Python string/token analysis over the command
text (`shlex.split` plus regex), never a subprocess call built from it.

No rule in this module inspects a command for a work-item/STORY token.
Commit-message and pushed-commit traceability belong to STORY-011/
STORY-012's Git hooks (`commit-msg`, `pre-push`), which validate the
actual message file/commit range — not a substring match against whatever
else happens to appear on the Bash command line (the exact v1 bug
characterized by `StoryTokenOutsideMessageTests`).
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config as agentforge_config  # noqa: E402
from scripts import path_policy  # noqa: E402

# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------

KNOWN_READ = "known-read"
KNOWN_WRITE = "known-write"
KNOWN_DESTRUCTIVE = "known-destructive"
AMBIGUOUS = "ambiguous"

BASH_CATEGORIES = (KNOWN_READ, KNOWN_WRITE, KNOWN_DESTRUCTIVE, AMBIGUOUS)

ALLOW = "allow"
DENY = "deny"
ASK = "ask"

# scope.mode values that must fail closed on a malformed hook payload
# (STORY-013 requirement). "off" and "observe" are exempt: "off" performs
# no evaluation at all, and "observe" is documented as warn-and-continue.
BLOCKING_MODES = ("ask", "deny-structured", "strict-agent")

# Structured (non-Bash) tool names that write files, across Claude and
# Codex naming. Everything else is treated as known-read: Claude/Codex
# structured tools are exact by construction, so this list is exhaustive
# by name rather than heuristic. Matched case-insensitively (see
# classify_structured_tool) so every one of Claude's PascalCase names and
# Codex's lowercase/snake_case equivalents is covered uniformly, instead
# of requiring a separately-listed lowercase alias per name.
STRUCTURED_WRITE_TOOL_NAMES = {
    "write",
    "edit",
    "multiedit",
    "notebookedit",
    "apply_patch",
}


@dataclass(frozen=True)
class BashClassification:
    """Result of classifying one Bash command string."""

    category: str
    reason: str


@dataclass(frozen=True)
class Decision:
    """A PreToolUse policy outcome: what to tell the harness, and why."""

    permission: str  # "allow" | "deny" | "ask"
    reason: str
    category: Optional[str] = None


# --------------------------------------------------------------------------
# Shell-indirection detection (documented as unsupported/ambiguous, never
# silently treated as classifiable)
# --------------------------------------------------------------------------

# Any of these substrings appearing anywhere in the raw command text —
# including inside quoted strings, deliberately conservative rather than
# attempting real shell parsing — mean the command cannot be reliably
# reduced to "the one thing it does". Pipes, redirection, command
# substitution, backgrounding, and chaining can all route data or control
# through a second command this module never inspects.
_INDIRECTION_MARKERS = (
    "|",  # pipe
    ";",  # statement separator
    "&&",
    "||",
    "&",  # backgrounding / (also covered by && above)
    "`",  # legacy command substitution
    "$(",  # command substitution
    "<(",  # process substitution
    ">(",  # process substitution
    ">>",
    ">",
    "<",
    "\n",
)

# Command/token names that indicate inline interpretation of
# attacker/agent-controlled text, or an encoded/obfuscated payload. Any of
# these appearing as a whole word/token anywhere in the command means the
# real effect is opaque to static analysis.
_OPAQUE_TOKENS = {
    "python",
    "python3",
    "perl",
    "ruby",
    "node",
    "sh",
    "bash",
    "zsh",
    "eval",
    "tee",
    "base64",
    "xargs",
}
_OPAQUE_TOKEN_RE = re.compile(
    r"(?<![\w.-])(" + "|".join(re.escape(t) for t in sorted(_OPAQUE_TOKENS)) + r")(?![\w.-])"
)


def _has_shell_indirection(command: str) -> Optional[str]:
    for marker in _INDIRECTION_MARKERS:
        if marker in command:
            return marker
    match = _OPAQUE_TOKEN_RE.search(command)
    if match:
        return match.group(1)
    return None


# --------------------------------------------------------------------------
# Git destructive-operation matching
# --------------------------------------------------------------------------

# Global options that take a separate following argument (space-separated,
# not "=" attached), e.g. `git -C /some/repo push`. Matched regardless of
# where they sit relative to other global options — every option before
# the subcommand is a global option in git's own grammar, so we skip them
# in order rather than searching for one specific position.
_GIT_GLOBAL_OPTS_WITH_SEPARATE_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--super-prefix",
    "--config-env",
}


def _skip_git_global_options(tokens: list[str]) -> int:
    """Return the index of the git subcommand in `tokens` (tokens after
    the leading "git"), skipping global options regardless of order or
    count -- this is what makes `git -C <dir> push`, `git -c a=b commit`,
    and reordered global flags resolve to the same subcommand as the bare
    form."""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not token.startswith("-"):
            return i
        if token in _GIT_GLOBAL_OPTS_WITH_SEPARATE_VALUE:
            i += 2  # option + its value
            continue
        # "--git-dir=x" style attached value, or a boolean global flag
        # (--no-pager, --paginate, -p, --bare, ...): consume just the one
        # token either way.
        i += 1
    return i


def _has_flag(tokens: list[str], *, short_chars: str = "", long_names: tuple = ()) -> bool:
    """True if any token is one of the exact long options in `long_names`,
    a long option in `long_names` with an "=" value attached, or a short
    option cluster (starts with "-", not "--") containing any character
    in `short_chars`."""
    for token in tokens:
        if token.startswith("--"):
            name = token.split("=", 1)[0]
            if name in long_names:
                return True
        elif token.startswith("-") and token != "-":
            cluster = token[1:]
            if short_chars and any(ch in cluster for ch in short_chars):
                return True
    return False


def _has_long_prefix(tokens: list[str], prefix: str) -> bool:
    return any(token == prefix or token.startswith(prefix + "=") for token in tokens)


def _classify_git(tokens: list[str]) -> BashClassification:
    """`tokens` are everything after the leading "git" token (global
    options included, not yet skipped)."""
    sub_index = _skip_git_global_options(tokens)
    if sub_index >= len(tokens):
        return BashClassification(KNOWN_READ, "bare 'git' invocation (no subcommand)")

    subcommand = tokens[sub_index]
    rest = tokens[sub_index + 1 :]

    if subcommand == "reset":
        if _has_long_prefix(rest, "--hard"):
            return BashClassification(
                KNOWN_DESTRUCTIVE, "git reset --hard discards working tree and index changes"
            )
        return BashClassification(KNOWN_WRITE, "git reset without --hard")

    if subcommand == "clean":
        if _has_flag(rest, short_chars="fFxX", long_names=("--force",)):
            return BashClassification(
                KNOWN_DESTRUCTIVE, "git clean with a force flag deletes untracked files"
            )
        return BashClassification(
            KNOWN_READ, "git clean without a force flag (git itself refuses to delete)"
        )

    if subcommand == "branch":
        is_force = _has_flag(rest, short_chars="fF", long_names=("--force",))
        is_delete = _has_flag(rest, short_chars="dD") or _has_long_prefix(rest, "--delete")
        is_move = _has_flag(rest, short_chars="mM") or _has_long_prefix(rest, "--move")
        # -D is shorthand for --delete --force; -M is shorthand for --move
        # --force (can silently overwrite an existing branch of the target
        # name). Either capitalized short flag, or the lowercase long-form
        # pair, is destructive.
        if _has_flag(rest, short_chars="D") or _has_flag(rest, short_chars="M") or (
            is_delete and is_force
        ) or (is_move and is_force):
            return BashClassification(
                KNOWN_DESTRUCTIVE,
                "git branch -D/-M or --delete/--move with --force force-deletes or "
                "force-overwrites a branch",
            )
        positional = [t for t in rest if not t.startswith("-")]
        if positional:
            return BashClassification(KNOWN_WRITE, "git branch creates/renames a branch")
        return BashClassification(KNOWN_READ, "git branch with no destructive flags lists branches")

    if subcommand == "push":
        # A ":<ref>" delete-refspec (e.g. `git push origin :feature`) is
        # the classic syntax for deleting a remote ref, equivalent in
        # effect to --delete but without any flag to match on.
        has_delete_refspec = any(
            tok.startswith(":") and tok != ":" and not tok.startswith("-") for tok in rest
        )
        if (
            _has_flag(rest, short_chars="f", long_names=("--force",))
            or _has_long_prefix(rest, "--force-with-lease")
            or _has_long_prefix(rest, "--force-if-includes")
        ):
            return BashClassification(
                KNOWN_DESTRUCTIVE,
                "git push with --force/-f/--force-with-lease can overwrite remote history",
            )
        if _has_flag(rest, short_chars="d", long_names=("--delete",)) or has_delete_refspec:
            return BashClassification(
                KNOWN_DESTRUCTIVE,
                "git push --delete or a ':<ref>' delete-refspec removes a remote ref",
            )
        return BashClassification(KNOWN_WRITE, "git push without a force/delete flag")

    if subcommand == "checkout":
        if "--" in rest or "." in rest or _has_flag(rest, short_chars="f", long_names=("--force",)):
            return BashClassification(
                KNOWN_DESTRUCTIVE,
                "git checkout with '--', '.', or --force discards working tree changes",
            )
        return BashClassification(KNOWN_WRITE, "git checkout switching branches/commit")

    if subcommand == "switch":
        if _has_flag(rest, short_chars="f", long_names=("--force", "--discard-changes")):
            return BashClassification(
                KNOWN_DESTRUCTIVE,
                "git switch --force/--discard-changes discards local changes",
            )
        return BashClassification(KNOWN_WRITE, "git switch changes the current branch")

    if subcommand == "restore":
        if _has_long_prefix(rest, "--staged") and not _has_long_prefix(rest, "--worktree"):
            return BashClassification(
                KNOWN_WRITE, "git restore --staged only unstages, working tree is untouched"
            )
        return BashClassification(
            KNOWN_DESTRUCTIVE, "git restore without --staged-only discards working tree changes"
        )

    if subcommand in ("status", "log", "diff", "show", "fetch", "remote", "blame", "reflog",
                      "describe", "rev-parse", "ls-files", "shortlog", "rev-list", "cat-file"):
        return BashClassification(KNOWN_READ, f"git {subcommand} does not mutate repository state")

    if subcommand in ("add", "commit", "merge", "pull", "tag", "stash", "rebase",
                      "cherry-pick", "revert", "init", "clone", "submodule"):
        return BashClassification(KNOWN_WRITE, f"git {subcommand} mutates repository state")

    return BashClassification(
        AMBIGUOUS, f"git subcommand '{subcommand}' is not in the classified set"
    )


# --------------------------------------------------------------------------
# Non-git command matching
# --------------------------------------------------------------------------

_SQL_DESTRUCTIVE_RE = re.compile(
    r"\b(drop|truncate)\s+table\b", re.IGNORECASE
)

_READ_COMMANDS = {
    "ls", "pwd", "cat", "echo", "grep", "head", "tail", "wc", "which", "type",
    "printenv", "diff", "file", "stat", "printf",
}
_WRITE_COMMANDS = {
    "mkdir", "touch", "cp", "mv", "chmod", "chown", "ln",
    "npm", "pip", "pip3", "yarn", "pnpm", "cargo",
}


def _classify_find(tokens: list[str]) -> BashClassification:
    if "-delete" in tokens or "-exec" in tokens or "-execdir" in tokens:
        return BashClassification(
            KNOWN_DESTRUCTIVE, "find with -delete/-exec can remove or run arbitrary commands"
        )
    return BashClassification(KNOWN_READ, "find without -delete/-exec only searches")


def _classify_rm(tokens: list[str]) -> BashClassification:
    return BashClassification(KNOWN_DESTRUCTIVE, "rm deletes files irreversibly from the CLI")


def _classify_sed(tokens: list[str]) -> BashClassification:
    if _has_flag(tokens, short_chars="i", long_names=("--in-place",)):
        return BashClassification(KNOWN_WRITE, "sed -i / --in-place edits the file on disk")
    return BashClassification(KNOWN_READ, "sed without -i only prints to stdout")


_SPECIAL_COMMANDS = {
    "find": _classify_find,
    "rm": _classify_rm,
    "sed": _classify_sed,
}


def classify_bash_command(command: str) -> BashClassification:
    """Classify a raw Bash command string. Never executes or re-interprets
    the command through a shell; pure static string/token analysis."""
    if not command or not command.strip():
        return BashClassification(KNOWN_READ, "empty command")

    if _SQL_DESTRUCTIVE_RE.search(command):
        return BashClassification(
            KNOWN_DESTRUCTIVE, "command contains a DROP/TRUNCATE TABLE statement"
        )

    marker = _has_shell_indirection(command)
    if marker is not None:
        return BashClassification(
            AMBIGUOUS,
            f"shell indirection ({marker!r}) makes the effective command opaque to static "
            "analysis; see docs/threat-model.md",
        )

    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return BashClassification(AMBIGUOUS, f"unparsable shell syntax: {exc}")

    if not tokens:
        return BashClassification(KNOWN_READ, "empty command")

    # Skip leading environment-variable assignments (FOO=bar cmd ...) and
    # common invocation wrappers so the real command is what gets matched.
    i = 0
    env_assignment_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
    while i < len(tokens) and env_assignment_re.match(tokens[i]):
        i += 1
    while i < len(tokens) and tokens[i] in ("sudo", "env", "nice", "nohup"):
        i += 1
    if i >= len(tokens):
        return BashClassification(AMBIGUOUS, "command has no invocable program after wrappers")

    program = Path(tokens[i]).name  # tolerate absolute paths like /usr/bin/git
    rest = tokens[i + 1 :]

    if program == "git":
        return _classify_git(rest)
    if program in _SPECIAL_COMMANDS:
        return _SPECIAL_COMMANDS[program](rest)
    if program in _READ_COMMANDS:
        return BashClassification(KNOWN_READ, f"'{program}' is a recognized read-only command")
    if program in _WRITE_COMMANDS:
        return BashClassification(KNOWN_WRITE, f"'{program}' is a recognized non-destructive write")

    return BashClassification(
        AMBIGUOUS, f"'{program}' is not in the classified command set"
    )


def classify_structured_tool(tool_name: str) -> str:
    """Exact, name-based classification for structured (non-Bash) tools.
    No path/allow-list canonicalization happens here -- that is
    `scripts/path_policy.py`'s job, wired in below by `_decide_structured`
    for `deny-structured`/`strict-agent` modes; see the module docstring
    and docs/threat-model.md."""
    if isinstance(tool_name, str) and tool_name.lower() in STRUCTURED_WRITE_TOOL_NAMES:
        return KNOWN_WRITE
    return KNOWN_READ


# --------------------------------------------------------------------------
# Mode wiring
# --------------------------------------------------------------------------


def _decide_bash(
    classification: BashClassification, mode: str, agent_type: Optional[str], scope_agents: dict
) -> Decision:
    if mode == "observe":
        return Decision(
            ALLOW,
            f"[observe] Bash classified {classification.category}: {classification.reason}",
            classification.category,
        )

    if mode == "ask":
        if classification.category in (KNOWN_DESTRUCTIVE, AMBIGUOUS):
            return Decision(
                ASK,
                f"Bash call classified {classification.category}: {classification.reason}",
                classification.category,
            )
        return Decision(
            ALLOW,
            f"Bash classified {classification.category}: {classification.reason}",
            classification.category,
        )

    if mode == "deny-structured":
        # deny-structured's documented coverage is structured Write/Edit
        # calls only (execution plan policy-modes table: "Enforces
        # covered structured tools only"). Bash is out of its coverage by
        # definition; classify for visibility but never gate on it here.
        return Decision(
            ALLOW,
            f"[deny-structured does not cover Bash] classified {classification.category}: "
            f"{classification.reason}",
            classification.category,
        )

    if mode == "strict-agent":
        if not agent_type or agent_type not in scope_agents:
            return Decision(
                DENY,
                "strict-agent mode denies Bash calls with no attributed, configured agent "
                f"(agent_type={agent_type!r})",
                classification.category,
            )
        if classification.category in (KNOWN_DESTRUCTIVE, AMBIGUOUS):
            return Decision(
                DENY,
                f"strict-agent mode denies {classification.category} Bash calls even for "
                f"configured agent {agent_type!r}: {classification.reason}",
                classification.category,
            )
        return Decision(
            ALLOW,
            f"strict-agent: {agent_type!r} may run {classification.category} Bash: "
            f"{classification.reason}",
            classification.category,
        )

    raise ValueError(f"unhandled scope.mode: {mode!r}")


def _decide_structured_write_path(
    tool_name: str,
    tool_input: dict,
    project_root: Path,
    agent_type: str,
    scope_agents: dict,
) -> Decision:
    """Canonical path enforcement (STORY-014) for one structured write
    call already known to belong to a configured agent (`agent_type` is
    guaranteed present in `scope_agents` by both callers below). Shared by
    `deny-structured` and `strict-agent` so the two modes apply the exact
    same path logic, and look up the agent's allow-list exactly once,
    after attribution/mode gating has decided enforcement applies."""
    allow_entries = scope_agents[agent_type].get("allow", [])
    raw_target = path_policy.extract_target_path(tool_input)
    if raw_target is None:
        return Decision(
            DENY,
            f"{tool_name} write has no recognizable target path in tool_input "
            "(checked file_path/notebook_path/path/file)",
            KNOWN_WRITE,
        )

    result = path_policy.check_path(project_root, raw_target, allow_entries)
    if result.allowed:
        return Decision(
            ALLOW, f"{tool_name} target {raw_target!r} is in scope: {result.reason}", KNOWN_WRITE
        )
    return Decision(
        DENY, f"{tool_name} target {raw_target!r} is out of scope: {result.reason}", KNOWN_WRITE
    )


def _decide_structured(
    tool_name: str,
    tool_input: dict,
    category: str,
    mode: str,
    agent_type: Optional[str],
    scope_agents: dict,
    project_root: Path,
) -> Decision:
    if mode == "observe":
        return Decision(
            ALLOW, f"[observe] {tool_name} classified {category}", category
        )

    if mode == "ask":
        # Structured tools are exact by name; only writes are worth a
        # confirmation prompt, and even then only as an early UX nudge —
        # canonical path checking is reserved for the blocking modes below.
        if category == KNOWN_WRITE:
            return Decision(ASK, f"{tool_name} is a structured write call", category)
        return Decision(ALLOW, f"{tool_name} classified {category}", category)

    if mode == "deny-structured":
        # STORY-014: real canonical path enforcement, but scoped by
        # design to agents named in scope.agents -- "agents" is the only
        # allow-list this config section has (docs/agentforge-config.md).
        # A call with no agent_type at all (the ordinary primary-session
        # case: agent_type is documented as optional outside subagent
        # calls) or an agent_type not present in scope.agents has no
        # configured scope to check against, so deny-structured does not
        # restrict it. This is the explicit, tested missing/unknown-agent
        # behavior for this mode -- see docs/threat-model.md and contrast
        # with strict-agent below, which denies exactly this case.
        if category != KNOWN_WRITE:
            return Decision(ALLOW, f"{tool_name} classified {category}", category)
        if not agent_type or agent_type not in scope_agents:
            return Decision(
                ALLOW,
                f"deny-structured has no configured scope for agent_type={agent_type!r}; "
                f"{tool_name} is not restricted",
                category,
            )
        return _decide_structured_write_path(
            tool_name, tool_input, project_root, agent_type, scope_agents
        )

    if mode == "strict-agent":
        # Agent attribution is checked first, for every structured call
        # regardless of category -- symmetric with _decide_bash above.
        # Gating only on `category == KNOWN_WRITE` here would let a call
        # with a missing/unrecognized tool_name (which classifies as
        # KNOWN_READ by default) skip attribution entirely, undermining
        # strict-agent's "deny outside an explicit, configured agent"
        # guarantee for exactly the payloads that most need it.
        if not agent_type or agent_type not in scope_agents:
            return Decision(
                DENY,
                f"strict-agent mode denies {tool_name!r} with no attributed, configured agent "
                f"(agent_type={agent_type!r})",
                category,
            )
        if category != KNOWN_WRITE:
            return Decision(
                ALLOW, f"strict-agent: {agent_type!r} may run {tool_name} ({category})", category
            )
        return _decide_structured_write_path(
            tool_name, tool_input, project_root, agent_type, scope_agents
        )

    raise ValueError(f"unhandled scope.mode: {mode!r}")


def evaluate(
    tool_name: str,
    tool_input: dict,
    agent_type: Optional[str],
    mode: str,
    scope_agents: dict,
    project_root: Optional[Path] = None,
) -> Decision:
    """Dispatch a single PreToolUse call to the Bash or structured-tool
    policy. `mode` must already be one of the non-"off" scope.mode values
    (main() short-circuits "off" before calling this).

    `project_root` anchors canonical path enforcement (STORY-014) for
    structured writes under `deny-structured`/`strict-agent`; it is
    ignored by every other mode and by Bash classification. Defaults to
    the current working directory, matching how `main()` derives it from
    the hook payload's `cwd`.
    """
    if project_root is None:
        project_root = Path.cwd()

    if tool_name in ("Bash", "bash"):
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return Decision(ALLOW, "Bash call has no command text to classify")
        classification = classify_bash_command(command)
        return _decide_bash(classification, mode, agent_type, scope_agents)

    category = classify_structured_tool(tool_name)
    return _decide_structured(
        tool_name, tool_input, category, mode, agent_type, scope_agents, project_root
    )


# --------------------------------------------------------------------------
# Hook protocol: stdin JSON in, stdout JSON out, diagnostics on stderr
# --------------------------------------------------------------------------


def parse_hook_payload(raw: str) -> tuple[Optional[dict], Optional[str]]:
    """Parse the PreToolUse stdin payload. Returns (payload, None) on
    success or (None, error_message) on any parse/shape problem. Unlike
    v1's `load_payload()` (characterized in
    tests/test_v1_characterization.py::MalformedJsonFailsOpenTests), the
    caller decides whether a malformed payload fails open or closed based
    on the configured scope.mode -- this function only reports the fact
    of the problem."""
    if not raw or not raw.strip():
        return None, "empty stdin"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON on stdin: {exc.msg} at line {exc.lineno} column {exc.colno}"
    if not isinstance(data, dict):
        return None, "hook payload must be a JSON object"
    return data, None


def _warn(message: str) -> None:
    print(f"agentforge scope_policy: {message}", file=sys.stderr)


def _response_json(decision: Decision) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision.permission,
                "permissionDecisionReason": decision.reason,
            }
        }
    )


def _project_root(payload: Optional[dict]) -> Path:
    """The project root for both config lookup and canonical path
    enforcement (STORY-014): the hook payload's `cwd`, or the process's
    own working directory when `cwd` is absent (matching `evaluate()`'s
    own default so a direct call and a `main()`-driven call resolve
    identically)."""
    cwd_value = payload.get("cwd") if payload else None
    return Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else Path.cwd()


def _project_config_path(payload: Optional[dict]) -> Path:
    return _project_root(payload) / ".agentforge" / "config.json"


def _load_scope_config(config_path: Path) -> tuple[dict, list]:
    """Load the project config for scope-policy purposes. A missing or
    invalid config falls back to DEFAULT_CONFIG (scope.mode "off") rather
    than an implicit strict mode: see docs/threat-model.md for why a
    broken *optional* governance file must not freeze every tool call --
    the actual enforcement boundary is the commit-msg/pre-push Git hooks
    (STORY-011/012), not this lifecycle hook (ADR-0004)."""
    if not config_path.is_file():
        return agentforge_config.DEFAULT_CONFIG, []
    data, issues = agentforge_config.load_for_observation(config_path)
    if data is None:
        return agentforge_config.DEFAULT_CONFIG, issues
    return data, []


def main(argv: Optional[list] = None) -> int:
    raw = sys.stdin.read()
    payload, parse_error = parse_hook_payload(raw)

    config_path = _project_config_path(payload)
    cfg, cfg_issues = _load_scope_config(config_path)
    if cfg_issues:
        _warn(
            f"could not load {config_path}, falling back to scope.mode=off: "
            + "; ".join(issue.format() for issue in cfg_issues)
        )
    mode = cfg["scope"]["mode"]

    if mode == "off":
        return 0  # no hook policy at all: do not even report the parse error

    if payload is None:
        if mode in BLOCKING_MODES:
            decision = Decision(
                DENY,
                f"malformed PreToolUse payload under scope.mode={mode!r}: {parse_error}",
            )
            print(_response_json(decision))
            return 0
        _warn(f"malformed PreToolUse payload; observe mode continues: {parse_error}")
        return 0

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    agent_type = payload.get("agent_type")
    agent_type = agent_type if isinstance(agent_type, str) and agent_type else None
    scope_agents = cfg.get("scope", {}).get("agents", {})
    if not isinstance(scope_agents, dict):
        scope_agents = {}

    decision = evaluate(
        tool_name, tool_input, agent_type, mode, scope_agents, project_root=_project_root(payload)
    )
    print(_response_json(decision))
    if mode == "observe":
        _warn(decision.reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
