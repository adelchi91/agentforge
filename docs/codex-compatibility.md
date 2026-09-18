# Compatibility: AgentForge on Codex

STORY-018 evidence, recorded **2026-09-17/18**. Every Codex-specific claim
in this document was checked against the current Codex documentation via
WebFetch (quoted URLs below) rather than assumed from training data or from
this repository's own pre-existing (and, in places, stale) v1 docs — see
"Corrections to this repo's own prior Codex claims" below for exactly where
those two disagreed and which one this document trusts. This is the STORY-018
counterpart to `docs/compatibility.md` (STORY-003, Claude/Matt coexistence);
it follows the same conventions — dated evidence, explicit citations,
limitations stated rather than glossed over.

## What "Codex parity" means here

STORY-018 does not duplicate AgentForge's policy logic for Codex. Every
behavior below is produced by the exact same Python modules Claude Code's
`hooks/hooks.json` already wires — `scripts/context.py` (STORY-009/010) and
`scripts/scope_policy.py` (STORY-013/014) — fed a Codex-shaped hook payload
instead of a Claude-shaped one. `tests/test_cross_harness_hooks.py` proves
this behaviorally (same input fields, same output, for both payload shapes);
there is no second, Codex-specific implementation of any policy decision
anywhere in this story's diff.

## Sources consulted

Primary, current Codex documentation, each fetched and read in full on
**2026-09-17**:

1. **Hooks** — <https://learn.chatgpt.com/docs/hooks> (canonical page;
   `https://developers.openai.com/codex/hooks` 308-redirects here). Hook
   event names, payload/response shapes, the `hooks.json` structure, and
   the `PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT` environment variables.
2. **Subagents / custom agents** —
   <https://learn.chatgpt.com/docs/agent-configuration/subagents>
   (`https://developers.openai.com/codex/subagents` redirects here). Custom
   -agent TOML file location, required/optional keys, `sandbox_mode`.
3. **Build skills** — <https://learn.chatgpt.com/docs/build-skills>
   (`https://developers.openai.com/codex/skills` redirects here). Skill
   directory layout, discovery-path priority, implicit vs. explicit
   invocation, and the `agents/openai.yaml` per-skill policy file.
4. **Plugins** — <https://developers.openai.com/codex/plugins/build>. What a
   Codex "plugin" package is, its manifest, `PLUGIN_ROOT`/`PLUGIN_DATA`
   resolution, and its marketplace/distribution model.
5. **Matt Pocock's own installation instructions** for `mattpocock/skills`
   (via WebSearch, not a Codex-vendor page — this claim is about Matt's
   repository, not about Codex itself): `github.com/mattpocock/skills`'s
   `README.md` and `.agents/install-block.md`, corroborated by
   `deepwiki.com/mattpocock/skills` and `aihero.dev`. All agree the
   supported command is `npx skills@latest add mattpocock/skills`, which
   then interactively asks which coding agents to target (Claude Code,
   Cursor, Codex, …). **This confirms the exact command this repository's
   plan already names is still accurate — no change needed.**

Every fact below is attributed to one of these five; anything current
documentation did not confirm is called out explicitly under "Known
limitations / open questions," not guessed.

## Hook events: current names, shapes, and what AgentForge wires

Per source 1, Codex's current hook event set (fetched 2026-09-17):

| Event | Fires when | Can block | Key event-specific fields |
|---|---|---|---|
| `SessionStart` | session begins (`startup`\|`resume`\|`clear`\|`compact`) | yes (`continue: false`) | `source` |
| `SessionEnd` | session archived/closed, or exits, or ~30 min idle | no (advisory) | `reason` |
| `SubagentStart` | a subagent spawns | no (parsed, ignored) | `agent_type`, `agent_id` |
| `SubagentStop` | a subagent completes | yes | `agent_type`, `agent_id`, `agent_transcript_path` |
| `PreToolUse` | before a tool executes (Bash, `apply_patch`, MCP) | yes (deny/allow/rewrite) | `tool_name`, `tool_input`, `tool_use_id` |
| `PermissionRequest` | before an approval prompt | yes (allow/deny) | `tool_name`, `tool_input` |
| `PostToolUse` | after a tool produces output | yes | `tool_name`, `tool_input`, `tool_response`, `tool_use_id` |
| `PreCompact` | before chat compaction | yes | `trigger` (`manual`\|`auto`) |
| `PostCompact` | after chat compaction | yes | `trigger` |
| `UserPromptSubmit` | user submits a prompt | yes (deny) | `prompt` |
| `Stop` | one model turn completes | yes | `stop_hook_active`, `last_assistant_message` |
| `Interrupt` | user interrupts an active turn | no (advisory) | `turn_id`, `permission_mode` |

