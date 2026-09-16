# AgentForge v2 detailed user stories

These stories are implementation contracts for the plan in `agentforge-v2-execution-plan.md`. Each story should fit one focused Claude Code session. If implementation reveals a larger unit, split the story before coding; do not silently widen it.

## STORY-001 — Freeze v1 behavior and record architectural decisions

**User story:** As the AgentForge maintainer, I want a reproducible v1 baseline and explicit v2 ADRs so that restructuring does not erase working behavior or reopen settled product decisions.

**Depends on:** none

**Scope:** Git metadata; `docs/architecture.md`; `docs/adr/`; `tests/fixtures/v1/`; test-only files. Do not change runtime behavior.

**Implementation requirements:**

- Create an annotated recovery tag for the exact pre-v2 commit, only if it does not already exist.
- Capture the current Claude and Codex example trees as golden fixtures or checksums.
- Add ADRs for: companion-not-fork; one tracker source of truth; skills vs agents vs hooks vs work contracts; hooks are guardrails; no network access inside hooks; no copied runtime hooks; migration safety is domain-specific.
- Add characterization tests for the existing bugs: dotfile normalization, `..` path escape, `git -C ... push`, story token outside the commit message, Bash file writes, malformed JSON fail-open, and PreCompact log not being restored.
- Tests must describe current behavior without blessing unsafe behavior as the v2 contract.

**Acceptance criteria:**

- A documented immutable v1 recovery reference exists.
- Every decision above has an ADR with context, decision, consequences, and rejected alternatives.
- Each known hook weakness has a failing or expected-characterization test.
- No production file behavior changes.

**Verification:**

```bash
git show-ref --tags agentforge-v1.1.0-pre-v2
python3 -m unittest discover -s tests -p 'test_v1_characterization.py' -v
git diff --check
```

## STORY-002 — Create the namespaced companion-plugin skeleton

**User story:** As a Claude Code user, I want AgentForge and Matt's skills to load simultaneously under separate namespaces so that I can use every upstream command without collisions.

**Depends on:** STORY-001

**Scope:** `.claude-plugin/`; new `skills/`, `hooks/`, `scripts/`, `agents/`; package metadata; minimal README installation section. Do not delete legacy files yet.

**Implementation requirements:**

- Rename the plugin identity to `agentforge` while preserving a migration note for `project-bootstrap` users.
- Use standard plugin directories: `skills/`, `agents/`, `hooks/hooks.json`, and `scripts/`.
- Add placeholder `setup` and `prepare-work` skills with unique AgentForge names only.
- Reference scripts through `${CLAUDE_PLUGIN_ROOT}`; never assume scripts were copied into the project.
- Add `CHANGELOG.md` and a single machine-readable version source synchronized with the manifest.
- Keep Matt's skill names absent from AgentForge.

**Acceptance criteria:**

- `claude plugin validate . --strict` succeeds.
- Loading AgentForge and Matt's plugin together reports no component-name collision.
- `/agentforge:setup` and Matt's `/mattpocock-skills:ask-matt` are both discoverable.
- The plugin contains no vendored Matt source.

**Verification:**

```bash
claude plugin validate . --strict
python3 -m unittest tests.test_plugin_smoke -v
rg -n 'name: (grilling|to-spec|to-tickets|implement|tdd|code-review)$' skills && exit 1 || true
git diff --check
```

## STORY-003 — Prove upstream installation and dependency behavior

**User story:** As an installer, I want a verified way to obtain Matt's complete plugin beside AgentForge so that users receive upstream commands without AgentForge owning a fork.

**Depends on:** STORY-002

**Scope:** manifest dependency field; `tests/integration/`; `docs/compatibility.md`; README. Do not modify Matt's repository.

**Implementation requirements:**

- Test dependency resolution from AgentForge's marketplace when `mattpocock-skills` is available from the official marketplace.
- Run tests in isolated temporary Claude configuration homes for: neither installed, Matt already installed, dependency auto-install, AgentForge uninstall, Matt update, and incompatible requested version.
- If cross-marketplace dependency resolution is reliable, retain the dependency with the broadest tested compatible semver range.
- Otherwise remove the dependency and make setup report the exact official install command, then stop before writing project configuration.
- Store a tested upstream version and commit in `docs/compatibility.md`; it is compatibility evidence, not vendored source or a permanent user pin.

