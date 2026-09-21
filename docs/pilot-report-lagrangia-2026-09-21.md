# AgentForge v2 pilot report — Lagrangia (in progress)

Copied from `docs/pilot-report-template.md` on 2026-09-21 to start a real
pilot run. This file is being filled in live as the pilot proceeds —
sections below marked `TODO` are genuinely not done yet; do not treat
this file as complete until Section 7's Go/No-Go is filled in.

## 1. Choose the pilot project

```
Project name:        Lagrangia MecAI (Dessia Technologies)
Repository:          /Users/adelchiasta/Dev/LAGRANGIA (root above several
                      per-service git repos — a monorepo-to-multirepo
                      migration in progress; the root itself is
                      intentionally not a git repo)
Primary language:    Python
Existing test suite: TODO (framework, approx. test count, runtime)
Existing tracker:    Jira (dessia.atlassian.net) — epic under pilot:
                      https://dessia.atlassian.net/browse/DERY-3916
AgentForge v1 user already? Yes — this pilot exercises
                      scripts/migrate_v1.py (see Section 5, done).
Pilot start date:    2026-09-21
Pilot end date:      TODO
Pilot operator:      adelchi91
AgentForge version under test: 2.0.0-dev (agentforge-v2, commit 8247537
                      at pilot start; local scope install from
                      /Users/adelchiasta/Dev/perso/claude_code_template)
Claude Code CLI version:       TODO (run `claude --version`)
```

