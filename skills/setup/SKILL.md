---
name: setup
description: Configure the AgentForge companion layer in the current repository — committed policy config, constitution pointers, and work-contract rules — without overwriting existing CLAUDE.md, AGENTS.md, settings, or Matt Pocock's setup block. Use when the user asks to "set up AgentForge", "configure AgentForge", "install AgentForge in this project", or runs `/agentforge:setup`.
---

# AgentForge Setup

Configures the AgentForge companion layer in the current project:
creates or updates a short, delimited pointer block in exactly one
constitution file (`CLAUDE.md` or `AGENTS.md`), and creates
`.agentforge/config.json` from the validated template if it does not
already exist. This skill never touches Claude/Codex settings, Git hooks,
or any content outside its own delimited block — see "What this skill does
not do" below.

## Step 1: check for mattpocock-skills

Run `claude plugin list` (plain text is fine; no flags needed). Look for an
entry whose plugin id starts with `mattpocock-skills@` and whose status is
enabled.

- **If it is present and enabled:** continue to "Step 2" below.
- **If it is missing, disabled, or `claude plugin list` reports no plugins
  installed:** tell the user AgentForge works best alongside Matt Pocock's
  engineering skills and that it isn't installed yet. Print this exact
  install command:

  ```bash
  claude plugin marketplace add anthropics/claude-plugins-official
  claude plugin install mattpocock-skills@claude-plugins-official --scope user
  ```

  Then **stop** — do not write, edit, or propose edits to any project
  file. The user can re-run `/agentforge:setup` after installing Matt's
  plugin.

## Step 2: plan

Run the setup planner against the project root (the current working
directory, unless the user names another path). This never writes
anything to disk:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py plan --project-root .
```

The command prints a JSON plan with a `status` field:

- **`"needs_choice"`** — neither `CLAUDE.md` nor `AGENTS.md` exists, or
  both already exist with no unambiguous prior AgentForge block to infer
  from. Ask the user which file AgentForge should manage: `CLAUDE.md` or
  `AGENTS.md`. Re-run the plan command with
  `--constitution-target CLAUDE.md` or `--constitution-target AGENTS.md`
  added, using their answer.
- **`"blocked"`** — either the AgentForge marker block in the chosen
  constitution file is malformed (unmatched, duplicated, or nested
  `<!-- agentforge:start -->`/`<!-- agentforge:end -->` markers), or an
  existing `.agentforge/config.json` failed validation. Print every entry
  in `blocking_issues` to the user verbatim (they name the exact file and
  field) and **stop** — do not write anything, do not attempt to repair or
  replace the offending file yourself.
- **`"ok"`** — the plan is ready. Note the `plan_id` field — this is the
  exact identifier of *this* proposal (it is bound to the resolved
  constitution target, every input file's content, every proposed change's
  output, and this plugin's own template versions). Continue to "Step 3".

## Step 3: present the plan and get one approval

Show the user every entry in `changes` (path, action, and diff — actions
of `"none"` mean that file is already correct and needs no write) and
every entry in `notes` (informational: whether `docs/agents/` exists,
whether `.claude/settings*.json` exist, whether a Git hook manager such as
`core.hooksPath`, an existing `commit-msg`/`pre-push` hook, Husky, or
pre-commit already owns Git hooks here). Notes are report-only — this
skill makes no settings or Git-hook changes regardless of what they show.

Ask for one explicit approval covering the whole transaction (every
`"create"`/`"update"` entry in `changes` together — never approve or apply
a subset). This is **one approved transaction with stale-plan protection,
not a filesystem-atomic transaction**: if a write fails partway through
Step 4 (e.g. permission denied creating `.agentforge/`), files already
written before the failure are not rolled back — report the error and
re-run `/agentforge:setup` to pick up where it left off; do not describe
Step 4 as atomic.

- **If the user cancels:** stop. Nothing has been written — `plan` never
  writes to disk, and Step 4 is never reached.
- **If the user approves:** remember this exact `plan_id` and continue to
  "Step 4".

## Step 4: apply

Re-run the same command with `apply` in place of `plan`, the same
`--constitution-target` (if one was needed), and
`--approved-plan-id <plan_id>` set to the exact `plan_id` the user just
approved in Step 3:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py apply --project-root . --approved-plan-id <plan_id>
```

`apply` recomputes the plan immediately before writing and compares its
fresh `plan_id` against `--approved-plan-id`:

- a fresh `status` of `"needs_choice"`/`"blocked"` is returned as-is,
  nothing is written — report it and return to the relevant earlier step;
- a fresh `status` of `"stale"` means project state changed between Step 2
  and this step (for example, the user hand-edited the constitution file,
  or another process modified `.agentforge/config.json`, in the meantime).
  Nothing was written. Present the newly attached `changes`/`notes` exactly
  as a new Step 3, obtain a fresh approval for the new `plan_id`, and
  re-run Step 4 with that new id — never reuse the old `plan_id` or assume
  the old approval still covers the new proposal;
- a fresh `status` of `"ok"` means every non-`"none"` change was written.

Report the final list of files changed (and note that a second, identical
run of this skill will show every entry as `"none"` — setup is
idempotent).

## What this skill does not do

- It never edits both `CLAUDE.md` and `AGENTS.md`; when both exist it
  manages exactly one, chosen by the user or inferred from which file
  already carries the AgentForge block.
- It never touches any content outside its own
  `<!-- agentforge:start -->` / `<!-- agentforge:end -->` block — existing
  prose, and any block belonging to Matt Pocock's own setup, are preserved
  byte-for-byte, including exact line endings and final-newline state.
- It never writes `.claude/settings.json`, `.claude/settings.local.json`,
  or any Git hook (`core.hooksPath`, `commit-msg`, `pre-push`) — those are
  STORY-011 through STORY-014.
- It never fetches a tracker item, writes `.agentforge/active-work.json`,
  or injects session context — those are STORY-006 through STORY-010.
