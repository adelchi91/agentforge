---
state: draft
blockers:
updated_at:
---
# {{WORK_ITEM_ID}} — {{TITLE}}

<!--
Local Markdown work-item template, read by AgentForge's `local` tracker
adapter (`${CLAUDE_PLUGIN_ROOT}/scripts/work_items.py`'s
`_resolve_local`/`_parse_local_markdown`). The front matter above
(`state`, `blockers`, `updated_at`) and this
heading are the only parts that adapter reads structurally; everything
below the heading is this item's `body` verbatim.

`{{WORK_ITEM_ID}}` is this file's own name (a file named `STORY-006.md`
under `tracker.local_root` resolves to canonical id `local:STORY-006`) —
never invent a different identifier scheme here. `blockers:` is a plain
comma-separated list of the *other* tracker items this one depends on,
exactly as already assigned by whatever created this ticket (Matt
Pocock's `to-tickets`, or a person) — never renumbered or reassigned by
filling in this template.

See skills/work-contract/SKILL.md for how to write every section below.
-->

## What to build

{{WHAT_TO_BUILD}}
<!-- User-observable terms: what changes for whoever exercises the
     resulting behavior, never internal implementation detail. -->

## Blocked by

{{BLOCKED_BY}}
<!-- Canonical, provider-qualified identities only (e.g. `local:STORY-050`,
     `github:owner/repo#41`), matching this file's own `blockers:` front
     matter exactly. Write "None" explicitly if nothing blocks this item
     -- never leave this section blank. -->

## Acceptance criteria

{{ACCEPTANCE_CRITERIA}}
<!-- Observable outcomes only -- each criterion must be checkable by
     someone with no knowledge of the implementation. -->

## May touch

{{MAY_TOUCH}}
<!-- Concrete paths or path globs this work is expected to change. -->

## Must not touch

{{MUST_NOT_TOUCH}}
<!-- Concrete paths this work must never modify. -->

## Verification commands

{{VERIFICATION_COMMANDS}}
<!--
Every command here must:
  - already exist in this repository (check package.json scripts, a
    Makefile/justfile, pyproject.toml/tox.ini/pytest.ini, etc. before
    writing it down) -- never a guessed or "standard-sounding" command;
  - be safe to run as a verification step -- existing is not enough; a
    real command that drops/resets data, force-pushes, or requires live
    production credentials must not be listed even if it exists, unless
    a safe equivalent (--dry-run/--check/staging-only) is used instead;
  - be mapped to at least one acceptance criterion above, and say which
    one;
  - be a real, runnable command -- never "run the tests", "verify
    manually", a bare TODO, or "...".

If no automated verification is possible for this item (a pure prose
change, a manual step in a third-party system), say so explicitly and
name the manual check that substitutes for it. Do not leave this section
empty or silently omit it.
-->

## Out of scope

{{OUT_OF_SCOPE}}
<!-- What a reader might assume is included but deliberately is not. -->

## Completion evidence

Pending — filled in after execution.
<!-- Never pre-fill this section. After the verification commands above
     have actually run, record what happened: exit status, a relevant
     output excerpt, or a pointer to the run. -->
