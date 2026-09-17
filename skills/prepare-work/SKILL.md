---
name: prepare-work
description: Resolve a configured work item, validate its blockers are closed (or explicitly overridden), validate its work contract is complete, and snapshot it to local active-work state so lifecycle hooks can restore scope and verification commands without network access. Use when the user asks to "prepare work on", "start work item", "start ticket", or runs `/agentforge:prepare-work <id>`.
---

# AgentForge Prepare Work

Resolves one work item through the project's configured tracker
(`.agentforge/config.json`'s `tracker.type` — `local`, `github`, or
`gitlab`; STORY-006), checks that its blockers are closed and its work
contract is complete, and — only after those checks pass and, where
anything would be written, after explicit approval — writes the bounded
runtime snapshot `.agentforge/active-work.json`. That snapshot (never the
network, never a session transcript) is what a later lifecycle hook
(STORY-009/010) reads to restore scope, exclusions, and verification
commands after a restart, resume, clear, or compaction.

All underlying logic lives in
`${CLAUDE_PLUGIN_ROOT}/scripts/active_state.py`, which builds on
STORY-006's `work_items.py` (tracker resolution) and STORY-007's
work-contract discipline (`skills/work-contract/SKILL.md`). Every
subcommand below prints one JSON object to stdout; read `status` first.

