# AgentForge threat model

This document exists because of `docs/adr/0004-hooks-are-guardrails.md`:
the honesty requirement in that ADR ("AgentForge must stop claiming that
text-pattern hooks form a security boundary") is only meaningful if the
actual coverage and gaps are written down somewhere a user will read
before they rely on this layer. It is required output for STORY-013, not
optional polish.

## This is not a security sandbox

`scripts/scope_policy.py` (the PreToolUse graded command-policy engine)
and the rest of AgentForge's lifecycle hooks run **inside** the agent's
own tool-call loop, using the same interpreter the agent is directing.
Nothing in this layer can stop:

- a differently-phrased shell command that routes around a classified
  pattern;
- an agent that decides not to call a tool AgentForge would have
  classified (the hook only fires on tool calls it is given);
- a compromised or malicious model deliberately obfuscating intent.

**Actual enforcement boundaries**, per `docs/plans/agentforge-v2-execution-plan.md`'s
product-boundaries section and ADR-0004, are:

| Concern | Owned by |
|---|---|
| Commit-message / pushed-commit traceability | Git `commit-msg` / `pre-push` hooks (STORY-011, STORY-012), plus CI |
| Merge authorization | Branch protection / human review |
| Filesystem / network isolation | Native OS sandbox or container |
| Code quality | Formatter, linter, type checker, test suite, CI |

Lifecycle hooks (`PreToolUse` included) provide **context, UX feedback,
audit trail, and defense in depth** — same-turn signals that Git hooks
(commit/push time only) and CI (post-push only) cannot give. They are a
useful second layer, not the boundary.

## What `scope_policy.py` classifies, and how confidently

### Structured tools (`Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `apply_patch`)

These are classified **exactly**, by tool name, because Claude/Codex
report them precisely — there is no shell text to parse. This module only
answers "is this a write, and is it attributable to a configured agent?"
It does **not** perform canonical path/allow-list enforcement (resolving
`..`, symlinks, or dotfile-vs-stripped-dotfile ambiguity against
`scope.agents.<name>.allow`) — that is STORY-014's explicit scope
("Canonicalize paths and expose honest scope modes"). Concretely, as of
STORY-013:

- `deny-structured` mode does **not yet deny any structured write**. It
  classifies for visibility only. Do not configure `deny-structured` and
  assume out-of-scope writes are blocked until STORY-014 ships.
- `strict-agent` mode denies **every** structured tool call (reads
  included, not just writes) when it has no `agent_type`, or an
  `agent_type` not present in `scope.agents` — attribution is checked
  first, before category, so a missing or not-yet-recognized tool name
  can never quietly skip the check by defaulting to a read-shaped
  category. A configured agent's writes are then allowed regardless of
  *which* path they target — pending STORY-014's canonical path check.
- Bash-driven file writes (`echo x > file`, `sed -i`, `cp`, ...) are
  **never** covered by structured-tool policy at all, by construction —
  see the Bash section below. A `deny-structured`/`strict-agent`
  deployment that only reasons about `Write`/`Edit` calls has a
  Bash-shaped hole regardless of STORY-014.

### Bash commands

Bash commands are the part risk #4 in the execution plan calls out
explicitly: **"Bash cannot be reliably classified with regex."**
`classify_bash_command()` never promises complete coverage. It produces
one of four categories:

- `known-read` — recognized as non-mutating (`git status`, `git log`,
  `ls`, `cat`, `grep`, `find` without `-delete`/`-exec`, `sed` without
  `-i`, ...).
- `known-write` — recognized as mutating but not destructive (`git add`,
  `git commit`, `git push` without a force/delete flag, `git checkout
  <ref>`, `mkdir`, `cp`, `sed -i`, package-manager installs, ...).
- `known-destructive` — recognized as discarding work or history
  irreversibly from the CLI's own perspective (see the Git table below,
  plus `rm`, `find -delete`, and `DROP`/`TRUNCATE TABLE`).
- `ambiguous` — anything this module could not confidently place in the
  three categories above, **including every command it does not
  recognize at all**. Unrecognized is ambiguous, never silently read-safe
  or silently allowed.

#### Git destructive operations covered regardless of surface form