Every payload additionally carries `session_id`, `transcript_path`, `cwd`,
`hook_event_name`, `model`, and `permission_mode`; turn-scoped events add
`turn_id`. This is a superset of what a Claude Code payload carries for the
same event (Claude's payloads omit `model`/`permission_mode`/
`transcript_path`/`tool_use_id`/`turn_id`) — `tests/test_cross_harness_hooks.py`
builds both shapes explicitly and asserts AgentForge's shared logic ignores
the Codex-only fields it does not need.

### What AgentForge wires, and why

- **`SessionStart`** → `scripts/context.py` (STORY-009). Codex's `source`
  enum is exactly `startup|resume|clear|compact`, the same four values
  STORY-009 already requires equivalent context for — no branching needed,
  and `tests/test_cross_harness_hooks.py::SessionStartCrossHarnessTests`
  proves all four produce identical output through the real module.
- **`UserPromptSubmit`** → `scripts/context.py` (STORY-010). Codex's
  `prompt` field is the same field name and semantics Claude Code uses.
- **`PreToolUse`** → `scripts/scope_policy.py` (STORY-013/014). Codex's
  blocking response shape for this event
  (`hookSpecificOutput.permissionDecision` = `allow`/`deny`, plus
  `permissionDecisionReason`) is documented identically to Claude Code's —
  `scripts/scope_policy.py`'s existing `_response_json` needed no change.
- **`SessionEnd`**: **not wired to anything by this story.** AgentForge has
  no state that needs flushing at session end — `.agentforge/active-work.json`
  is already durably written at `prepare-work` time, not accumulated over a
  session and flushed later. Wiring a no-op handler here would add a moving
  part with nothing to justify it. This is a deliberate absence, not an
  oversight: the important part of "current Codex has SessionEnd" for
  STORY-018 was retiring the *stale claim* it doesn't exist (see
  "Corrections" below), not inventing new session-end behavior AgentForge
  never needed.
- **`PreCompact`**: **not wired.** AgentForge's only compaction-relevant
  behavior is *restoring* context after compaction, which is `SessionStart`
  with `source: "compact"` — already covered above. There is nothing
  AgentForge needs to do *before* compaction happens.
- **`PermissionRequest`**: **not wired**, deliberately. Its payload
  (`tool_name`, `tool_input`) looks compatible with
  `scripts/scope_policy.py`'s existing parsing, but current documentation
  does not confirm its response contract is identical to `PreToolUse`'s in
  every respect, and this story did not find a live Codex session to verify
  it empirically. Recorded under "Known limitations" below rather than
  wired on an unverified assumption.

### `hooks.json` structure

Source 1 documents events nested under a top-level `"hooks"` key — the same
shape Claude Code's `hooks/hooks.json` already uses:

```json
{
  "hooks": {
    "SessionStart": [ { "hooks": [ { "type": "command", "command": "..." } ] } ]
  }
}
```

This repository's `templates/codex/hooks.json` already used this wrapper
shape before this story (it predates STORY-018); `tests/test_codex_packaging.py
::CodexHooksJsonTests::test_has_a_hooks_wrapper_key` pins it going forward.

### Command-path resolution: no confirmed always-on equivalent to `${CLAUDE_PLUGIN_ROOT}`

Source 1 states that for **plugin-bundled** hooks, Codex sets `PLUGIN_ROOT`/
`PLUGIN_DATA`, and — for compatibility with existing plugin hook scripts —
also sets `CLAUDE_PLUGIN_ROOT`/`CLAUDE_PLUGIN_DATA`. Source 4 confirms the
same `PLUGIN_ROOT`/`PLUGIN_DATA` pair for a genuine Codex "plugin" package
and adds that a **repository-local, non-plugin** `.codex/hooks.json` (a bare
project scaffold, not an installed plugin) should instead resolve paths
relative to the Git root (`$(git rev-parse --show-toplevel)/.codex/hooks/...`),
because no `PLUGIN_ROOT`-equivalent variable is defined for that case at all.

