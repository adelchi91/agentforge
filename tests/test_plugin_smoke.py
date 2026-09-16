"""Smoke tests for the STORY-002 namespaced companion-plugin skeleton.

These check what can be verified without shelling out to the `claude` CLI
(that is covered separately by `claude plugin validate . --strict`, run as
its own verification command). They encode the STORY-002 acceptance
criteria that are checkable as plain file/JSON facts:

  - the plugin identity is `agentforge`, with a migration path recorded for
    `project-bootstrap` users;
  - the plugin and marketplace manifests agree on the plugin name;
  - `setup` and `prepare-work` skills exist under unique AgentForge names;
  - no skill uses a name reserved for Matt Pocock's plugin (mattpocock-skills);
  - no vendored copy of Matt's plugin exists in this repository;
  - hooks/hooks.json is valid JSON and scripts are referenced through
    `${CLAUDE_PLUGIN_ROOT}`, never a path assuming in-project copies;
  - there is one machine-readable version source, synchronized with the
    plugin manifest and the changelog.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Matt Pocock's shipped skill names (mattpocock-skills), reserved so AgentForge
# never shadows them. Superset of the names checked by the STORY-002
# verification `rg` command. Manually maintained — update if his plugin's
# skill roster changes.
MATT_SKILL_NAMES = {
    "diagnosing-bugs",
    "tdd",
    "prototype",
    "research",
    "domain-modeling",
    "codebase-design",
    "code-review",
    "resolving-merge-conflicts",
    "wizard",
    "grilling",
    "writing-for-agents",
    "to-spec",
    "to-tickets",
    "implement",
    "ask-matt",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def skill_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{skill_md} has no YAML frontmatter block"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


class PluginIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = read_json(REPO_ROOT / ".claude-plugin" / "plugin.json")
        self.marketplace = read_json(REPO_ROOT / ".claude-plugin" / "marketplace.json")

    def test_plugin_is_named_agentforge(self) -> None:
        self.assertEqual(self.plugin["name"], "agentforge")

    def test_marketplace_plugin_entry_matches_plugin_name(self) -> None:
        entries = {p["name"] for p in self.marketplace["plugins"]}
        self.assertIn(self.plugin["name"], entries)
        self.assertNotIn("project-bootstrap", entries)

    def test_marketplace_records_project_bootstrap_rename(self) -> None:
        self.assertEqual(
            self.marketplace.get("renames", {}).get("project-bootstrap"),
            "agentforge",
        )

    def test_no_component_name_collision_with_matt_skills(self) -> None:
        marketplace_names = {p["name"] for p in self.marketplace["plugins"]}
        self.assertTrue(marketplace_names.isdisjoint(MATT_SKILL_NAMES))


class VersionSyncTests(unittest.TestCase):
    def test_version_file_matches_plugin_manifest(self) -> None:
        version_file = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        plugin = read_json(REPO_ROOT / ".claude-plugin" / "plugin.json")
        self.assertEqual(version_file, plugin["version"])

    def test_changelog_top_entry_matches_version_file(self) -> None:
        version_file = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        match = re.search(r"^## \[([^\]]+)\]", changelog, re.MULTILINE)
        self.assertIsNotNone(match, "CHANGELOG.md has no '## [version]' heading")
        self.assertEqual(match.group(1), version_file)


class SkillSkeletonTests(unittest.TestCase):
    def test_setup_skill_exists_with_unique_name(self) -> None:
        fields = skill_frontmatter(REPO_ROOT / "skills" / "setup" / "SKILL.md")
        self.assertEqual(fields["name"], "setup")
        self.assertNotIn(fields["name"], MATT_SKILL_NAMES)

    def test_prepare_work_skill_exists_with_unique_name(self) -> None:
        fields = skill_frontmatter(REPO_ROOT / "skills" / "prepare-work" / "SKILL.md")
        self.assertEqual(fields["name"], "prepare-work")
        self.assertNotIn(fields["name"], MATT_SKILL_NAMES)

    def test_no_skill_under_skills_dir_uses_a_reserved_matt_name(self) -> None:
        skills_dir = REPO_ROOT / "skills"
        found_names = {
            skill_frontmatter(skill_md)["name"]
            for skill_md in skills_dir.glob("*/SKILL.md")
        }
        self.assertTrue(found_names)
        self.assertTrue(found_names.isdisjoint(MATT_SKILL_NAMES))

    def test_skill_markdown_never_assumes_scripts_were_copied_into_project(
        self,
    ) -> None:
        for skill_md in (REPO_ROOT / "skills").glob("*/SKILL.md"):
            text = skill_md.read_text(encoding="utf-8")
            for match in re.finditer(r"[^\s`]*\bscripts/[\w.\-/]+", text):
                reference = match.group(0)
                self.assertTrue(
                    reference.startswith("${CLAUDE_PLUGIN_ROOT}/scripts/"),
                    f"{skill_md} references {reference!r} without "
                    "${CLAUDE_PLUGIN_ROOT}",
                )


class StandardDirectoriesTests(unittest.TestCase):
    def test_standard_plugin_directories_exist(self) -> None:
        for name in ("skills", "agents", "hooks", "scripts"):
            self.assertTrue((REPO_ROOT / name).is_dir(), f"missing {name}/")

    def test_hooks_manifest_is_valid_json(self) -> None:
        hooks = read_json(REPO_ROOT / "hooks" / "hooks.json")
        self.assertIn("hooks", hooks)
        self.assertIsInstance(hooks["hooks"], dict)


class NoVendoredMattSourceTests(unittest.TestCase):
    def test_no_directory_named_after_matts_plugin(self) -> None:
        for path in REPO_ROOT.rglob("*"):
            if ".git" in path.parts:
                continue
            if path.is_dir() and path.name in {"mattpocock-skills", "mattpocock"}:
                self.fail(f"found a directory that looks like vendored Matt source: {path}")

    def test_no_skill_directory_shares_a_name_with_matts_skills(self) -> None:
        skills_dir = REPO_ROOT / "skills"
        skill_dir_names = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        self.assertTrue(skill_dir_names.isdisjoint(MATT_SKILL_NAMES))


if __name__ == "__main__":
    unittest.main()