The classifier walks the actual token list (via `shlex.split`, never a
raw substring/regex match against the whole command line) and skips git's
global options — `-C <dir>`, `-c <key>=<value>`, `--git-dir`,
`--work-tree`, boolean flags — in any order before locating the
subcommand. This is what fixes the exact v1 bug in
`tests/test_v1_characterization.py::GitDashCPushBypassTests`
(`\bgit\s+push\b` missing `git -C <dir> push`). Covered forms:

| Operation | Matched regardless of |
|---|---|
| `git reset --hard` | `git -C <dir> reset --hard`, option order, extra global flags |
| `git clean -f` / `-fd` / `--force` | short-cluster combination, option order |
| `git branch -D` / `--delete --force` | option order, `-C`, extra global flags |
| `git branch -M` / `--move --force` | force-rename that can silently overwrite an existing branch |
| `git push --force` / `-f` / `--force-with-lease[=<refspec>]` / `--force-if-includes` | flag position (before or after the remote/refspec), `-C` |
| `git push --delete` / `-d` / a `:<ref>` delete-refspec | remote branch deletion, option order, refspec vs. flag syntax |
| `git checkout -- <path>` / `git checkout .` / `git checkout --force` | option order |
| `git switch --force` / `--discard-changes` | option order |
| `git restore <path>` (without `--staged`-only) | option order |

`git push --force-with-lease` is classified `known-destructive` even
though it is *safer* than plain `--force` (it refuses if the remote ref
moved unexpectedly) — it can still discard a collaborator's work when its
precondition happens to hold, so this module does not attempt the
finer-grained "was the lease actually protective" judgment.

#### Explicitly unsupported: shell indirection

This module makes **no attempt** to reliably classify a command once
control or data can flow through a second interpreter it is not
inspecting. Any of the following anywhere in the raw command text —
**including inside quoted strings**, deliberately conservative rather
than attempting real shell parsing — is classified `ambiguous`
unconditionally, before any git/rm/etc-specific logic runs:

- pipes (`|`), statement separators (`;`), `&&`/`||`, backgrounding (`&`)
- command/process substitution (`` ` ``, `$(...)`, `<(...)`, `>(...)`)
- redirection (`>`, `>>`, `<`)
- inline interpreters as a bare word anywhere in the command: `python`,
  `python3`, `perl`, `ruby`, `node`, `sh`, `bash`, `zsh`, `eval`
- `tee`, `xargs`, `base64` as a bare word anywhere in the command
  (encoded or piped-through payloads)
- unparsable shell syntax (e.g. unbalanced quoting)

This is a **known, permanent, documented limitation**, not a bug list to
work through: a bespoke shell parser sufficient to see through arbitrary
pipes, subshells, and inline interpreters would still not close the gap
(the interpreter itself can run anything), so this module does not
attempt it. It also means the classifier is deliberately over-inclusive:
`git commit -m "compares a > b"` is `ambiguous` (the message text happens
to contain `>`) even though the actual command is a harmless commit. That
false positive is the accepted cost of never claiming a false negative
here — in `ask`/`strict-agent` modes an ambiguous classification produces
a confirmation prompt or a deny, not a silent pass.

#### What is deliberately out of scope for "encoded/indirect commands"

Bare-word detection of `base64`/`eval`/inline-interpreter names catches
the common cases in the STORY-013 acceptance criteria, but it is a
heuristic, not a decoder: a sufficiently obfuscated payload (nested
encoding, a renamed/aliased interpreter binary, a compiled helper that
itself execs a string) is not guaranteed to trip any of these markers.
Treat every `ambiguous` classification as "not evaluated," and every
absence of an `ambiguous` classification as "no known indirection marker
was present" — never as "this command was verified safe."

## Malformed input handling

Two different kinds of "malformed" apply here, and they are handled
differently on purpose:

- **A malformed PreToolUse hook payload** (invalid JSON, or JSON that
  isn't an object, on stdin) fails **closed** — an explicit `deny` — under
  any blocking `scope.mode` (`ask`, `deny-structured`, `strict-agent`).
  Under `observe` mode it fails **open** with a stderr warning, and under
  `off` it is not even inspected. This intentionally does **not**
  reproduce the v1 bug characterized in
  `tests/test_v1_characterization.py::MalformedJsonFailsOpenTests`
  ("a hook documented as a hard-block guardrail silently allows the tool
  call when its own input is unparsable") for any mode that claims to
  block anything.
- **A missing or invalid project config** (`.agentforge/config.json`)
  falls back to `DEFAULT_CONFIG` (`scope.mode: "off"`) with a stderr
  warning, in every case — including when a blocking mode was
  presumably intended but the file is corrupted. This is a deliberate
  asymmetry: a broken *optional* governance file must not freeze every
  tool call in the session (this hook is a guardrail per ADR-0004, not
  the enforcement boundary — commit-msg/pre-push Git hooks are, and they
  apply their own STORY-004 fail-closed rule to their own config
  reads). A project that wants a config error to be loud should watch for
  the stderr warning or add a CI check that validates
  `.agentforge/config.json` with `scripts/config.py --mode enforce`.

## No work-item token matching

This module has no STORY-XXX (or other work-item identifier) awareness at
all. It does not scan Bash commands for a token anywhere in the string —
that was the v1 bug in
`tests/test_v1_characterization.py::StoryTokenOutsideMessageTests`
(a token in an unrelated `--file` argument satisfied a check meant for
the actual commit message). Commit-message and pushed-commit traceability
is STORY-011/STORY-012's job, validated against the real message
file/commit range by Git hooks, not against whatever else happens to
appear on the same Bash command line.

## Commit-message traceability (STORY-011)

`scripts/git_policy.py` plus the installed `templates/git-hooks/commit-msg`
script are the actual enforcement boundary this document's table above
already names for "Commit-message / pushed-commit traceability" — a real
Git `commit-msg` hook that Git itself invokes with the path to the actual
commit message file, never a PreToolUse scan of shell-command text. This
closes the exact v1 gap characterized in
`tests/test_v1_characterization.py::StoryTokenOutsideMessageTests` (a
STORY-XXX token anywhere in the raw Bash command line — e.g. an unrelated
`--file=STORY-001.md` argument — satisfied the old check even though the
actual `-m` message had no reference) and
`::GitDashCPushBypassTests` (`git -C <dir> push` bypassing a regex that
only matched `git push` with no separating flag). A real Git hook has no
such gap: Git invokes `commit-msg` for `git commit`, `git -C <dir>
commit`, a shell alias, `git commit -F <file>` (the GUI-client shape), and
`git merge`, regardless of how the command was spelled, because Git
itself — not this module — decides when to run it.

AgentForge intentionally added **no** PreToolUse early-warning check for
commit traceability in this story. `scope_policy.py` already documents,
above, that it has "no work-item token matching" at all, and the exact
reason given there — a token match against shell-command text is the v1
bug, not a mitigation for it — applies with equal force to a
would-be non-authoritative PreToolUse warning for `git commit`. Adding one
would either (a) re-implement the same fragile shell-text heuristic this
story exists to retire, or (b) require parsing the real `-m`/`-F` message
out of an arbitrary shell command line, which is exactly the "cannot be
reliably classified with regex" problem risk #4 already describes for
Bash generally. The Git `commit-msg` hook already gives same-commit
feedback (it runs before the commit is created, so a rejected commit never
lands in the object database) without that risk, so no separate
lifecycle-hook layer was added on top of it.

### What is checked, and how

- The hook receives `$1`, the path to a temporary file containing the
  actual proposed commit message. `git_policy.check_commit_message_file`
  reads that file's bytes directly — it never inspects `sys.argv`,
  `$BASH_COMMAND`, or any other shell context.
- The message is checked against `.agentforge/config.json`'s
  `identifier.pattern` (STORY-004), using the same `re.fullmatch`
  semantics `scripts/config.py` and `scripts/work_items.py` already use
  for that field (see `docs/agentforge-config.md`): a whitespace-delimited
  token (edge punctuation like `:`, `.`, `()` stripped) must fullmatch the
  pattern somewhere in the message. This is one generic mechanism driven
  entirely by the project's own configured pattern — GitHub's `"^#\\d+$"`,
  a cross-repo `"^[\\w.-]+/[\\w.-]+#\\d+$"`, GitLab's `"^#\\d+$"`, and a
  local project's `"^STORY-\\d{3,}$"` are all the same code path, never a
  hardcoded per-provider regex.
- `traceability.mode` (STORY-004) gates behavior exactly as documented
  there: `off` performs no check at all; `observe` runs the check and
  reports the result but never blocks the commit (`ValidationResult.ok`
  can be `False` while `.blocking` is `False`); `enforce` blocks a
  noncompliant commit with a nonzero hook exit code.
- A missing `.agentforge/config.json` is treated as "AgentForge is not
  configured for this project" and never blocks a commit. An existing but
  *invalid* config fails closed regardless of `traceability.mode` — this
  hook is the documented "Git-hook policy check" example in
  `scripts/config.py`'s own module docstring for when an enforcement
  caller must receive a hard validation failure, not a silent fallback.
  An unreadable config (permission error, or a TOCTOU race between the
  existence check and the read) fails closed the same way, never with an
  uncaught traceback.
- `strip_comment_lines` only recognizes `#` as the comment character
  (Git's own default `core.commentChar`) and the exact `git commit -v`
  scissors line. A project that has changed `core.commentChar` to
  something else gets no special handling for that character — its
  editor-template comment lines are scanned like ordinary message text
  instead of being stripped. This is a narrow, known limitation (a
  non-default `core.commentChar` is uncommon) rather than a full
  reimplementation of Git's own cleanup logic, which would require this
  module to read the project's Git config on every invocation.

### Exemptions are narrow and hardcoded, not project-configurable

The only default exemption is Git's own auto-generated merge-commit
subject shapes (`Merge branch '...'`, `Merge remote-tracking branch
'...'`, `Merge tag '...'`), matched by `is_git_merge_commit`. This is
deliberately narrow, per the execution plan's decision that default
exemptions must stay narrow:

- A GitHub/GitLab server-side "Merge pull request #42 from ..." message is
  **not** exempt — that text is a hosting-provider convention, not
  something Git itself generates, and it commonly already carries the
  original branch's own identifier reference in its body regardless.
- A `git revert` commit ("Revert \"...\"") is **not** exempt — reverting
  is a deliberate, authored action with real consequences, and the
  execution plan lists it only as an example of a class a project *could*
  choose to exempt, not a default.
- There is currently no way for a project to widen this list via
  `.agentforge/config.json`. `scripts/config.py`'s `traceability` schema
  (STORY-004) has only a `mode` field; adding a project-configurable
  exemption list (e.g. `traceability.exempt_merge_commits` or a custom
  regex list) would require extending that closed schema, which is
  outside this story's stated scope (`scripts/config.py` is not among the
  files STORY-011 is scoped to touch). This is a known, intentionally
  deferred gap — see this story's final report for the explicit
  cross-story note — not an oversight.

### Bypass instructions and limitations (read this before relying on this layer)

A **local** Git hook is a client-side mechanism. None of the following
can be prevented by `commit-msg` alone, and every one of them is a real,
available bypass:

- **`git commit --no-verify`** (or `-n`) skips every local hook, including
  this one, unconditionally. This is Git's own documented escape hatch,
  not a bug in this module.
- **An uninstalled hook.** A fresh `git clone` has no hooks at all until
  `scripts/git_policy.py install` (or the equivalent setup flow) has been
  run against that checkout; hooks are never transmitted by `git clone`
  or `git pull`.
- **`core.hooksPath` pointed elsewhere (or unset) by local config.**
  Anyone with write access to the repository's own Git config can redirect
  or remove hook enforcement for their own clone.
- **Server-side / API commits.** A commit created through a hosting
  provider's web UI or REST/GraphQL API (e.g. GitHub's "edit this file"
  button, `createCommitOnBranch`) never runs any local Git hook, because
  no local Git client is involved at all.
