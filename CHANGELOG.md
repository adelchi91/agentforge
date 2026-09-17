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
