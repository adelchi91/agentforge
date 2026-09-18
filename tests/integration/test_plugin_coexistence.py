"""STORY-003 — upstream installation and dependency coexistence tests.

These exercise the real `claude plugin` CLI against a plugin manifest,
never the real user Claude configuration. Every test creates its own
throwaway `CLAUDE_CONFIG_DIR` (a fresh `tempfile.mkdtemp()`) and removes it
in `tearDown`; no test reads or writes `~/.claude`.

Three test classes, split per STORY-003's instruction to separate
network/auth-sensitive CLI integration tests from deterministic ones:

- `OfflineCoexistenceTests` uses only local-directory marketplaces: this
  repository, and `tests/fixtures/fake_upstream_marketplace/` — an
  original, non-vendored fixture plugin that stands in for a real
  companion plugin (e.g. mattpocock-skills) so the *mechanics* of
  coexistence (separate identities, independent install/uninstall/update)
  can be proven without any network access. These run by default in CI.

- `DependencyMechanismTests` uses `tests/fixtures/fake_dependent_marketplace/`
  — two more original fixture plugins that declare a `dependencies` entry
  on `fake-upstream-skills@fake-upstream` — to exercise the two required
  scenarios that are otherwise only documented as manual CLI transcripts
  in `docs/compatibility.md`: a declared dependency that isn't installed
  (no auto-install; a `failed to load`-style error), and a declared
  version range an installed dependency doesn't satisfy. Both are local
  and git-tag-free, so they don't reproduce the git-tag-resolution failure
  documented against the real `mattpocock-skills` (that needs a
  url+sha-sourced marketplace entry, which is why it stays in the live
  class and `docs/compatibility.md` instead). Runs offline, by default.

- `LiveMattCoexistenceTests` additionally clones the real
  `claude-plugins-official` marketplace and installs the real
  `mattpocock-skills` plugin over the network (public, unauthenticated git
  access — no credentials are read or written). This is the only place
  real upstream identity/skill-count facts are asserted. It is skipped
  unless `AGENTFORGE_LIVE_INTEGRATION=1` is set, since network access
  makes it nondeterministic in offline/sandboxed CI.

- `PinnedMattCoexistenceTests` (STORY-020) shares every coexistence
  assertion with `LiveMattCoexistenceTests` via the `MattCoexistenceMixin`
  below, but resolves `mattpocock-skills` from
  `tests/fixtures/pinned_mattpocock_marketplace/` instead of the real
  `claude-plugins-official` marketplace — a local marketplace.json using
  the exact same `{"source": "url", "url": ..., "sha": ...}` shape
  Anthropic's own marketplace entry uses, just naming one fixed,
  previously-verified-good commit (the version 1.2.3 pin recorded in
  `docs/compatibility.md`) instead of whatever that marketplace currently
  points to. This is STORY-020's "pinned known-good Matt release" leg of
  the integration matrix; `LiveMattCoexistenceTests` is the "latest
  available release" leg. Running both and comparing outcomes is the
  categorization mechanism `.github/workflows/integration.yml` uses:
  pinned passes + latest fails → upstream drift (Matt's repository or the
  official marketplace's pointer changed); pinned itself fails → an
  AgentForge-side or Claude-CLI-version regression, since this exact
  upstream state was previously confirmed working. Also opt-in only,
  behind `AGENTFORGE_LIVE_INTEGRATION=1` (it still clones the real
  `mattpocock/skills.git` over the network, just at a fixed commit).

The full manual scenario matrix (8 scenarios, including the legacy
`project-bootstrap` rename path and `--plugin-dir` loading) and the
dependency-mechanism evidence behind STORY-003's decision to ship no
`dependencies` field are recorded in `docs/compatibility.md`; this module
encodes the subset that is worth running as a repeatable regression guard.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_MARKETPLACE = REPO_ROOT / "tests" / "fixtures" / "fake_upstream_marketplace"
DEPENDENT_FIXTURE_MARKETPLACE = REPO_ROOT / "tests" / "fixtures" / "fake_dependent_marketplace"
PINNED_MATT_MARKETPLACE = REPO_ROOT / "tests" / "fixtures" / "pinned_mattpocock_marketplace"

# STORY-020: the version 1.2.3 commit docs/compatibility.md recorded as
# tested-good on 2026-09-16. Kept here (not just in the fixture
# marketplace.json) so PinnedMattCoexistenceTests's docstrings/messages
# can cite it directly. Re-pin deliberately, not automatically, if that
# evidence is ever refreshed against a newer commit.
KNOWN_GOOD_MATT_SHA = "3cca18b368ae95cdbdebbff572ccafa662551015"

CLAUDE_BIN = shutil.which("claude")
LIVE = os.environ.get("AGENTFORGE_LIVE_INTEGRATION") == "1"


def run_claude(config_dir: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return subprocess.run(
        [CLAUDE_BIN, *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def plugin_list(config_dir: Path) -> list[dict]:
    """Returns the parsed array from `claude plugin list --json`.

    Note: `claude plugin list --json` (no `--available`) returns a bare
    JSON array of installed plugins, each with `id` and `enabled` keys —
    a different shape from `--available --json`, which wraps
    `{"installed": [...], "available": [...]}`. This helper only uses the
    bare-array form.
    """
    result = run_claude(config_dir, "plugin", "list", "--json")
    if not result.stdout.strip():
        return []
    return json.loads(result.stdout)


def installed_names(config_dir: Path) -> set[str]:
    return {p["id"] for p in plugin_list(config_dir)}


def by_id(config_dir: Path) -> dict[str, dict]:
    return {p["id"]: p for p in plugin_list(config_dir)}


def load_errors(config_dir: Path, plugin_id: str) -> list[str]:
    """`claude plugin list --json` entries are `enabled: true` even when a
    declared dependency is missing or unsatisfied — the load failure only
    surfaces as a non-empty `errors` array. There is no `status` field."""
    return by_id(config_dir).get(plugin_id, {}).get("errors", [])


def promoted_skill_snapshot(config_dir: Path, plugin_id: str) -> dict[str, Path]:
    """{promoted skill identifier: Path to its SKILL.md}, read directly from
    the plugin's own installed manifest — not from `claude plugin details`
    text output, so this proves the actual promoted skill set, not just a
    component count.

    Resolves the plugin's on-disk root via `installPath` from
    `claude plugin list --json` (not a glob under `plugins/cache/`), so it
    always points at the currently active install, including right after an
    update that bumped the version directory.

    mattpocock-skills' `plugin.json` declares an explicit top-level
    `"skills"` array of configured paths — 25 entries, deliberately
    excluding `skills/deprecated/`, `skills/in-progress/`, and `skills/misc/`
    even though those also contain `SKILL.md` files on disk (37 total).
    That array is the authoritative "promoted" set when present. Plugins
    that instead rely on the `skills/*/SKILL.md` directory convention (this
    repo's own manifest, and the offline test fixtures) have no such array;
    every `skills/*/SKILL.md` counts as promoted for those.

    Returns `{}` if the plugin isn't installed at all, so callers can
    compare an absent-before/absent-after pair as trivially equal.
    """
    entry = by_id(config_dir).get(plugin_id)
    if entry is None:
        return {}
    root = Path(entry["installPath"])
    manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text())

    configured = manifest.get("skills")
    if configured is not None:
        snapshot = {}
        for raw in configured:
            rel = raw[2:] if raw.startswith("./") else raw
            snapshot[rel] = root / rel / "SKILL.md"
        return snapshot

    return {
        skill_md.parent.relative_to(root).as_posix(): skill_md
        for skill_md in root.glob("skills/*/SKILL.md")
    }


def assert_promoted_skills_preserved(
    testcase: unittest.TestCase, before: dict[str, Path], after: dict[str, Path]
) -> None:
    """Exact set equality on promoted skill identifiers, plus a check that
    every skill path the after-snapshot names still exists on disk. Set
    equality (not a count) so an upstream release that adds or removes a
    skill fails loudly here instead of being masked by a >= bound."""
    testcase.assertEqual(set(before), set(after))
    for identifier, path in after.items():
        testcase.assertTrue(path.is_file(), f"{identifier}: {path} no longer exists")


@unittest.skipUnless(CLAUDE_BIN, "claude CLI not found on PATH")
class IsolatedConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.config_dir = Path(tempfile.mkdtemp(prefix="agentforge-story003-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.config_dir, ignore_errors=True)


class OfflineCoexistenceTests(IsolatedConfigTestCase):
    """No network access; both marketplaces are added by local path."""

    def _add_marketplaces(self) -> None:
        r1 = run_claude(self.config_dir, "plugin", "marketplace", "add", str(REPO_ROOT))
        self.assertEqual(r1.returncode, 0, r1.stderr)
        r2 = run_claude(self.config_dir, "plugin", "marketplace", "add", str(FIXTURE_MARKETPLACE))
        self.assertEqual(r2.returncode, 0, r2.stderr)

    def _install_both(self) -> None:
        r1 = run_claude(
            self.config_dir, "plugin", "install", "fake-upstream-skills@fake-upstream", "-y"
        )
        self.assertEqual(r1.returncode, 0, r1.stderr)
        r2 = run_claude(self.config_dir, "plugin", "install", "agentforge@agentforge", "-y")
        self.assertEqual(r2.returncode, 0, r2.stderr)

    # Scenario 1: neither plugin installed.
    def test_neither_plugin_installed_is_the_clean_baseline(self) -> None:
        self._add_marketplaces()
        self.assertEqual(installed_names(self.config_dir), set())

    # Scenario 2: upstream installed directly before AgentForge.
    def test_fake_upstream_installed_directly_before_agentforge(self) -> None:
        self._add_marketplaces()
        self._install_both()

        plugins = by_id(self.config_dir)
        self.assertIn("agentforge@agentforge", plugins)
        self.assertIn("fake-upstream-skills@fake-upstream", plugins)
        self.assertTrue(plugins["agentforge@agentforge"]["enabled"])
        self.assertTrue(plugins["fake-upstream-skills@fake-upstream"]["enabled"])

    # STORY-003 dependency decision, encoded as a regression guard: the
    # shipped manifest declares no `dependencies` field. See
    # docs/compatibility.md for the empirical evidence (git-tag-based
    # version resolution against mattpocock/skills.git is unreliable, and
    # even a working dependency form turns a missing companion plugin into
    # a hard "failed to load" for all of AgentForge rather than the
    # graceful setup-time message the product boundary requires).
    def test_agentforge_installs_without_a_dependency_field(self) -> None:
        manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
        self.assertNotIn(
            "dependencies",
            manifest,
            "AgentForge's manifest should not declare a plugin dependency — "
            "see docs/compatibility.md for why cross-marketplace dependency "
            "resolution was tested and rejected in STORY-003.",
        )

        self._add_marketplaces()
        result = run_claude(self.config_dir, "plugin", "install", "agentforge@agentforge", "-y")
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertTrue(by_id(self.config_dir)["agentforge@agentforge"]["enabled"])

    # Scenario 4: uninstalling AgentForge must not uninstall a directly
    # installed companion plugin.
    def test_uninstalling_agentforge_preserves_directly_installed_upstream_plugin(self) -> None:
        self._add_marketplaces()
        self._install_both()

        before = promoted_skill_snapshot(self.config_dir, "fake-upstream-skills@fake-upstream")

        result = run_claude(self.config_dir, "plugin", "uninstall", "agentforge@agentforge", "-y")
        self.assertEqual(result.returncode, 0, result.stderr)

        names = installed_names(self.config_dir)
        self.assertNotIn("agentforge@agentforge", names)
        self.assertIn("fake-upstream-skills@fake-upstream", names)
        self.assertTrue(by_id(self.config_dir)["fake-upstream-skills@fake-upstream"]["enabled"])

        after = promoted_skill_snapshot(self.config_dir, "fake-upstream-skills@fake-upstream")
        assert_promoted_skills_preserved(self, before, after)

    # Scenario 5: updating the companion plugin independently must not
    # disturb AgentForge's installed state.
    def test_updating_fake_upstream_does_not_disturb_agentforge(self) -> None:
        self._add_marketplaces()
        self._install_both()

        before_agentforge = by_id(self.config_dir)["agentforge@agentforge"]
        before_upstream_skills = promoted_skill_snapshot(
            self.config_dir, "fake-upstream-skills@fake-upstream"
        )

        result = run_claude(
            self.config_dir, "plugin", "update", "fake-upstream-skills@fake-upstream", "-y"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        after_agentforge = by_id(self.config_dir)["agentforge@agentforge"]
        self.assertEqual(before_agentforge, after_agentforge)

        after_upstream_skills = promoted_skill_snapshot(
            self.config_dir, "fake-upstream-skills@fake-upstream"
        )
        assert_promoted_skills_preserved(self, before_upstream_skills, after_upstream_skills)

    # Scenario 8 (static half): skill/agent identifiers never collide.
    # Namespacing is driven by each plugin.json's `name` field, which is
    # identical whether a plugin is loaded via marketplace install or
    # `--plugin-dir` — so this filesystem comparison is a valid proxy for
    # both loading paths (see docs/compatibility.md for the full argument
    # and the live-session evidence already captured in the STORY-002
    # commit).
    def test_no_skill_or_agent_name_collision_between_agentforge_and_fixture_upstream(self) -> None:
        agentforge_name = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())[
            "name"
        ]
        upstream_name = json.loads(
            (FIXTURE_MARKETPLACE / ".claude-plugin" / "plugin.json").read_text()
        )["name"]
        self.assertNotEqual(agentforge_name, upstream_name)

        agentforge_skills = {p.name for p in (REPO_ROOT / "skills").glob("*") if p.is_dir()}
        upstream_skills = {
            p.name for p in (FIXTURE_MARKETPLACE / "skills").glob("*") if p.is_dir()
        }
        self.assertTrue(agentforge_skills.isdisjoint(upstream_skills))

    def test_strict_validate_passes_for_agentforge_manifest(self) -> None:
        result = subprocess.run(
            [CLAUDE_BIN, "plugin", "validate", str(REPO_ROOT), "--strict"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_strict_validate_passes_for_fixture_marketplace(self) -> None:
        result = subprocess.run(
            [CLAUDE_BIN, "plugin", "validate", str(FIXTURE_MARKETPLACE), "--strict"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class DependencyMechanismTests(IsolatedConfigTestCase):
    """Exercises the manifest `dependencies` mechanism itself, offline, via
    fixture plugins that declare it — not AgentForge, which declares no
    dependency (see `docs/compatibility.md` for why).
    """

    def _add_marketplaces(self) -> None:
        r1 = run_claude(self.config_dir, "plugin", "marketplace", "add", str(FIXTURE_MARKETPLACE))
        self.assertEqual(r1.returncode, 0, r1.stderr)
        r2 = run_claude(
            self.config_dir, "plugin", "marketplace", "add", str(DEPENDENT_FIXTURE_MARKETPLACE)
        )
        self.assertEqual(r2.returncode, 0, r2.stderr)

    # Required scenario: dependency auto-install. Installing a plugin that
    # declares a dependency succeeds (exit 0) even though the dependency
    # isn't installed, and nothing auto-installs it.
    def test_declared_dependency_is_not_auto_installed(self) -> None:
        self._add_marketplaces()
        result = run_claude(
            self.config_dir, "plugin", "install", "fake-dependent-skills@fake-dependent", "-y"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertNotIn("fake-upstream-skills@fake-upstream", installed_names(self.config_dir))
        errors = load_errors(self.config_dir, "fake-dependent-skills@fake-dependent")
        self.assertTrue(errors and "fake-upstream-skills@fake-upstream" in errors[0])

    def test_installing_the_missing_dependency_afterward_self_heals(self) -> None:
        self._add_marketplaces()
        run_claude(self.config_dir, "plugin", "install", "fake-dependent-skills@fake-dependent", "-y")

        result = run_claude(
            self.config_dir, "plugin", "install", "fake-upstream-skills@fake-upstream", "-y"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertEqual(load_errors(self.config_dir, "fake-dependent-skills@fake-dependent"), [])

    # Required scenario: incompatible requested version. When the
    # dependency is already installed at a version the declared range
    # rejects, the *install itself* fails (not merely a load-time error).
    def test_incompatible_version_dependency_fails_install(self) -> None:
        self._add_marketplaces()
        run_claude(self.config_dir, "plugin", "install", "fake-upstream-skills@fake-upstream", "-y")

        result = run_claude(
            self.config_dir,
            "plugin",
            "install",
            "fake-dependent-incompatible-skills@fake-dependent",
            "-y",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not satisfy", result.stdout + result.stderr)

        errors = load_errors(self.config_dir, "fake-dependent-incompatible-skills@fake-dependent")
        self.assertTrue(errors and "^99.0.0" in errors[0])

    def test_strict_validate_passes_for_dependent_fixture_marketplace(self) -> None:
        result = subprocess.run(
            [CLAUDE_BIN, "plugin", "validate", str(DEPENDENT_FIXTURE_MARKETPLACE), "--strict"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class MattCoexistenceMixin:
    """Shared, marketplace-parametrized coexistence assertions against the
    real `mattpocock-skills` plugin. Deliberately NOT a `TestCase` subclass
    itself (only `unittest.TestCase` subclasses that mix this in are test
    classes), so unittest discovery never tries to instantiate it alone —
    it has no `MATT_MARKETPLACE_NAME`/`_add_matt_marketplace` of its own.

    A concrete subclass must set `MATT_MARKETPLACE_NAME` and implement
    `_add_matt_marketplace`; every test method below reads the resulting
    plugin id through `self.matt_plugin_id` rather than a hardcoded
    string, so the same three assertions run unchanged against whichever
    marketplace resolution the subclass wires up (STORY-020: real
    "latest" vs. real "pinned known-good").
    """

    MATT_MARKETPLACE_NAME: str = ""

    @property
    def matt_plugin_id(self) -> str:
        return f"mattpocock-skills@{self.MATT_MARKETPLACE_NAME}"

    def _add_matt_marketplace(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _install_matt(self) -> None:
        result = run_claude(
            self.config_dir,
            "plugin",
            "install",
            self.matt_plugin_id,
            "-y",
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    # Scenario 2 + acceptance criterion: all promoted Matt skills remain
    # available once AgentForge is installed alongside. Set equality
    # (before installing AgentForge vs. after), not a hardcoded minimum —
    # the only hardcoded number is the observed v1.2.3 baseline count,
    # asserted separately from the preservation check itself. This is
    # also STORY-020's drift signal: run unchanged against both the
    # pinned and latest marketplaces, a mismatch here that only fails on
    # the latest leg is upstream drift, not an AgentForge defect.
    def test_matt_installed_directly_then_agentforge_both_enabled(self) -> None:
        self._add_matt_marketplace()
        self._install_matt()

        before = promoted_skill_snapshot(self.config_dir, self.matt_plugin_id)
        self.assertEqual(
            len(before), 25, "observed baseline for the tested mattpocock-skills v1.2.3 pin"
        )

        result = run_claude(self.config_dir, "plugin", "install", "agentforge@agentforge", "-y")
        self.assertEqual(result.returncode, 0, result.stderr)

        plugins = by_id(self.config_dir)
        self.assertTrue(plugins["agentforge@agentforge"]["enabled"])
        self.assertTrue(plugins[self.matt_plugin_id]["enabled"])

        after = promoted_skill_snapshot(self.config_dir, self.matt_plugin_id)
        assert_promoted_skills_preserved(self, before, after)

    # Scenario 4, against the real upstream plugin.
    def test_uninstall_agentforge_preserves_directly_installed_matt(self) -> None:
        self._add_matt_marketplace()
        self._install_matt()
        run_claude(self.config_dir, "plugin", "install", "agentforge@agentforge", "-y")

        before = promoted_skill_snapshot(self.config_dir, self.matt_plugin_id)

        result = run_claude(self.config_dir, "plugin", "uninstall", "agentforge@agentforge", "-y")
        self.assertEqual(result.returncode, 0, result.stderr)

        names = installed_names(self.config_dir)
        self.assertNotIn("agentforge@agentforge", names)
        self.assertIn(self.matt_plugin_id, names)

        after = promoted_skill_snapshot(self.config_dir, self.matt_plugin_id)
        assert_promoted_skills_preserved(self, before, after)

    # Scenario 5, against the real upstream plugin: updating Matt
    # independently must not disturb AgentForge's installed-plugin record,
    # nor its own promoted skill set.
    def test_updating_matt_does_not_disturb_agentforge(self) -> None:
        self._add_matt_marketplace()
        self._install_matt()
        run_claude(self.config_dir, "plugin", "install", "agentforge@agentforge", "-y")

        before_agentforge = by_id(self.config_dir)["agentforge@agentforge"]
        before_matt_skills = promoted_skill_snapshot(self.config_dir, self.matt_plugin_id)

        result = run_claude(
            self.config_dir,
            "plugin",
            "update",
            self.matt_plugin_id,
            "-y",
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        after_agentforge = by_id(self.config_dir)["agentforge@agentforge"]
        self.assertEqual(before_agentforge, after_agentforge)

        after_matt_skills = promoted_skill_snapshot(self.config_dir, self.matt_plugin_id)
        assert_promoted_skills_preserved(self, before_matt_skills, after_matt_skills)


@unittest.skipUnless(CLAUDE_BIN, "claude CLI not found on PATH")
@unittest.skipUnless(LIVE, "set AGENTFORGE_LIVE_INTEGRATION=1 to run live-network tests")
class LiveMattCoexistenceTests(MattCoexistenceMixin, IsolatedConfigTestCase):
    """Real mattpocock-skills at whatever commit `claude-plugins-official`
    currently resolves it to ("latest available release"), over the
    network. Opt-in only.

    Uses public, unauthenticated git access to the real
    `claude-plugins-official` marketplace and `mattpocock/skills.git`.
    Never touches the real user config; never writes credentials into the
    isolated config dir it creates.

    STORY-020: adds the marketplace by its explicit `https://github.com/...`
    URL, not the `owner/repo` shorthand. Verified (`GIT_SSH_COMMAND` pointed
    at a config with no identity) that the shorthand form clones over SSH
    (`git@github.com:...`), which GitHub refuses with no registered key even
    for a public repository — exactly the failure mode a GitHub Actions
    runner hits with no SSH key provisioned. The explicit HTTPS URL clones
    anonymously and needs no credential at all, which is what actually
    makes this test CI-runnable rather than laptop-only.
    """

    MATT_MARKETPLACE_NAME = "claude-plugins-official"

    def _add_matt_marketplace(self) -> None:
        result = run_claude(
            self.config_dir,
            "plugin",
            "marketplace",
            "add",
            "https://github.com/anthropics/claude-plugins-official.git",
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_claude(self.config_dir, "plugin", "marketplace", "add", str(REPO_ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)

    # Scenario 7: the marketplace `renames` field is discovery metadata,
    # not an automatic migration. Proven by repointing the marketplace a
    # legacy install came from at the current manifest and confirming the
    # old plugin id is silently dropped from the installed-plugins
    # registry rather than becoming `agentforge@agentforge`. Kept only on
    # this class (not the mixin): it exercises the `adelchi91/agentforge`
    # legacy-rename path, unrelated to which Matt marketplace is pinned,
    # so running it twice (once per Matt marketplace variant) would just
    # be a duplicate network round-trip with no new signal.
    def test_legacy_rename_is_not_automatic_migration(self) -> None:
        legacy = run_claude(
            self.config_dir,
            "plugin",
            "marketplace",
            "add",
            "https://github.com/adelchi91/agentforge.git",
            timeout=180,
        )
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        install = run_claude(
            self.config_dir, "plugin", "install", "project-bootstrap@agentforge", "-y"
        )
        self.assertEqual(install.returncode, 0, install.stderr)
        self.assertIn("project-bootstrap@agentforge", installed_names(self.config_dir))

        repoint = run_claude(self.config_dir, "plugin", "marketplace", "add", str(REPO_ROOT))
        self.assertEqual(repoint.returncode, 0, repoint.stderr)
        update = run_claude(self.config_dir, "plugin", "marketplace", "update", "agentforge")
        self.assertEqual(update.returncode, 0, update.stderr)

        names = installed_names(self.config_dir)
        self.assertNotIn(
            "agentforge@agentforge",
            names,
            "the rename must not silently activate the new identity",
        )


@unittest.skipUnless(CLAUDE_BIN, "claude CLI not found on PATH")
@unittest.skipUnless(LIVE, "set AGENTFORGE_LIVE_INTEGRATION=1 to run live-network tests")
class PinnedMattCoexistenceTests(MattCoexistenceMixin, IsolatedConfigTestCase):
    """Real mattpocock-skills, pinned at one fixed, previously-verified
    commit ("pinned known-good release" — STORY-020's other leg of the
    integration matrix). Opt-in only, and still a real network clone of
    `mattpocock/skills.git` (just at `KNOWN_GOOD_MATT_SHA` rather than
    whatever `claude-plugins-official` currently resolves to), so it sits
    behind the same `AGENTFORGE_LIVE_INTEGRATION=1` gate as
    `LiveMattCoexistenceTests`.

    Every test method it runs is inherited unchanged from
    `MattCoexistenceMixin` — this class exists only to point
    `_add_matt_marketplace` at
    `tests/fixtures/pinned_mattpocock_marketplace/` instead of the real
    `claude-plugins-official` marketplace. See the module docstring for
    how `.github/workflows/integration.yml` uses the pinned-vs-latest
    pair to categorize a failure as upstream drift or an AgentForge-side
    regression.
    """

    MATT_MARKETPLACE_NAME = "mattpocock-pinned"

    def _add_matt_marketplace(self) -> None:
        result = run_claude(
            self.config_dir,
            "plugin",
            "marketplace",
            "add",
            str(PINNED_MATT_MARKETPLACE),
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_claude(self.config_dir, "plugin", "marketplace", "add", str(REPO_ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pinned_marketplace_actually_resolves_the_known_good_sha(self) -> None:
        """Regression guard for the fixture itself: fails loudly (not as
        a mysterious install error) if `KNOWN_GOOD_MATT_SHA` and
        `tests/fixtures/pinned_mattpocock_marketplace/.claude-plugin/marketplace.json`
        are ever edited out of sync with each other."""
        marketplace_json = json.loads(
            (PINNED_MATT_MARKETPLACE / ".claude-plugin" / "marketplace.json").read_text()
        )
        (matt_entry,) = [
            p for p in marketplace_json["plugins"] if p["name"] == "mattpocock-skills"
        ]
        self.assertEqual(matt_entry["source"]["sha"], KNOWN_GOOD_MATT_SHA)


if __name__ == "__main__":
    unittest.main()