## Step 1: resolve and check

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/active_state.py resolve <id> --project-root .
```

This never writes anything. It reports:

- `status: "resolve_error"` — the tracker adapter could not resolve `<id>`
  (`error.kind` is one of `missing_cli`, `auth_failed`, `not_found`,
  `malformed_item`, `unsupported_tracker`, `ambiguous_identifier`,
  `cli_error` — see `docs/agents/issue-tracker.md`). Report `error.message`
  to the user verbatim and stop.
- `status: "ok"` with `readiness` and `contract` — continue to Step 2.

## Step 2: readiness (blockers)

Look at `readiness.ready`:

- **`true`**: every blocker (if any) is closed. Continue to Step 3.
- **`false`**: `readiness.unresolved` names every blocker that is not
  closed (each with its own `state`, or an `error` if it could not even
  be resolved). **Present every one of them to the user** — never only
  the first — and stop by default.
  - If the user explicitly approves proceeding anyway, re-run every
    `plan`/`apply` command below with `--override-blockers` added. This
    is recorded as visible evidence in the written snapshot's
    `blocker_override` field (which blockers were overridden) — it is
    never a silent bypass.
  - Do not pass `--override-blockers` on your own initiative. It requires
    the user's explicit approval for this exact ticket, every time.

GitHub and GitLab items always report zero blockers today (STORY-006 does
not infer a "blocked by" edge from issue text), so `readiness.ready` is
trivially `true` for a remote tracker.

## Step 3: work contract completeness

Look at `contract.complete`:

- **`true`**: continue to Step 4.
- **`false`**: `contract.missing` names every required section
  (`What to build`, `Blocked by`, `Acceptance criteria`, `May touch`,
  `Must not touch`, `Verification commands`, `Out of scope`) that is
  absent or an obvious placeholder (empty, `TODO`, `...`, a
  `{{template hole}}`). `Completion evidence` is never reported missing
  here — an absent one defaults to "Pending — filled in after execution."

  Draft the missing sections yourself, following
  `skills/work-contract/SKILL.md`'s discipline exactly (vertical-sliced
  "What to build", observable acceptance criteria, only real
  already-existing verification commands, an explicit "no automated
  verification" acknowledgment where appropriate) — **never invent or
  rename the identity or the `Blocked by` edges**; those are immutable
  here (see "What this skill does not do").

  Write your drafted sections to a small JSON file (section name → new
  content string), e.g. `/tmp/agentforge-contract-updates.json`:

  ```json
  { "Verification commands": "- python3 -m unittest tests.test_foo -v" }
  ```

  Plan the update — never writes anything:

  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/active_state.py contract-plan <id> \
    --project-root . --updates-json /tmp/agentforge-contract-updates.json
  ```

  - `status: "no_change"` — the contract was already complete; nothing to
    do, continue to Step 4.
  - `status: "unsupported_remote"` — the tracker is `github`/`gitlab`.
    **This module has no write path for a remote tracker item** (STORY-006
    implemented fetch-only adapters). Show the user `diff` (computed
    against the item's current body) so they can see exactly what would
    change, and tell them to apply it themselves via
    `gh issue edit <n> --body-file ...` or `glab issue update <n>
    --description ...`, then re-run this skill from Step 1. Do not
    describe this as applied.
  - `status: "incomplete_updates"` — even with your drafted updates, one
    or more sections is still missing/placeholder; `contract.missing`
    names them. Draft more and re-plan.
  - `status: "ok"` — show the user `path` (the exact ticket file that
    would change) and `diff` (the exact unified diff) and **require
    explicit approval before writing**. If the user cancels, stop here;
    nothing has been written. If they approve, note the exact `plan_id`
    and apply it:

    ```bash
    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/active_state.py contract-apply <id> \
      --project-root . --updates-json /tmp/agentforge-contract-updates.json \
      --approved-plan-id <plan_id>
    ```

    `status: "stale"` means the ticket file changed between plan and
    apply (or no/wrong `--approved-plan-id` was given) — nothing was
    written; re-run `contract-plan` and get a fresh approval. A
    successful apply returns `status: "ok"` again; return to Step 1 to
    re-resolve the now-complete item.

## Step 4: prepare the snapshot

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/active_state.py prepare-plan <id> \
  --project-root . [--override-blockers]
```

(Add `--override-blockers` only if the user approved it in Step 2 —
always pass the same flag to both `prepare-plan` and `prepare-apply`.)

- `status: "resolve_error" | "blocked_by_dependencies" | "incomplete_contract"`
  — return to the matching step above.
- `status: "oversized"` — the serialized snapshot does not fit
  `context.max_bytes` even after shrinking the descriptive `title`/
  `out_of_scope_summary` fields. This is rare (it means the ticket's
  scope/verification content alone is larger than the configured byte
  budget) — tell the user to either raise `context.max_bytes` in
  `.agentforge/config.json` or shorten the ticket's `May touch`/
  `Must not touch`/`Verification commands` sections. Nothing is written;
  any previous valid snapshot is untouched.
- `status: "no_change"` — a previous snapshot already matches this item's
  identity, content, and blocker-override state exactly. Report that
  nothing needs to change; do not call `prepare-apply` (it would be a
  correct no-op, but there is nothing to approve).
- `status: "ok"` — show the user `diff` (the exact change to
  `.agentforge/active-work.json`) and get approval, then:

  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/active_state.py prepare-apply <id> \
    --project-root . --approved-plan-id <plan_id> [--override-blockers]
  ```

  A fresh `status: "stale"` means project state changed since the plan
  (or no/wrong `--approved-plan-id`); nothing was written — re-plan and
  get a new approval. `status: "write_error"` means the write itself
  failed (permission denied, an unsafe/symlinked `.agentforge` path);
  report the error, nothing was written, and any previous valid snapshot
  is untouched. `status: "ok"` means `.agentforge/active-work.json` was
  written and `.gitignore` was updated if needed (see below) — report the
  final snapshot's `canonical_id`, `allowed_paths`, `forbidden_paths`, and
  `verification_commands` to the user.

## `.gitignore`

`prepare-apply` surgically ensures exactly one line,
`.agentforge/active-work.json`, is present in the project's `.gitignore`
— creating the file if it does not exist, and leaving every other line,
comment, newline style, and final-newline state untouched. It never adds
`.agentforge/config.json` (that file is committed policy, not runtime
state) and never rewrites the file if the entry is already present.

## Clearing active work

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/active_state.py clear --project-root . --confirm
```

**Always ask the user to confirm before running this with `--confirm`.**
Without `--confirm`, the command reports `status: "not_confirmed"` and
deletes nothing — use that to show what would happen before asking. This
deletes only `.agentforge/active-work.json`; it never deletes, closes, or
updates any tracker item (local file, GitHub issue, or GitLab issue), and
running it again when no snapshot exists reports `status: "already_clear"`
rather than an error.

## What this skill does not do

- It never invents, renumbers, or reorders a canonical identity or a
  `Blocked by` edge — those belong to whatever created the ticket
  (Matt Pocock's `to-tickets`, or a person). `contract-plan`/`apply`
  silently drop any attempt to change `Blocked by` through a contract
  update.
- It never fetches or writes anything from a lifecycle hook — this is a
  user-invoked skill only (ADR-0005). STORY-009/010's hooks read the
  snapshot this skill writes; they never call a tracker adapter
  themselves.
- It never writes to a GitHub or GitLab issue body directly — STORY-006
  implemented fetch-only remote adapters. A remote contract update is
  always the user's own action via the tracker's own tool; this skill
  only proposes the diff.
- It never copies the full ticket body into
  `.agentforge/active-work.json`. The snapshot holds only identity, a
  source pointer, a content digest, scope (`allowed_paths`/
  `forbidden_paths`), `verification_commands`, and a short
  `out_of_scope_summary` — bounded by `context.max_bytes`.
- It does not judge whether a drafted acceptance criterion or
  verification command is *good* — that discipline lives entirely in
  `skills/work-contract/SKILL.md`; this skill's script only checks
  structural completeness (a section is present and not an obvious
  placeholder).
