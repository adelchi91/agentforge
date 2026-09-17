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
report them precisely — there is no shell text to parse. As of STORY-014,
`deny-structured` and `strict-agent` also perform **real canonical path
enforcement** against `scope.agents.<name>.allow`
(`scripts/path_policy.py`): the project root, the target path, and every
allowed root are resolved through symlinks and `..` normalization before
any ancestry comparison, a leading dot component (`.env`) is preserved
exactly (never `str.lstrip("./")`), and an exact-file allow entry
(`".env"`) is matched by equality while a directory-root entry
(`"allowed/"`) is matched by segment-aware ancestry — never a string
`startswith()` comparison, which would wrongly treat `"allowedx/"` as
inside `"allowed/"`. Concretely, as of STORY-014:

- `deny-structured` mode **now actually denies** a structured write whose
  canonicalized target does not resolve under one of its agent's allowed
  roots. Coverage is still scoped by `scope.agents`, the only allow-list
  this config section has: a call with no `agent_type` at all (the
  ordinary primary-session case — `agent_type` is documented as optional
  outside subagent calls), or an `agent_type` not present in
  `scope.agents`, has no configured scope to check against and is **not
  restricted** by `deny-structured`. Configuring `deny-structured` does
  not lock down the primary session; it constrains only the agent names
  you list under `scope.agents`.
- `strict-agent` mode still denies **every** structured tool call (reads
  included, not just writes) when it has no `agent_type`, or an
  `agent_type` not present in `scope.agents` — attribution is checked
  first, before category. A configured agent's write is then checked
  against its `allow` list with the same canonical path logic as
  `deny-structured`; an agent configured with an empty `allow: []` list
  has declared no writable paths and is denied every write, which is
  what makes `strict-agent` "require a custom agent definition with
  restricted Bash/tool declarations to be meaningful" — an agent with no
  declared restrictions gets no free rein.
- Neither mode's structured-write path enforcement is defeated by a
  Windows-style target or allow entry (`C:\Users\...`, `\\server\share`):
  `path_policy.py` rejects any backslash-containing or drive-letter path
  outright as an unsupported shape rather than silently mismatching or
  accepting it. This project only understands POSIX-style project-relative
  paths.
- Bash-driven file writes (`echo x > file`, `sed -i`, `cp`, ...) remain
  **completely outside `deny-structured`'s and `strict-agent`'s path
  coverage**, by construction — see the Bash section below.
  `classify_bash_command()`'s heuristic categories are a separate,
  inherently best-effort concern (STORY-013); STORY-014's canonical path
  enforcement applies only to the exact, name-based structured tools
  listed above. A `deny-structured`/`strict-agent` deployment that only
  reasons about `Write`/`Edit`/`MultiEdit`/`NotebookEdit` calls has a
  Bash-shaped hole that no amount of path canonicalization closes — an
  agent can always write outside its lane via `Bash` unless Bash itself is
  separately restricted (native tool permissions/allowlists, not this
  hook).

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

## Never re-executes the command under test

Every classification in this module is pure Python string/token analysis
(`shlex.split` plus regex) over the command text. It never builds a
second shell command containing the text being classified and never
shells out to interpret it. This closes off an entire class of injection
risk that a "classify by re-running a probe command" design would open.
