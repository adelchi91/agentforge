# AgentForge v2: Claude Code execution plan

Date: 2026-09-15
Target repository: `adelchi91/agentforge`
Upstream workflow plugin: `mattpocock/skills`

## Outcome

Rebuild AgentForge as a thin, cross-harness governance companion to Matt Pocock's engineering skills. Users retain every Matt command unchanged and gain a small set of AgentForge capabilities underneath them:

1. a minimal project constitution and integration configuration;
2. enriched work contracts with scope, exclusions, and runnable verification;
3. active-work context restored at session start, resume, and compaction;
4. commit and push traceability enforced by Git hooks, with Claude/Codex hooks used only for early feedback;
5. optional, explicitly graded scope guardrails;
6. migration-specific safety guidance;
7. tested Claude Code and Codex packaging.

AgentForge must stop claiming that text-pattern hooks form a security boundary. Native sandboxing, permissions, Git hooks, CI, and branch protection own hard enforcement. Lifecycle hooks provide context, UX, audit, and defense in depth.

## Reconciliation with the Claude assessment

The supplied assessment has the right central conclusion: Matt's repository should own the engineering workflow, while AgentForge should retain only a thin governance layer. This plan adopts its recommendations to preserve work-context injection, traceability, model/capability routing, migration safety, and cross-harness support; it also removes the fixed interview, linear story chain, generated persona bureaucracy, checkpoint ceremony, and silent formatter mutations.

Four implementation decisions are deliberately stronger or more current than the supplied answer:

1. **Commit traceability moves to Git, not another Bash regex.** A `commit-msg` hook validates the actual message file, and `pre-push` validates every outgoing commit. Claude/Codex PreToolUse checks may provide early warnings, but are not the source of truth.
2. **Scope enforcement is explicitly graded.** Current Claude Code documentation includes `agent_type` for hooks running within subagents, but the field is optional in general hook inputs. AgentForge must therefore test both cases and may never silently describe missing attribution as enforced scope.
3. **Current Codex has `SessionEnd`.** The v1 documentation's parity caveat is stale. v2 must test the current event set and use post-compaction `SessionStart` to restore active work, rather than preserving the old mapping as doctrine.
4. **Do not uninstall or delete v1 before characterization and migration tests exist.** Preserve a recovery tag/branch, build v2 alongside the legacy assets, and retire them only in STORY-019.

The assessment's recommendation to package AgentForge “as a skill” is interpreted as a full companion plugin containing a few skills plus hooks and optional agents. A skill alone cannot supply the complete lifecycle-hook, Git-hook, configuration, migration, and cross-harness surface.

## Repository strategy: companion, not fork

### Recommended

Keep `adelchi91/agentforge` independent. Install Matt's official plugin alongside it:

```bash
claude plugin install mattpocock-skills@claude-plugins-official --scope user
claude plugin marketplace add adelchi91/agentforge
claude plugin install agentforge@agentforge --scope user
```

Plugin skills are namespaced, so Matt's commands and AgentForge's commands can coexist without collisions. During development, load the AgentForge checkout directly:

```bash
cd /path/to/agentforge
claude --plugin-dir .
```

### Dependency experiment

Current Claude Code manifests support plugin dependencies. STORY-003 tests whether this works reliably across marketplaces:

```json
{
  "dependencies": [
    { "name": "mattpocock-skills", "version": "^1.2.3" }
  ]
}
```

If cross-marketplace resolution works in clean test homes, keep the dependency. If it does not, omit it and make `/agentforge:setup` detect the missing plugin and display the official installation command. Do not copy Matt's skills into AgentForge as a fallback.

### Do not use these strategies

- Do not merge Matt's unrelated Git history into AgentForge.
- Do not vendor or periodically copy his `skills/` directory.
- Do not duplicate or wrap every Matt command.
- Do not maintain an AgentForge fork merely to add governance hooks.
- Do not modify Matt's files to add AgentForge fields.

Fork `mattpocock/skills` only when preparing an upstream contribution. Keep that fork disposable and submit the change back through a pull request.

## Target architecture

