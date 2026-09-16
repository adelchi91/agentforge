"""Tests for STORY-017: optional capability agents replacing the default
persona roster.

Covers the STORY-017 acceptance criteria:
  - a default `/agentforge:setup` run generates no project-specific persona
    files and never enables a bundled capability agent;
  - `independent-reviewer` and `verifier` are the only two bundled optional
    agents added by this story, each with a valid definition and tools
    distinct from a mandatory persona (no Write/Edit for either; verifier
    also grants Bash to run declared commands, reviewer does not);
  - each agent's frontmatter `name` matches its filename and is usable as
    the `scope.agents` key STORY-014's scope hooks will key off (the
    documented `agent_type` identity);
  - no bundled agent hardcodes a dated full model id;
  - setup and dedicated documentation explain the concrete benefit of each
    agent and that both are off by default.

This story does not delete or modify the v1 project-bootstrap persona
agents (`interviewer.md`, `planner.md`, `scaffolder.md`) — that is
STORY-019's job (preserve legacy agents until STORY-019). A couple of
sanity checks below confirm this suite is not accidentally asserting
against a repository state where those files were removed.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config as config_module  # noqa: E402
from scripts import setup as setup_module  # noqa: E402

AGENTS_DIR = REPO_ROOT / "agents"

# STORY-017 bundled optional capability agents. Not a mandatory persona
# roster -- see docs/agents-capabilities.md.
CAPABILITY_AGENT_NAMES = ("independent-reviewer", "verifier")

# The v1 project-bootstrap meta-flow agents (STORY-002 baseline), preserved
# untouched per the execution plan's "preserve legacy agents until
# STORY-019". STORY-017 must not delete or rename these.
LEGACY_BOOTSTRAP_AGENT_NAMES = ("interviewer", "planner", "scaffolder")

# A dated, pinned full model id ends in an 8-digit date, e.g.
# "claude-sonnet-4-20250514". Aliases like "sonnet", "opus", "haiku",
# "inherit", and "fable" never match this.
_DATED_MODEL_ID_RE = re.compile(r"-\d{8}$")

_NO_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def agent_frontmatter(agent_md: Path) -> tuple[dict, str]:
    """Parse the flat (single-line, unindented) frontmatter keys of an
    agent definition file. Mirrors tests/test_plugin_smoke.py's
    skill_frontmatter helper: a folded/multi-line scalar (e.g. a ">"
    description) is skipped because its continuation lines are indented."""
    text = agent_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{agent_md} has no YAML frontmatter block"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields, text


def parse_tools(value: str) -> list[str]:
    return [tool.strip() for tool in value.split(",") if tool.strip()]


def tool_names(fields: dict) -> set[str]:
    return {tool.split("(", 1)[0] for tool in parse_tools(fields.get("tools", ""))}


class BundledAgentsExistTests(unittest.TestCase):
    def test_both_capability_agents_are_bundled(self) -> None:
        for name in CAPABILITY_AGENT_NAMES:
            self.assertTrue(
                (AGENTS_DIR / f"{name}.md").is_file(),
                f"expected agents/{name}.md to exist",
            )

    def test_at_most_two_new_capability_agents_added(self) -> None:
        # STORY-017: "at most two bundled optional agents". Everything under
        # agents/ must be either a capability agent or a preserved legacy one.
        known = set(CAPABILITY_AGENT_NAMES) | set(LEGACY_BOOTSTRAP_AGENT_NAMES)
        found = {path.stem for path in AGENTS_DIR.glob("*.md")}
        self.assertTrue(
            found.issubset(known),
            f"unexpected agent file(s) beyond the documented roster: {found - known}",
        )

    def test_legacy_bootstrap_agents_are_preserved(self) -> None:
        for name in LEGACY_BOOTSTRAP_AGENT_NAMES:
            self.assertTrue(
                (AGENTS_DIR / f"{name}.md").is_file(),
                f"legacy agent agents/{name}.md must be preserved until STORY-019",
            )


class FrontmatterNameIdentityTests(unittest.TestCase):
    """'Agent scope hooks use the frontmatter name, which is the documented
    agent_type identity' (STORY-017 requirement, STORY-014 concept)."""

    def test_name_field_matches_filename_stem(self) -> None:
        for name in CAPABILITY_AGENT_NAMES:
            fields, _ = agent_frontmatter(AGENTS_DIR / f"{name}.md")
            self.assertEqual(fields.get("name"), name)

    def test_name_is_a_valid_scope_agents_key(self) -> None:
        for name in CAPABILITY_AGENT_NAMES:
            self.assertRegex(name, config_module._AGENT_NAME_PATTERN.pattern)

    def test_scope_agents_config_validates_with_bundled_agent_names(self) -> None:
        # End-to-end: a project registering a bundled agent's identity under
        # scope.agents.<name> in .agentforge/config.json must pass the
        # STORY-004 validator, not just the isolated regex.
        for name in CAPABILITY_AGENT_NAMES:
            data = json.loads(json.dumps(config_module.DEFAULT_CONFIG))
            data["scope"] = {"mode": "off", "agents": {name: {"allow": ["src/"]}}}
            issues = config_module.validate_config(data)
            self.assertEqual(
                issues, [], f"{name}: {[issue.format() for issue in issues]}"
            )


class IndependentReviewerToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fields, self.text = agent_frontmatter(AGENTS_DIR / "independent-reviewer.md")

    def test_has_no_write_capable_tool(self) -> None:
        names = tool_names(self.fields)
        for forbidden in _NO_WRITE_TOOLS:
            self.assertNotIn(forbidden, names)

    def test_grants_read_only_inspection_tools(self) -> None:
        names = tool_names(self.fields)
        self.assertIn("Read", names)
        self.assertTrue({"Grep", "Glob"} & names, "expected Grep and/or Glob")

    def test_any_bash_grant_is_restricted_to_read_only_commands(self) -> None:
        tools = parse_tools(self.fields.get("tools", ""))
        bash_grants = [tool for tool in tools if tool.startswith("Bash")]
        self.assertTrue(bash_grants, "expected at least one scoped Bash(...) grant")
        for grant in bash_grants:
            self.assertNotEqual(
                grant, "Bash", "independent-reviewer must not receive unrestricted Bash"
            )

    def test_description_and_body_state_it_is_read_only_and_optional(self) -> None:
        self.assertIn("read-only", self.text.lower())
        self.assertIn("optional", self.text.lower())


class VerifierToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fields, self.text = agent_frontmatter(AGENTS_DIR / "verifier.md")

    def test_has_no_write_capable_tool(self) -> None:
        names = tool_names(self.fields)
        for forbidden in _NO_WRITE_TOOLS:
            self.assertNotIn(forbidden, names)

    def test_grants_bash_and_read(self) -> None:
        names = tool_names(self.fields)
        self.assertIn("Bash", names)
        self.assertIn("Read", names)

    def test_description_and_body_state_it_runs_only_declared_commands(self) -> None:
        lowered = self.text.lower()
        self.assertIn("verification", lowered)
        self.assertIn("optional", lowered)
        self.assertIn("cannot edit", lowered)


class NoDatedModelIdTests(unittest.TestCase):
    def test_no_bundled_capability_agent_pins_a_dated_full_model_id(self) -> None:
        for name in CAPABILITY_AGENT_NAMES:
            fields, _ = agent_frontmatter(AGENTS_DIR / f"{name}.md")
            model = fields.get("model")
            if model is None:
                continue  # omitted -> inherits session model, also acceptable
            self.assertNotRegex(
                model,
                _DATED_MODEL_ID_RE,
                f"agents/{name}.md pins a dated full model id: {model!r}",
            )


class SetupGeneratesNoPersonaFilesTests(unittest.TestCase):
    """STORY-017 acceptance criterion: 'A default setup generates no
    project-specific persona files.'"""

    def test_default_setup_plan_never_proposes_an_agents_path(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = setup_module.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            for change in plan.changes:
                self.assertFalse(
                    change.path.startswith("agents/")
                    or change.path.startswith(".claude/agents/")
                    or change.path.startswith(".codex/agents/"),
                    f"default setup unexpectedly proposes touching {change.path}",
                )

    def test_shipped_config_template_enables_no_agent_by_default(self) -> None:
        data = json.loads(
            (REPO_ROOT / "templates" / "agentforge-config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["scope"]["agents"], {})
        self.assertEqual(data["scope"]["mode"], "off")

    def test_default_config_module_constant_enables_no_agent(self) -> None:
        self.assertEqual(config_module.DEFAULT_CONFIG["scope"]["agents"], {})


class SetupSkillDocumentsCapabilityAgentsTests(unittest.TestCase):
    def test_setup_skill_mentions_both_agents_and_default_off(self) -> None:
        text = (REPO_ROOT / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")
        for name in CAPABILITY_AGENT_NAMES:
            self.assertIn(name, text)
        self.assertRegex(
            text.lower(),
            r"off by default|default[^.\n]{0,30}off|not enabled by default",
        )


class CapabilitiesDocumentationTests(unittest.TestCase):
    def test_agents_capabilities_doc_exists_and_covers_both_agents(self) -> None:
        doc_path = REPO_ROOT / "docs" / "agents-capabilities.md"
        self.assertTrue(doc_path.is_file(), "expected docs/agents-capabilities.md")
        text = doc_path.read_text(encoding="utf-8")
        for name in CAPABILITY_AGENT_NAMES:
            self.assertIn(name, text)
        self.assertIn("persona", text.lower())


if __name__ == "__main__":
    unittest.main()