**This means an environment-variable path can only be relied on if
AgentForge ships as a genuine, installed Codex plugin package** (source 4's
`plugin.json` + `skills/` bundle format) — which this story does not attempt
to build (see "Known limitations" below). For the concrete artifacts this
story does ship (`templates/codex/agents/*.toml`, `templates/codex/hooks.json`),
neither can assume any environment variable is set, so:

- `scripts/context.py`/`scripts/scope_policy.py` (the shared policy modules)
  never read an environment variable at all — they resolve everything from
  the hook payload's own `cwd` field, which every source above confirms
  every hook payload carries regardless of platform or packaging.
  `tests/test_cross_harness_hooks.py::NoClaudeOnlyEnvironmentDependencyTests`
  proves this behaviorally (both hooks still produce correct output with
  `CLAUDE_PLUGIN_ROOT`/`PLUGIN_ROOT`/their `*_DATA` counterparts stripped
  from the environment) and structurally (neither module's executable
  source contains an `os.environ`/`os.getenv` call at all).
- `scripts/git_policy.py`'s Git-hook installer already solved exactly this
  "cannot rely on an env var that only exists inside a live session" problem
  for `commit-msg`/`pre-push` (STORY-011/012) by baking the plugin's absolute
  `scripts/` directory into the installed hook file at install time. This
  story's `templates/codex/hooks.json` documents (in-file, in its
  `description` field) the same baked-absolute-path approach as the
  supported installation route for a project that is not using AgentForge
  as a Codex plugin package — it does not implement a new installer command
  for it, which is out of this story's stated scope (`skills/setup`'s
  installer flow, not named among STORY-018's scoped files).

## Custom agents: TOML, required/optional keys, `sandbox_mode`

Per source 2 (fetched 2026-09-17):

- **File location**: standalone TOML files, one agent per file, under
  `.codex/agents/` (project-scoped) or `~/.codex/agents/` (personal) —
  **not** a single `agents/openai.yaml` or any YAML file at all. Codex
  identifies the agent by its `name` field, not its filename (matching the
  filename to `name` is only a convention).
- **Required keys**: `name`, `description`, `developer_instructions`.
- **Optional keys**: any other supported `config.toml` key, including
  `model`, `model_reasoning_effort`, `sandbox_mode`, `mcp_servers`,
  `skills.config`.
- **`sandbox_mode`**: source 2 shows `"read-only"` and `"workspace-write"`
  used in examples but does not publish one single exhaustive enum list;
  `"danger-full-access"` is the third value this repository's own
  pre-existing v1 examples and general Codex sandbox terminology use, and
  is included here as "confirmed by repeated documented usage," not as a
  guaranteed-complete enum — see "Known limitations."

STORY-018 adds `templates/codex/agents/independent-reviewer.toml` and
`templates/codex/agents/verifier.toml`, Codex-TOML ports of STORY-017's
`agents/independent-reviewer.md`/`agents/verifier.md`. Both are bundled but
**optional** — nothing in AgentForge writes them into a project
automatically. `tests/test_codex_packaging.py::NewCodexAgentTomlTests`
validates both against the confirmed key set and `sandbox_mode` values
above, and against STORY-017's own "no dated full model id" rule (both
omit `model` entirely rather than guess at whether Codex has an `"inherit"`
sentinel the way Claude Code's `model: inherit` does — current documentation
does not confirm one).

**Known, documented gap**: Claude's `verifier.md` grants exactly
`tools: Read, Bash` — a real, per-tool-name enforcement boundary with no
`Write`/`Edit` at all. Codex's custom-agent schema has no per-tool allow/deny
list; `sandbox_mode` is coarser (whole-filesystem read-only vs.
workspace-write, not "this tool but not that one"). `verifier.toml` uses
`sandbox_mode = "read-only"`, matching this repository's own pre-existing
Codex precedent for the same kind of role
(`examples/codex-minimal/.codex/agents/tester.toml`), but this is a weaker,
coarser boundary than Claude's tool-grant list — documented here rather than
silently presented as equivalent.

