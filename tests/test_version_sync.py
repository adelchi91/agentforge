"""Tests for scripts/check_version_sync.py (STORY-020).

Covers: the real repository must currently pass (a regression guard
against the actual `VERSION` / `plugin.json` / `CHANGELOG.md` files, not
just fixtures), plus every mismatch/malformed-input shape the script is
documented to catch, built from throwaway temp-directory fixtures so no
test ever mutates the real repository files.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import check_version_sync as vsync  # noqa: E402


def _write_repo(
    root: Path,
    *,
    version_file: str = "2.0.0-dev\n",
    plugin_version: object = "2.0.0-dev",
    changelog_heading: str = "## [2.0.0-dev] - Unreleased\n",
    marketplace_version: object = None,
    omit_version_file: bool = False,
    omit_plugin_json: bool = False,
    omit_changelog: bool = False,
) -> None:
    if not omit_version_file:
        (root / "VERSION").write_text(version_file, encoding="utf-8")

    plugin_dir = root / ".claude-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    if not omit_plugin_json:
        manifest = {"name": "agentforge"}
        if plugin_version is not None:
            manifest["version"] = plugin_version
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

    marketplace = {"name": "agentforge"}
    if marketplace_version is not None:
        marketplace["version"] = marketplace_version
    (plugin_dir / "marketplace.json").write_text(json.dumps(marketplace), encoding="utf-8")

    if not omit_changelog:
        (root / "CHANGELOG.md").write_text(
            f"# Changelog\n\n{changelog_heading}\n### Added\n\n- stuff\n", encoding="utf-8"
        )


class RealRepositoryTests(unittest.TestCase):
    """The actual repository this test runs from must always pass -- this
    is the story's own literal verification command, run as a test too so
    a future story can't silently desync the files without a test
    failure telling them so."""

    def test_real_repository_is_in_sync(self) -> None:
        issues = vsync.check_version_sync(REPO_ROOT)
        self.assertEqual(issues, [], [i.format() for i in issues])


class InSyncFixtureTests(unittest.TestCase):
    def test_matching_fixture_has_no_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root)
            self.assertEqual(vsync.check_version_sync(root), [])

    def test_marketplace_version_present_and_matching_is_fine(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, marketplace_version="2.0.0-dev")
            self.assertEqual(vsync.check_version_sync(root), [])

    def test_release_version_with_no_prerelease_suffix_is_valid(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(
                root,
                version_file="2.0.0\n",
                plugin_version="2.0.0",
                changelog_heading="## [2.0.0] - 2026-09-18\n",
            )
            self.assertEqual(vsync.check_version_sync(root), [])


class MismatchTests(unittest.TestCase):
    def test_plugin_json_mismatch_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, plugin_version="2.0.1-dev")
            issues = vsync.check_version_sync(root)
            self.assertTrue(
                any("plugin.json" in i.detail and "2.0.1-dev" in i.detail for i in issues), issues
            )

    def test_changelog_mismatch_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, changelog_heading="## [1.9.9] - Unreleased\n")
            issues = vsync.check_version_sync(root)
            self.assertTrue(
                any("CHANGELOG.md" in i.detail and "1.9.9" in i.detail for i in issues), issues
            )

    def test_marketplace_version_mismatch_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, marketplace_version="0.0.1")
            issues = vsync.check_version_sync(root)
            self.assertTrue(
                any("marketplace.json" in i.detail and "0.0.1" in i.detail for i in issues), issues
            )

    def test_all_mismatches_are_reported_together_not_just_the_first(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(
                root,
                plugin_version="9.9.9",
                changelog_heading="## [8.8.8] - Unreleased\n",
            )
            issues = vsync.check_version_sync(root)
            locations = {i.location for i in issues}
            self.assertEqual(len(issues), 2, issues)
            self.assertEqual(locations, {"version sync"})


class MalformedInputTests(unittest.TestCase):
    def test_missing_version_file_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, omit_version_file=True)
            issues = vsync.check_version_sync(root)
            self.assertTrue(any(i.location == "VERSION" for i in issues), issues)

    def test_version_file_with_two_lines_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, version_file="2.0.0-dev\nextra\n")
            issues = vsync.check_version_sync(root)
            self.assertTrue(
                any(i.location == "VERSION" and "one non-blank line" in i.detail for i in issues),
                issues,
            )

    def test_version_file_with_invalid_shape_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, version_file="v2.0\n")
            issues = vsync.check_version_sync(root)
            self.assertTrue(
                any(i.location == "VERSION" and "not a valid" in i.detail for i in issues), issues
            )

    def test_missing_plugin_json_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, omit_plugin_json=True)
            issues = vsync.check_version_sync(root)
            self.assertTrue(
                any(".claude-plugin/plugin.json" in i.location for i in issues), issues
            )

    def test_plugin_json_missing_version_field_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, plugin_version=None)
            issues = vsync.check_version_sync(root)
            self.assertTrue(
                any(
                    ".claude-plugin/plugin.json" in i.location and "missing" in i.detail
                    for i in issues
                ),
                issues,
            )

    def test_invalid_json_in_plugin_manifest_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root)
            (root / ".claude-plugin" / "plugin.json").write_text("{not json", encoding="utf-8")
            issues = vsync.check_version_sync(root)
            self.assertTrue(
                any(".claude-plugin/plugin.json" in i.location and "invalid JSON" in i.detail
                    for i in issues),
                issues,
            )

    def test_missing_changelog_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, omit_changelog=True)
            issues = vsync.check_version_sync(root)
            self.assertTrue(any(i.location == "CHANGELOG.md" for i in issues), issues)

    def test_changelog_with_no_release_heading_is_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root)
            (root / "CHANGELOG.md").write_text("# Changelog\n\nNothing here.\n", encoding="utf-8")
            issues = vsync.check_version_sync(root)
            self.assertTrue(
                any(i.location == "CHANGELOG.md" and "no '## [" in i.detail for i in issues),
                issues,
            )


class CliEntryPointTests(unittest.TestCase):
    def test_main_returns_zero_for_a_synced_fixture(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root)
            self.assertEqual(vsync.main(["--root", str(root)]), 0)

    def test_main_returns_one_for_a_mismatched_fixture(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, plugin_version="9.9.9")
            self.assertEqual(vsync.main(["--root", str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
