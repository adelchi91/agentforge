# Changelog

All notable changes to AgentForge are documented in this file.

## [2.0.0-dev] - Unreleased

### Changed

- Renamed the plugin identity from `project-bootstrap` to `agentforge`
  (STORY-002). Anyone who previously ran
  `claude plugin install project-bootstrap@agentforge` should reinstall as
  `claude plugin install agentforge@agentforge`; the marketplace manifest's
  `renames` map records this so tooling can resolve the old name.

- Updated the README install section to `agentforge@agentforge` and added an
  upgrade note for `project-bootstrap` installs.

### Added

- Namespaced companion-plugin skeleton: `skills/`, `agents/`, `hooks/hooks.json`,
  and `scripts/` at the plugin root, alongside the existing v1 layout
  (STORY-002).
- Placeholder skills `agentforge:setup` and `agentforge:prepare-work`. Both are
  stubs; full behavior lands in STORY-005 and STORY-008 respectively.
- `VERSION` as the single machine-readable version source, kept in sync with
  `.claude-plugin/plugin.json`'s `version` field.
- `docs/compatibility.md`: STORY-003's full coexistence evidence — 8
  installation/upgrade/uninstall scenarios, the dependency-mechanism
  investigation, and the legacy-rename investigation, each run against an
  isolated `CLAUDE_CONFIG_DIR`.
- `tests/integration/test_plugin_coexistence.py` (with `tests/integration/__init__.py`):
  offline coexistence tests (local-directory marketplaces only, run by
  default) plus opt-in network-backed tests against the real
  `mattpocock-skills` plugin (`AGENTFORGE_LIVE_INTEGRATION=1`).
- `tests/fixtures/fake_upstream_marketplace/`: a small, original fixture
  plugin standing in for a third-party companion plugin so coexistence
  mechanics can be tested offline without depending on or vendoring
  `mattpocock/skills`.
- `tests/fixtures/fake_dependent_marketplace/`: two small, original
  fixture plugins that declare a `dependencies` field on the fake
  upstream plugin (one unversioned, one at a deliberately incompatible
  `^99.0.0` range), used to reproduce the dependency-mechanism and
  incompatible-version scenarios offline.
- A "Using AgentForge alongside mattpocock-skills" section in `README.md`.

The v1 `project-bootstrap` 6-step interview (`/bootstrap`, `/story`,
`/add-agent`, `/project-review`) remains present and unchanged; it is not
removed until a later story retires it (see
`docs/plans/agentforge-v2-execution-plan.md`).

### Decided (STORY-003)

- No `dependencies` field on `mattpocock-skills` in `.claude-plugin/plugin.json`.
  Tested several forms of a cross-marketplace plugin dependency in isolated
  Claude Code configs; none auto-installs the companion plugin, and every
  version-ranged form is unreliable against `mattpocock/skills`' current git
  tagging. Even the one reliable form (marketplace-qualified, unversioned)
  makes all of AgentForge fail to load whenever Matt isn't installed yet,
  which contradicts the companion-plugin boundary in ADR-0001. Both plugins
  are installed as two independent, order-independent steps instead. Full
  evidence in `docs/compatibility.md`.
- The marketplace `renames` field (added in STORY-002) is confirmed to be
  discovery metadata only — it does not migrate an installed
  `project-bootstrap@agentforge` to `agentforge@agentforge` automatically.
  README and `docs/compatibility.md` document the exact, tested manual
  migration order (uninstall old → update marketplace → install new).

### Added (STORY-007, STORY-011, STORY-014)

- `skills/work-contract/SKILL.md`: the reusable work-contract discipline —
  `What to build`, `Blocked by`, `Acceptance criteria`, `May touch`/
  `Must not touch`, `Verification commands`, `Out of scope`, and
  `Completion evidence`. Rejects vague or invented verification commands
  and preserves the canonical identity and blocking edges Matt's
  `to-tickets` workflow already assigned, rather than reinventing them
  (STORY-007). `templates/local-work-item.md` is the matching local-tracker
  template, and `evals/work-contract/` covers feature, bug,
  documentation-only, migration, and external-manual-step work.
- `scripts/git_policy.py` and `templates/git-hooks/commit-msg`: a real Git
  `commit-msg` hook that validates the actual commit message file Git
  hands it — never shell-command text — against the project's configured
  tracker identifier pattern (GitHub, GitLab, or local). Installation
  detects and never overwrites an existing hook manager (Husky,
  `pre-commit`, a custom `core.hooksPath`, or an existing `commit-msg`),
  chaining to it when safe, and falls back to documented manual
  integration or a CI-only `check-commit` command otherwise (STORY-011).
