# AgentForge v2 release guide

**v2 is not yet declared stable.** `VERSION` reads `2.0.0-dev`, not
`2.0.0`, and stays that way until `docs/pilot-report-template.md` has
been filled in for a real pilot and its Section 7 Go/No-Go says GO. See
"Pilot gate" near the bottom of this document for exactly what is
missing and what a human needs to do next.

This document exists because STORY-001 through STORY-019 each wrote
their own doc (`docs/architecture.md`, `docs/compatibility.md`,
`docs/codex-compatibility.md`, `docs/migration-v1-to-v2.md`,
`docs/threat-model.md`, `docs/agentforge-config.md`) and none of them, on
their own, answers "what do I need to know before I install/upgrade/
trust this." This page ties them together and is the one to read first;
it cross-references rather than duplicates the detailed evidence in each
source document, and if this page and a source document ever disagree,
the source document (the one with the dated evidence) wins.

## What AgentForge v2 actually is

A companion Claude Code / Codex plugin, not a fork of
[Matt Pocock's engineering skills](https://github.com/mattpocock/skills)
(ADR-0001). It adds a thin governance layer underneath Matt's plugin:

- `setup` / `prepare-work`: user-invoked skills that configure a project
  and snapshot active work.
- `work-contract`, `reconcile-docs`, `migration-safety`: model-invoked
  disciplines for contract quality, spec/ticket reconciliation, and safe
  migrations.
- Git-level commit/push traceability (`commit-msg`/`pre-push` hooks) and
  graded, honestly-labeled scope guardrails (never called a sandbox).
- Tested Codex parity, reusing the same policy modules rather than a
  second implementation.

**What this repository also still contains, unchanged:** the original
`project-bootstrap` 6-step interview (`/bootstrap`, `/story`,
`/add-agent`, `/project-review`, the interviewer/planner/scaffolder
agents). The v2 execution plan's own text about adopting a leaner
approach ("removes the fixed interview, linear story chain, generated
persona bureaucracy, checkpoint ceremony") describes the *design
philosophy* the new companion-layer skills follow — it is not a claim
that the old interview flow was deleted. It explicitly was not: "The v1
`project-bootstrap` 6-step interview... remains present and unchanged;
it is not removed until a later story retires it" (CHANGELOG.md,
STORY-002). No story through STORY-019 retired it, and this story does
not either — see "What actually changed for v1 users" below for the one
piece of ceremony that genuinely was removed, and why the rest was kept.

## Installation

See `README.md`'s "Install" section for the full, current instructions
(plugin marketplace install, coexisting with `mattpocock-skills`, and the
script installer for Codex or non-plugin Claude use). Summary:

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install mattpocock-skills@claude-plugins-official --scope user

claude plugin marketplace add adelchi91/agentforge
claude plugin install agentforge@agentforge --scope user
```

Order does not matter; AgentForge's manifest declares no `dependencies`
field on `mattpocock-skills` (STORY-003's tested, deliberate decision —
full evidence in `docs/compatibility.md`). Once both are installed, run
`/agentforge:setup` inside the target project — it plans, shows a diff,
and asks for one explicit approval before writing anything
(`skills/setup/SKILL.md`).

## Coexistence with mattpocock-skills

Full 8-scenario matrix, dependency-mechanism evidence, and the legacy
`project-bootstrap` → `agentforge` rename investigation:
`docs/compatibility.md`. Codex-specific coexistence and current hook/
custom-agent semantics: `docs/codex-compatibility.md`. In short: both
plugins install, update, and uninstall independently; uninstalling
AgentForge never touches a directly-installed `mattpocock-skills`, and
vice versa.

## Upgrade

```bash
claude plugin marketplace update agentforge
claude plugin update agentforge
```

If you are still on the pre-rename `project-bootstrap@agentforge`
identity, the marketplace's `renames` entry is discovery metadata only —
it does **not** migrate an existing install automatically (tested,
STORY-003). Migrate in this order (leaves no duplicate or orphaned
install):

```bash
claude plugin uninstall project-bootstrap@agentforge -y
claude plugin marketplace update agentforge
claude plugin install agentforge@agentforge -y
```

## Uninstall

```bash
claude plugin uninstall agentforge@agentforge
```

Or use the `/plugin` menu inside a session. This removes the plugin
only — it never touches a project's `.agentforge/config.json`,
`.agentforge/active-work.json`, constitution block, or installed Git
hooks. Project cleanup (if wanted) is manual: remove the AgentForge
marker block from `CLAUDE.md`/`AGENTS.md`, delete `.agentforge/`, and
uninstall the `commit-msg`/`pre-push` hooks per whatever chaining
`scripts/git_policy.py` set up (`docs/threat-model.md`'s "Bypass
instructions and limitations" sections document the exact hook-manager
detection and chaining behavior to reverse).

## Migrating an existing v1 project, and rollback

`docs/migration-v1-to-v2.md` is the full artifact-by-artifact mapping
(retained / transformed / archived / manual_review / obsolete) and every
judgment call behind it. Key properties, all tested
(`tests/test_v1_migration.py`, `tests/test_migration_rollback.py`):

- Nothing is ever deleted. Superseded content moves to a timestamped
  `.agentforge/migration-archive/<timestamp>/`.
- `--dry-run` causes zero filesystem changes; running the migration
  twice is a true no-op the second time.
- v1 hooks are disabled only after v2 hooks are confirmed installed and
  validated (`--v2-hooks-validated`) — a project is never left with
  neither hook active.
- **Rollback**: `migrate_v1.py rollback --project-root . --timestamp
  <ts>` replays the migration's own manifest to restore every modified
  file byte-for-byte and move every archived file back. Proven against
  fixtures in CI (`tests/test_migration_rollback.py`) — **but STORY-020's
  own stability gate requires this to also be exercised for real, once,
  during the pilot; see "Pilot gate" below.** A fixture-level pass is
  necessary evidence, not sufficient evidence, for this specific
  requirement.

## Assurance modes (how honest each policy setting actually is)

From the execution plan's grading table, encoded in
`scripts/config.py`/`docs/agentforge-config.md` and explained in full in
`docs/threat-model.md`:

| Mode | Behavior | Claim allowed |
|---|---|---|
| `off` | No hook policy | No enforcement |
| `observe` | Log/report suspicious operations | Observational only |
| `ask` | Request confirmation for ambiguous or risky tool calls | Interactive guardrail |
| `deny-structured` | Deny out-of-scope `Write`/`Edit` calls after canonical path checks | Enforces covered structured tools only |
| `strict-agent` | Custom agent has restricted tools/Bash allowlist plus structured path checks | Strong within documented tool coverage, not an OS boundary |

None of these is ever labeled "sandboxing." Every default ships at its
quietest setting (`tracker.type = "local"`, every other mode `off`) —
installing AgentForge's config never silently enables blocking or
mutating behavior (`docs/agentforge-config.md`, "Defaults are fully
non-destructive").

**Real enforcement boundaries** (the things that actually cannot be
talked around by a differently-phrased command), per
`docs/threat-model.md`:

| Concern | Owned by |
|---|---|
| Commit-message / pushed-commit traceability | Git `commit-msg` / `pre-push` hooks (STORY-011/012), plus CI |
| Merge authorization | Branch protection / human review |
| Filesystem / network isolation | Native OS sandbox or container |
| Code quality | Formatter, linter, type checker, test suite, CI |

Lifecycle hooks (`PreToolUse` included) are context, UX feedback, audit
trail, and defense in depth — a useful second layer, never the boundary
itself. Read `docs/threat-model.md` in full before enabling
`deny-structured` or `strict-agent` and relying on them for anything.

## Compatibility matrix

| Surface | Status | Evidence |
|---|---|---|
| Claude Code, standalone | Fully supported | `docs/compatibility.md` |
| Claude Code + mattpocock-skills | Fully supported, both independently installable/updatable/uninstallable | `docs/compatibility.md` (8-scenario matrix) |
| Codex | Supported with documented, current-as-of-2026-09 limitations (no confirmed `agent_type`-equivalent attribution under Codex custom agents; `PermissionRequest` not wired; no canonical `sandbox_mode` enumeration; coarser sandbox granularity than Claude's) | `docs/codex-compatibility.md` |
| Codex + mattpocock-skills | Install Matt's skills via `npx skills@latest add mattpocock/skills` until his native Codex plugin ships | `docs/codex-compatibility.md` |
| Upstream `mattpocock-skills` — pinned known-good release (v1.2.3, commit `3cca18b368ae95cdbdebbff572ccafa662551015`) | Passing as of 2026-09-18 | `tests/integration/test_plugin_coexistence.py::PinnedMattCoexistenceTests`, `.github/workflows/integration.yml` |
| Upstream `mattpocock-skills` — latest available release (whatever `claude-plugins-official` currently resolves to) | Passing as of 2026-09-18 (also v1.2.3-tagged, commit `959a8e9f1edc3adbe2f7e3054bb6fbefa6696260` — the official marketplace's pointer moved without a semver bump between 2026-09-16 and 2026-09-18, itself a small piece of drift worth knowing about) | `tests/integration/test_plugin_coexistence.py::LiveMattCoexistenceTests`, `.github/workflows/integration.yml` |

## Continuous integration

Three workflows, deliberately separated by what they need:

- **`.github/workflows/ci.yml`** — required on every push/PR. Unit tests
  across a Python × OS matrix, JSON validation, shell syntax, a
  whitespace `git diff --check` across the PR's own commit range, and
  `claude plugin validate . --strict`. No network dependency beyond
  installing the `claude` CLI itself (`curl -fsSL
  https://claude.ai/install.sh | bash` — confirmed to need no
  authentication for `plugin validate`, which is local manifest/
  directory-structure validation only).
  - **Python versions**: 3.10, 3.11, 3.12, 3.13. 3.9 is excluded (EOL
    2025-10-05). This repository pins no `python_requires` of its own;
    every `scripts/*.py` module is stdlib-only with no version-gated
    syntax, so the matrix floor is "not yet end-of-life," not an
    empirically narrower tested minimum.
  - **Operating systems**: `ubuntu-latest` and `macos-latest` only.
    `windows-latest` is excluded: `scripts/git_policy.py`,
    `scripts/setup.py`, and `scripts/scope_policy.py` call `os.chmod`
    and install POSIX-shebang (`#!/bin/sh`) Git hooks
    (`templates/git-hooks/commit-msg`, `templates/git-hooks/pre-push`).
    Windows support is not an explicit goal yet; this is a stated
    exclusion, not a silent gap.
  - **Verified live on GitHub Actions (2026-09-19), one real bug found
    and fixed**: the first real run failed both `unit tests
    (ubuntu-latest, py3.10)` and `unit tests (macos-latest, py3.10)`
    while every other job (py3.11/3.12/3.13 on both OSes, JSON
    validation, shell syntax, `git diff --check`,
    `claude plugin validate --strict`) passed — exactly the kind of gap
    this sandbox's local-only verification could not catch.
    `tests/test_codex_packaging.py`'s TOML validation (STORY-018) did
    `import tomllib` unconditionally; that module is Python 3.11+
    stdlib only, so it does not exist on 3.10 and every test in that
    module failed to even collect. Fixed by falling back to `tomli`
    (`tomllib`'s own pre-3.11 backport) when the stdlib import fails,
    and adding `pip install "tomli; python_version < '3.11'"` as a CI
    step (a no-op on 3.11+, where the stdlib module is already
    preferred) — verified both the fallback-import path and the full
    `test_codex_packaging` suite locally under a simulated
    `tomllib`-unavailable environment before pushing the fix. This is
    the real end-to-end verification the note above once said was still
    pending.
- **`.github/workflows/integration.yml`** — the pinned-vs-latest
  upstream matrix (see "Compatibility matrix" above). Runs weekly, on
  demand, and (non-blocking, `continue-on-error: true` per leg) on a PR
  that touches the coexistence surface. Categorizes a failure as
  upstream drift (pinned passes, latest fails) or an AgentForge-side/
  CLI-version regression (pinned itself fails) — see the workflow's own
  comments for the heuristic's exact limits. This workflow needed a real
  fix to be CI-runnable at all: `claude plugin marketplace add
  owner/repo` resolves to an SSH clone
  (`git@github.com:owner/repo.git`), which GitHub refuses with no
  registered key even for a public repository — verified directly by
  pointing `GIT_SSH_COMMAND` at an identity-less config. Both live test
  classes now add marketplaces by explicit `https://github.com/...` URL
  instead, which clones anonymously. See the dated addendum in
  `docs/compatibility.md` for the full account of this correction.
- **`.github/workflows/plugin-eval.yml`** — manual-only
  (`workflow_dispatch`). See "Plugin evals" immediately below for why.

## Plugin evals

`claude plugin eval . --eval-dir evals` is a real command with a real,
documented case/grader schema (confirmed via `claude plugin eval --help`
and `claude plugin eval init --help`), and `evals/` already has cases
covering work-contract quality, spec/ticket reconciliation, and
migration classification (STORY-007/STORY-016). This story added:

- `evals/setup/` (new category): setup preserves existing `CLAUDE.md`/
  `AGENTS.md` prose and Matt Pocock's own block, follows a
  plan-then-approve flow rather than claiming files are already
  written, and stops before writing anything when `mattpocock-skills`
  is missing.
- One "does not fire" (`max: 0`) grader per skill that previously had
  only positive `skill-fires.md` (`min: 1`) graders — `setup`,
  `work-contract`, `reconcile-docs`, and an addition to
  `migration-safety`'s existing `ordinary-feature-work` case.

See `evals/README.md` for the full category table and the deliberate
scope bound on how many cases this suite carries.

**This command could not be executed in the sandbox this story was
implemented in**: `claude plugin eval` reported `` `plugin eval` is
currently in early access `` on every invocation, including
`claude plugin eval init --bare`. This is a **per-account, Anthropic-side
enablement**, not a local settings flag or environment variable a
maintainer can flip themselves (confirmed: no `settings.json` key, no
`claude config set` option, no effect from `claude update`). Whoever
runs the actual release process needs an account with this early-access
flag enabled, plus an `ANTHROPIC_API_KEY` (as the `plugin-eval.yml`
workflow's repository secret, or locally). Once available:

```bash
claude plugin eval . --eval-dir evals
```

and attach the resulting report (or `.github/workflows/plugin-eval.yml`'s
uploaded `plugin-eval-results` artifact) to the release candidate, per
STORY-020's acceptance criterion that "plugin eval results and known
variance are published with the release candidate."

## Release process

This is a single-maintainer plugin repository with one published
package (no monorepo, no independently-versioned sub-packages), so a
tool like [Changesets](https://github.com/changesets/changesets) — built
for coordinating independent version bumps and changelog fragments
across many packages in one JS monorepo — would add process overhead
(a changeset file per PR, a release PR bot, a Node toolchain this
otherwise-Python repository does not need) without solving a problem
this repository actually has. Instead, the reviewable process this
repository already practices (STORY-002 onward; see every prior
`CHANGELOG.md` entry) is kept as the deliberate choice:

1. Every story/PR adds its own dated, detailed `### Added/Changed/Fixed
   (STORY-XXX)` section to `CHANGELOG.md` as part of the same PR that
   makes the change — this is the "changeset," reviewed in the same
   diff as the code, rather than a separate file merged later by
   automation.
2. A release bumps exactly three places together, atomically, in one
   PR: `VERSION`, `.claude-plugin/plugin.json`'s `"version"` field, and
   `CHANGELOG.md`'s top `## [X.Y.Z] - <date>` heading (replacing
   `- Unreleased`).
3. `python3 scripts/check_version_sync.py` (STORY-020) is the mechanical
   check that those three never drift apart — it is wired into
   `ci.yml`'s `unit-tests` job and fails the build if any of them
   disagree, or if `CHANGELOG.md` has no valid release heading at all.
4. The release PR is reviewed like any other change (this is the
   "reviewable" part Changesets would otherwise provide) before the tag
   is pushed.

## Threat model

Full document: `docs/threat-model.md` (required reading before enabling
`deny-structured`/`strict-agent`, or before relying on commit/push
traceability for anything beyond defense-in-depth). It exists because of
ADR-0004's honesty requirement: "AgentForge must stop claiming that
text-pattern hooks form a security boundary." The one-paragraph version:
lifecycle hooks run inside the agent's own tool-call loop and cannot stop
a differently-phrased command, an agent that simply doesn't call a
classified tool, or a compromised model. The things that actually cannot
be talked around are listed in "Assurance modes" above.

## What actually changed for v1 users (compatibility breaks)

- **Plugin identity renamed**: `project-bootstrap` → `agentforge`
  (STORY-002/003). The marketplace `renames` entry is discovery metadata
  only, not an automatic migration — see "Upgrade" above for the exact
  manual steps. This is the one break every existing installed user
  hits regardless of whether they adopt any new v2 feature.
- **Post-edit auto-formatting removed** (STORY-015, applies to the
  shared hook suite both v1 and v2 projects use):
  `templates/shared/hooks/post_tool_use.py` no longer runs `ruff --fix`/
  `eslint --fix` after every edit. It now only reports findings when a
  project explicitly opts `quality.post_edit` into `"report"`
  (`docs/agentforge-config.md`); silent mutation is not merely
  discouraged, the schema makes it unrepresentable. Any project that was
  relying on the old auto-fix behavior will need to run its formatter
  explicitly instead. This is the one piece of "v1 ceremony" this
  repository can honestly claim was removed, everywhere, unconditionally
  — the interview/persona/checkpoint flow described at the top of this
  document was a deliberate keep, not an oversight.
- **No `dependencies` field on `mattpocock-skills`** (STORY-003) — not a
  behavior change from v1 (v1 never declared this either), but worth
  stating: installing AgentForge never auto-installs Matt's plugin; both
  are always two explicit steps.
- **A migrated v1 project's `scope.mode` starts at `"observe"`, never
  higher, regardless of what v1 claimed** (`docs/migration-v1-to-v2.md`,
  "The Bash/scope-enforcement warning"). If your v1 `scopes.json` implied
  stronger enforcement than v1 actually provided (it always did — see
  `tests/test_v1_characterization.py`), migration will not silently
  carry that overclaim forward into v2's config; you must explicitly opt
  into `"deny-structured"` or `"strict-agent"` after reading
  `docs/threat-model.md`.
- **A migrated v1 Codex project's stale `Stop`-mapped `session_end.py`
  registration is flagged, not auto-corrected** — the *new* Codex
  packaging template (STORY-018) correctly registers on `SessionEnd`,
  but an already-generated project's `.codex/hooks.json` is left as-is
  by migration; fix it by hand if you still use that hook independently
  of the AgentForge plugin (`docs/migration-v1-to-v2.md`).

No other behavior change to already-generated v1 projects is introduced
by installing the v2 plugin — the v1 6-step interview, its templates,
and its generated output format are byte-for-byte what they were before
(`tests/fixtures/v1/examples_checksums.json`).

## Pilot gate (v2 is not yet stable)

STORY-020 requires, before v2.0.0 can be declared stable:

1. A pilot on one real Python project across at least five work items
   (feature, bug, refactor, docs-only, migration), recording baseline
   vs. v2 metrics.
2. No unresolved severity-high hook/config defect.
3. The migration rollback exercised for real (not just proven against
   fixtures in CI).

**None of this has happened yet.** `docs/pilot-report-template.md` is
the ready-to-fill structure for item 1 (and tracks items 2-3 as explicit
checklists) — a human maintainer needs to actually run it against a real
project over real elapsed time; an agent implementing this story cannot
fabricate that evidence without defeating the entire point of "tested
outcomes rather than prompt confidence" this story exists to enforce.

**What a human needs to do next:**

1. Pick a real Python project (Section 1 of the template).
2. Capture or reconstruct a baseline (Section 2).
3. Run the five work items under v2, recording every metric (Section 3).
4. Actually run `migrate_v1.py apply` then `migrate_v1.py rollback` on a
   real project state, not just the test suite (Section 5).
5. Log every severity-high defect found along the way, resolved or not
   (Section 6).
6. Fill in Section 7's Go/No-Go honestly. Only on GO: bump `VERSION` and
   `.claude-plugin/plugin.json` to `2.0.0` (dropping `-dev`), update
   `CHANGELOG.md`'s heading to `## [2.0.0] - <real date>`, and get an
   early-access-enabled account to run `claude plugin eval` and attach
   its results to the release PR.

Until then, `VERSION` stays `2.0.0-dev` and every doc in this repository
that references "v2" should be read as "the v2 candidate under
evaluation," not "the shipped, stable release."
