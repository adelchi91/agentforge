# Migrating an AgentForge v1 project to v2

STORY-019 evidence and reference, recorded **2026-09-18**. This document
follows the same conventions as `docs/compatibility.md` and
`docs/codex-compatibility.md`: dated, concrete, limitations stated rather
than glossed over. The executable source of truth is
`scripts/migrate_v1.py`, `tests/test_v1_migration.py`, and
`tests/test_migration_rollback.py`; this document explains the mapping
and the judgment calls behind it.

Central risk this whole story is designed against: **irreversible data
loss.** Nothing described below ever deletes a v1 file. Superseded
content is moved into a timestamped archive
(`.agentforge/migration-archive/<timestamp>/`), and every applied
migration prints exact rollback steps and writes a manifest
`scripts/migrate_v1.py rollback` can replay exactly.

## What "v1" means here

"v1" is `project-bootstrap`'s output before STORY-002 renamed the plugin
to `agentforge` -- the generated scaffolds documented in `examples/README.md`
and frozen byte-for-byte by `tests/fixtures/v1/examples_checksums.json`.
Concretely, any of:

- `.claude/CLAUDE.md` (Claude's constitution -- note this lives **nested
  under `.claude/`**, not at the project root, which is the v2 location)
- `AGENTS.md` at the project root alongside a `.codex/` directory (Codex's
  constitution -- already at the v2 location; an `AGENTS.md` with no
  `.codex/` directory at all is never treated as a v1 artifact)