- `scripts/path_policy.py`: canonical path/allow-list utilities that
  resolve the project root, target paths, and every allowed root through
  symlink and `..` normalization before any ancestry comparison, and
  distinguish an exact-file allowance from a directory-root allowance.
  Wired into `scripts/scope_policy.py` so `deny-structured` mode now
  actually denies an out-of-scope structured write instead of only
  classifying it, and dotfiles like `.env` are preserved exactly rather
  than string-stripped (STORY-014).

### Fixed

- `docs/threat-model.md` had lost the `## Never re-executes the command
  under test` section header during the STORY-011 merge, orphaning that
  section's body text at the end of the file with no heading. Restored;
  no policy semantics changed.

### Added (STORY-008)

- `scripts/active_state.py`: `/agentforge:prepare-work <id>` implemented
  end to end — resolves the configured work item (STORY-006), checks
  every blocker is closed (or is explicitly, visibly overridden by the
  user), checks the eight-section work contract is structurally complete
  (STORY-007), and writes the bounded, gitignored runtime snapshot
  `.agentforge/active-work.json` (schema version, canonical id, title,
  source pointer, content digest, prepared-at timestamp, allowed/
  forbidden paths, verification commands, out-of-scope summary, and
  blocker-override evidence when applicable). Every step is a plan/apply
  pair using the same approval-binding, stale-plan-safe shape
  `scripts/setup.py` already established (STORY-005): nothing is written
  until an explicit `--approved-plan-id` matches a freshly recomputed
  plan.
  - A missing contract section can be filled and, for the `local`
    tracker only, written back to the ticket file after an explicit diff
    approval (`contract-plan`/`contract-apply`); GitHub/GitLab items get
    a proposed diff but no automatic remote write — STORY-006 implemented
    fetch-only adapters, so a remote contract update is always the user's
    own action via the tracker's own edit command.
  - The snapshot is bounded by `context.max_bytes`: an oversized snapshot
    is shrunk by truncating only `title`/`out_of_scope_summary` (identity,
    source, scope, and verification commands are never touched), and is
    rejected outright — never truncated into invalid JSON — if shrinking
    those two fields still does not fit.
  - Re-preparing an unchanged item is a true no-op (content-digest
    equality is checked before ever touching the file); a fetch,
    contract, oversized, or write failure always leaves whatever valid
    snapshot already existed on disk untouched, and a malformed previous
    snapshot never blocks a subsequent successful prepare.
  - `.gitignore` gains exactly one surgical entry,
    `.agentforge/active-work.json`, preserving every other line, comment,
    newline style, and final-newline state; `.agentforge/config.json` is
    never added to it.
  - `--clear` requires explicit confirmation, deletes only
    `.agentforge/active-work.json`, never touches a tracker item, and is
    idempotent when no snapshot exists.
  - The runtime-state destination is resolved through symlinks
    (`scripts/path_policy.py`, STORY-014) and refuses to write or delete
    outside the project root.

### Added (STORY-008, STORY-012)

- `/agentforge:prepare-work` (above) and pre-push commit validation are now
  both integrated into `agentforge-v2`.
- `scripts/git_policy.py` and `templates/git-hooks/pre-push`: real pre-push
  validation of every unique outgoing commit across all pushed refs, not
  just HEAD, against the same tracker-identifier policy STORY-011 enforces
  at commit time. Correctly handles new branches, deleted refs, force
  pushes, multiple refs, and commits duplicated across ranges; a compliant
  HEAD never masks an older noncompliant commit, and deletions are always
  allowed. Installation extends STORY-011's hook-manager detection to
  `pre-push` without overwriting an existing hook (Husky, `pre-commit`,
  `core.hooksPath`, or a custom `pre-push`), chaining to it when one
  exists; a `check-range` CI command validates a supplied base/head range
  outside of a real push. `--no-verify`, a missing local installation, and
  server-side CI/branch protection remain out of this hook's reach and are
  documented as limitations (STORY-012).

### Added (STORY-009)