**Acceptance criteria:**

- A clean-machine path is automated or documented with exact commands.
- Uninstalling AgentForge does not uninstall a directly installed Matt plugin.
- Updating Matt's plugin does not overwrite AgentForge state.
- All promoted Matt skills remain present.

**Verification:**

```bash
python3 -m unittest tests.integration.test_plugin_coexistence -v
claude plugin validate . --strict
git diff --check
```

## STORY-004 — Define and validate project configuration

**User story:** As a project maintainer, I want a small committed configuration with explicit policy modes so that AgentForge behavior is reviewable and does not depend on generated prompt prose.

**Depends on:** STORY-002

**Scope:** `templates/agentforge-config.json`; `scripts/config.py`; schema/docs/tests.

**Configuration fields:**

- `schema_version`;
- `tracker.type`: `github`, `gitlab`, or `local`;
- `tracker.repository` and local issue root where applicable;
- `identifier.pattern` and examples;
- `context.max_bytes`;
- `traceability.mode`: `off`, `observe`, or `enforce`;
- `scope.mode`: `off`, `observe`, `ask`, `deny-structured`, or `strict-agent`;
- `scope.agents` mapping;
- `migration_policy.enabled`;
- `quality.post_edit`: `off` or `report` only.

**Implementation requirements:**

- Use JSON so hooks need no third-party YAML dependency.
- Validate types, enumerations, required fields, regex compilation, relative project paths, and unsupported schema versions.
- Configuration errors must produce a precise diagnostic. Enforcement paths fail closed; observation paths report and continue.
- Defaults must not silently enable destructive or blocking behavior.

**Acceptance criteria:**

- Valid examples for all three trackers load.
- Unknown fields are either rejected or explicitly preserved according to a documented forward-compatibility rule.
- Invalid regex, absolute local tracker path, traversal path, and unknown policy mode are rejected.
- Default mode is non-destructive and accurately documented.

**Verification:**

```bash
python3 -m unittest tests.test_config -v
python3 -m json.tool templates/agentforge-config.json >/dev/null
git diff --check
```

## STORY-005 — Implement idempotent, non-destructive setup

**User story:** As an existing project owner, I want `/agentforge:setup` to add only AgentForge's configuration and pointers so that my current `CLAUDE.md`, `AGENTS.md`, settings, Matt configuration, and prose survive unchanged.

**Depends on:** STORY-004

**Scope:** `skills/setup/`; setup helper; templates; setup fixtures/tests.

**Implementation requirements:**

- Inspect `CLAUDE.md`, `AGENTS.md`, `docs/agents/`, `.agentforge/`, `.claude/settings*.json`, and existing Git hooks before proposing writes.
- If neither constitution exists, ask which file to create. If one exists, edit that one only.
- Manage a delimited block: `<!-- agentforge:start -->` through `<!-- agentforge:end -->`.
- The block contains short pointers to committed config, tracker/domain docs, and work-contract rules. It must not duplicate Matt's setup block.
- Present an exact file/diff preview and request one approval for the setup transaction.
- A second identical run must produce no diff.
- Never overwrite existing Git hook management; report detected ownership and available integration modes.

**Acceptance criteria:**

- Tests cover empty repo, CLAUDE-only, AGENTS-only, both present, existing Matt block, existing AgentForge block, malformed block, and pre-existing settings/hooks.
- Surrounding user text is byte-for-byte preserved.
- Re-running setup is idempotent.
- Cancellation writes nothing.

**Verification:**

```bash
python3 -m unittest tests.test_setup_idempotence -v
python3 -m unittest tests.test_setup_preservation -v
git diff --check
```

## STORY-006 — Implement tracker identifiers and local adapters

**User story:** As a user working with GitHub, GitLab, or local Markdown, I want AgentForge to resolve one work-item identity consistently so that context, commits, and verification refer to the same unit of work.

**Depends on:** STORY-004

**Scope:** `scripts/work_items.py`; fixtures; adapter tests; tracker documentation.

**Implementation requirements:**