- `.claude/settings.json` / `.codex/hooks.json` wiring v1's shared hook
  suite (`templates/shared/hooks/*.py` in this repository's own history)
- `.claude/hooks/*.py` / `.codex/hooks/*.py` and their sibling
  `scopes.json`
- `.claude/stories/STORY-*.md` / `.agents/stories/STORY-*.md`
- `.claude/agents/*.md` / `.codex/agents/*.toml` (custom personas)
- `.claude/skills/*/SKILL.md` / `.agents/skills/*/SKILL.md` (project
  -specific skills, unrelated to AgentForge's own)
- `project_context.md`, `roadmap.md` at the project root

A project with **both** a `.claude/`-style and a `.codex/`/`.agents/`
-style scaffold present at once is a **mixed** scaffold; every artifact
kind above is planned independently regardless of which harness(es) a
project uses, so a mixed project's Claude and Codex sides are each
migrated on their own terms.

## The five categories

`scripts/migrate_v1.py` classifies **every** detected v1 artifact into
exactly one of these -- nothing is ever left unclassified:

| Category | Meaning |
|---|---|
| `retained` | Kept exactly where it is, untouched. AgentForge v2 does not own or replace this content. |
| `transformed` | Converted into a v2 equivalent; the original is archived once the new form exists. |
| `archived` | Moved into the timestamped archive, superseded by a v2 mechanism, with nothing further to convert. |
| `manual_review` | A human decision is required; nothing is touched automatically. |
| `obsolete` | Dead weight with a clear v2 replacement and no ongoing function; archived, never deleted. |

## Artifact-by-artifact mapping

| v1 artifact | Category | What happens |
|---|---|---|
| `.claude/CLAUDE.md` (no root `CLAUDE.md`/`AGENTS.md` yet) | `transformed` | Full content copied to a new root `CLAUDE.md`, with the standard AgentForge managed block (`scripts/setup.py`'s `AGENTFORGE_BLOCK`, unchanged) appended, plus a distinctly-marked `<!-- agentforge:migrated-v1-constraints:... -->` block carrying the v1 "Golden Rule"/"Hard Constraints" sections verbatim. The original nested file is then `archived` (never left duplicated). |
| Root `AGENTS.md` alongside `.codex/` | `transformed` | Already at the v2 location -- the AgentForge managed block is appended in place via the same `setup._plan_block_change` logic; every existing line of prose (including v1's "Codex Workflow Rules") is preserved verbatim. No archiving. |
| Both a root constitution file and `.claude/CLAUDE.md` present | `manual_review` | AgentForge never guesses which is authoritative; nothing is touched until you merge them by hand. |
| `.claude/stories/STORY-*.md`, `.agents/stories/STORY-*.md` | `transformed` (or `manual_review`) | Converted to `templates/local-work-item.md`'s eight-section shape under `tracker.local_root` (only when `tracker.type` is `local`; a `github`/`gitlab` project gets `manual_review` instead, since STORY-006's adapters are fetch-only). The original id (`STORY-NNN`) is preserved as the new file's own name/heading, and `migrated_from`/`migrated_v1_agent` front-matter fields record provenance. A v1 `Status: DONE` story gets `state: done` and an explicit note that its completion evidence was not re-captured, rather than a misleading fresh `"Pending"`. The original story file is then `archived`. A pre-existing local work item with the same id and different content is left untouched and reported `manual_review` -- an existing ticket is never overwritten. |
| `.claude/hooks/scopes.json`, `.codex/hooks/scopes.json` | `transformed` (config merge) + `archived` (the file) | Every agent's `allow` list is merged into `.agentforge/config.json`'s `scope.agents` immediately (an existing agent entry is never overwritten); `scope.mode` moves from `"off"` to `"observe"` only when an agent was actually added -- never straight to a blocking mode. The original `scopes.json` **file itself** is archived separately, paired with an explicit warning (see below), and only once `--v2-hooks-validated` is passed -- v1's `pre_tool_use.py` treats a missing `scopes.json` as "nothing configured, unrestricted," so archiving it while that hook is still wired would silently disable v1's own functional scope restriction. |
| `.claude/hooks/*.py`, `.codex/hooks/*.py` (the shared v1 hook suite) | `archived` | Superseded by AgentForge v2's own plugin-level hooks (`hooks/hooks.json` -> `scripts/scope_policy.py`/`scripts/context.py`). **Deferred** (nothing written) until `--v2-hooks-validated` is passed. |
| `.claude/settings.json` | `transformed` | Only the hook-matcher entries whose command references `.claude/hooks/` are removed; every other key (`permissions`, anything else) is left untouched. Deferred until `--v2-hooks-validated`, same as above. |
| `.codex/hooks.json` | `archived` (whole file) or `transformed` | If the file's only content is v1's own hook wiring, the whole file is archived once validated. If something else survives stripping (a hand-added entry), the file is rewritten in place instead, minus only the v1 entries. |
| `.claude/session-log.txt` | `obsolete` | Write-only v1 PreCompact log (`session_start.py` never reads it back -- `tests/test_v1_characterization.py::PreCompactLogNotRestoredTests`); superseded entirely by `.agentforge/active-work.json`. Deferred until hooks are validated (the hook that writes it is still active until then). |
| `.claude/agents/*.md`, `.codex/agents/*.toml` (custom personas) | `retained` | Continue to function as ordinary Claude Code/Codex custom subagents under v2 -- AgentForge does not manage personas. If a persona's checkpoint/"wait for GO" ceremony paragraph is detected, a paired `manual_review` note points at the execution plan's removal of checkpoint ceremony as a default, without auto-editing the persona. |
| `.claude/skills/*/SKILL.md`, `.agents/skills/*/SKILL.md` | `retained` | Ordinary project skills, unrelated to AgentForge's own; untouched. |
| `project_context.md`, `roadmap.md` | `retained` | Domain content AgentForge v2 does not own. |
| An already-v2 project (`.agentforge/config.json` present and valid, no v1 artifacts) | n/a | `plan_migration` returns `"no_change"` immediately -- migrating an already-migrated project is a safe no-op, never an error and never duplicate work. |

## The Bash/scope-enforcement warning

Per the execution plan: *"AgentForge must stop claiming that text-pattern
hooks form a security boundary"* and *"Bash cannot be reliably classified
with regex."* v1's `pre_tool_use.py` docstring explicitly claimed to
enforce three rules -- destructive-command blocking, STORY-XXX commit/push
traceability, and per-agent file scopes -- entirely through Bash regex
matching. `tests/test_v1_characterization.py` demonstrates every one of
these is bypassable today: `git -C <dir> push` escapes the push check, a
STORY-XXX token anywhere on the command line (not just the actual commit
message) satisfies the commit check, a relative `../` path escapes scope
checking, and a malformed JSON payload fails open rather than closed.

**Whenever migration detects a v1 `scopes.json` (which is always paired
with this same shared `pre_tool_use.py` hook), it emits an explicit
warning surfacing exactly this** -- never silently carrying the false
claim forward. v2's `scope.mode` after migration is set to `"observe"`
(report-only, never blocking) specifically so the migrated config never
claims stronger enforcement than the honest grading table in
`docs/plans/agentforge-v2-execution-plan.md` allows; a project must
explicitly opt into `"deny-structured"` or `"strict-agent"` afterward,
having read `docs/threat-model.md` first.

## The Codex `Stop`/`SessionEnd` stale claim

v1's documentation claimed Codex had no `SessionEnd` event, so its
`.codex/hooks.json` registers `session_end.py` on the per-turn `Stop`
event instead. Current Codex documentation contradicts this --
`SessionEnd` is a real, distinct event (`docs/codex-compatibility.md`).
Migration surfaces this as an explicit warning whenever a v1
`.codex/hooks.json` with a `Stop`-mapped hook is detected. AgentForge v2
does not need this wiring at all (it has no `SessionEnd`-triggered
behavior of its own), so no replacement registration is created -- but a
project that keeps using this file's hooks independently of the
AgentForge plugin should change `Stop` to `SessionEnd` by hand.

## Hook gating: never neither, never both unvalidated

Disabling a v1 hook and its registration only happens once
`--v2-hooks-validated` is passed to `apply`. Until then, every
hook-related change (archiving `.claude/hooks/*.py`/`.codex/hooks/*.py`
and their sibling `scopes.json`, stripping `.claude/settings.json`/
`.codex/hooks.json`) is computed and reported with `action: "deferred"`
but **not written** -- the project's v1 hooks stay fully wired and
active, reading exactly the files they always read. This is deliberate:
a project must never be left with neither the old nor the new hook
active, and v1's hooks and v2's plugin-level hooks are never both live
and unvalidated at once (the constitution/story/scope-config-merge
changes apply independently of this gate, since none of those remove
anything a hook still reads -- only `scopes.json`'s own archiving is hook
-gated, not the config merge that reads from it).

`skills/migrate-v1/SKILL.md` operationalizes "v2 hooks validated" as: the
AgentForge v2 plugin is confirmed installed and enabled (`claude plugin
list`) -- v2's hooks are the plugin's own `hooks/hooks.json`, not
something copied per-project, so there is no separate per-project
"install" step to check beyond that.

## Rollback

Every `apply` writes `.agentforge/migration-archive/<timestamp>/manifest.json`
recording, for every change: a modified file's pre-migration backup (or
the fact that it did not exist before, so rollback deletes it), and every
moved file's archive location. `rollback_migration` (CLI: `migrate_v1.py
rollback --project-root . --timestamp <ts>`) replays this manifest
exactly -- restoring every modified file byte-for-byte, deleting every
file the migration created, and moving every archived file back to its
original location. The archive directory itself is never deleted by
rollback (kept as an audit trail). Two migrations applied to the same
project (for example, the ordinary flow followed by a second
`--v2-hooks-validated` pass once the plugin is confirmed) get independent
timestamps and roll back independently of each other --
`tests/test_migration_rollback.py::test_two_sequential_migrations_each_roll_back_independently`.

## Idempotence

Running the migration twice produces the same end state the second time:
every `transformed`/`archived` item that already reached its target state
reports `action: "none"`, and `plan_migration` returns `status:
"no_change"` once nothing is left to write --
`tests/test_v1_migration.py::IdempotenceTests`. This mirrors STORY-008's
"re-preparing unchanged work is a true no-op" pattern.

## Known limitations and judgment calls

- **A mixed scaffold's two constitution files (v1 Codex `AGENTS.md` and
  v1 Claude `.claude/CLAUDE.md`) are always classified independently**,
  never allowing one side's handling to make the other silently vanish
  from the report -- since Codex's `AGENTS.md` is already at the v2 root
  location, its presence means a root constitution file already exists,
  so the Claude side becomes `manual_review` rather than being merged
  into it automatically. Similarly, a mixed scaffold that has the *same*
  `STORY-NNN` id under both `.claude/stories/` and `.agents/stories/`
  (v1 never deduplicated identifiers across harnesses) never lets the
  second one silently overwrite the first's freshly-converted work item
  -- whichever is processed first wins the shared target, and the other
  is reported `manual_review` with its original file left untouched.
- **Remote-tracker projects cannot have their v1 stories converted
  automatically.** STORY-006's GitHub/GitLab adapters are fetch-only; a
  project configured for a remote tracker gets `manual_review` entries
  naming each story that needs to be recreated as a remote issue by hand.
- **A story file that does not carry a recognizable `# STORY-XXX --
  Title` heading is `manual_review`**, never guessed at from surrounding
  content.
- **A v1 story's "Depends on:" field is only converted to a canonical
  `local:STORY-NNN` blocker reference when it contains a recognizable
  `STORY-\d{3,}` token.** Free-text dependency descriptions are carried
  through verbatim, clearly labeled as unverified, rather than silently
  dropped or misrepresented as a validated blocking edge.
- **A checkpoint/"wait for GO" ceremony paragraph inside a custom
  persona, or a "Codex Workflow Rules" section inside `AGENTS.md`, is
  flagged `manual_review`, never auto-edited.** Removing v1's checkpoint
  ceremony (the execution plan's explicit target) requires editing
  arbitrary prose inside a file this migration does not otherwise rewrite
  wholesale; auto-editing prose outside the AgentForge-owned marker
  blocks is exactly the kind of judgment call this story's central risk
  (irreversible data loss from an automated prose edit gone wrong) argues
  against making unsupervised.
- **`scope.mode` moves from `"off"` to `"observe"` when a v1 agent is
  migrated in, never further.** A project that wants `"deny-structured"`
  or `"strict-agent"` enforcement must opt in explicitly after reading
  `docs/threat-model.md` -- migration will never make that call for you.