- `scripts/context.py` and a `SessionStart` entry in `hooks/hooks.json`:
  active work restored on every lifecycle boundary — `startup`, `resume`,
  `clear`, and `compact` all read the same `.agentforge/active-work.json`
  snapshot STORY-008 writes and produce equivalent `additionalContext`
  (identity, source pointer, allowed/forbidden paths, verification
  commands), with no branching on which source triggered the call.
  - Reads only the committed config and the gitignored runtime snapshot —
    no subprocess, no network call (ADR-0005).
  - A missing snapshot is a silent no-op; a malformed one (bad JSON/
    encoding, wrong shape, or a missing identity field) is a visible
    stderr warning, never an uncaught exception, and never written to
    stdout. A "stale" (old `prepared_at`) snapshot is rendered exactly
    like any other valid one — there is no expiry/staleness policy.
  - The emitted context is bounded to the project's configured
    `context.max_bytes`, dropping the out-of-scope summary first, then
    verification commands, then forbidden paths, then allowed paths, in
    that order, before ever touching identity or the source pointer.
  - `scripts/context.py` is also the shared module STORY-010's
    `UserPromptSubmit` handler lands in; this story only implements
    `handle_session_start` and leaves that dispatch as an explicit
    extension point.

### Added (STORY-009, STORY-010)

- STORY-010's `UserPromptSubmit` handler is now integrated alongside
  STORY-009's `SessionStart` handler in the same `scripts/context.py` and
  the same `hooks/hooks.json`. Both hooks were built independently in
  parallel worktrees and reconciled during integration: dispatch between
  them is now purely by the `hook_event_name` field every hook payload
  carries (no CLI subcommand), and the runtime-snapshot reader they share
  was unified onto `scripts/active_state.py`'s symlink-safe path
  resolution, closing a gap where STORY-009's original standalone reader
  joined `.agentforge/active-work.json` without going through that
  safety check.
- `UserPromptSubmit` detects the project's configured canonical
  work-item identifier in the submitted prompt (gated by STORY-006's
  identifier-shape classification, so a repository, path, or
  wrong-tracker-shaped token never matches) and injects: the bounded
  active work contract when it matches the current active-work snapshot;
  only the detected id, the current active id (or "none"), and a
  `/agentforge:prepare-work <id>` instruction when it does not; or an
  explicit ambiguity report when more than one distinct identifier is
  detected in one prompt. Version strings, dates, and line-number
  references are never false positives. Never fetches remote content or
  shells out, even under a github/gitlab tracker. Turn-level
  de-duplication is documented as a known, accepted limitation — the
  hook payload carries no stable per-turn key, only a session-wide one
  that would suppress re-injection for too long.

### Added (STORY-018)

- Codex parity, reusing the same Python policy modules and fixtures
  rather than a second implementation: `tests/test_cross_harness_hooks.py`
  feeds byte-distinct Claude-shaped and Codex-shaped payloads through the
  real `scripts/context.py`/`scripts/scope_policy.py` handlers and asserts
  identical behavior, including with `CLAUDE_PLUGIN_ROOT`/`PLUGIN_ROOT`
  and their `*_DATA` counterparts stripped from the environment — a static
  check also confirms neither module contains `os.environ`/`os.getenv` at
  all. `tests/test_codex_packaging.py` covers the Codex-side packaging.
- `skills/{setup,prepare-work,work-contract,reconcile-docs,migration-safety}/agents/openai.yaml`:
  per-skill Codex invocation policy (`policy.allow_implicit_invocation`),
  one file per skill directory rather than a single top-level file —
  verified against current Codex skill-discovery documentation
  (`https://learn.chatgpt.com/docs/build-skills`) rather than assumed; a
  test pins that no stray top-level `agents/openai.yaml` was also added.
- `templates/codex/agents/independent-reviewer.toml` and `verifier.toml`:
  STORY-017's two capability agents, ported to Codex's TOML custom-agent
  format (`https://learn.chatgpt.com/docs/agent-configuration/subagents`).
- `templates/codex/hooks.json`: corrected `"Stop"` to `"SessionEnd"` for
  the session-record hook — the old mapping was the exact per-turn-`Stop`
  anti-pattern the execution plan explicitly warns against now that
  current Codex has a real `SessionEnd` event
  (`https://learn.chatgpt.com/docs/hooks`). This is a live scaffolding
  template, not a checksum-frozen fixture; the parallel, byte-frozen
  `examples/codex-minimal/.codex/` tree is deliberately left stale and
  documented as such — migrating generated example projects is STORY-019.
- `docs/codex-compatibility.md`: the full citation trail for every
  Codex-specific claim above, plus an explicit "Known limitations / open
  questions" section (unconfirmed `agent_type`-equivalent attribution
  under Codex custom agents, `PermissionRequest` deliberately not wired,
  no single canonical `sandbox_mode` enumeration, Codex's coarser sandbox
  granularity versus Claude's per-tool grants, and that AgentForge does
  not yet ship as an installable Codex plugin package).

### Added (STORY-019)