- Define a normalized `WorkItem` record: provider, canonical ID, title, URL/path, body, state, blockers, updated timestamp, and content digest.
- Implement local Markdown resolution first with no network access.
- Implement GitHub and GitLab fetching as explicit setup/skill operations, not hook operations; use configured CLI workflows from `docs/agents/issue-tracker.md`.
- Reject ambiguous bare numbers when the provider is not known.
- Sanitize remote content before serializing it to active state; enforce maximum bytes.
- Return structured errors for missing CLI, authentication, not found, malformed item, and unsupported tracker.

**Acceptance criteria:**

- Local IDs and paths resolve to the same canonical identity.
- GitHub `#123` and GitLab `#123` resolve only under their configured provider.
- Remote failures never corrupt existing active state.
- Unit tests mock all external commands; no network is required.

**Verification:**

```bash
python3 -m unittest tests.test_work_items -v
python3 -m unittest tests.test_tracker_adapters -v
git diff --check
```

## STORY-007 — Add the reusable work-contract discipline

**User story:** As an implementing agent, I want every accepted work item to state behavior, boundaries, executable checks, and exclusions so that “done” is independently verifiable.

**Depends on:** STORY-006

**Scope:** `skills/work-contract/`; `templates/local-work-item.md`; documentation and eval cases.

**Required contract sections:**

- `What to build` in user-observable terms;
- `Blocked by` using canonical work-item identities;
- `Acceptance criteria` with observable outcomes;
- `May touch` and `Must not touch`;
- `Verification commands`, each runnable and mapped to at least one criterion;
- `Out of scope`;
- `Completion evidence` to be filled after execution.

**Implementation requirements:**

- Teach vertical slicing and defer to Matt's `to-tickets` for decomposition.
- Reject prose such as “run the tests” in verification commands.
- Require explicit acknowledgment if no runnable verification exists.
- Do not invent project commands; inspect repository configuration or ask.
- Do not add AgentForge lifecycle statuses.

**Acceptance criteria:**

- The skill can enrich a Matt-generated local ticket without changing its identity or blocking edges.
- The skill can identify missing/unsafe/placeholder commands.
- Eval fixtures include feature, bug, documentation-only, migration, and external-manual-step work.
- No persona or model-routing instructions appear in the skill.

**Verification:**

```bash
python3 -m unittest tests.test_work_contract -v
claude plugin eval . --eval-dir evals/work-contract
git diff --check
```

## STORY-008 — Prepare and snapshot active work

**User story:** As a developer starting a ticket, I want `/agentforge:prepare-work <id>` to validate readiness and save a local snapshot so that later hooks can restore context without network access.

**Depends on:** STORY-005, STORY-006, STORY-007

**Scope:** `skills/prepare-work/`; `.agentforge/active-work.json` schema; helper/tests; gitignore update logic.

**Implementation requirements:**

- Resolve the configured work item and verify blockers are closed or explicitly overridden by the user.
- Check the work contract; propose missing fields and require approval before updating the tracker/local file.
- Save only the normalized, size-bounded snapshot to `.agentforge/active-work.json`.
- Include canonical ID, title, source pointer, digest, fetched-at, allowed/forbidden paths, verification commands, and out-of-scope summary.
- Add only `.agentforge/active-work.json` to `.gitignore`; keep `.agentforge/config.json` committed.
- Support `--clear` behavior through the skill instructions without deleting any tracker item.

**Acceptance criteria:**

- Preparing an unblocked complete item writes valid active state.
- Blocked work stops with named blockers.
- Re-preparing unchanged work is idempotent.
- Fetch/update failure preserves the previous valid snapshot.
- Clear removes runtime state only after confirmation.

**Verification:**

```bash
python3 -m unittest tests.test_prepare_work -v
python3 -m unittest tests.test_active_state_atomicity -v
git diff --check
```

## STORY-009 — Restore active work on lifecycle boundaries

**User story:** As a Claude or Codex user, I want active work context injected after startup, resume, clear, and compaction so that scope and verification survive context resets.

**Depends on:** STORY-008

**Scope:** lifecycle hook entry point; `hooks/hooks.json`; `scripts/context.py`; tests.

**Implementation requirements:**