```text
agentforge/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── hooks/
│   └── hooks.json
├── scripts/
│   ├── agentforge_hook.py
│   ├── config.py
│   ├── context.py
│   ├── git_policy.py
│   └── scope_policy.py
├── skills/
│   ├── setup/SKILL.md
│   ├── prepare-work/SKILL.md
│   ├── work-contract/SKILL.md
│   ├── reconcile-docs/SKILL.md
│   └── migration-safety/SKILL.md
├── agents/
│   ├── independent-reviewer.md
│   └── verifier.md
├── templates/
│   ├── agentforge-config.json
│   ├── claude-agent-skills-block.md
│   ├── local-work-item.md
│   └── git-hooks/
│       ├── commit-msg
│       └── pre-push
├── tests/
│   ├── fixtures/
│   ├── test_config.py
│   ├── test_context_hooks.py
│   ├── test_git_policy.py
│   ├── test_scope_policy.py
│   ├── test_setup_idempotence.py
│   └── test_plugin_smoke.py
├── evals/
├── docs/
│   ├── architecture.md
│   ├── compatibility.md
│   ├── migration-v1-to-v2.md
│   └── threat-model.md
├── AGENTS.md
├── CLAUDE.md
├── CHANGELOG.md
├── LICENSE
├── README.md
└── pyproject.toml
```

Generated project state:

```text
project/
├── CLAUDE.md or AGENTS.md       # small managed block, never wholesale replacement
├── docs/agents/                 # compatible with Matt's setup conventions
├── .agentforge/
│   ├── config.json              # committed policy/configuration
│   └── active-work.json         # runtime state, gitignored
└── .githooks/agentforge/        # optional Git-level traceability enforcement
```

Plugin scripts stay in `${CLAUDE_PLUGIN_ROOT}`. They are not copied into every project. Project-specific state stays in the project. This prevents old hook code from being frozen across generated repositories.

## Product boundaries

### AgentForge owns

- setup and configuration;
- constitution pointers and hard project constraints;
- work-contract extensions;
- active-work state and context injection;
- optional traceability and scope policies;
- optional custom agents with different runtime capabilities;
- Claude/Codex compatibility and tests.

### Matt's plugin owns

- grilling and clarification;
- domain modeling and ADR creation;
- specifications;
- ticket decomposition and dependency graphs;
- TDD;
- bug diagnosis;
- code review;
- architecture improvement;
- triage, research, prototypes, and handoffs.

### External systems own

- issue status and dependency truth: configured issue tracker;
- immutable commit enforcement: Git hooks and CI;
- merge authorization: branch protection/human approval;
- filesystem/network isolation: native sandbox or container;
- code quality: repository formatter, linter, type checker, test suite, and CI.

## Invocation model

User-invoked AgentForge skills:

- `/agentforge:setup`: configure the companion layer without overwriting the repository.
- `/agentforge:prepare-work <id>`: fetch/validate a work item, enrich missing contract fields, and set active work.

Model-invoked AgentForge skills:

- `work-contract`: reusable rules for scope, verification commands, exclusions, and completion evidence.
- `reconcile-docs`: compare a proposed spec/ticket graph with reference documents and report omissions or contradictions.
- `migration-safety`: apply extract/expand/migrate/validate/contract/delete sequencing only to migrations.

Do not create AgentForge wrappers named `grilling`, `to-spec`, `to-tickets`, `implement`, `tdd`, or `code-review`. Users call Matt's namespaced skills directly.

## Normal user flow

```text
/mattpocock-skills:grill-with-docs
          ↓
/mattpocock-skills:to-spec
          ↓
/mattpocock-skills:to-tickets
          ↓
/agentforge:prepare-work <ticket-id>
          ↓
/mattpocock-skills:implement
          ↓
/mattpocock-skills:code-review
          ↓
Git/CI/human merge controls
```

For a small task, skip spec/tickets and let `/agentforge:prepare-work` create or accept one local work contract. For a very large unclear effort, use Matt's Wayfinder before `to-spec`.

## Policy modes

AgentForge configuration must name its assurance level honestly:

| Mode | Behavior | Claim allowed |
|---|---|---|
| `off` | No hook policy | No enforcement |
| `observe` | Log/report suspicious operations | Observational only |
| `ask` | Request confirmation for ambiguous or risky tool calls | Interactive guardrail |
| `deny-structured` | Deny out-of-scope `Write`/`Edit` calls after canonical path checks | Enforces covered structured tools only |
| `strict-agent` | Custom agent has restricted tools/Bash allowlist plus structured path checks | Strong within documented tool coverage, not an OS boundary |

Never label these modes “secure sandbox.”

## Definition of done for v2

AgentForge v2 is ready when:

- Matt's full promoted plugin remains independently installable and every namespaced command remains callable.
- AgentForge installs and runs without copying Matt's source.
- Setup is idempotent and preserves existing `CLAUDE.md`, `AGENTS.md`, settings, hooks, and user prose.
- All hook paths use `${CLAUDE_PLUGIN_ROOT}` and project state is stored outside the plugin cache.
- Dotfiles and `..` traversal cases are covered by tests.
- Shell-write limitations are documented and tested; no unsupported security claim remains.
- Git commit-msg and pre-push tests cover all configured identifier formats and every outgoing commit.
- Startup/resume/compact context injection is tested with fixtures.
- Claude plugin strict validation, unit tests, scenario evals, and both pinned/current upstream compatibility checks pass in CI.
- Existing AgentForge v1 users have a reversible migration path.

## Execution protocol in Claude Code

1. Create an `agentforge-v2` branch. Tag or branch the current v1 state before restructuring.
2. Copy this plan and `agentforge-v2-user-stories.md` into `docs/plans/` in the AgentForge checkout.
3. Install Matt's official plugin separately and run its setup in the AgentForge repository.
4. Work one story per branch or isolated worktree. Respect the dependency graph in the story backlog.
5. At the start of a story, ask Claude to read the full story and all named source files.
6. Use Matt's `tdd` skill for implementation stories and `code-review` against the story branch's merge base before merging.
7. Record discoveries by updating the plan rather than silently changing scope.
8. Merge only when the story's commands pass and every acceptance criterion has evidence.

Suggested kickoff commands:

```bash
git switch -c agentforge-v2
git tag agentforge-v1.1.0-pre-v2
claude plugin install mattpocock-skills@claude-plugins-official --scope user
claude --plugin-dir .
```

Tagging is intentionally explicit because it creates a recovery point. If the tag already exists, verify it points at the intended v1 commit instead of moving it.

## Dependency graph and delivery slices

```text
001 Baseline and ADRs
 ├─002 v2 plugin skeleton
 │  ├─003 upstream coexistence/dependency proof
 │  ├─004 project config schema
 │  │  ├─005 idempotent setup
 │  │  ├─006 tracker identifiers/adapters
 │  │  └─013 policy engine foundation
 │  ├─016 migration-safety skill
 │  └─017 optional agents
 ├─015 remove silent mutation hooks
006 → 007 work-contract discipline
005 + 006 + 007 → 008 prepare-work/active state
008 → 009 lifecycle context injection
008 → 010 prompt context injection
006 → 011 commit-msg enforcement → 012 pre-push enforcement
013 → 014 graded scope guardrails
003 + 009 + 010 + 012 + 014 + 016 + 017 → 018 Codex parity
005 through 018 → 019 v1 migration
all implementation stories → 020 CI, evals, release and pilot
```

The full acceptance criteria and commands are in [agentforge-v2-user-stories.md](./agentforge-v2-user-stories.md).

## Risks and explicit decisions

1. **Cross-marketplace plugin dependency may not resolve consistently.** STORY-003 proves it in clean homes and retains separate installation as the fallback.
2. **Remote issue fetching inside hooks is slow and fragile.** Hooks never perform network calls. `/agentforge:prepare-work` fetches and snapshots remote work; lifecycle hooks read the snapshot.
3. **Git `core.hooksPath` can conflict with existing hooks.** Installation must detect and refuse to overwrite. Prefer a documented chained dispatcher or CI-only mode when another manager owns hooks.
4. **Bash cannot be reliably classified with regex.** The policy engine never promises complete filesystem scope enforcement for unrestricted Bash.
5. **Matt's skills evolve independently.** Test against a known-good tag/SHA and the current released plugin. Do not pin users forever to the known-good version.
6. **Generated constitution blocks can drift.** Mark only the AgentForge-owned block and update it surgically; never regenerate the entire file.
7. **Issue trackers differ.** Keep identifier parsing and fetching behind small adapters, with local Markdown as the zero-network reference implementation.

## Sources that constrain this plan

- Claude Code plugin skills are namespaced and multiple plugins can be loaded together: [Create plugins](https://code.claude.com/docs/en/plugins).
- Plugin manifests support `dependencies`, hook paths, skill paths, and strict validation: [Plugins reference](https://code.claude.com/docs/en/plugins-reference).
- Claude hook inputs now document `agent_type` for subagent calls, but it remains optional outside that context: [Hooks reference](https://code.claude.com/docs/en/hooks).
- Claude hooks receive JSON on stdin and PreToolUse can deny a call, but matchers select tool names rather than filesystem paths: [Hooks guide](https://code.claude.com/docs/en/hooks-guide).
- Current Codex documentation supports project hooks, post-compaction SessionStart, custom agents, and sandbox modes: [OpenAI Hooks](https://learn.chatgpt.com/docs/hooks), [OpenAI Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