Note on tracker: `to-tickets`/AgentForge have no native Jira integration
(see README's "Temporary: connecting Jira via the Atlassian MCP
connector" section) — ticket creation for this pilot goes through a
manual bridge via the authenticated `claude.ai Atlassian` MCP connector,
not either skill's own tracker adapter.

## 2. Capture a baseline first

```
Baseline method: TODO (fresh / RECONSTRUCTED)
```

## 3. The five required work items

None started yet. Note: the v1→v2 *scaffold* migration done in Section 5
below is **not** one of these five — the "migration" item required here
is a real code-level migration (schema/API/dependency/code-path
replacement) exercised with the `migration-safety` skill, still to be
picked from the Lagrangia backlog.

### 3.1 Feature — TODO
### 3.2 Bug fix — TODO
### 3.3 Refactor — TODO
### 3.4 Docs-only change — TODO
### 3.5 Migration (code-level, not the v1→v2 tooling) — TODO

## 4. Aggregate comparison

Not yet — fill in after all five items are done.

## 5. Migration rollback — exercised for real (DONE)

```
[x] Ran `migrate_v1.py plan --project-root .` against the real
    Lagrangia project root and reviewed the plan (plan_id
    885d1782d3a165537d2798a8a49453b88500f76b6e65f574daa63d465e928ea1).
    Report: 78 transformed items narrated by the assistant (AGENTS.md +
    .agentforge/config.json + "76 story files") — see discrepancy note
    below; 76 archived, 4 manual_review, 23 retained, no warnings, no
    blocking issues. No v1 hooks were found registered at all, so no
    "Bash-blocking was never a real boundary" warning applied here.
[x] Ran `apply` with `--v2-hooks-validated` (AgentForge v2 confirmed
    installed/enabled first via `claude plugin list`). Flag had no
    effect since no v1 hooks existed to disable.
[x] Confirmed the project worked normally afterward: AGENTS.md pointer
    block added with existing prose preserved, docs/work-items/ created,
    .agentforge/config.json present, custom personas retained unchanged.
[x] Ran `migrate_v1.py rollback --project-root . --timestamp
    20260921T085426001565Z` for real.
[x] Confirmed rollback actually restored the pre-migration state:
    - `diff AGENTS.md <archive>/before/AGENTS.md` → empty output (byte-
      identical).
    - `docs/work-items/` → empty/gone.
    - `.agentforge/config.json` → removed.
    - `.claude/stories/` → all originals back, including the untouched
      `STORY-017-040.md` (74 files total).
    - Re-running `plan` afterward produced the *same* plan_id as the
      original approved plan — strong evidence the state was restored
      exactly, not just approximately.
[x] Recorded discrepancy: the assistant's own narrated summary of the
    plan/apply JSON quoted "76 story files" / "78 transformed items,"
    but the actual manifest (`manifest.json`, grepped directly for
    `"kind": "move"`) recorded exactly **73** move entries — matching
    STORY-001–072 (72) + STORY-079 (1), consistent with a genuine
    numbering gap at STORY-073–078 in Lagrangia's own roadmap (confirmed
    separately: those numbers have no story file anywhere, individual or
    combined — not a migration defect, just unused numbers). This is a
    **narration-accuracy finding, not a tool/hook/config defect** — the
    underlying JSON and manifest were internally consistent with each
    other throughout; only the chat's prose paraphrase of them drifted,
    and it recurred (the same "76/78" figures were repeated, unprompted,
    on a later plan re-run) rather than self-correcting. See Section 8.
```

After rollback was verified, re-applied the migration (fresh plan_id
`9028ba499e5a4e3131b7ef7d8590e08dd9c1bd3a4384bb034a49ff9956a7e7ef`, after
manually archiving the one stale `manual_review` item —
`.claude/stories/STORY-017-040.md`, confirmed to be a pre-existing
summary/index page with no unique content, moved by hand to
`docs/archive/STORY-017-040.md` since it wasn't part of the migration's
own manifest either way). Final state: `.claude/stories/` empty, 73 work
items under `docs/work-items/`, migration confirmed idempotent (a
follow-up `plan` reported `"no_change"`-equivalent — clean, only the 3
remaining `manual_review` persona notes below).

**Still open, by design (`manual_review`, untouched by `apply`):**
- `.claude/agents/scaffolder.md`, `.claude/agents/service-scaffolder.md`,
  `.codex/agents/scaffolder.toml` — each has a "Behaviour Rules" section
  describing v1's CHECKPOINT/"wait for GO" ceremony, which v2 drops by
  default. Deferred by the pilot operator's own choice — not blocking.

## 6. Severity-high hook/config defect log

| # | Description | Severity | Where (hook/script/skill) | Status | Resolution / issue link |
|---|---|---|---|---|---|
| — | None found so far. | — | — | — | — |

## 7. Go / No-Go

```
Any unresolved severity-high defect from Section 6?          no (none found so far)
Section 5 checklist fully checked?                            yes
Both "no" and "yes" respectively required to proceed — but Section 3/4
(the five real work items and their aggregate comparison) are not done
yet, so this is NOT a GO/NO-GO decision point. Too early.

Overall recommendation:  TODO — pilot still in progress
  [ ] GO
  [ ] NO-GO
```

## 8. Free-form findings

- **Narration accuracy**: relying on a Claude session's own prose recall
  of structured tool output (plan/apply JSON, manifest.json) introduced
  a numeric discrepancy (76/78 vs. the real 73) that took a direct
  manifest check to resolve, and the same imprecise figures were
  repeated verbatim on a later, unprompted re-summary rather than
  self-correcting. Worth remembering for the rest of this pilot: verify
  counts against raw JSON/manifests directly rather than trusting a
  session's narrated summary of them, especially across multiple turns.
- **STORY-017-040.md**: confirmed to be a stale planning-era summary
  page (table of STORY-017–040 as rows, no per-story body, no
  `# STORY-XXX — Title` heading) predating the individual story files —
  correctly flagged `manual_review` by the migration (it doesn't match
  the parser's per-story pattern) rather than silently mis-converted or
  dropped. Confirmed nothing unique was lost: every story number it
  lists already has its own migrated `docs/work-items/STORY-0XX.md`.
- **STORY-073–078 gap**: not a migration defect — those numbers simply
  have no story file anywhere in `.claude/stories/` (individual or
  summary), consistent with a roadmap renumbering/skip that predates
  this pilot.
- **"Not a git repo" at the project root**: expected and by design —
  Lagrangia's root sits above several per-service git repos as part of
  its own monorepo-to-multirepo migration. The AgentForge migration
  tool's archive+rollback mechanism doesn't depend on git at all, so
  this had no practical effect on the pilot.
