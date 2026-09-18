# AgentForge v2 pilot report (template — not yet filled in)

**Status as of 2026-09-18: this pilot has not been run.** No section
below contains real data. This file is the structure a human maintainer
fills in while running the pilot STORY-020 requires before v2 can be
declared stable; see `docs/release-v2.md`'s "Pilot gate" section for how
this fits into the overall release process, and why an agent implementing
STORY-020 could not honestly fill this in itself (a real pilot needs real
elapsed wall-clock time on a real external project — it cannot be
simulated in one sitting without becoming exactly the "prompt confidence
instead of tested outcomes" this story exists to reject).

Copy this file to `docs/pilot-report-<project-name>-<date>.md` when
starting a real run, and fill in every `TODO` below. Do not edit this
template file itself with real data — keep it reusable for the next
pilot (a v2.1 feature pilot, a second reference project, etc.).

## 1. Choose the pilot project

**Requirements** (from STORY-020's acceptance criteria):

- One real Python project — not a toy, not one of this repository's own
  `examples/`. Ideally one you already maintain and know well enough to
  judge whether AgentForge's output is actually correct, not merely
  plausible.
- It should already have (or be given, before the pilot starts) a real
  test suite, a real tracker (GitHub Issues, GitLab, or a local
  `docs/work-items/` directory — STORY-006's three adapters), and a real
  Git remote with at least a nominal review process, so traceability and
  scope-policy findings mean something.
- It must be a project you are willing to run `scripts/migrate_v1.py`
  (or a from-scratch `/agentforge:setup`) against, since one of the five
  work items is explicitly a migration.

```
Project name:        TODO
Repository:          TODO
Primary language:    TODO (must be Python per STORY-020's own wording)
Existing test suite: TODO (framework, approx. test count, runtime)
Existing tracker:    TODO (github / gitlab / local)
AgentForge v1 user already? TODO (yes -> this pilot also exercises
                              scripts/migrate_v1.py; no -> this pilot
                              exercises /agentforge:setup from scratch)
Pilot start date:    TODO
Pilot end date:      TODO
Pilot operator:      TODO (name/handle)
AgentForge version under test: TODO (VERSION file contents at pilot start)
Claude Code CLI version:       TODO (`claude --version`)
```

## 2. Capture a baseline first

Before installing or using AgentForge v2 on this project, do (or recall,
if freshly done) the **same five work items** — or five comparable ones
of the same five kinds — using your normal process (v1 AgentForge if you
were already a user, or no AgentForge at all). This is the "baseline vs
v2" comparison STORY-020 requires; without it, every v2 number below is
uncalibrated.

If a true prospective baseline is impractical (the work already
happened historically), reconstruct it from memory/history as
faithfully as possible and mark it `RECONSTRUCTED` rather than silently
presenting it as freshly measured — this template's whole point is not
overstating what was actually observed.

```
Baseline method: TODO (fresh / RECONSTRUCTED)
```

## 3. The five required work items

STORY-020 requires **at least five** work items covering **feature,
bug, refactor, docs-only change, and migration**. Add rows if you run
more than five; do not drop below five or silently substitute a
different category for one of these.

For each item, fill in both the **baseline** run (Section 2's process)
and the **v2** run (using AgentForge v2's setup/prepare-work/work-contract
flow alongside Matt Pocock's skills, per `docs/release-v2.md`).

### 3.1 Feature

```
Work item id / title: TODO
Baseline setup time (minutes, zero to "ready to start coding"): TODO
v2 setup time (minutes):                                        TODO
Baseline human approval count (explicit approve/confirm gates):  TODO
v2 human approval count:                                         TODO
Context loss incidents (had to re-explain scope/state after a
  restart, /clear, or compaction):
  Baseline: TODO      v2: TODO
Scope-policy findings (v2 only — deny-structured/strict-agent
  denials, or observe-mode reports; "off" if scope policy was not
  enabled for this item):                                        TODO
Invalid commits (commits rejected or that should have been
  rejected by commit-msg/pre-push traceability — v2 only, "n/a" if
  traceability was off):                                         TODO
First-pass test success (tests passed without a fix-up round):
  Baseline: TODO      v2: TODO
Review findings (count, from a human or Matt's code-review skill):
  Baseline: TODO      v2: TODO
Rework (distinct follow-up commits/sessions needed after the
  first "done" claim):
  Baseline: TODO      v2: TODO
Notes / anything surprising:                                     TODO
```

### 3.2 Bug fix

```
(same fields as 3.1)
```

### 3.3 Refactor

```
(same fields as 3.1)
```

### 3.4 Docs-only change

```
(same fields as 3.1 — expect "n/a" for scope-policy/invalid-commits/
first-pass-test-success if the change genuinely touches no code path;
record that explicitly rather than leaving it blank, per
evals/work-contract/documentation-only-readme-update/'s requirement
that "no automated verification" be stated, not silently omitted)
```

### 3.5 Migration

```
Work item id / title: TODO
Migration kind (schema / API / dependency / code-path replacement): TODO
Did the migration-safety skill correctly classify this as a
  migration and apply extract/expand/migrate/validate/contract/
  delete phase sequencing (evals/migration-safety/ and ADR-0007)?    TODO
Was anything deleted before its replacement was validated (the one
  hard rule migration-safety enforces)? Should always be "no":       TODO
(plus every field from 3.1)
```

## 4. Aggregate comparison

Fill in after all five items are done. This is the table STORY-020's
"record baseline vs v2" requirement is actually asking for — a rollup,
not just the per-item detail above.

| Metric | Baseline | v2 | Delta / notes |
|---|---|---|---|
| Median setup time (minutes) | TODO | TODO | TODO |
| Total human approval count | TODO | TODO | TODO |
| Context loss incidents | TODO | TODO | TODO |
| Scope-policy findings (total) | n/a | TODO | TODO |
| Invalid commits (total) | TODO | TODO | TODO |
| First-pass test success rate | TODO | TODO | TODO |
| Review findings (total) | TODO | TODO | TODO |
| Rework instances (total) | TODO | TODO | TODO |

## 5. Migration rollback — must be exercised, not just tested in CI

STORY-020 is explicit: *"Do not declare v2 stable until... the migration
rollback has been exercised."* `tests/test_migration_rollback.py` proves
the mechanism works against fixtures; it does not substitute for running
it once for real. During this pilot:

```
[ ] Ran `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_v1.py plan
    --project-root .` against the real pilot project and reviewed the
    plan.
[ ] Ran `apply` (with --v2-hooks-validated once v2 hooks were confirmed
    installed and enabled).
[ ] Confirmed the project worked normally afterward (v2 hooks active,
    constitution/stories/scopes preserved per the plan's classification).
[ ] Ran `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_v1.py rollback
    --project-root . --timestamp <ts>` for real.
[ ] Confirmed rollback actually restored the pre-migration state:
    previous hook registration active again, every modified file
    byte-for-byte restored, every archived file back in its original
    location.
[ ] Recorded any discrepancy between what rollback claimed to restore
    and what was actually observed:                                TODO
```

If this checklist is not fully checked, v2 is not stable regardless of
how good the aggregate numbers in Section 4 look.

## 6. Severity-high hook/config defect log

STORY-020: *"no unresolved severity-high hook/config defects"* is the
other hard gate. Log every defect found during the pilot here, not just
ones that happened to block progress. A defect is severity-high if it:
silently produces an incorrect commit/push/scope decision, corrupts or
loses project state (constitution, stories, active-work snapshot,
migration archive), or causes a hook to hang/crash the agent's tool loop.

| # | Description | Severity | Where (hook/script/skill) | Status | Resolution / issue link |
|---|---|---|---|---|---|
| TODO | TODO | high / medium / low | TODO | open / resolved | TODO |

## 7. Go / No-Go

```
Any unresolved severity-high defect from Section 6?          TODO (yes/no)
Section 5 checklist fully checked?                            TODO (yes/no)
Both "no" and "yes" respectively required to proceed.

Overall recommendation:  TODO
  [ ] GO — declare this AgentForge version stable, bump VERSION off
      the "-dev"/"-rc" suffix, and update CHANGELOG.md's release date.
  [ ] NO-GO — list exactly what must change before the next pilot
      attempt: TODO
```

## 8. Free-form findings

Anything Sections 1-7's structure didn't have a place for — surprising
skill-triggering behavior, a work-contract that needed heavy manual
correction, a scope-policy false positive/negative, documentation that
was wrong or missing when you needed it, anything that made you trust
or distrust a specific AgentForge claim more than before the pilot.

```
TODO
```