- `scripts/migrate_v1.py` and `skills/migrate-v1/SKILL.md`: a reversible
  migration from `project-bootstrap`'s v1 scaffolds to v2, designed
  against one central risk — irreversible data loss. Nothing is ever
  deleted: superseded content moves to a timestamped
  `.agentforge/migration-archive/<timestamp>/`, and every applied
  migration writes a manifest `migrate_v1.py rollback` can replay exactly
  to restore the previous hook registration and active files.
  - Detects Claude, Codex, and mixed v1 scaffolds and classifies every
    detected artifact into exactly one of `retained`/`transformed`/
    `archived`/`manual_review`/`obsolete` — nothing is left unclassified.
  - v1 stories convert to v2 tracker work items only after an explicit
    preview/approval step, reusing STORY-005's plan/apply
    approval-binding shape rather than a new confirmation mechanism;
    original v1 IDs are preserved in the new item's metadata.
  - v1's constitution/golden-rule content is extracted into the v2
    managed constitution block without overwriting the rest of the
    file's prose; v1 scopes convert to v2 policy modes, with an explicit
    warning wherever a v1 project claimed Bash enforcement it never
    actually had.
  - v1 hooks are disabled only after the new v2 hooks are installed and
    validated — a project is never left with neither hook active.
  - `--dry-run` causes zero filesystem changes; running the migration
    twice on the same project is a true no-op the second time, mirroring
    STORY-008's re-prepare idempotence.
  - `docs/migration-v1-to-v2.md` documents the full artifact-by-artifact
    mapping and the judgment calls behind it, following the same
    conventions as `docs/compatibility.md`/`docs/codex-compatibility.md`.
  - `tests/fixtures/v1_projects/`: original fixtures (minimal Claude,
    minimal Codex, Lagrangia-style, hand-edited, partially installed,
    already-migrated) built from what `examples/` and
    `tests/fixtures/v1/` actually contain, without touching either
    checksum-frozen tree.

### Added (STORY-020)

**v2 is not yet declared stable** — see "Not done" below before reading
this as a release.

- `.github/workflows/ci.yml`: required CI on every push/PR — unit tests
  across a Python (3.10-3.13) × OS (`ubuntu-latest`, `macos-latest`;
  `windows-latest` excluded and documented, since `scripts/git_policy.py`/
  `scripts/setup.py`/`scripts/scope_policy.py` call `os.chmod` and install
  POSIX-shebang Git hooks) matrix, JSON validation (every tracked
  `*.json` except the one intentionally-malformed test fixture), a
  shebang-based shell-syntax check (`install.sh`, the two Git hook
  templates), a `git diff --check` across the PR's merge-base range, and
  `claude plugin validate . --strict`. Verified locally end-to-end
  (every embedded shell snippet run directly against this repository;
  YAML parsed with PyYAML) — live GitHub Actions execution was not
  available in this sandbox to verify.
- `.github/workflows/integration.yml`: the pinned-known-good-vs-latest
  upstream `mattpocock-skills` matrix STORY-020 asks for, wiring
  STORY-003's existing opt-in live mechanism
  (`AGENTFORGE_LIVE_INTEGRATION=1`) into CI rather than duplicating it.
  Categorizes a failure as upstream drift (pinned passes, latest fails)
  or an AgentForge-side/CLI-version regression (pinned itself fails).
  Fixing this to actually run on a stock CI runner surfaced a real,
  previously-undocumented gap: `claude plugin marketplace add owner/repo`
  resolves to an SSH clone that GitHub refuses with no registered key
  even for a public repo (verified directly) — `tests/integration/test_plugin_coexistence.py`'s
  live test classes now add marketplaces by explicit `https://github.com/...`
  URL instead, which clones anonymously; `docs/compatibility.md` carries
  a dated correction of its earlier "unauthenticated SSH" claim.
- `tests/integration/test_plugin_coexistence.py`: refactored
  `LiveMattCoexistenceTests`'s three marketplace-parametrized assertions
  into a shared `MattCoexistenceMixin`, and added
  `PinnedMattCoexistenceTests` — the same assertions run against
  `tests/fixtures/pinned_mattpocock_marketplace/`, a local marketplace
  fixture that resolves the real `mattpocock-skills` plugin at the fixed
  commit `docs/compatibility.md` already recorded as tested-good
  (version 1.2.3, `3cca18b368ae95cdbdebbff572ccafa662551015`), using the
  exact same `{source: url, url, sha}` shape `claude-plugins-official`'s
  own marketplace entry uses — not a fork or vendored copy. Both classes
  verified live in this session: currently green on both legs (no
  upstream drift detected as of 2026-09-18).
