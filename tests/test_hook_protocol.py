"""Tests for the STORY-013 PreToolUse hook protocol (scripts/scope_policy.py
`main()`): stdin JSON in, `hookSpecificOutput` JSON out, diagnostics on
stderr only.

Covers:
  - scope.mode is read from the project's `.agentforge/config.json`
    (resolved from the hook payload's `cwd`), not from an argument.
  - `off` performs no evaluation at all: no stdout, exit 0, even on a
    malformed payload.
  - `observe` warns to stderr and continues (allows) on a malformed
    payload -- this is the one case where a blocking-shaped bug is
    intentionally *not* reproduced from v1: v1 failed open unconditionally
    (tests/test_v1_characterization.py::MalformedJsonFailsOpenTests); here
    fail-open is scoped to observe/off only.
  - `ask`, `deny-structured`, and `strict-agent` all return a clear deny
    response on a malformed payload (fail closed under any blocking mode).
  - stdout carries only the hook protocol JSON; everything else is on
    stderr.
  - A valid payload flows through to a `permissionDecision` matching the
    classification and configured mode.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config as agentforge_config  # noqa: E402
from scripts import scope_policy  # noqa: E402


def write_config(project_dir: Path, mode: str, agents: dict | None = None) -> None:
    cfg = json.loads(json.dumps(agentforge_config.DEFAULT_CONFIG))  # deep copy
    cfg["scope"]["mode"] = mode
    if agents is not None:
        cfg["scope"]["agents"] = agents
    config_dir = project_dir / ".agentforge"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


def run_hook(raw_stdin: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO(raw_stdin)):
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = scope_policy.main()
    return exit_code, out.getvalue(), err.getvalue()


def parse_permission_decision(stdout_text: str) -> dict:
    payload = json.loads(stdout_text)
    return payload["hookSpecificOutput"]


class PreToolUseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_dir = Path(self._tmp.name)

    # -- off mode: no hook policy at all -----------------------------

    def test_off_mode_produces_no_stdout_for_a_valid_payload(self) -> None:
        write_config(self.project_dir, "off")
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": "git reset --hard"},
        }
        exit_code, out, _err = run_hook(json.dumps(payload))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_off_mode_produces_no_stdout_for_a_malformed_payload(self) -> None:
        write_config(self.project_dir, "off")
        # off mode can't even know the payload's cwd, so it resolves
        # config from the process cwd; run from inside the project dir.
        with mock.patch.object(Path, "cwd", return_value=self.project_dir):
            exit_code, out, _err = run_hook("{not valid json")
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    # -- malformed payload: fails open only in off/observe -----------

    def test_malformed_json_under_observe_mode_warns_and_allows(self) -> None:
        write_config(self.project_dir, "observe")
        with mock.patch.object(Path, "cwd", return_value=self.project_dir):
            exit_code, out, err = run_hook("{not valid json")
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "", "observe mode must not emit a deny/ask on a malformed payload")
        self.assertIn("malformed", err.lower())

    def test_empty_stdin_under_observe_mode_warns_and_allows(self) -> None:
        write_config(self.project_dir, "observe")
        with mock.patch.object(Path, "cwd", return_value=self.project_dir):
            exit_code, out, err = run_hook("")
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertIn("malformed", err.lower())

    def test_malformed_json_under_ask_mode_denies(self) -> None:
        write_config(self.project_dir, "ask")
        with mock.patch.object(Path, "cwd", return_value=self.project_dir):
            exit_code, out, _err = run_hook("{not valid json")
        self.assertEqual(exit_code, 0)
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("malformed", decision["permissionDecisionReason"].lower())

    def test_malformed_json_under_deny_structured_mode_denies(self) -> None:
        write_config(self.project_dir, "deny-structured")
        with mock.patch.object(Path, "cwd", return_value=self.project_dir):
            exit_code, out, _err = run_hook("{not valid json")
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_malformed_json_under_strict_agent_mode_denies(self) -> None:
        write_config(self.project_dir, "strict-agent")
        with mock.patch.object(Path, "cwd", return_value=self.project_dir):
            exit_code, out, _err = run_hook("{not valid json")
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_empty_stdin_under_a_blocking_mode_denies(self) -> None:
        write_config(self.project_dir, "ask")
        with mock.patch.object(Path, "cwd", return_value=self.project_dir):
            exit_code, out, _err = run_hook("")
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_non_object_json_under_a_blocking_mode_denies(self) -> None:
        write_config(self.project_dir, "ask")
        with mock.patch.object(Path, "cwd", return_value=self.project_dir):
            exit_code, out, _err = run_hook("[1, 2, 3]")
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "deny")

    # -- valid payloads flow through to the expected decision --------

    def test_ask_mode_valid_payload_destructive_bash_asks(self) -> None:
        write_config(self.project_dir, "ask")
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": "git push --force origin main"},
        }
        exit_code, out, _err = run_hook(json.dumps(payload))
        self.assertEqual(exit_code, 0)
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "ask")
        self.assertEqual(decision["hookEventName"], "PreToolUse")

    def test_ask_mode_valid_payload_read_only_bash_allows(self) -> None:
        write_config(self.project_dir, "ask")
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": "git status"},
        }
        _exit_code, out, _err = run_hook(json.dumps(payload))
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "allow")

    def test_observe_mode_valid_payload_logs_and_allows(self) -> None:
        write_config(self.project_dir, "observe")
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": "git reset --hard"},
        }
        _exit_code, out, err = run_hook(json.dumps(payload))
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "allow")
        self.assertIn("known-destructive", err)

    def test_strict_agent_mode_denies_without_agent_type(self) -> None:
        write_config(self.project_dir, "strict-agent")
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": "git status"},
        }
        _exit_code, out, _err = run_hook(json.dumps(payload))
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_strict_agent_mode_allows_configured_agent_known_read(self) -> None:
        write_config(self.project_dir, "strict-agent", agents={"dev": {"allow": ["src/"]}})
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "agent_type": "dev",
            "tool_input": {"command": "git status"},
        }
        _exit_code, out, _err = run_hook(json.dumps(payload))
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "allow")

    def test_structured_write_tool_under_ask_mode_asks(self) -> None:
        write_config(self.project_dir, "ask")
        payload = {
            "tool_name": "Write",
            "cwd": str(self.project_dir),
            "tool_input": {"file_path": "src/main.py"},
        }
        _exit_code, out, _err = run_hook(json.dumps(payload))
        decision = parse_permission_decision(out)
        self.assertEqual(decision["permissionDecision"], "ask")

    # -- protocol hygiene ---------------------------------------------

    def test_stdout_contains_only_the_hook_json_no_extra_lines(self) -> None:
        write_config(self.project_dir, "ask")
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": "git status"},
        }
        _exit_code, out, _err = run_hook(json.dumps(payload))
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        json.loads(lines[0])  # must be exactly one JSON document

    def test_missing_config_file_falls_back_to_off_and_allows_silently(self) -> None:
        # No .agentforge/config.json at all: DEFAULT_CONFIG (scope.mode
        # "off") applies, not an error.
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": "git reset --hard"},
        }
        exit_code, out, _err = run_hook(json.dumps(payload))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_invalid_config_file_warns_and_falls_back_to_off(self) -> None:
        config_dir = self.project_dir / ".agentforge"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text("{not valid json", encoding="utf-8")
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": "git reset --hard"},
        }
        exit_code, out, err = run_hook(json.dumps(payload))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertIn("scope.mode=off", err)

    def test_never_shells_out_with_the_command_text(self) -> None:
        # Never interpolate command text into another shell command
        # (STORY-013 requirement): classification must not invoke
        # subprocess at all.
        write_config(self.project_dir, "ask")
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": "git status; touch /tmp/should-not-run-$$"},
        }
        with mock.patch("subprocess.run", side_effect=AssertionError("must not shell out")):
            with mock.patch("subprocess.Popen", side_effect=AssertionError("must not shell out")):
                exit_code, out, _err = run_hook(json.dumps(payload))
        self.assertEqual(exit_code, 0)
        parse_permission_decision(out)  # did not raise -> no subprocess call happened


if __name__ == "__main__":
    unittest.main()
