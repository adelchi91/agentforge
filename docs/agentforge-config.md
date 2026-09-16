# AgentForge project configuration (STORY-004)

`.agentforge/config.json` (shipped as `templates/agentforge-config.json`
before a project customizes it) is AgentForge's one committed policy file.
It is validated by `scripts/config.py`, which has no third-party runtime
dependency — plain JSON, stdlib `json`/`re` only, per ADR-0004/ADR-0005's
requirement that hooks stay fast, dependency-free, and honest about what
they enforce.

This document is the schema reference. `scripts/config.py`'s module
docstring and `tests/test_config.py` are the executable source of truth;
this file explains the *why* behind the rules they encode.

## Top-level fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | integer | yes | Must be a version this `config.py` supports (`1` today). See "Schema evolution" below. |
| `tracker` | object | yes | One work-item source of truth (ADR-0002). Shape depends on `tracker.type`. |
| `identifier` | object | yes | The regex AgentForge uses to recognize a work-item id in a prompt/commit (STORY-010, STORY-011). |
| `context` | object | yes | Byte-bound for injected hook context (STORY-009). |
| `traceability` | object | yes | Commit/push traceability policy mode (STORY-011/012). |
| `scope` | object | yes | Structured-write scope policy mode (STORY-013/014). |
| `migration_policy` | object | yes | Whether the migration-safety discipline is active for this project (STORY-016). |
| `quality` | object | yes | Post-edit reporting policy (STORY-015 — never a mutating mode). |

No other top-level field is permitted — see "Forward-compatibility policy" below.

### `tracker`

```json
{ "type": "github", "repository": "owner/repo" }
{ "type": "gitlab", "repository": "group/project" }
{ "type": "local",  "local_root": "docs/work-items" }
```

- `type`: `github`, `gitlab`, or `local`. Exactly one tracker is the
  source of truth per project (ADR-0002) — there is no multi-tracker mode.
- `repository`: required for `github`/`gitlab`, must match `owner/repo`
  (`^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`); **forbidden** for `local`.