- Handle `SessionStart` sources `startup`, `resume`, `clear`, and `compact`.
- Read committed config and active snapshot only; perform no network operations.
- Emit concise additional context containing identity, title, source pointer, scope, exclusions, and verification commands.
- Enforce configured byte limits with deterministic truncation that preserves identity and source pointer.
- Treat missing state as a normal no-op; treat malformed state as a visible warning, never an exception traceback.
- Ensure hook stdout contains only the expected protocol response; diagnostics go to stderr.

**Acceptance criteria:**

- All four lifecycle sources produce equivalent relevant context.
- Missing, stale, oversized, and malformed state fixtures are covered.
- The hook completes within 100 ms on fixture data in CI.
- No session log is required to restore state.

**Verification:**

```bash
python3 -m unittest tests.test_context_hooks.SessionStartTests -v
python3 -m unittest tests.test_hook_performance -v
git diff --check
```

## STORY-010 — Inject named work context on prompt submission

**User story:** As a user who mentions a work item in a prompt, I want AgentForge to inject the matching local snapshot or a precise preparation instruction so that the agent does not operate on an unverified assumption.

**Depends on:** STORY-008

**Scope:** UserPromptSubmit handler; identifier parsing; tests.

**Implementation requirements:**

- Detect configured canonical identifiers without matching arbitrary numbers.
- If the identifier matches active state, inject the bounded work contract.
- If it differs, inject only: the detected ID, current active ID, and instruction to run `/agentforge:prepare-work <id>` before editing.
- Never fetch remote content from the hook.
- Handle multiple IDs by reporting the ambiguity; do not select the first silently.
- Avoid re-injecting the same full context repeatedly within a turn if the hook protocol exposes a stable turn/session key.

**Acceptance criteria:**

- Tests cover matching, mismatching, absent, malformed, and multiple identifiers.
- False-positive examples such as versions, dates, and line numbers do not activate the hook.
- Hook output never exceeds the configured context limit.

**Verification:**

```bash
python3 -m unittest tests.test_context_hooks.UserPromptSubmitTests -v
git diff --check
```

## STORY-011 — Enforce commit traceability at the Git layer

**User story:** As a maintainer, I want commits to reference the configured work-item identity even when created outside Claude so that traceability is real rather than dependent on shell-command text.

**Depends on:** STORY-006

**Scope:** `templates/git-hooks/commit-msg`; installer/checker; `scripts/git_policy.py`; tests/docs.

**Implementation requirements:**

- Validate the actual commit message file supplied by Git's `commit-msg` hook.
- Support provider-specific patterns and explicit exempt commit classes such as merge/revert only when configured.
- Detect an existing `core.hooksPath`, Husky, pre-commit framework, or existing `commit-msg`; never overwrite it.
- Provide three installation outcomes: chained installation, documented manual integration, or CI-only enforcement.
- Keep a Claude PreToolUse check only as an early UX warning and label it non-authoritative.
- Avoid accepting an identifier in comments or unrelated shell segments as proof of the commit message.

**Acceptance criteria:**

- Valid and invalid commit-message fixtures behave correctly for all providers.
- `git -C`, aliases, GUI commits, and direct terminal commits are covered by Git-level enforcement.
- Existing hook managers are preserved.
- Bypass instructions and limitations are documented in the threat model.

**Verification:**

```bash
python3 -m unittest tests.test_git_policy.CommitMessageTests -v
python3 -m unittest tests.test_git_hook_installation -v
git diff --check
```

## STORY-012 — Validate every outgoing commit before push

**User story:** As a maintainer, I want every commit being pushed to satisfy traceability rules so that checking only `HEAD` cannot hide noncompliant commits.

**Depends on:** STORY-011

**Scope:** pre-push hook; Git range calculation; tests/docs.

**Implementation requirements:**

- Read pre-push refs from stdin and calculate each outgoing commit range, including new branches and deleted refs.
- Validate every non-exempt outgoing commit subject/body according to configuration.
- Handle multiple refs in one push.
- Fail with a concise list of offending SHAs and subjects.
- Do not block deletion pushes unless another configured policy requires it.
- Add a CI command that validates a supplied base/head range for environments where local Git hooks are optional.

**Acceptance criteria:**