- `.github/workflows/plugin-eval.yml`: manual-only (`workflow_dispatch`)
  eval runner, since `claude plugin eval` reported "currently in early
  access" on every invocation in this sandbox — confirmed to be a
  per-account, Anthropic-side enablement with no local settings/env-var
  toggle, not something this story could work around.
- `evals/setup/` (new eval category): setup preserves existing
  `CLAUDE.md`/`AGENTS.md` prose and Matt Pocock's own block, follows a
  plan-then-approve flow rather than claiming files are already written,
  and stops before writing anything when `mattpocock-skills` is missing.
- One "does not fire" (`max: 0`, `tool_used`) grader added per skill that
  previously had only a positive `skill-fires.md` (`min: 1`) indicator:
  `setup/unrelated-question-does-not-trigger/`,
  `work-contract/unrelated-question-does-not-trigger/`,
  `reconcile-docs/single-document-no-proposal-does-not-trigger/`, and a
  `skill-does-not-fire.md` grader added to migration-safety's existing
  `ordinary-feature-work/` case. `evals/README.md` documents the full
  category table and the suite's deliberate cost/scope bound.
- `scripts/check_version_sync.py`: verifies `VERSION`,
  `.claude-plugin/plugin.json`'s `"version"`, `CHANGELOG.md`'s most
  recent release heading, and (if ever present) a `"version"` field in
  `.claude-plugin/marketplace.json` all name the same version — reports
  every mismatch found, not just the first. `tests/test_version_sync.py`
  covers the real repository (a regression guard against future desync)
  plus every malformed-input and mismatch shape.
- `docs/release-v2.md`: the consolidated release/README-facing document
  STORY-020 asks for — installation, coexistence, upgrade, uninstall,
  migration rollback, the assurance-mode and compatibility-matrix
  tables, the CI/eval/release-process design, an honest "what actually
  changed for v1 users" compatibility-break list (the plugin rename, the
  post-edit auto-fix removal, the migrated-project `scope.mode`
  downgrade, the un-auto-corrected Codex `Stop`/`SessionEnd` stale
  mapping), and the pilot gate status. Cross-references rather than
  duplicates every prior story's own doc.
- `docs/pilot-report-template.md`: the ready-to-fill pilot report
  structure from STORY-020's acceptance criteria (five required work
  items — feature, bug, refactor, docs-only, migration; baseline-vs-v2
  metrics; a migration-rollback-exercised checklist; a severity-high
  defect log; a Go/No-Go section).
- `README.md`: a short "v2 status" banner pointing at `docs/release-v2.md`.
- Release process decision, documented in `docs/release-v2.md`: plain
  `CHANGELOG.md` + `VERSION` + `plugin.json`, reviewed in the same PR as
  the change and mechanically checked by `check_version_sync.py`, rather
  than adopting Changesets — this is a single-package, single-maintainer
  Python plugin repository, not the multi-package JS monorepo shape
  Changesets is built for.

### Not done (this story's explicit, honest scope limit)

- **The real pilot itself was not run.** STORY-020 requires piloting v2
  on one real Python project across five real work items and recording
  baseline-vs-v2 metrics; that needs real elapsed wall-clock time on a
  real external project and cannot be produced inside one implementation
  session without becoming exactly the fabricated "prompt confidence"
  this story exists to reject. `docs/pilot-report-template.md` is the
  structure; it is unfilled.
  `docs/release-v2.md`'s "Pilot gate" section states this explicitly and
  lists what a human needs to do next.
- **`claude plugin eval . --eval-dir evals` was not executed in this
  session** for the same reason noted above (per-account early-access
  gate) — the new and existing eval cases are believed correct against
  the documented case/grader schema but unverified by an actual run.
- **v2.0.0 is not released.** `VERSION` and `.claude-plugin/plugin.json`
  remain `2.0.0-dev`; this section is itself evidence for, not a
  declaration of, the release.
- **Live GitHub Actions execution of the three new workflows was not
  verified** — only local execution of each step's underlying logic, per
  `docs/release-v2.md`'s "Continuous integration" section.

### Fixed

- `tests/test_codex_packaging.py` (STORY-018) imported stdlib `tomllib`
  unconditionally; that module doesn't exist before Python 3.11, so
  every test in the file failed to collect on py3.10 — caught by the
  first real `ci.yml` run on both `ubuntu-latest` and `macos-latest`
  (2026-09-19), exactly the gap local-only verification couldn't catch.
  Falls back to `tomli` when the stdlib import fails; `ci.yml` installs
  it with `pip install "tomli; python_version < '3.11'"` (a no-op on
  3.11+). See `docs/release-v2.md`'s "Continuous integration" section
  for the full account.