**Unconfirmed**: whether a Codex custom agent's `name` appears on that
agent's own outgoing `PreToolUse`/tool-call payloads the way Claude Code's
`agent_type` field does for a subagent call. This matters directly for
`scope_policy.py`'s `strict-agent` mode, which attributes a call to a
configured agent via `agent_type`. None of sources 1–4 confirm which payload
field (if any) would carry this identity for a Codex custom agent's calls.
`tests/test_cross_harness_hooks.py::PreToolUseCrossHarnessTests` proves
`scope_policy.py`'s attribution logic behaves identically **given** an
`agent_type` field is present in a Codex-shaped payload; it cannot prove
Codex actually populates that field for a real custom-agent invocation,
because no source confirms the mechanism. Treat `strict-agent` mode's
Codex-side attribution as unverified until a live Codex session confirms it
— recorded as an open question, not asserted as working.

## Skills: directory layout, discovery, and per-skill invocation policy

Per source 3 (fetched 2026-09-17):

- **Layout**: `<skill-dir>/SKILL.md` (required, YAML frontmatter with
  `name`/`description`), plus optional `scripts/`, `references/`, `assets/`,
  and `agents/openai.yaml`.
- **Discovery priority**: `$CWD/.agents/skills` → `$CWD/../.agents/skills` →
  `$REPO_ROOT/.agents/skills` → `$HOME/.agents/skills` → `/etc/codex/skills`
  → built-in. Duplicate names across scopes are **not merged** — both
  appear.
- **Invocation**: explicit (`$skillname` in Codex) or implicit (the model
  matches the prompt against the skill's `description`). Implicit invocation
  defaults to **enabled**.
- **Per-skill override**: `agents/openai.yaml`, **inside that skill's own
  directory** — quoted example from source 3:

  ```yaml
  policy:
    allow_implicit_invocation: false
  ```

  Setting this to `false` means the skill only activates on an explicit,
  by-name invocation.

**This directly corrects the literal reading of this story's own task
text**, which asked to "Add `agents/openai.yaml` ... covering every
AgentForge skill" — read naturally, that sentence describes one file. The
verified mechanism is the opposite: **one `agents/openai.yaml` per skill
directory**, because the file's location *is* the scope (Codex reads it
relative to each skill it loads, not once globally). STORY-018 ships:

| Skill | `allow_implicit_invocation` | Why |
|---|---|---|
| `skills/setup/agents/openai.yaml` | `false` | User-invoked only (`/agentforge:setup`) — the execution plan's "Invocation model" section lists it as a user command, and it writes project files. |
| `skills/prepare-work/agents/openai.yaml` | `false` | User-invoked only (`/agentforge:prepare-work <id>`) — must never resolve a work item the model merely guessed at from prompt text. |
| `skills/work-contract/agents/openai.yaml` | `true` | Model-invoked reusable discipline per the execution plan. |
| `skills/reconcile-docs/agents/openai.yaml` | `true` | Model-invoked reusable discipline per the execution plan. |
| `skills/migration-safety/agents/openai.yaml` | `true` | Model-invoked, but conditional — the skill's own "classify the work first" step (unchanged by this story) is what keeps implicit invocation from forcing phase ceremony onto ordinary feature work; `allow_implicit_invocation` only controls whether the model may *consider* the skill at all. |

`tests/test_codex_packaging.py::PerSkillInvocationPolicyTests` pins this
table, including an explicit assertion that no stray top-level
`agents/openai.yaml` was (re-)added.

AgentForge's existing `skills/<name>/SKILL.md` layout already matches the
required shape above (source 3's discovery paths are `.agents/skills/*`
project/user directories, but source 4 separately confirms a **Codex
plugin** may bundle skills directly in its own `skills/` directory — the
exact directory name AgentForge already uses as a Claude Code plugin). No
directory restructuring was needed to add the per-skill policy files.

## Matt Pocock's skills on Codex

Confirmed via source 5: `npx skills@latest add mattpocock/skills` is still
the correct, current installation command. It interactively lets the user
choose which of Matt's skills to install and which coding agents to target,
including Codex; his eleven-or-so skills install under `~/.agents/skills/`
and are made available to Codex from there. **No change was needed** to this
repository's existing instruction to use this command until Matt ships a
native Codex plugin.

## Corrections to this repository's own prior Codex claims

This repository's v1 content (`METHODOLOGY.md`, `refs/methodology.md`,
`docs/architecture.md`, `templates/shared/hooks/session_end.py`, and the
`examples/*/session_end.py`/`hooks.json` copies of it) states that "Codex
has no SessionEnd event," so the v1 session-record hook was registered on
Codex's per-turn `Stop` event instead. **Current Codex documentation
contradicts this** — `SessionEnd` exists as a real, distinct Codex event
(see the table above). This is exactly the stale claim the execution plan's
decision #3 already flagged in the abstract ("Current Codex has SessionEnd.
The v1 documentation's parity caveat is stale.") — this story is what
confirmed it concretely against current documentation.

