# AgentForge v1 architecture (frozen baseline)

This document captures the architecture as it exists at the
`agentforge-v1.1.0-pre-v2` tag (same commit as `v1.1.0`). It is a snapshot,
not a design proposal. It exists so that STORY-002 onward has a fixed
reference point to restructure from, and so ADRs in `docs/adr/` can cite
concrete v1 behavior instead of relying on memory of what v1 did.

For the v2 target architecture, see
[`docs/plans/agentforge-v2-execution-plan.md`](plans/agentforge-v2-execution-plan.md).

## Repository shape

The repo is packaged as a single Claude Code plugin (`project-bootstrap`,
marketplace name `agentforge`) plus a parallel Codex skill entry point:

```text
.claude-plugin/{plugin.json, marketplace.json}   plugin + marketplace manifest
commands/{bootstrap,story,add-agent,project-review}.md   Claude slash commands
agents/{interviewer,planner,scaffolder}.md       bootstrap-flow personas
steps/01_documents.md … 06_scaffold.md           the 6-step interview, step by step
refs/{decision_framework,methodology,model_routing}.md   reference material steps point to
templates/
  claude/     Claude-target output templates (CLAUDE.md, settings.json, agent.md, skill.md)
  codex/      Codex-target output templates (AGENTS.md, agent.toml, hooks.json, skill.md)
  shared/
    hooks/    the Python hook suite, shared verbatim by both targets
    story.md  the story template
.agents/skills/project-bootstrap/SKILL.md         Codex-native skill entry point
examples/{lagrangia,minimal,codex-minimal}/       golden reference output examples
install.sh                                        non-plugin installer (curl | bash)
```

`project-bootstrap` (the tool in this repo) is not itself a "bootstrapped
project" — it has no `CLAUDE.md`/`AGENTS.md` constitution at its own root
and no `.claude/hooks/` of its own. It *generates* those artifacts inside
other projects when `/bootstrap` is run there.

## The five mechanisms (as generated into a target project)

| Mechanism | Claude target | Codex target | Nature | Role |
|---|---|---|---|---|
| Constitution | `CLAUDE.md` | `AGENTS.md` | Deterministic | Rules loaded every session |
| Skills | `.claude/skills/` | `.agents/skills/` | Probabilistic | Knowledge chunks loaded on demand |
| Hooks | `.claude/hooks/` + `settings.json` | `.codex/hooks/` + `.codex/hooks.json` | Deterministic | Runtime guardrails |
| Agents | `.claude/agents/*.md` | `.codex/agents/*.toml` | Probabilistic | Personas + model assignment |
| Stories | `.claude/stories/` | `.agents/stories/` | Contract | Units of work + verification |

Full rationale for this split is in `METHODOLOGY.md` (unchanged by this
story) and is not repeated here.

## Hook contract (shared Python, both platforms)

Both platforms invoke the same scripts from `templates/shared/hooks/` with
the hook payload as JSON on stdin; `exit 2` hard-blocks, `exit 0` allows.

| Event | Script | Current behavior |
|---|---|---|
| SessionStart | `session_start.py` | Injects the constitution's Golden Rule and the active story (derived from `git branch --show-current` / latest commit subject) as `additionalContext`. Fires for every source (startup/resume/clear/compact) — there is no source-specific branching. |
| UserPromptSubmit | `user_prompt_submit.py` | If the prompt contains a `STORY-\d{3,}` token, injects that story's `Scope`/`Out of Scope`/`Handoff` sections. |
| PreToolUse | `pre_tool_use.py` | Blocks a fixed regex of destructive Bash (`rm -rf`, force push, `DROP`/`TRUNCATE TABLE`); requires a `STORY-XXX` token somewhere in `git commit`/`git push` invocations; enforces per-agent write scopes from `scopes.json` for `Write`/`Edit`/`MultiEdit`/`NotebookEdit`/`apply_patch` only. |
| PostToolUse | `post_tool_use.py` | Best-effort `ruff --fix` / `eslint --fix` on the touched file after any structured write, if the linter binary is present. Always exits 0; mutates the file it just lints. |
| SubagentStop | `subagent_stop.py` | Appends a `HANDOFF` line (agent + story) to `session-log.txt`. |
| PreCompact | `pre_compact.py` | Appends a `COMPACT` line (story + branch) to `session-log.txt`. |
| SessionEnd (Claude) / Stop (Codex) | `session_end.py` | Appends a `SESSION RECORD` block to `session-log.txt`. Registered on `SessionEnd` for Claude and `Stop` for Codex, so on Codex it fires once per turn rather than once per session. |

