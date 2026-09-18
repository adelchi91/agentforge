# Compatibility: AgentForge alongside mattpocock-skills

STORY-003 evidence, recorded **2026-09-16** against `claude` CLI
**2.1.239**. Where a scenario needed the real
`mattpocock-skills@claude-plugins-official` plugin, the tested pin was
**version 1.2.3**, marketplace-pinned at commit
`3cca18b368ae95cdbdebbff572ccafa662551015` of
`https://github.com/mattpocock/skills.git`. This is compatibility
evidence for that specific date/CLI/upstream-version combination, not a
vendored copy or a permanent pin — see "Known limitations" below for when
to re-run it.

Every command ran in a throwaway `CLAUDE_CONFIG_DIR` created under this
machine's `/private/tmp` scratch area for this session and deleted
afterward — never the real user configuration. Marketplace `add`
operations that reached GitHub used public, unauthenticated
`git@github.com:...` SSH clones; no credential material was read from or
written into any isolated config.

> **STORY-020 correction (2026-09-18):** that SSH-clone claim was only
> true because the machine that recorded this evidence happened to have a
> GitHub-registered SSH key. Verified directly (pointing `GIT_SSH_COMMAND`
> at an identity-less config): `claude plugin marketplace add owner/repo`
> resolves to a `git@github.com:owner/repo.git` clone, and GitHub refuses
> that with "Permission denied (publickey)" for a public repo with no
> registered key at all — the opposite of unauthenticated. Passing the
> explicit `https://github.com/owner/repo.git` URL instead clones
> anonymously with no key required. `tests/integration/test_plugin_coexistence.py`'s
> `LiveMattCoexistenceTests` and `PinnedMattCoexistenceTests` now add
> marketplaces by explicit HTTPS URL for exactly this reason — it is what
> makes them runnable on a stock GitHub Actions runner
> (`.github/workflows/integration.yml`), which has no SSH key provisioned
> by default. This page's own transcripts below still show the shorthand
> form as originally run; treat "unauthenticated" in them as "used no
> credentials I supplied," not "works with no SSH key present."

## Two coverage tiers

