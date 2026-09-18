---
name: migrate-v1
description: Migrate an existing AgentForge v1 (project-bootstrap) project to v2 -- classify every v1 artifact as retained, transformed, archived, manual review, or obsolete; convert v1 stories to v2 work items and v1 scopes to v2 policy config only after explicit approval; never delete anything. Use when the user asks to "migrate to AgentForge v2", "upgrade this project's AgentForge scaffold", or runs `/agentforge:migrate-v1`.
---

# AgentForge v1 -> v2 Migration

Migrates an existing v1 `project-bootstrap` scaffold (Claude, Codex, or a
mixed project using both) toward the v2 architecture, without ever
deleting a v1 file. Every decision this skill makes is visible in the
migration report before anything is written; see
`docs/migration-v1-to-v2.md` for the full artifact-mapping table and the
judgment calls behind it.

All underlying logic lives in
`${CLAUDE_PLUGIN_ROOT}/scripts/migrate_v1.py`. It reuses `setup.py`'s
tested constitution-block insertion (STORY-005) and `config.py`'s
validated schema (STORY-004) rather than reimplementing either.

## Step 0: this is high-risk -- read before running anything

The migration never deletes a v1 file. Anything superseded is moved into
a timestamped archive (`.agentforge/migration-archive/<timestamp>/`), and
`apply` always returns exact rollback steps. Even so:

- Run `plan` (Step 2) first and actually read the report. Do not skip to
  `apply` on a project you have not reviewed.
- If the project is under version control with no uncommitted changes,
  this skill has an even easier rollback available: `git status` /
  `git diff` before running anything, so a plain `git checkout -- .` is
  also always an option in addition to the migration's own rollback
  command.

## Step 1: check whether v2 hooks can be validated yet

Run `claude plugin list` and look for an entry whose plugin id starts
with `agentforge@` (or, in a `--plugin-dir` development session, confirm
this checkout is the one currently loaded) and whose status is enabled.

- **If AgentForge v2 is installed and enabled:** v2's own lifecycle hooks
  (`hooks/hooks.json` -- `scope_policy.py`, `context.py`)
  are already active for this session. You may pass `--v2-hooks-validated`
  in Step 4 to also disable and archive the project's copied v1 hooks
  (`.claude/hooks/*.py`, `.codex/hooks/*.py`, and their registration in
  `.claude/settings.json`/`.codex/hooks.json`).
- **If it is missing or disabled:** do not pass `--v2-hooks-validated`.
  The migration still proceeds for everything else (constitution, stories,
  scope config) -- only the v1 hook disable/archive step is deferred, so
  the project is never left with neither the old nor the new hook active.
  Re-run Step 4 with `--v2-hooks-validated` once AgentForge is installed
  and enabled.

## Step 2: plan (dry run)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_v1.py plan --project-root .
```

Add `--v2-hooks-validated` only if Step 1 confirmed AgentForge v2 is
active. This never writes anything to disk regardless.

The command prints a JSON report with a `status` field:

- **`"no_change"`** -- either no v1 artifacts were found at all, or a
  prior migration already handled everything (this is the safe, expected
  outcome for a project that is already v2). Nothing further to do.
- **`"blocked"`** -- an existing `.agentforge/config.json` fails schema
  validation. Print every entry in `blocking_issues` verbatim and
  **stop**; fix that file by hand (or restore it), then re-run.
- **`"ok"`** -- ready to review. Continue to Step 3.

## Step 3: present the report and get one approval

Show the user, grouped by category, every entry in `items`
(`retained`/`transformed`/`archived`/`manual_review`/`obsolete`, each
with its `reason`) and every entry in `warnings`. In particular:

- **Any warning mentioning "never a real security boundary"** means this
  project's v1 `pre_tool_use.py` claimed Bash-based destructive-command
  blocking and per-agent scope enforcement that was always bypassable
  (shell indirection, `git -C`, a stray STORY-XXX token, unresolved `..`).
  Make sure the user reads this before approving -- v2's `scope.mode`
  starts at `"observe"` after migration specifically so nothing silently
  claims stronger enforcement than it delivers; point them at
  `docs/threat-model.md` before they consider `deny-structured` or
  `strict-agent`.
- **Every `manual_review` item is never touched by `apply`** -- these are
  reported for a human decision (a name collision, an ambiguous
  reference, hand-edited prose next to a nested constitution file, a
  lingering "wait for GO" checkpoint paragraph) and stay exactly as they
  are until the user acts on them directly.

Ask for one explicit approval covering the whole transaction. If the user
cancels, stop -- nothing has been written.

## Step 4: apply

Re-run with `apply` and the exact `plan_id` from Step 2's report:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_v1.py apply --project-root . \
  --approved-plan-id <plan_id> [--v2-hooks-validated]
```

`apply` recomputes the plan immediately before writing:

- a fresh `"blocked"` is returned as-is, nothing written;
- a fresh `"stale"` means project state changed since Step 2 (someone
  hand-edited a file in the meantime) -- present the new report as a
  fresh Step 3 and get a new approval before retrying;
- a fresh `"ok"` whose `plan_id` matches writes every change and returns
  `rollback_steps` (concrete, ready-to-run commands) and `manifest_path`
  (the exact file `rollback` below reads).

Report the files changed, and that a second run of this skill (Step 2)
will report `"no_change"` -- migration is idempotent.

## Rollback

Every applied migration can be undone exactly, using the manifest it
wrote:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_v1.py rollback --project-root . \
  --timestamp <timestamp-from-the-archive-directory-name>
```

This restores every modified file to its exact pre-migration bytes,
deletes every file the migration created, and moves every archived file
back to its original location. The archive directory itself
(`.agentforge/migration-archive/<timestamp>/`) is never deleted by
rollback -- it stays as an audit trail.

## What this skill does not do

- It never deletes a v1 file. Superseded content is archived, never
  removed.
- It never converts a story to a remote tracker (GitHub/GitLab) item --
  STORY-006's adapters are fetch-only. A project configured for a remote
  tracker gets `manual_review` entries for its v1 stories instead.
- It never disables a v1 hook or its registration until
  `--v2-hooks-validated` is explicitly passed.
- It never overwrites an existing local work item, an existing root
  constitution file's content, or an existing `scope.agents` entry --
  collisions are reported as `manual_review`, never silently resolved.