- **A stale or moved plugin installation.** The installed hook script has
  this AgentForge checkout's absolute `scripts/` directory baked in at
  install time (`${CLAUDE_PLUGIN_ROOT}` is only defined inside a live
  Claude Code session, so the hook cannot rely on it at commit time — see
  `render_hook_script`'s docstring). If the plugin is reinstalled at a
  different path, the hook fails open (prints a warning, exits 0) rather
  than blocking every commit — re-run the installer after any plugin
  relocation.
- **Retroactive history rewrites.** `commit-msg` validates a message at
  the moment a commit is *created*. It says nothing about a commit that
  is later amended, rebased, or cherry-picked with `--no-verify`, and it
  never inspects history that already exists. Validating every commit in
  an outgoing push range is STORY-012's explicit scope, not this one's.

**The mitigation for all of the above is the CI-only fallback**
(`python3 scripts/git_policy.py check-commit <sha> --project-root
<checkout>`), run as a required status check under branch protection. A
local hook is same-commit UX and defense in depth; a server-side/CI check
that a human cannot silently opt out of on their own machine is the only
layer here that approaches a real boundary, and even it only covers
commits it is actually invoked against (STORY-012 covers push ranges;
STORY-020 covers wiring it into CI).

### Existing hook managers are detected, never silently overwritten

`plan_hook_install`/`apply_hook_install` reuse
`scripts.setup.detect_hook_managers` (STORY-005) rather than re-deriving
Husky/`pre-commit`/`core.hooksPath` detection, and always resolve one of
exactly three outcomes:

- **`chained`** — no other hook manager was detected. If an existing,
  unrecognized `commit-msg` script is already present at the resolved
  hooks directory, it is renamed to `commit-msg.pre-agentforge` and the
  installed AgentForge hook runs it first, aborting the commit if it
  fails, before running its own check. The renamed file keeps its
  original permission bits exactly — if it was not executable (Git
  itself silently ignores a non-executable hook, so this is the "already
  dormant" state), the backup stays non-executable and is never chained,
  rather than AgentForge reactivating a hook Git had been correctly
  ignoring. Re-running the installer is idempotent: an already-
  AgentForge-managed hook (detected by an exact marker string) is simply
  rewritten, and an existing backup is never clobbered by a second
  install.
- **`manual`** — Husky (`.husky/`) or the `pre-commit` framework
  (`.pre-commit-config.yaml`) was detected. Nothing is written; documented
  instructions for adding the same check into that tool's own
  configuration are returned instead, because those tools manage their
  hook files in ways an automatic overwrite from outside could conflict
  with.
- **`ci_only`** — the target is not a usable Git working tree at all (or
  `git` itself is unavailable), so no local hook can be installed;
  instructions for the CI fallback are returned instead.

The resolved install location is always the *effective* Git hooks
directory (`git rev-parse --git-path hooks`, run inside `project_root`) —
this correctly resolves a configured `core.hooksPath`, and, critically,
the *shared* hooks directory of a Git worktree, where `.git` is a file
(not a directory) pointing at `<main-repo>/.git/worktrees/<name>` rather
than containing a `hooks/` subdirectory of its own. This story's own
implementation checkout is itself such a worktree, and
`tests/test_git_hook_installation.py::WorktreeTests` exercises that
layout explicitly rather than only asserting it in the abstract.

### Findings from independent code review

STORY-011's implementation went through Matt's two-axis code review
(Standards + Spec) against the pre-story baseline before being committed.
Confirmed correctness findings were fixed and covered by a new regression
test in the same pass: the octopus-merge exemption gap (`is_git_merge_commit`
missing the plural "Merge branches '...' and '...'" shape), the
executable-bit reactivation bug described above, the uncaught
`UnicodeDecodeError` in `check_commit` on a non-UTF-8 message, and the
uncaught `OSError` in `load_project_config` on an unreadable config file.

Two review findings were deliberately **not** actioned, and are recorded
here rather than silently dropped:

- **A Claude/Codex PreToolUse early-warning check.** The task scoping
  this story explicitly marks this "(optional, early-UX-only)", and this
  document's own "No work-item token matching" reasoning for
  `scope_policy.py` applies with equal force here: any such check would
  either reintroduce the fragile shell-text heuristic this story exists
  to retire, or require parsing a real message out of an arbitrary shell
  command line (execution-plan risk #4). No PreToolUse warning was added.
- **A `.agentforge/config.json`-driven exemption list** (e.g. letting a
  project opt `revert` commits, or a custom regex, into the exemption
  set). This would require extending `scripts/config.py`'s closed
  `traceability` schema, which this story's own stated scope excludes
  (`scripts/config.py` is not among the files STORY-011 is scoped to
  touch). Recorded as a cross-story gap for whichever later story extends
  that schema, per the "Exemptions" section above.

Every classification in this module is pure Python string/token analysis
(`shlex.split` plus regex) over the command text. It never builds a
second shell command containing the text being classified and never
shells out to interpret it. This closes off an entire class of injection
risk that a "classify by re-running a probe command" design would open.