- `local_root`: required for `local`, **forbidden** for `github`/`gitlab`.
  Must be a safe relative project path:
  - no absolute path (`/etc/passwd`, a Windows drive letter like `C:\`,
    or a UNC path like `\\server\share`);
  - no `~` home-directory expansion;
  - no `..` traversal component, checked component-by-component after
    splitting on both `/` and `\` (so `docs/../../outside` is rejected
    regardless of platform);
  - a leading dot component (`.agentforge/work-items`) is preserved and
    valid — this validator never uses `str.lstrip("./")`, the exact v1 bug
    characterized in `tests/test_v1_characterization.py` that silently
    turned `.env` into `env`.

### `identifier`

```json
{ "pattern": "^STORY-\\d{3,}$", "examples": ["STORY-001", "STORY-042"] }
```

- `pattern`: a non-empty string compiled with `re.compile`. An invalid
  regex is a validation error naming `identifier.pattern`, not a crash.
- `examples`: a non-empty array of strings, each of which must
  `re.fullmatch` `pattern` — a partial match (e.g. `STORY-001-extra`
  against `^STORY-\d{3,}$`) is rejected, since `fullmatch` semantics are
  what STORY-010's prompt-scanning and STORY-011's commit-message checks
  rely on.

### `context`

```json
{ "max_bytes": 8000 }
```

- `max_bytes`: a positive integer, capped at `MAX_CONTEXT_BYTES_CEILING`
  (65536) in `scripts/config.py`. This bounds how much text a lifecycle
  hook may inject into a session (STORY-009/010); it is a safety ceiling,
  not a performance tuning knob.

### `traceability`

```json
{ "mode": "off" }
```

One of `off`, `observe`, `enforce` (ADR-0004's policy-mode table). Actual
Git-level enforcement is STORY-011/012; this field only records the
configured intent that those later hooks read.

### `scope`

```json
{
  "mode": "off",
  "agents": {
    "verifier": { "allow": ["tests/", "src/"] }
  }
}
```

- `mode`: one of `off`, `observe`, `ask`, `deny-structured`,
  `strict-agent` — the exact five grades from the execution plan's policy
  table. Never call any of these "sandboxing"; see ADR-0004.
- `agents`: a mapping of agent name (`^[A-Za-z][A-Za-z0-9_-]*$`) to
  `{ "allow": [...] }`, where each entry is a safe relative path using the
  same rules as `tracker.local_root` above (no absolute paths, no `..`
  traversal, dotfiles preserved). Empty (`{}`) is valid and is the
  default — scope policy has no effect until a project opts an agent in.

### `migration_policy`

```json
{ "enabled": false }
```

A single boolean. `migration-safety` (STORY-016) is a skill that only
activates when the work at hand is a migration (ADR-0007); this flag does
not itself force any phase structure — it is read by later stories to
decide whether the discipline is even offered for this project.

### `quality`

```json
{ "post_edit": "off" }
```

`post_edit` is restricted to exactly `off` or `report` — **never** a
mutating mode. STORY-015 deleted the v1 behavior of silently running
`ruff --fix`/`eslint --fix` after every edit; the schema itself makes that
mode unrepresentable rather than merely undocumented, so a future config
cannot reintroduce silent mutation by hand-editing the file.

## Defaults are fully non-destructive

`scripts/config.py`'s `DEFAULT_CONFIG` (identical to
`templates/agentforge-config.json`, checked by
`tests/test_config.py::TemplateFileTests`) ships with every policy mode
at its quietest setting:

- `tracker.type = "local"` — zero-network, matches ADR-0002/ADR-0005.
- `traceability.mode = "off"`
- `scope.mode = "off"` (and `scope.agents = {}`)
- `migration_policy.enabled = false`
- `quality.post_edit = "off"`

This satisfies the STORY-004 acceptance criterion that installing
AgentForge's config never silently enables blocking or mutating behavior.
A project opts into `observe`, `ask`, `enforce`, `deny-structured`,
`strict-agent`, or `report` deliberately, field by field.

## Forward-compatibility policy: closed schema

**Unknown fields are rejected, at every level, not silently ignored or
passed through.** `validate_config` calls `_check_unknown_keys` against an
explicit allow-list for the top level and for every nested object
(`tracker`, `identifier`, `context`, `scope.agents.<name>`, etc.).

This was a deliberate choice between two options:

1. **Reject unknown fields (chosen).** A typo (`"tracebility"` instead of
   `"traceability"`) or a field copied from a future version of this
   schema produces an immediate, precise diagnostic naming the exact
   unrecognized field — instead of the field being silently accepted and
   quietly having no effect, which is a much harder class of bug to
   notice in a *committed, reviewed* policy file (the entire point of
   STORY-004 per its user story: "AgentForge behavior is reviewable and
   does not depend on generated prompt prose").
2. **Preserve unknown fields untouched (rejected).** This would let an
   older plugin version tolerate a newer project config, but it means a
   config with a misspelled field name is indistinguishable from a config
   that correctly omitted that field — exactly the silent-failure mode
   the strict option avoids. Since `schema_version` already exists as the
   explicit, visible mechanism for schema evolution, there is no need for
   per-field tolerance on top of it.

Schema evolution happens by bumping `schema_version` and updating
`SUPPORTED_SCHEMA_VERSIONS` together with the validators that understand
the new shape — never by a validator silently accepting a field it does
not recognize under the current version.

## Enforcement vs. observation callers

Two entry points, matching the STORY-004 requirement that "enforcement
callers must receive a hard validation failure" while "observation
callers may report a diagnostic and continue":

- `load_for_enforcement(path) -> dict` raises `ConfigValidationError`
  (carrying the full list of `ConfigIssue`s, not just the first) on any
  parse or schema problem. Use this wherever an invalid config must stop
  the calling operation outright.
- `load_for_observation(path) -> (dict | None, list[ConfigIssue])` never
  raises for a config problem — a missing file, malformed JSON, and every
  schema violation all come back as `(None, issues)` for the caller to
  log and continue past (e.g. by falling back to `DEFAULT_CONFIG`).

`scripts/config.py` can also be run directly for a manual check:

```bash
python3 scripts/config.py .agentforge/config.json --mode enforce   # exit 1 on any issue
python3 scripts/config.py .agentforge/config.json --mode observe   # always exit 0, diagnostics on stderr
```

Every diagnostic (`ConfigIssue.format()`) names only the offending
configuration field path and the offending value taken from the config
file itself — e.g. `tracker.local_root: must be a relative path
(absolute paths are not allowed) (got: '/etc/passwd')`. Diagnostics never
include environment variables, other files' contents, or anything beyond
the config path and the specific field/value that failed.

## What this story does not implement

Per the STORY-004 scope boundary: this module validates configuration
data only. It does not write `.agentforge/config.json` into a project
(STORY-005), fetch anything from a tracker (STORY-006), install any Git
or Claude/Codex hook (STORY-009 through STORY-014), or enforce any policy
against a real tool call. Later stories import `scripts/config.py` and
call `load_for_enforcement`/`load_for_observation` rather than
reimplementing validation.
