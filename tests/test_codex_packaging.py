"""Tests for STORY-018's Codex packaging surface: per-skill invocation
policy, Codex hook configuration, and custom-agent TOML validity.

Every fact this module asserts about "what current Codex documentation
allows" (valid `agents/openai.yaml` schema/location, valid custom-agent TOML
keys, valid `sandbox_mode` values, the `hooks.json` envelope shape) was
verified against the current Codex documentation via WebFetch before being
encoded here -- see `docs/codex-compatibility.md` for the full citations.
This module does not re-implement any policy; it only validates that the
shipped packaging files (`skills/*/agents/openai.yaml`,
`templates/codex/agents/*.toml`, `templates/codex/hooks.json`) are shaped
the way that documentation says Codex expects.

`skills/*/agents/openai.yaml` deliberately exists once **per skill
directory** (`skills/<name>/agents/openai.yaml`), not as a single top-level
`agents/openai.yaml` covering every skill -- https://learn.chatgpt.com/docs/build-skills
(fetched 2026-09-17) documents this file as living inside each skill's own
directory, one skill's invocation policy at a time. A single top-level file
of that name would not even be read by Codex's skill loader for any skill
other than one literally living at the repository root.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

try:
    import tomllib  # stdlib, Python 3.11+
except ModuleNotFoundError:  # Python 3.10: no stdlib tomllib yet
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SKILLS_DIR = REPO_ROOT / "skills"

# Every AgentForge skill (target architecture: docs/plans/agentforge-v2
# -execution-plan.md) and its documented invocation model, from that plan's
# "Invocation model" section: user-invoked skills are explicit slash
# commands (`/agentforge:setup`, `/agentforge:prepare-work <id>`) that
# mutate project state and must never fire because a model merely judged a
# prompt "sounded relevant"; model-invoked skills are reusable disciplines
# meant to activate whenever the work at hand matches, without requiring an
# explicit by-name invocation every time.
EXPECTED_IMPLICIT_INVOCATION = {
    "setup": False,
    "prepare-work": False,
    "work-contract": True,
    "reconcile-docs": True,
    "migration-safety": True,
}


def _parse_openai_yaml_policy(path: Path) -> dict:
    """Minimal, dependency-free parser for this repo's `agents/openai.yaml`
    files. These files are deliberately tiny and fixed-shape (a `policy:`
    mapping with one `allow_implicit_invocation: <bool>` key, per
    https://learn.chatgpt.com/docs/build-skills's own example) --
    `scripts/config.py`'s own module docstring already establishes this
    repo's stdlib-only-dependency convention for anything a hook or test
    must parse, so this avoids adding a PyYAML dependency for a two-line
    fixed shape rather than because a real YAML parser is unavailable."""
    text = path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert lines, f"{path} has no non-comment content"
    assert lines[0].strip() == "policy:", f"{path}: expected a top-level 'policy:' mapping, got {lines[0]!r}"
    match = re.match(r"^\s*allow_implicit_invocation:\s*(true|false)\s*$", lines[1])
    assert match, f"{path}: expected 'allow_implicit_invocation: true|false' on the second content line"
    return {"allow_implicit_invocation": match.group(1) == "true"}


class PerSkillInvocationPolicyTests(unittest.TestCase):
    def test_every_agentforge_skill_has_a_per_skill_openai_yaml(self) -> None:
        for name in EXPECTED_IMPLICIT_INVOCATION:
            path = SKILLS_DIR / name / "agents" / "openai.yaml"
            self.assertTrue(path.is_file(), f"expected {path} to exist")

    def test_no_stray_top_level_agents_openai_yaml(self) -> None:
        # The literal ask in STORY-018's own task text ("Add agents/openai.yaml
        # ... covering every AgentForge skill") reads naturally as one
        # top-level file; current Codex documentation does not support that
        # shape (the file is skill-directory-scoped), so this asserts the
        # corrected design was actually applied, not the naive one.
        self.assertFalse(
            (REPO_ROOT / "agents" / "openai.yaml").exists(),
            "a single top-level agents/openai.yaml is not how Codex scopes skill "
            "invocation policy -- see docs/codex-compatibility.md",
        )

    def test_implicit_invocation_policy_matches_the_execution_plans_invocation_model(self) -> None:
        for name, expected in EXPECTED_IMPLICIT_INVOCATION.items():
            path = SKILLS_DIR / name / "agents" / "openai.yaml"
            policy = _parse_openai_yaml_policy(path)
            self.assertEqual(
                policy["allow_implicit_invocation"],
                expected,
                f"skills/{name}/agents/openai.yaml: expected allow_implicit_invocation={expected}",
            )

    def test_user_invoked_skills_disable_implicit_invocation(self) -> None:
        for name in ("setup", "prepare-work"):
            policy = _parse_openai_yaml_policy(SKILLS_DIR / name / "agents" / "openai.yaml")
            self.assertFalse(policy["allow_implicit_invocation"])

    def test_model_invoked_skills_leave_implicit_invocation_enabled(self) -> None:
        for name in ("work-contract", "reconcile-docs", "migration-safety"):
            policy = _parse_openai_yaml_policy(SKILLS_DIR / name / "agents" / "openai.yaml")
            self.assertTrue(policy["allow_implicit_invocation"])


# --------------------------------------------------------------------------
# Custom-agent TOML validation (independent-reviewer.toml, verifier.toml,
# templates/codex/agent.toml, and the pre-existing v1 examples).
# --------------------------------------------------------------------------

# Verified against https://learn.chatgpt.com/docs/agent-configuration/subagents
# (fetched 2026-09-17): name, description, and developer_instructions are
# required; the remaining keys are optional config.toml keys a custom agent
# may also set.
REQUIRED_AGENT_TOML_KEYS = {"name", "description", "developer_instructions"}
ALLOWED_AGENT_TOML_KEYS = REQUIRED_AGENT_TOML_KEYS | {
    "model",
    "model_reasoning_effort",
    "sandbox_mode",
    "mcp_servers",
    "skills",
}

# Sandbox mode values actually observed in current Codex documentation and
# in this repository's own pre-existing Codex examples
# (examples/codex-minimal/.codex/agents/*.toml, frozen v1 content); the
# docs did not provide one single exhaustive enum listing, so this set is
# deliberately named as "confirmed valid", not "the complete universe" --
# see docs/codex-compatibility.md's "Known limitations".
CONFIRMED_SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}

NEW_CODEX_AGENT_TOML_FILES = (
    REPO_ROOT / "templates" / "codex" / "agents" / "independent-reviewer.toml",
    REPO_ROOT / "templates" / "codex" / "agents" / "verifier.toml",
)

# Pre-existing v1 TOML the task asked to check "confirming the keys used are
# real, current" -- read-only validation, no modification (these files are
# also covered by tests/fixtures/v1/examples_checksums.json's frozen-content
# guarantee).
EXISTING_CODEX_AGENT_TOML_FILES = (
    REPO_ROOT / "examples" / "codex-minimal" / ".codex" / "agents" / "dev.toml",
    REPO_ROOT / "examples" / "codex-minimal" / ".codex" / "agents" / "final-judge.toml",
    REPO_ROOT / "examples" / "codex-minimal" / ".codex" / "agents" / "tester.toml",
)


class NewCodexAgentTomlTests(unittest.TestCase):
    def test_each_new_agent_toml_parses_as_valid_toml(self) -> None:
        for path in NEW_CODEX_AGENT_TOML_FILES:
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"expected {path} to exist")
                with path.open("rb") as handle:
                    tomllib.load(handle)  # raises TOMLDecodeError on invalid syntax

    def test_each_new_agent_toml_has_every_required_key(self) -> None:
        for path in NEW_CODEX_AGENT_TOML_FILES:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
            missing = REQUIRED_AGENT_TOML_KEYS - data.keys()
            self.assertFalse(missing, f"{path} is missing required key(s): {missing}")

    def test_each_new_agent_toml_uses_only_documented_keys(self) -> None:
        for path in NEW_CODEX_AGENT_TOML_FILES:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
            unknown = data.keys() - ALLOWED_AGENT_TOML_KEYS
            self.assertFalse(unknown, f"{path} uses undocumented key(s): {unknown}")

    def test_each_new_agent_toml_sandbox_mode_is_a_confirmed_value(self) -> None:
        for path in NEW_CODEX_AGENT_TOML_FILES:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
            sandbox_mode = data.get("sandbox_mode")
            if sandbox_mode is None:
                continue
            self.assertIn(sandbox_mode, CONFIRMED_SANDBOX_MODES, path)

    def test_new_agent_tomls_do_not_pin_a_dated_full_model_id(self) -> None:
        # Mirrors STORY-017's tests/test_agents.py requirement for the
        # Claude-side bundled agents (agents/independent-reviewer.md,
        # agents/verifier.md); the Codex ports must not regress it.
        dated_model_id_re = re.compile(r"-\d{8}$")
        for path in NEW_CODEX_AGENT_TOML_FILES:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
            model = data.get("model")
            if model is None:
                continue
            self.assertNotRegex(model, dated_model_id_re, path)

    def test_independent_reviewer_toml_is_read_only(self) -> None:
        path = REPO_ROOT / "templates" / "codex" / "agents" / "independent-reviewer.toml"
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        self.assertEqual(data.get("sandbox_mode"), "read-only")

    def test_agent_names_match_their_filenames(self) -> None:
        for path in NEW_CODEX_AGENT_TOML_FILES:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
            self.assertEqual(data.get("name"), path.stem)


class ExistingCodexAgentTomlValidationTests(unittest.TestCase):
    """Read-only validation of the pre-existing (v1, frozen) Codex agent
    TOML already shipped in this repository -- confirms the keys and
    sandbox_mode values it uses are real and current, without modifying it
    (tests/fixtures/v1/examples_checksums.json still governs its content)."""

    def test_existing_agent_toml_parses_and_uses_only_documented_keys(self) -> None:
        for path in EXISTING_CODEX_AGENT_TOML_FILES:
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"expected {path} to exist")
                with path.open("rb") as handle:
                    data = tomllib.load(handle)
                missing = REQUIRED_AGENT_TOML_KEYS - data.keys()
                self.assertFalse(missing, f"{path} is missing required key(s): {missing}")
                unknown = data.keys() - ALLOWED_AGENT_TOML_KEYS
                self.assertFalse(unknown, f"{path} uses undocumented key(s): {unknown}")

    def test_existing_agent_toml_sandbox_mode_is_a_confirmed_value(self) -> None:
        for path in EXISTING_CODEX_AGENT_TOML_FILES:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
            sandbox_mode = data.get("sandbox_mode")
            if sandbox_mode is None:
                continue
            self.assertIn(sandbox_mode, CONFIRMED_SANDBOX_MODES, path)


class TemplateCodexAgentTomlPlaceholderTests(unittest.TestCase):
    """templates/codex/agent.toml is a `{{PLACEHOLDER}}`-driven template for
    the v1 scaffolder, not a literal agent definition -- it cannot be
    validated key-value the way a real agent can, but its *keys* (before
    substitution) must still be the documented ones."""

    def test_template_uses_only_documented_top_level_keys(self) -> None:
        path = REPO_ROOT / "templates" / "codex" / "agent.toml"
        text = path.read_text(encoding="utf-8")
        top_level_keys = set()
        for line in text.splitlines():
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if match:
                top_level_keys.add(match.group(1))
        self.assertTrue(top_level_keys, "expected at least one top-level key in the template")
        unknown = top_level_keys - ALLOWED_AGENT_TOML_KEYS
        self.assertFalse(unknown, f"{path} uses undocumented key(s): {unknown}")


# --------------------------------------------------------------------------
# templates/codex/hooks.json: structural validation + the SessionEnd fix.
# --------------------------------------------------------------------------


class CodexHooksJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        path = REPO_ROOT / "templates" / "codex" / "hooks.json"
        self.data = json.loads(path.read_text(encoding="utf-8"))

    def test_has_a_hooks_wrapper_key(self) -> None:
        # https://learn.chatgpt.com/docs/hooks (fetched 2026-09-17):
        # Codex's hooks.json nests every event under a top-level "hooks"
        # key, exactly like Claude Code's hooks/hooks.json -- there is no
        # separate "events at the root" shape to support.
        self.assertIn("hooks", self.data)

    def test_session_end_is_used_instead_of_stop(self) -> None:
        # The exact anti-pattern flagged for this story: current Codex has
        # a real SessionEnd event (learn.chatgpt.com/docs/hooks), so mapping
        # the session-record hook to per-turn Stop is stale, not a current
        # parity limitation.
        self.assertIn("SessionEnd", self.data["hooks"])
        self.assertNotIn("Stop", self.data["hooks"])

    def test_every_wired_event_name_is_a_documented_codex_event(self) -> None:
        documented_events = {
            "SessionStart",
            "SessionEnd",
            "SubagentStart",
            "SubagentStop",
            "PreToolUse",
            "PermissionRequest",
            "PostToolUse",
            "PreCompact",
            "PostCompact",
            "UserPromptSubmit",
            "Stop",
            "Interrupt",
        }
        for event_name in self.data["hooks"]:
            self.assertIn(event_name, documented_events, event_name)


if __name__ == "__main__":
    unittest.main()
