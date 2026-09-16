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

The v1 `project-bootstrap` 6-step interview (`/bootstrap`, `/story`,
`/add-agent`, `/project-review`) remains present and unchanged; it is not
removed until a later story retires it (see
`docs/plans/agentforge-v2-execution-plan.md`).