**What this story changed, and what it deliberately left alone:**

- `templates/codex/hooks.json` (the live scaffolding template a fresh v1
  -flow project would get) — **corrected**: `"Stop"` → `"SessionEnd"` for
  the `session_end.py` registration. This is a pure event-name fix; it does
  not change which file gets generated or what that file does.
- `examples/codex-minimal/.codex/hooks.json`, `.codex/hooks/session_end.py`,
  and every file under `examples/lagrangia/`, `examples/minimal/` —
  **left unchanged**. These are frozen v1 characterization fixtures: every
  file in all three example trees is checksummed by
  `tests/fixtures/v1/examples_checksums.json` and asserted byte-for-byte
  unchanged by `tests/test_v1_examples_fixture.py`, specifically so v2
  restructuring work does not silently drift them. Migrating v1 example
  content (including this stale claim) is STORY-019's stated job
  ("Migrate existing AgentForge v1 projects safely"), not STORY-018's —
  this document records the gap explicitly instead of quietly fixing it out
  from under that story's own frozen-baseline contract, or quietly leaving
  it undocumented.
- `METHODOLOGY.md`, `refs/methodology.md`, `docs/architecture.md` (the latter
  is explicitly `docs/architecture.md`'s own header: "AgentForge v1
  architecture (frozen baseline) ... a snapshot, not a design proposal") —
  **left unchanged**, for the same reason: they document the v1 baseline as
  it existed at the `agentforge-v1.1.0-pre-v2` tag, on purpose.

A Codex user reading `templates/codex/hooks.json` today gets the corrected
mapping; a Codex user reading the frozen `examples/codex-minimal/` reference
tree still sees the pre-correction (and now-known-stale) `Stop` mapping,
with this section as the pointer to the fix and the reason it was not
applied there.

## Known limitations / open questions

- **AgentForge does not yet ship as an installable Codex plugin package**
  (source 4's `plugin.json` + bundled `skills/`/MCP format, distributed via
  a Codex marketplace). What this story ships instead — `templates/codex/hooks.json`,
  `templates/codex/agents/*.toml`, and `skills/*/agents/openai.yaml` — is
  project-level scaffolding a Codex project can adopt, consistent with how
  this repository's pre-existing v1 Codex flow already worked. Whether
  AgentForge should additionally package itself as a genuine Codex plugin
  (letting `CLAUDE_PLUGIN_ROOT`/`PLUGIN_ROOT` resolve automatically, per
  source 1's compatibility variable) is an open product decision, not
  resolved by this story — "Agent Plugins" packaging is new enough that only
  one of the five sources consulted here (source 4) describes it in any
  detail.
- **`PermissionRequest` is not wired.** Its payload looks compatible with
  `scripts/scope_policy.py`, but no source consulted here confirms its
  response contract is identical to `PreToolUse`'s deny/allow shape in
  every respect; wiring it on that unconfirmed assumption was rejected.
- **Whether a Codex custom agent's calls carry an `agent_type`-equivalent
  identity field is unconfirmed** (see "Custom agents" above) — this is the
  one open question that most directly affects whether `scope.mode:
  strict-agent` actually attributes calls correctly under Codex, as opposed
  to merely handling the field correctly *if* present.
- **`sandbox_mode`'s complete enum is not published as one list** by source
  2; `read-only`/`workspace-write`/`danger-full-access` are confirmed by
  repeated documented/observed usage (including this repository's own v1
  Codex examples), not by one canonical enumeration.
- **Codex's coarser `sandbox_mode` cannot reproduce Claude's per-tool grant
  list** (see `verifier.toml`'s gap above) — a real, permanent capability
  difference between the two platforms' custom-agent models, not a bug in
  this story's port.
- **No live Codex CLI session was available to this story** to empirically
  confirm any of the above against a running install; every claim here is
  sourced from Codex's own published documentation (sources 1–4) and, for
  Matt's install command only, from his repository's own instructions
  (source 5), fetched on the dates stated, not from executing `codex`
  itself. Documentation for a fast-moving CLI can drift from the shipped
  binary — re-verify before trusting this document if the Codex CLI version
  in use has changed materially since 2026-09-17/18.