- Tests cover new branch, updated branch, multiple refs, force push input, deletion, merge commit, empty range, and missing remote base.
- A compliant `HEAD` cannot mask an older noncompliant outgoing commit.
- No network is required for unit tests.

**Verification:**

```bash
python3 -m unittest tests.test_git_policy.PrePushTests -v
python3 -m unittest tests.test_git_policy.RangeValidationTests -v
git diff --check
```

## STORY-013 — Replace regex blocklists with a graded command-policy engine

**User story:** As a user, I want risky command handling to be explicit and testable so that AgentForge warns or blocks consistently without pretending to parse arbitrary shell perfectly.

**Depends on:** STORY-004

**Scope:** `scripts/scope_policy.py`; PreToolUse handler; threat model; fixtures/tests.

**Implementation requirements:**

- Separate exact structured-tool policy from Bash heuristics.
- Categorize Bash calls as `known-read`, `known-write`, `known-destructive`, or `ambiguous`.
- Match common Git destructive operations regardless of global options such as `git -C`, while documenting shell indirection limitations.
- In `observe`, log classification. In `ask`, request approval for destructive/ambiguous calls. In strict-agent mode, deny commands outside an explicit agent allowlist.
- Never interpolate command text into another shell command.
- Malformed payloads under a blocking mode must return a clear deny response; observation mode may warn and continue.

**Acceptance criteria:**

- Tests cover `git -C`, option reordering, force-with-lease, reset, clean, branch deletion, restore/checkout, redirection, pipes, command substitution, `python -c`, `tee`, and encoded/indirect commands.
- Documentation states which cases are intentionally ambiguous or unsupported.
- No rule relies on the mere presence of a work-item token elsewhere in the command.

**Verification:**

```bash
python3 -m unittest tests.test_scope_policy.CommandPolicyTests -v
python3 -m unittest tests.test_hook_protocol.PreToolUseTests -v
git diff --check
```

## STORY-014 — Canonicalize paths and expose honest scope modes

**User story:** As a custom-agent user, I want structured file writes checked against canonical allowed roots so that dotfiles work, traversal escapes fail, and unsupported Bash writes are not misrepresented.

**Depends on:** STORY-013

**Scope:** canonical path utilities; structured write enforcement; scope docs/tests.

**Implementation requirements:**

- Resolve project root, target, symlinks, and `..` before comparing path ancestry.
- Preserve leading dot components; never use `lstrip("./")`.
- Reject targets outside the project root and symlinks escaping an allowed root.
- Match exact files separately from allowed directories.
- Apply enforcement only when `agent_type` maps to a configured agent; define explicit behavior for missing/unknown `agent_type` by mode.
- `deny-structured` documentation must state that unrestricted Bash is outside coverage.
- `strict-agent` requires a custom agent definition with restricted Bash/tool declarations.

**Acceptance criteria:**

- `.github/workflows/ci.yml` matches an allowed `.github/workflows/` root.
- `.env` remains `.env`, not `env`.
- `allowed/../../outside`, absolute outside paths, and escaping symlinks are rejected.
- Windows path fixtures are covered even if CI runs on Unix.
- Unknown-agent behavior is tested for every policy mode.

**Verification:**

```bash
python3 -m unittest tests.test_scope_policy.PathPolicyTests -v
python3 -m unittest tests.test_scope_policy.AgentIdentityTests -v
git diff --check
```

## STORY-015 — Remove silent post-edit mutation

**User story:** As a developer using TDD, I want post-edit quality hooks to report findings without silently rewriting files so that red/green causality and the visible diff remain trustworthy.

**Depends on:** STORY-001

**Scope:** PostToolUse hook; quality configuration; docs/tests.

**Implementation requirements:**

- Delete the automatic `ruff --fix` and `eslint --fix` behavior.
- If quality reporting is enabled, identify only the explicit edited path from structured tool input.
- Run repository-declared check commands in non-mutating mode, with a strict timeout.
- Report command, exit status, and bounded output to the agent.
- For patch tools that do not expose a reliable path list, skip with a diagnostic instead of scanning arbitrary text tokens.

**Acceptance criteria:**

- File checksums are identical before and after the quality hook.
- Missing tools, timeouts, nonzero results, multiple edited files, and unknown patch inputs are covered.
- Default configuration does not run a linter on every edit.