`session-log.txt` is append-only. Nothing in this suite ever reads it back
into a session — `session_start.py`'s active-story detection is entirely
independent of it, re-derived from git on every call.

`scopes.json` maps agent name (matched against the hook payload's
`agent_type`) to an `allow` list of path prefixes; an agent with an empty
list is fully write-blocked, and an agent absent from the map is not
scope-restricted at all (including the main session, which is never
scope-restricted).

## Known weaknesses at this baseline

These are characterized, not fixed, by this story — see
`tests/test_v1_characterization.py` for executable proof of each, and
`docs/plans/agentforge-v2-execution-plan.md` for the v2 decisions that
address them (notably STORY-011 through STORY-015).

1. **Dotfile normalization** — `pre_tool_use.normalise()` uses
   `str.lstrip("./")`, which strips leading `.`/`/` characters one at a
   time rather than a `"./"` prefix as a unit, so `.env` normalizes to
   `env` and no longer matches a scope entry for `.env`.
2. **`..` path escape** — the same function never calls `resolve()` on
   relative paths, so `allowed/../../outside/x` still satisfies
   `startswith("allowed/")` and escapes scope checking. Absolute paths
   *are* resolved and correctly rejected — only the relative branch is
   affected.
3. **`git -C ... push`** — `check_bash`'s regexes require `git` and
   `push`/`commit` to be separated only by whitespace
   (`\bgit\s+push\b`), so `git -C <dir> push` and `git -C <dir> commit`
   bypass both the destructive-push check and the STORY-XXX requirement
   entirely.
4. **Story token outside the commit message** — the STORY-XXX check
   scans the whole raw Bash command string, so a token in an unrelated
   flag or filename (e.g. `git commit --file=STORY-001.md -m "..."`)
   satisfies the check even when the actual `-m` message has no story
   reference.
5. **Bash file writes are unscoped** — `check_scope` is only invoked for
   `tool_name` in `{Write, Edit, MultiEdit, NotebookEdit, apply_patch}`
   (plus lowercase Codex variants). A `Bash` command that writes a file
   (`echo x > outside/file`) is never scope-checked, regardless of the
   agent's configured `allow` list.
6. **Malformed JSON fails open** — `load_payload()` catches
   `json.JSONDecodeError` and returns `{}`; `main()` treats an empty
   payload as "nothing to check" and returns `0` (allow). A hook that is
   documented as a hard-block guardrail silently allows the tool call
   when its own input is unparsable.
7. **PreCompact's log is write-only** — `pre_compact.py` records the
   active story and branch to `session-log.txt` before compaction, but
   `session_start.py` never opens that file; it only re-derives state
   from live git commands. If git can no longer supply a story id after
   compaction (branch renamed, detached HEAD, squashed commit), the
   PreCompact record is unrecoverable despite having been faithfully
   written.
8. **Post-edit auto-fix is a silent mutation** — `post_tool_use.py` runs
   `ruff --fix` / `eslint --fix` in place on every touched file, which
   changes file content the agent did not explicitly request and can
   mask red/green causality during TDD. (Documented here for
   completeness; STORY-015 removes it — not in scope for this story.)

None of the above is changed by this story. `tests/test_v1_characterization.py`
proves items 1–7 against the live hook source; item 8 is descriptive only
(no test asserts a linter ran, since ruff/eslint may not be installed in
CI).