1. **Offline, deterministic, run by default and in CI.**
   `OfflineCoexistenceTests` and `DependencyMechanismTests` in
   `tests/integration/test_plugin_coexistence.py` exercise every
   dependency-mechanism scenario (unversioned resolution, incompatible
   version, absence) against two small, original fixture marketplaces —
   `tests/fixtures/fake_upstream_marketplace/` and
   `tests/fixtures/fake_dependent_marketplace/` — never the real
   `mattpocock-skills` marketplace entry, never the network. This is what
   `python3 -m unittest tests.integration.test_plugin_coexistence -v`
   (the story's verification command) runs by default.
2. **Opt-in, live, network-dependent.** `LiveMattCoexistenceTests` is the
   only class that installs the real
   `mattpocock-skills@claude-plugins-official` plugin and reproduces the
   real upstream git-tag-resolution failure (see "Version-ranged
   resolution..." below). It needs outbound network access to GitHub and
   is skipped unless `AGENTFORGE_LIVE_INTEGRATION=1` is set, so neither a
   default run nor CI depends on GitHub being reachable. The
   **2026-09-16 / claude 2.1.239 / mattpocock-skills 1.2.3** figures
   throughout this document are that tier's most recent recorded pass;
   re-run `AGENTFORGE_LIVE_INTEGRATION=1 python3 -m unittest
   tests.integration.test_plugin_coexistence.LiveMattCoexistenceTests -v`
   before trusting them again if the CLI or upstream tagging has moved.

Tier 1's fixture-based "incompatible requested version" case
(`DependencyMechanismTests.test_incompatible_version_dependency_fails_install`,
a fabricated `^99.0.0` range) proves the CLI's version-*comparison* logic
deterministically. It is deliberately narrower than the real failure this
document records in "Version-ranged resolution requires upstream git tags
that don't reliably exist" below — that failure is about the specific
tags `mattpocock/skills` has actually published, which only tier 2 can
reproduce against the real repository; a local fixture cannot fabricate
it without just hardcoding the conclusion.

## Dependency decision: **no `dependencies` field**

The plan (`docs/plans/agentforge-v2-execution-plan.md`) proposed testing:

```json
{ "dependencies": [{ "name": "mattpocock-skills", "version": "^1.2.3" }] }
```

This was added to `.claude-plugin/plugin.json`, tested empirically across
several forms, and then **removed**. AgentForge v2 ships with no
`dependencies` field. Evidence:

### 1. There is no auto-install, in any form tested

Every dependency form produced the same result on `claude plugin install
agentforge@agentforge`: the install itself succeeds, but the plugin comes
up as `✘ failed to load` until the user *manually* runs a separate
install command. Nothing auto-installs the dependency. Example
(`{"name": "mattpocock-skills", "version": "^1.2.3"}`, official
marketplace pre-added):

```
$ claude plugin install agentforge@agentforge -y
✔ Successfully installed plugin: agentforge@agentforge (scope: user)

$ claude plugin list
  ❯ agentforge@agentforge
    Status: ✘ failed to load
    Error: Dependency "mattpocock-skills@claude-plugins-official" is not
    installed — run `claude plugin install
    mattpocock-skills@claude-plugins-official`, or check that its
    marketplace is added
```

### 2. Without an explicit `marketplace` field, resolution defaults to the *same* marketplace as the declaring plugin — never cross-marketplace

`{"name": "mattpocock-skills", "version": "^1.2.3"}` (no `marketplace`
key) resolved as `mattpocock-skills@agentforge` — i.e. it looked for Matt's
plugin **inside AgentForge's own marketplace**, which per ADR-0001 never
vendors it and never will. This form can *never* be satisfied:

```
Error: Dependency "mattpocock-skills@agentforge" is not installed —
run `claude plugin install mattpocock-skills@agentforge`, ...
```

This reproduced identically with no `version` key at all. An explicit
`"marketplace": "claude-plugins-official"` field fixes this specific
failure (see form 4 below) — but the plan's proposed shape (bare `name` +
semver `version`) is the one most naturally written, and it is silently
wrong.

### 3. Version-ranged resolution requires upstream git tags that don't reliably exist

With `"marketplace": "claude-plugins-official"` **and** `"version":
"^1.2.3"` set, installing `agentforge` while Matt was *not yet installed*
failed differently:

```
✘ Failed to install plugin "agentforge@agentforge": Dependency
"mattpocock-skills@claude-plugins-official" is not installed — run
`claude plugin install mattpocock-skills@claude-plugins-official` ...
```

But attempting that exact suggested command directly also failed:

```
$ claude plugin install mattpocock-skills@claude-plugins-official -y
✘ Failed to install plugin "mattpocock-skills@claude-plugins-official":
Plugin "mattpocock-skills@claude-plugins-official" has no git tag
satisfying >=1.2.3 <2.0.0-0
```

With **AgentForge's dependency declaration still installed**, this
failure is not scoped to AgentForge — it poisons *any* subsequent install
of `mattpocock-skills@claude-plugins-official` in that config, including
a completely unrelated, unconstrained `claude plugin install
mattpocock-skills@claude-plugins-official -y` with no version argument.
Uninstalling `agentforge` first, then re-running the exact same
unconstrained install command, succeeded immediately and reported
version `1.2.3`. The version constraint was carried globally by
AgentForge's presence in the config, not scoped to AgentForge's own
resolution.

Root cause, confirmed against the real upstream repository
(`git ls-remote --tags https://github.com/mattpocock/skills.git`):
`mattpocock/skills` tagged its `1.0.0` release as both `v1.0.0` and
`mattpocock-skills@1.0.0`, but every release since (`v1.1.0` through the
`v1.2.3` the marketplace currently pins) is tagged only as `vX.Y.Z` — the
`mattpocock-skills@X.Y.Z` naming the installer's git-tag scan appears to
require was dropped after 1.0.0. This is an upstream tagging convention
entirely outside AgentForge's control (plan risk #5: "Matt's skills
evolve independently"), and it means a semver-*range* dependency against
this specific plugin cannot be made reliable by choosing a different
range — the mechanism is the problem, not the number.

A version-mismatch (as opposed to version-*unresolvable*) case gives a
cleaner error and does work correctly when the dependency is already
installed — `{"version": "^99.0.0"}` against an installed `1.2.3`
produces `Requires "mattpocock-skills@claude-plugins-official" ^99.0.0,
installed 1.2.3` and a clean install failure. The comparison logic is
fine; it is *resolution* (finding something to install that satisfies
the range) that is unreliable.

### 4. The one form that "works" still isn't worth shipping

`{"name": "mattpocock-skills", "marketplace": "claude-plugins-official"}`
— explicit marketplace, **no version constraint** — is the only form
tested that behaves sanely: it never auto-installs, but it gives a
correctly-targeted error naming the exact install command, and once Matt
is installed (before or after AgentForge), AgentForge loads successfully
without needing to be reinstalled.

This was rejected anyway, for a product reason rather than a mechanism
reason: declaring *any* dependency makes AgentForge's entire plugin
`✘ failed to load` — zero skills, zero agents, nothing — whenever Matt
isn't installed yet. That contradicts the companion-plugin boundary in
ADR-0001 and the execution plan's fallback design, which both expect
AgentForge to be independently useful (setup, work-contract discipline,
migration-safety) regardless of installation order. A hard load-gate on
a companion plugin is a worse failure mode than a graceful, scoped
message from `/agentforge:setup` — which is what STORY-003 was asked to
build in the dependency's absence, and which does not sacrifice any of
AgentForge's own functionality when Matt is missing.

### Decision

`.claude-plugin/plugin.json` ships with **no `dependencies` field**. Users
install both plugins as two ordinary, independent steps:

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install mattpocock-skills@claude-plugins-official --scope user

claude plugin marketplace add adelchi91/agentforge
claude plugin install agentforge@agentforge --scope user
```

`skills/setup/SKILL.md` implements the presence-check fallback the plan
asked for: it checks `claude plugin list` for an enabled
`mattpocock-skills@...` entry and, if missing, prints the exact command
above and stops before writing any project file. The rest of setup
(inspecting `CLAUDE.md`/`AGENTS.md`/`.agentforge/`, proposing the
`<!-- agentforge:start -->` block) remains STORY-005's placeholder — that
check is the entire STORY-003 scope of `skills/setup/SKILL.md`.

## Legacy rename: `project-bootstrap` → `agentforge`

`marketplace.json`'s `"renames": {"project-bootstrap": "agentforge"}`
field (added in STORY-002) is **discovery/documentation metadata only in
Claude Code 2.1.239. It does not migrate an installed plugin, and it does
not redirect a fresh install of the old name.**

Reproduced on an isolated config, using the real, currently-published
`adelchi91/agentforge` GitHub repository (still `project-bootstrap`
identity on `main` at the time of this test) for the legacy install step,
then repointing that same marketplace name at this checkout (which
carries the rename and the new `agentforge` identity):

```
$ claude plugin marketplace add adelchi91/agentforge
$ claude plugin install project-bootstrap@agentforge -y
✔ Successfully installed plugin: project-bootstrap@agentforge

$ claude plugin marketplace add <path-to-this-checkout>   # same marketplace name: "agentforge"
✔ Successfully added marketplace: agentforge
$ claude plugin marketplace update agentforge
✔ Successfully updated marketplace: agentforge

$ claude plugin list
No plugins installed. Use `claude plugin install` to install a plugin.
```

The previously-installed plugin did not become `agentforge@agentforge` —
it disappeared from `installed_plugins.json` entirely (verified directly:
`{"version": 2, "plugins": {}}`) the moment the marketplace it depends on
stopped listing a plugin named `project-bootstrap`. Its plugin cache
directory (`plugins/cache/agentforge/project-bootstrap/1.1.0/`) is left
on disk, orphaned and unused. Attempting to reinstall the old name
afterward does not get redirected by the `renames` map either:

```
$ claude plugin install project-bootstrap@agentforge -y
✘ Failed to install plugin "project-bootstrap@agentforge": Plugin
"project-bootstrap" not found in marketplace "agentforge". Your local
copy may be out of date — try `claude plugin marketplace update agentforge`.
```

`claude plugin list --available --json` was also checked for any surfaced
alias/rename metadata; none appears. **This is not automatic migration**,
and AgentForge's documentation must not claim it is.

### Reversible manual migration (tested, clean)

Uninstalling the legacy plugin **before** the marketplace is repointed
produces a clean result — no orphaned cache entry, no ambiguity:

```bash
# 1. Remove the old identity first, while its marketplace still resolves it.
claude plugin uninstall project-bootstrap@agentforge -y

# 2. Pull the marketplace's new manifest (once agentforge-v2 is published to
#    adelchi91/agentforge's default branch).
claude plugin marketplace update agentforge

# 3. Install the renamed identity.
claude plugin install agentforge@agentforge -y
```

Verified on an isolated config: this exact three-command sequence, in
this order, produces a single clean `agentforge@agentforge` entry with no
duplicate or orphaned `project-bootstrap` remnant.

**Rollback**, if needed after step 2/3: the marketplace has already been
updated in place, so the old name is no longer resolvable from it. Roll
back by re-adding the marketplace pinned at the pre-v2 recovery tag
(`agentforge-v1.1.0-pre-v2`, created in STORY-001) or commit instead of
the default branch, then reinstalling `project-bootstrap@agentforge`:

```bash
claude plugin marketplace remove agentforge
claude plugin marketplace add adelchi91/agentforge#agentforge-v1.1.0-pre-v2
claude plugin install project-bootstrap@agentforge -y
```

(The `#<ref>` pinning syntax was not itself exercised in this story; if
it is not supported, the equivalent is cloning that tag locally and
adding it as a directory-source marketplace, exactly as this story's own
tests do for `REPO_ROOT`.)

