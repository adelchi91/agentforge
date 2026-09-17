# Issue tracker CLI workflows (STORY-006)

`scripts/work_items.py` resolves one normalized `WorkItem` from exactly the
tracker a project configures (`tracker.type` in `.agentforge/config.json`,
ADR-0002). This document is the CLI-workflow contract its GitHub and
GitLab adapters assume — the *why* and *what command* behind
`_resolve_github`/`_resolve_gitlab`, the same way
`docs/agentforge-config.md` is the schema reference for `scripts/config.py`.

**Local Markdown needs none of this.** `tracker.type: "local"` never
shells out to anything; this document only applies when a project
configures `tracker.type: "github"` or `"gitlab"`.

## Where this code runs — and where it never runs

Per ADR-0005 ("no hook performs a network call"), the GitHub/GitLab code
paths in `scripts/work_items.py` are reachable only from explicit,
user-invoked skill operations:

- `/agentforge:setup` (validating that a configured remote tracker is
  reachable before committing to it);
- `/agentforge:prepare-work <id>` (STORY-008 — fetching and snapshotting
  one work item).

No lifecycle hook (`SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PostToolUse`, `SubagentStop`, `PreCompact`, `SessionEnd`/`Stop`) may ever
import or call `_resolve_github`/`_resolve_gitlab`, directly or
transitively. Hooks read only the local `.agentforge/active-work.json`
snapshot that `prepare-work` already wrote.

## Required CLIs and authentication

| Tracker | CLI | Auth |
|---|---|---|
| `github` | [`gh`](https://cli.github.com/) | `gh auth login` (or `GH_TOKEN`/`GITHUB_TOKEN` in the environment) completed once, out-of-band, before running `/agentforge:setup` or `/agentforge:prepare-work`. |
| `gitlab` | [`glab`](https://gitlab.com/gitlab-org/cli) | `glab auth login` (or `GITLAB_TOKEN` in the environment) completed once, out-of-band, before running `/agentforge:setup` or `/agentforge:prepare-work`. |

AgentForge never stores a credential, never prompts for one, and never
runs an interactive login flow itself — it only shells out to the
already-authenticated CLI and reports a structured `auth_failed` error
(see "Structured errors" below) if that CLI reports it is not logged in.

## Exact commands invoked

Every external command is invoked through an injectable `runner`
parameter (defaulting to `subprocess.run`) so callers — and every test in
`tests/test_tracker_adapters.py` — can substitute a fake without a real
network connection or a real `gh`/`glab` binary on PATH.

**GitHub** (`tracker.type: "github"`, `tracker.repository: "owner/repo"`):

```bash
gh issue view <number> --repo owner/repo --json number,title,body,state,url,updatedAt
```

Field mapping onto `WorkItem`:

| `gh` JSON field | `WorkItem` field |
|---|---|
| `number` | part of `canonical_id` (`github:owner/repo#<number>`) |
| `title` | `title` (sanitized) |
| `body` | `body` (sanitized, size-bounded) |
| `state` | `state` |
| `url` | `source` |
| `updatedAt` | `updated_at` |

`blockers` is always `()` for GitHub today — GitHub issues have no native
"blocked by" field, and this story does not implement a body-text
convention for inferring one (documented limitation; see the STORY-006
final report).

**GitLab** (`tracker.type: "gitlab"`, `tracker.repository: "group/project"`):

```bash
glab issue view <number> --repo group/project --output json
```

Field mapping onto `WorkItem`:

| `glab` JSON field | `WorkItem` field |
|---|---|
| `iid` | part of `canonical_id` (`gitlab:group/project#<iid>`) |
| `title` | `title` (sanitized) |
| `description` | `body` (sanitized, size-bounded) |
| `state` | `state` |
| `web_url` | `source` |
| `updated_at` | `updated_at` |

`blockers` is always `()` for GitLab today, for the same reason as GitHub.

These exact flags are this module's assumed CLI contract. They are
exercised only against mocked `runner` output in tests (no network, no
real CLI required to run the test suite) — if a future `gh`/`glab`
release changes flag names or JSON field names, update this table, the
adapter code, and the mocked fixtures in `tests/test_tracker_adapters.py`
together.

## Identifier rules

- A **work-item identifier** for `github`/`gitlab` is `#123` or bare
  `123` — nothing else. `owner/repo` (a **repository identifier**, the
  same shape as `tracker.repository`) is explicitly rejected as a
  work-item identifier with a `malformed_item` error naming the
  confusion, never silently reinterpreted.
- A **bare number with no tracker configured at all** (`config=None`, or
  `tracker.type` missing/unrecognized) is rejected as `ambiguous_identifier`
  — this module never guesses GitHub vs. GitLab vs. local from the
  identifier's shape alone. Once exactly one tracker is configured, the
  same bare number resolves only under that provider (`#123` under a
  `github` config and `#123` under a `gitlab` config produce different
  `canonical_id`s and never cross-resolve).

## Sanitization and size bounds

Remote content is untrusted. Before any GitHub/GitLab `title`/`body` is
placed on a `WorkItem`:

1. Control characters (except newlines) are stripped and line endings are
   normalized to `\n`.
2. The result is bounded to `context.max_bytes` from the project's
   `.agentforge/config.json` (STORY-004; `scripts.config.DEFAULT_CONFIG`
   supplies `8000` as the fallback when a caller's config omits the
   `context` section), truncated on a safe UTF-8 character boundary.
   `WorkItem.truncated` records whether truncation happened.

## Structured errors

`resolve_work_item` never raises for a recognized remote-tracker failure.
It returns a `WorkItemResult` whose `.error.kind` is one of:

| Kind | When |
|---|---|
| `missing_cli` | `gh`/`glab` is not installed or not on `PATH` (`FileNotFoundError` from the CLI invocation). |
| `auth_failed` | The CLI exits non-zero and its stderr indicates an authentication/authorization problem. |
| `not_found` | The CLI exits non-zero and its stderr indicates the issue/repository does not exist. |
| `malformed_item` | The identifier has the wrong shape for the configured provider, or the CLI's stdout is not the expected JSON shape. |
| `unsupported_tracker` | `tracker.type` is not `github`, `gitlab`, or `local`, or a required field (e.g. `tracker.repository`) is missing. |
| `ambiguous_identifier` | A bare number was given with no tracker configured at all. |
| `cli_error` | Any other CLI failure (timeout, unexpected exit, unexpected exception) — a catch-all so no exception ever escapes `resolve_work_item`. |

A remote failure of any kind never touches `.agentforge/active-work.json`
— `resolve_work_item` performs no filesystem writes at all; only the
caller (`/agentforge:prepare-work`, STORY-008) decides what, if anything,
to write, and does so only on a successful `WorkItemResult`.

## What this document does not cover

- Writing `.agentforge/active-work.json` from a resolved `WorkItem`
  (STORY-008).
- Injecting resolved work-item context into a session (STORY-009/010).
- Any commit-message or push-time tracker-identifier enforcement
  (STORY-011/012).