**Verification:**

```bash
python3 -m unittest tests.test_quality_hook -v
git diff --check
```

## STORY-016 — Extract document reconciliation and migration safety skills

**User story:** As a planner, I want reusable document reconciliation and migration safety disciplines so that AgentForge preserves its best planning knowledge without retaining the six-step framework.

**Depends on:** STORY-002

**Scope:** `skills/reconcile-docs/`; `skills/migration-safety/`; references/evals.

**Implementation requirements:**

- `reconcile-docs` compares source documents against a proposed spec or ticket graph and reports uncovered requirements, contradictions, stale assumptions, and deliberate exclusions. It does not own interviewing or ticket creation.
- `migration-safety` applies only when the work is a migration. It combines extract/expand/migrate/validate/contract/delete sequencing with an explicit no-delete-before-validation policy.
- Both are model-invoked reusable disciplines, not personas.
- Both use context pointers and avoid copying whole source documents into outputs.
- Neither forces phases onto ordinary feature work.

**Acceptance criteria:**

- Eval cases distinguish migration from ordinary brownfield feature work.
- Reconciliation identifies both an omitted requirement and an intentional exclusion without conflating them.
- Migration deletion cannot be recommended before replacement verification evidence exists.

**Verification:**

```bash
claude plugin eval . --eval-dir evals/reconcile-docs
claude plugin eval . --eval-dir evals/migration-safety
git diff --check
```

## STORY-017 — Replace the default persona roster with optional capability agents

**User story:** As a project owner, I want custom agents only when they provide isolation or distinct capabilities so that I avoid role ceremony while retaining independent verification where valuable.

**Depends on:** STORY-002, STORY-004

**Scope:** `agents/`; agent templates; setup selection; tests/docs.

**Implementation requirements:**

- Remove interviewer, planner, scaffolder, dev, tester, and final-judge as mandatory generated roles.
- Provide at most two bundled optional agents: `independent-reviewer` and `verifier`.
- Reviewer is read-only and optimized for independent evidence; verifier runs only configured verification commands and cannot edit source.
- Do not hardcode dated full model IDs in generated project files. Use supported aliases/capability defaults where available, or inherit unless the user explicitly pins a model.
- Setup explains the concrete benefit and defaults both agents off.
- Agent scope hooks use the frontmatter `name`, which is the documented `agent_type` identity.

**Acceptance criteria:**

- A default setup generates no project-specific persona files.
- Enabling either agent produces a valid definition with distinct tools/permissions.
- Agent tests confirm the names match configured scope identities.
- Documentation explains when a subagent is preferable to a permanent persona.

**Verification:**

```bash
python3 -m unittest tests.test_agents -v
claude plugin validate . --strict
git diff --check
```

## STORY-018 — Provide tested Codex parity without duplicating policy code

**User story:** As a Codex user, I want the same AgentForge work context and policy semantics through Codex-native packaging so that Claude support does not become the only maintained path.

**Depends on:** STORY-003, STORY-009, STORY-010, STORY-012, STORY-014, STORY-016, STORY-017

**Scope:** Codex plugin/skill metadata; `.agents` metadata; Codex hook configuration; compatibility tests/docs.

**Implementation requirements:**

- Reuse the same Python policy modules and fixtures.
- Use current Codex `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PreCompact`, and `SessionEnd` semantics where appropriate; do not map session end to per-turn `Stop` unless explicitly desired.
- Add `agents/openai.yaml` for every AgentForge skill with correct implicit-invocation policy.
- Package promoted skills without copying Matt's repository.
- Document Matt's Codex installation through `npx skills@latest add mattpocock/skills` until his native plugin is available.
- Validate custom agent TOML keys and sandbox modes against current documentation.

**Acceptance criteria:**

- Shared hook fixtures pass against Claude and Codex payload shapes.
- Platform-specific protocol output has golden tests.
- No Claude-only path or environment variable is required by shared logic.
- Codex limitations are explicit and current.

**Verification:**

```bash
python3 -m unittest tests.test_cross_harness_hooks -v
python3 -m unittest tests.test_codex_packaging -v
git diff --check
```

## STORY-019 — Migrate existing AgentForge v1 projects safely