### Duplicate commands during migration

If a user installs the legacy `project-bootstrap@agentforge` *and*
separately loads this checkout via `--plugin-dir .` (or installs
`agentforge@agentforge` before uninstalling the old one), **both sets of
namespaced commands are available at once** — `project-bootstrap:bootstrap`
and `agentforge:setup` side by side — because the two plugin identities
are genuinely different plugins as far as the CLI is concerned; nothing
merges or dedupes them. This is not a name collision (no shared
component name), but it is a real UX duplicate during migration. It was
first observed live during STORY-002 (see that commit message) and is
resolved by following the manual migration steps above, which uninstall
the old identity before installing the new one.

## `--plugin-dir` alongside a marketplace-installed plugin

Not exercised as a live authenticated session in this story — per the
task's safety constraints (prefer auth-free CLI inspection and
deterministic filesystem assertions; an isolated `CLAUDE_CONFIG_DIR` has
no login, and logging one in was out of scope). Evidence instead:

- `claude plugin validate <path> --strict` — which loads and validates
  the exact manifest `--plugin-dir` would load, with no live session —
  passes for this checkout.
- Claude Code's plugin namespacing is driven entirely by each plugin's
  `plugin.json` `"name"` field (`agentforge` here, `mattpocock-skills` for
  Matt's), which is identical whether the plugin reaches the session via
  a marketplace install or `--plugin-dir`. The marketplace-install case
  (this checkout installed via `agentforge@agentforge` alongside a real
  `mattpocock-skills@claude-plugins-official` install, both `enabled`,
  zero shared skill/agent names across AgentForge's 6 skills / 3 agents
  and Matt's 25 skills) is exercised live in
  `LiveMattCoexistenceTests.test_matt_installed_directly_then_agentforge_both_enabled`.
  Since collision-freedom is a property of the two plugins' `name` fields
  and component directories — not of how a session loaded either plugin —
  this result is a valid proxy for `--plugin-dir` loading.
- STORY-002's commit message additionally records a real, live
  `--plugin-dir .` session on this machine (pre-STORY-003) confirming
  zero skill/agent name overlap between `agentforge:*` (loaded via
  `--plugin-dir .`) and `mattpocock-skills:*` (marketplace-installed).
  That is prior, point-in-time evidence, not something re-run in this
  story; treat it as corroborating, not authoritative on its own.

## Scenario summary

| # | Scenario | Result |
|---|---|---|
| 1 | Neither installed | Clean baseline; `claude plugin list` reports no plugins. |
| 2 | Matt installed directly, then AgentForge | Both `enabled`; all 25 Matt skills present; zero name collisions. |
| 3 | AgentForge with proposed dependency declaration | Rejected — see "Dependency decision" above. |
| 4 | Uninstall AgentForge after Matt installed directly | Matt remains installed and `enabled`, unaffected. |
| 5 | Update Matt independently, AgentForge still installed | AgentForge's installed-plugin record is byte-for-byte unchanged. |
| 6 | Incompatible Matt version requested via dependency | Clean, correct version-mismatch error when Matt is already installed (`requires ^99.0.0, installed 1.2.3`); a *resolvable-but-unsatisfied* range and an *unresolvable* range (case 3 above) produce different error shapes — both were observed. |
| 7 | Legacy `project-bootstrap@agentforge`, then rename path | `renames` is metadata-only, not automatic migration (see above). Manual uninstall → marketplace update → install is clean and reversible. |
| 8 | AgentForge via `--plugin-dir .` beside Matt's released plugin | No collision by construction (name-field-driven namespacing); not re-verified live this story — see caveat above. |

## Known limitations

- `claude plugin update <name>` requires a marketplace-qualified id
  (`mattpocock-skills@claude-plugins-official`); the bare name alone
  fails with `Plugin "mattpocock-skills" not found` even when only one
  marketplace provides it. Document the qualified form in README/setup
  guidance.
- Dependency-resolution behavior (all of the above) is specific to Claude
  Code 2.1.239 and to `mattpocock/skills`' current tagging practice.
  Re-run this story's tests before re-attempting a `dependencies` field
  if either the CLI's resolver or Matt's release tagging changes.
- `LiveMattCoexistenceTests` in
  `tests/integration/test_plugin_coexistence.py` needs outbound network
  access to GitHub over SSH and is skipped by default
  (`AGENTFORGE_LIVE_INTEGRATION=1` to opt in); CI environments without
  that access will only run `OfflineCoexistenceTests` and
  `DependencyMechanismTests`.
- Promoted-skill preservation (`promoted_skill_snapshot` in the same
  module) is checked by exact set equality of the plugin's own declared
  skill paths before/after each AgentForge lifecycle operation, plus a
  file-existence check on every path — not a component count. The only
  hardcoded number is a one-line assertion that the currently tested
  mattpocock-skills v1.2.3 pin promotes exactly 25 skills, kept separate
  from the preservation check so a future upstream release that adds or
  removes a skill fails the baseline assertion (which needs updating) but
  not the preservation one (which shouldn't).
