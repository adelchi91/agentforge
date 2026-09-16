"""Tests for the STORY-004 project configuration contract (scripts/config.py).

Covers:
  - valid examples for all three tracker types (github, gitlab, local);
  - every required field, enum, regex, relative-path, and traversal check
    named in docs/plans/agentforge-v2-user-stories.md's STORY-004;
  - unsupported schema_version rejection;
  - the forward-compatibility policy (unknown fields are rejected, not
    silently ignored or preserved) documented in docs/agentforge-config.md;
  - the enforce/observe split: enforcement callers get a hard exception,
    observation callers get a diagnostic and a None config, never a raise;
  - diagnostics identify the offending config path and value without
    leaking unrelated environment data.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "config"


def issue_paths(issues) -> set[str]:
    return {issue.path for issue in issues}


class DefaultConfigTests(unittest.TestCase):
    def test_default_config_has_no_validation_issues(self) -> None:
        self.assertEqual(config.validate_config(config.DEFAULT_CONFIG), [])

    def test_default_config_is_fully_non_destructive(self) -> None:
        self.assertEqual(config.DEFAULT_CONFIG["traceability"]["mode"], "off")
        self.assertEqual(config.DEFAULT_CONFIG["scope"]["mode"], "off")
        self.assertEqual(config.DEFAULT_CONFIG["quality"]["post_edit"], "off")

    def test_default_config_traceability_mode_is_off_or_observe(self) -> None:
        self.assertIn(config.DEFAULT_CONFIG["traceability"]["mode"], ("off", "observe"))

    def test_default_config_scope_mode_is_off_or_observe(self) -> None:
        self.assertIn(config.DEFAULT_CONFIG["scope"]["mode"], ("off", "observe"))

    def test_default_config_post_edit_is_off_or_report(self) -> None:
        self.assertIn(config.DEFAULT_CONFIG["quality"]["post_edit"], ("off", "report"))


class TemplateFileTests(unittest.TestCase):
    """The shipped templates/agentforge-config.json must match config.py's
    DEFAULT_CONFIG exactly, the same way VERSION is kept in sync with
    plugin.json (tests/test_plugin_smoke.py::VersionSyncTests)."""

    def test_template_file_is_valid_json(self) -> None:
        path = REPO_ROOT / "templates" / "agentforge-config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)

    def test_template_file_matches_default_config(self) -> None:
        path = REPO_ROOT / "templates" / "agentforge-config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data, config.DEFAULT_CONFIG)

    def test_template_file_has_no_validation_issues(self) -> None:
        path = REPO_ROOT / "templates" / "agentforge-config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(config.validate_config(data), [])


class ValidTrackerExampleTests(unittest.TestCase):
    def _load(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_valid_github_example_loads(self) -> None:
        data = self._load("valid_github.json")
        self.assertEqual(config.validate_config(data), [])

    def test_valid_gitlab_example_loads(self) -> None:
        data = self._load("valid_gitlab.json")
        self.assertEqual(config.validate_config(data), [])

    def test_valid_local_example_loads(self) -> None:
        data = self._load("valid_local.json")
        self.assertEqual(config.validate_config(data), [])

    def test_valid_local_example_with_dotfile_root_preserves_leading_dot(self) -> None:
        # Regression guard for the v1 lstrip("./") dotfile bug (ADR-0004):
        # a leading-dot local_root must not be mistaken for unsafe.
        data = self._load("valid_local_dotfile_root.json")
        self.assertEqual(config.validate_config(data), [])
        self.assertEqual(data["tracker"]["local_root"], ".agentforge/work-items")


class RootShapeTests(unittest.TestCase):
    def test_non_object_root_is_rejected(self) -> None:
        issues = config.validate_config(["not", "an", "object"])
        self.assertEqual(issue_paths(issues), {"<root>"})

    def test_unknown_top_level_field_is_rejected(self) -> None:
        data = json.loads(json.dumps(config.DEFAULT_CONFIG))
        data["extra_field"] = "surprise"
        issues = config.validate_config(data)
        self.assertIn("extra_field", issue_paths(issues))

    def test_missing_top_level_sections_are_each_reported(self) -> None:
        issues = config.validate_config({})
        self.assertEqual(
            issue_paths(issues),
            {
                "schema_version",
                "tracker",
                "identifier",
                "context",
                "traceability",
                "scope",
                "migration_policy",
                "quality",
            },
        )


class SchemaVersionTests(unittest.TestCase):
    def _base(self) -> dict:
        return json.loads(json.dumps(config.DEFAULT_CONFIG))

    def test_unsupported_schema_version_is_rejected(self) -> None:
        data = self._base()
        data["schema_version"] = 999
        issues = config.validate_config(data)
        self.assertIn("schema_version", issue_paths(issues))

    def test_non_integer_schema_version_is_rejected(self) -> None:
        data = self._base()
        data["schema_version"] = "1"
        issues = config.validate_config(data)
        self.assertIn("schema_version", issue_paths(issues))

    def test_boolean_schema_version_is_rejected(self) -> None:
        data = self._base()
        data["schema_version"] = True
        issues = config.validate_config(data)
        self.assertIn("schema_version", issue_paths(issues))

    def test_supported_schema_version_passes(self) -> None:
        data = self._base()
        data["schema_version"] = config.DEFAULT_SCHEMA_VERSION
        self.assertEqual(config.validate_config(data), [])


class TrackerValidationTests(unittest.TestCase):
    def _base(self) -> dict:
        return json.loads(json.dumps(config.DEFAULT_CONFIG))

    def test_unknown_tracker_type_is_rejected(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "jira", "repository": "acme/widgets"}
        issues = config.validate_config(data)
        self.assertIn("tracker.type", issue_paths(issues))

    def test_github_requires_repository(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "github"}
        issues = config.validate_config(data)
        self.assertIn("tracker.repository", issue_paths(issues))

    def test_github_repository_must_look_like_owner_slash_repo(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "github", "repository": "not-a-valid-repo-path"}
        issues = config.validate_config(data)
        self.assertIn("tracker.repository", issue_paths(issues))

    def test_github_rejects_local_root(self) -> None:
        data = self._base()
        data["tracker"] = {
            "type": "github",
            "repository": "acme/widgets",
            "local_root": "docs/work-items",
        }
        issues = config.validate_config(data)
        self.assertIn("tracker.local_root", issue_paths(issues))

    def test_local_requires_local_root(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "local"}
        issues = config.validate_config(data)
        self.assertIn("tracker.local_root", issue_paths(issues))

    def test_local_rejects_repository(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "local", "local_root": "docs/work-items", "repository": "acme/widgets"}
        issues = config.validate_config(data)
        self.assertIn("tracker.repository", issue_paths(issues))

    def test_local_root_absolute_path_is_rejected(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "local", "local_root": "/etc/passwd"}
        issues = config.validate_config(data)
        self.assertIn("tracker.local_root", issue_paths(issues))

    def test_local_root_traversal_is_rejected(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "local", "local_root": "docs/../../outside"}
        issues = config.validate_config(data)
        self.assertIn("tracker.local_root", issue_paths(issues))

    def test_local_root_windows_drive_letter_is_rejected(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "local", "local_root": r"C:\Users\evil"}
        issues = config.validate_config(data)
        self.assertIn("tracker.local_root", issue_paths(issues))

    def test_local_root_unc_path_is_rejected(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "local", "local_root": r"\\server\share"}
        issues = config.validate_config(data)
        self.assertIn("tracker.local_root", issue_paths(issues))

    def test_local_root_home_expansion_is_rejected(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "local", "local_root": "~/secrets"}
        issues = config.validate_config(data)
        self.assertIn("tracker.local_root", issue_paths(issues))

    def test_unknown_tracker_field_is_rejected(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "local", "local_root": "docs/work-items", "extra": True}
        issues = config.validate_config(data)
        self.assertIn("tracker.extra", issue_paths(issues))


class IdentifierValidationTests(unittest.TestCase):
    def _base(self) -> dict:
        return json.loads(json.dumps(config.DEFAULT_CONFIG))

    def test_invalid_regex_pattern_is_rejected(self) -> None:
        data = self._base()
        data["identifier"] = {"pattern": "([", "examples": ["STORY-001"]}
        issues = config.validate_config(data)
        self.assertIn("identifier.pattern", issue_paths(issues))

    def test_empty_pattern_is_rejected(self) -> None:
        data = self._base()
        data["identifier"] = {"pattern": "", "examples": ["STORY-001"]}
        issues = config.validate_config(data)
        self.assertIn("identifier.pattern", issue_paths(issues))

    def test_examples_must_be_non_empty(self) -> None:
        data = self._base()
        data["identifier"] = {"pattern": "^STORY-\\d{3,}$", "examples": []}
        issues = config.validate_config(data)
        self.assertIn("identifier.examples", issue_paths(issues))

    def test_example_not_matching_pattern_is_rejected(self) -> None:
        data = self._base()
        data["identifier"] = {"pattern": "^STORY-\\d{3,}$", "examples": ["NOT-A-MATCH"]}
        issues = config.validate_config(data)
        self.assertIn("identifier.examples[0]", issue_paths(issues))

    def test_example_partially_matching_pattern_is_rejected(self) -> None:
        # fullmatch semantics: trailing garbage after a valid prefix must fail.
        data = self._base()
        data["identifier"] = {"pattern": "^STORY-\\d{3,}$", "examples": ["STORY-001-extra"]}
        issues = config.validate_config(data)
        self.assertIn("identifier.examples[0]", issue_paths(issues))

    def test_valid_github_style_identifier(self) -> None:
        data = self._base()
        data["tracker"] = {"type": "github", "repository": "acme/widgets"}
        data["identifier"] = {"pattern": r"^#\d+$", "examples": ["#1", "#123"]}
        self.assertEqual(config.validate_config(data), [])


class ContextValidationTests(unittest.TestCase):
    def _base(self) -> dict:
        return json.loads(json.dumps(config.DEFAULT_CONFIG))

    def test_max_bytes_must_be_positive(self) -> None:
        data = self._base()
        data["context"] = {"max_bytes": 0}
        issues = config.validate_config(data)
        self.assertIn("context.max_bytes", issue_paths(issues))

    def test_max_bytes_must_not_be_negative(self) -> None:
        data = self._base()
        data["context"] = {"max_bytes": -100}
        issues = config.validate_config(data)
        self.assertIn("context.max_bytes", issue_paths(issues))

    def test_max_bytes_must_be_an_integer(self) -> None:
        data = self._base()
        data["context"] = {"max_bytes": "8000"}
        issues = config.validate_config(data)
        self.assertIn("context.max_bytes", issue_paths(issues))

    def test_max_bytes_rejects_absurdly_large_values(self) -> None:
        data = self._base()
        data["context"] = {"max_bytes": 10**9}
        issues = config.validate_config(data)
        self.assertIn("context.max_bytes", issue_paths(issues))


class TraceabilityValidationTests(unittest.TestCase):
    def _base(self) -> dict:
        return json.loads(json.dumps(config.DEFAULT_CONFIG))

    def test_unknown_mode_is_rejected(self) -> None:
        data = self._base()
        data["traceability"] = {"mode": "block-everything"}
        issues = config.validate_config(data)
        self.assertIn("traceability.mode", issue_paths(issues))

    def test_enforce_mode_is_a_valid_value(self) -> None:
        data = self._base()
        data["traceability"] = {"mode": "enforce"}
        self.assertEqual(config.validate_config(data), [])


class ScopeValidationTests(unittest.TestCase):
    def _base(self) -> dict:
        return json.loads(json.dumps(config.DEFAULT_CONFIG))

    def test_unknown_mode_is_rejected(self) -> None:
        data = self._base()
        data["scope"] = {"mode": "yolo", "agents": {}}
        issues = config.validate_config(data)
        self.assertIn("scope.mode", issue_paths(issues))

    def test_all_documented_modes_are_valid(self) -> None:
        for mode in ("off", "observe", "ask", "deny-structured", "strict-agent"):
            data = self._base()
            data["scope"] = {"mode": mode, "agents": {}}
            self.assertEqual(config.validate_config(data), [], msg=mode)

    def test_agents_allow_list_traversal_is_rejected(self) -> None:
        data = self._base()
        data["scope"] = {
            "mode": "deny-structured",
            "agents": {"reviewer": {"allow": ["src/../../etc"]}},
        }
        issues = config.validate_config(data)
        self.assertIn("scope.agents.reviewer.allow[0]", issue_paths(issues))

    def test_agents_allow_list_absolute_path_is_rejected(self) -> None:
        data = self._base()
        data["scope"] = {
            "mode": "deny-structured",
            "agents": {"reviewer": {"allow": ["/etc/passwd"]}},
        }
        issues = config.validate_config(data)
        self.assertIn("scope.agents.reviewer.allow[0]", issue_paths(issues))

    def test_agents_allow_list_valid_relative_paths_pass(self) -> None:
        data = self._base()
        data["scope"] = {
            "mode": "deny-structured",
            "agents": {"reviewer": {"allow": ["src/", ".github/workflows/", ".env"]}},
        }
        self.assertEqual(config.validate_config(data), [])

    def test_invalid_agent_name_is_rejected(self) -> None:
        data = self._base()
        data["scope"] = {
            "mode": "deny-structured",
            "agents": {"../escape": {"allow": ["src/"]}},
        }
        issues = config.validate_config(data)
        self.assertTrue(any(p.startswith("scope.agents.") for p in issue_paths(issues)))

    def test_agents_must_be_an_object(self) -> None:
        data = self._base()
        data["scope"] = {"mode": "off", "agents": ["not", "a", "mapping"]}
        issues = config.validate_config(data)
        self.assertIn("scope.agents", issue_paths(issues))


class MigrationPolicyValidationTests(unittest.TestCase):
    def _base(self) -> dict:
        return json.loads(json.dumps(config.DEFAULT_CONFIG))

    def test_enabled_must_be_boolean(self) -> None:
        data = self._base()
        data["migration_policy"] = {"enabled": "yes"}
        issues = config.validate_config(data)
        self.assertIn("migration_policy.enabled", issue_paths(issues))

    def test_enabled_true_is_valid(self) -> None:
        data = self._base()
        data["migration_policy"] = {"enabled": True}
        self.assertEqual(config.validate_config(data), [])


class QualityValidationTests(unittest.TestCase):
    def _base(self) -> dict:
        return json.loads(json.dumps(config.DEFAULT_CONFIG))

    def test_only_off_and_report_are_valid(self) -> None:
        for mode in ("off", "report"):
            data = self._base()
            data["quality"] = {"post_edit": mode}
            self.assertEqual(config.validate_config(data), [], msg=mode)

    def test_fix_mode_is_rejected(self) -> None:
        # STORY-015 removed silent auto-fix mutation; the schema must never
        # let a project re-enable it through config.
        data = self._base()
        data["quality"] = {"post_edit": "fix"}
        issues = config.validate_config(data)
        self.assertIn("quality.post_edit", issue_paths(issues))

    def test_enforce_mode_is_rejected(self) -> None:
        data = self._base()
        data["quality"] = {"post_edit": "enforce"}
        issues = config.validate_config(data)
        self.assertIn("quality.post_edit", issue_paths(issues))


class ConfigValidationErrorTests(unittest.TestCase):
    def test_error_message_lists_every_issue(self) -> None:
        issues = [
            config.ConfigIssue("tracker.type", "must be one of (...)", value="jira"),
            config.ConfigIssue("schema_version", "is required"),
        ]
        error = config.ConfigValidationError(issues)
        message = str(error)
        self.assertIn("tracker.type", message)
        self.assertIn("schema_version", message)

    def test_issues_attribute_preserves_order(self) -> None:
        issues = [
            config.ConfigIssue("a", "first"),
            config.ConfigIssue("b", "second"),
        ]
        error = config.ConfigValidationError(issues)
        self.assertEqual([i.path for i in error.issues], ["a", "b"])


class EnforcementLoadingTests(unittest.TestCase):
    def test_valid_file_loads_successfully(self) -> None:
        result = config.load_for_enforcement(FIXTURES / "valid_local.json")
        self.assertEqual(result["tracker"]["type"], "local")

    def test_invalid_file_raises_hard(self) -> None:
        with self.assertRaises(config.ConfigValidationError):
            config.load_for_enforcement(FIXTURES / "invalid_regex.json")

    def test_malformed_json_raises_hard(self) -> None:
        with self.assertRaises(config.ConfigValidationError):
            config.load_for_enforcement(FIXTURES / "malformed.json")

    def test_absolute_local_root_raises_hard(self) -> None:
        with self.assertRaises(config.ConfigValidationError):
            config.load_for_enforcement(FIXTURES / "invalid_absolute_local_root.json")

    def test_traversal_path_raises_hard(self) -> None:
        with self.assertRaises(config.ConfigValidationError):
            config.load_for_enforcement(FIXTURES / "invalid_traversal_path.json")

    def test_unknown_policy_mode_raises_hard(self) -> None:
        with self.assertRaises(config.ConfigValidationError):
            config.load_for_enforcement(FIXTURES / "invalid_scope_mode.json")

    def test_unsupported_schema_version_raises_hard(self) -> None:
        with self.assertRaises(config.ConfigValidationError):
            config.load_for_enforcement(FIXTURES / "invalid_schema_version.json")

    def test_unknown_field_raises_hard(self) -> None:
        with self.assertRaises(config.ConfigValidationError):
            config.load_for_enforcement(FIXTURES / "invalid_unknown_field.json")


class ObservationLoadingTests(unittest.TestCase):
    def test_valid_file_returns_config_and_no_issues(self) -> None:
        data, issues = config.load_for_observation(FIXTURES / "valid_local.json")
        self.assertIsNotNone(data)
        self.assertEqual(issues, [])

    def test_invalid_file_never_raises(self) -> None:
        try:
            data, issues = config.load_for_observation(FIXTURES / "invalid_regex.json")
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"observation loader raised {exc!r} instead of returning diagnostics")
        self.assertIsNone(data)
        self.assertTrue(issues)

    def test_malformed_json_never_raises(self) -> None:
        data, issues = config.load_for_observation(FIXTURES / "malformed.json")
        self.assertIsNone(data)
        self.assertTrue(issues)

    def test_missing_file_never_raises(self) -> None:
        data, issues = config.load_for_observation(FIXTURES / "does_not_exist.json")
        self.assertIsNone(data)
        self.assertTrue(issues)

    def test_diagnostic_identifies_config_path_and_value(self) -> None:
        _, issues = config.load_for_observation(FIXTURES / "invalid_absolute_local_root.json")
        formatted = "\n".join(issue.format() for issue in issues)
        self.assertIn("tracker.local_root", formatted)
        self.assertIn("/etc/passwd", formatted)

    def test_diagnostic_does_not_leak_environment_data(self) -> None:
        os.environ["AGENTFORGE_TEST_SECRET_TOKEN"] = "should-not-leak"
        try:
            _, issues = config.load_for_observation(FIXTURES / "invalid_regex.json")
        finally:
            del os.environ["AGENTFORGE_TEST_SECRET_TOKEN"]
        formatted = "\n".join(issue.format() for issue in issues)
        self.assertNotIn("should-not-leak", formatted)
        self.assertNotIn("AGENTFORGE_TEST_SECRET_TOKEN", formatted)


class CommandLineTests(unittest.TestCase):
    def test_enforce_mode_exits_nonzero_on_invalid_config(self) -> None:
        exit_code = config.main([str(FIXTURES / "invalid_regex.json"), "--mode", "enforce"])
        self.assertNotEqual(exit_code, 0)

    def test_enforce_mode_exits_zero_on_valid_config(self) -> None:
        exit_code = config.main([str(FIXTURES / "valid_local.json"), "--mode", "enforce"])
        self.assertEqual(exit_code, 0)

    def test_observe_mode_always_exits_zero(self) -> None:
        exit_code = config.main([str(FIXTURES / "invalid_regex.json"), "--mode", "observe"])
        self.assertEqual(exit_code, 0)

    def test_default_mode_is_enforce(self) -> None:
        exit_code = config.main([str(FIXTURES / "invalid_regex.json")])
        self.assertNotEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
