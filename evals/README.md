# AgentForge plugin evals

Run with `claude plugin eval . --eval-dir evals` (STORY-002/007's
established command; `claude plugin eval` itself is an early-access CLI
feature gated per-account, not a local toggle -- see
`docs/release-v2.md`'s "Plugin evals" section for what that means for
running these in this environment and in CI).

Each case is a `prompt.md` (frontmatter: `name`, `tags`, `plugins`, `runs`,
`max_turns`, `timeout_seconds`, plus the scenario body) and a `graders/`
directory of one `.md` grader per file (`type: regex | llm | tool_used`,
frontmatter fields per type, plus a prose rationale). No `case.yaml` files
are used anywhere in this suite -- keep new cases in the same
`prompt.md` + `graders/*.md` shape.

## Categories and what each proves

| Directory | Story | Proves |
|---|---|---|
| `work-contract/` | STORY-007 | The skill fires for real tickets and writes contracts that use the repository's real verification tooling, reject unsafe targets, and explicitly acknowledge when no automated verification exists -- never fabricated or vague. |
| `reconcile-docs/` | STORY-016 | The skill separates omissions, contradictions, stale assumptions, and intentional exclusions correctly, and does not fire without both a reference document and a proposal to compare it against (STORY-020 addition: `single-document-no-proposal-does-not-trigger/`). |
| `migration-safety/` | STORY-016 | The skill applies extract/expand/migrate/validate/contract/delete sequencing only to real migrations, and does not impose that ceremony -- or fire at all (STORY-020 addition: the `skill-does-not-fire.md` grader in `ordinary-feature-work/`) -- on ordinary brownfield feature work. |
| `setup/` | STORY-020 | The setup skill preserves existing `CLAUDE.md`/`AGENTS.md` prose and Matt Pocock's own block, follows a plan-then-approve flow rather than claiming files are already written, stops before writing anything when `mattpocock-skills` is missing, and does not fire for unrelated requests. |

## Skill triggering / non-triggering coverage (STORY-020)

Before this story, every `skill-fires.md` grader asserted only the
positive case (`min: 1`, marked with-only/ablation) -- there was no case
anywhere in this suite asserting a skill's *absence* for an out-of-scope
prompt. This story adds one `max: 0` "does not fire" grader per skill
that lacked one:

- `setup/unrelated-question-does-not-trigger/`
- `work-contract/unrelated-question-does-not-trigger/`
- `reconcile-docs/single-document-no-proposal-does-not-trigger/`
- `migration-safety/ordinary-feature-work/graders/skill-does-not-fire.md`
  (added to the existing case rather than a new one, since that case
  already sets up the exact "brownfield, additive, nothing replaced"
  scenario needed)

`prepare-work` has no eval cases yet -- deliberately excluded from this
pass. It is a stateful, multi-step skill (tracker resolution, blocker
checks, snapshot writes) that a prose-only eval turn cannot meaningfully
exercise without `Bash`/`Write` tool grants this suite does not currently
request; `tests/test_prepare_work.py` and `tests/test_active_state_atomicity.py`
cover its behavior at the unit level instead. Revisit if/when an eval
case is written with explicit `allowed_tools` and a scaffolded fixture
project.

## Cost/scope bound

This suite is deliberately small: 6 skills' worth of scenarios, not an
exhaustive cross-product of every skill against every possible prompt
shape. Each case runs 3 times (`runs: 3`) against the configured judge
model. Adding cases has a real, ongoing per-run cost -- keep additions
targeted at a specific, currently-unproven behavior claim rather than
broad coverage for its own sake.