**User story:** As an existing AgentForge user, I want a reversible migration that preserves my constitution, stories, scopes, and custom agents so that adopting v2 does not destroy project knowledge.

**Depends on:** STORY-005 through STORY-018

**Scope:** migration skill/script; mapping docs; fixtures/tests. Never delete v1 files automatically.

**Implementation requirements:**

- Detect v1 Claude, Codex, and mixed scaffolds.
- Produce a migration report mapping each v1 artifact to: retained, transformed, archived, manual review, or obsolete.
- Convert active stories to configured tracker work items only after preview/approval; preserve IDs in metadata where possible.
- Extract hard constraints and context pointers into the managed constitution block without overwriting other prose.
- Convert scopes into v2 policy modes but warn where v1 claimed unsupported Bash enforcement.
- Disable or unregister copied v1 hooks only after v2 hooks are validated.
- Move obsolete material to a timestamped archive directory rather than deleting it.
- Support dry-run and print exact rollback steps.

**Acceptance criteria:**

- Fixtures cover minimal Claude, minimal Codex, Lagrangia-style, hand-edited, partially installed, and already migrated projects.
- Dry-run causes no filesystem changes.
- Migration is idempotent.
- Rollback restores the previous hook registration and active files.
- No story or custom agent content is lost.

**Verification:**

```bash
python3 -m unittest tests.test_v1_migration -v
python3 -m unittest tests.test_migration_rollback -v
git diff --check
```

## STORY-020 — Add CI, plugin evals, release automation, and a pilot gate

**User story:** As the AgentForge maintainer, I want automated compatibility and behavioral evidence so that v2 releases are based on tested outcomes rather than prompt confidence.

**Depends on:** all previous stories

**Scope:** `.github/workflows/`; evals; release/version scripts; changelog; README; pilot report template.

**Implementation requirements:**

- CI matrix: supported Python versions and operating systems; unit tests; JSON validation; shell syntax; `git diff --check`; strict Claude plugin validation.
- Integration matrix: pinned known-good Matt release and latest available release, with failures categorized as upstream drift or AgentForge regression.
- Add plugin eval cases for setup preservation, work-contract quality, reconciliation, migration classification, and correct skill triggering/non-triggering.
- Add semantic version synchronization and Changesets or an equivalently reviewable release process.
- Document threat model, assurance modes, compatibility matrix, installation, coexistence, upgrade, uninstall, and rollback.
- Pilot on one real Python project for at least five work items: feature, bug, refactor, docs-only change, and migration.
- Record baseline vs v2: setup time, human approval count, context loss, scope-policy findings, invalid commits, first-pass test success, review findings, and rework.
- Do not declare v2 stable until there are no unresolved severity-high hook/config defects and the migration rollback has been exercised.

**Acceptance criteria:**

- Required CI passes from a clean checkout.
- Plugin eval results and known variance are published with the release candidate.
- Both Matt-only and Matt+AgentForge flows remain usable.
- The pilot report supports or falsifies the claimed value of each retained AgentForge feature.
- v2.0.0 release notes list removed v1 ceremony and all compatibility breaks.

**Verification:**

```bash
python3 -m unittest discover -s tests -v
claude plugin validate . --strict
claude plugin eval . --eval-dir evals
python3 scripts/check_version_sync.py
git diff --check
```

## Per-story Claude Code prompt

Use this prompt at the beginning of each implementation session:

```text
Implement STORY-XXX from docs/plans/agentforge-v2-user-stories.md.

Before editing:
1. Read docs/plans/agentforge-v2-execution-plan.md in full.
2. Read STORY-XXX and every file it names.
3. Inspect the current repository state and existing user changes.
4. State any discrepancy between the story and the repository.
5. Use the mattpocock-skills TDD discipline for implementation work.

Stay within the story scope. Do not modify mattpocock/skills or vendor its files.
Do not widen the story silently; propose a split if it cannot fit one session.
Run every verification command in the story. Then run the mattpocock-skills
code-review skill against this branch's merge base and fix confirmed findings.
Report acceptance-criterion evidence, commands and exit codes, changed files,
remaining risks, and the next unblocked story. Do not merge or push unless I ask.
```
