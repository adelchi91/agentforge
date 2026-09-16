"""Characterization tests for the v1 hook suite (templates/shared/hooks/).

These describe CURRENT behavior as of the agentforge-v1.1.0-pre-v2 tag,
including known weaknesses the v2 execution plan (docs/plans/
agentforge-v2-execution-plan.md) has already decided to fix. A test failing
here means v1 behavior changed underneath us; it is not a spec for v2.
None of these tests bless the weak behavior as correct, and none of them
edit templates/shared/hooks/*.py.

Covered characterizations:
  1. Dotfile normalization strips the leading dot (pre_tool_use.normalise).
  2. A relative ".." path escapes scope checking undetected.
  3. `git -C <dir> push` bypasses the STORY-XXX push check.
  4. A STORY-XXX token anywhere in the Bash command line satisfies the
     commit check, even outside the actual commit message.
  5. Bash-driven file writes are never scope-checked (only structured
     Write/Edit/MultiEdit/NotebookEdit/apply_patch tool calls are).
  6. Malformed JSON on stdin fails open (allowed) instead of blocking.
  7. PreCompact's session-log record is never read back by SessionStart,
     so it does not actually restore anything after compaction.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "templates" / "shared" / "hooks"


def load_hook(module_name: str, filename: str) -> types.ModuleType:
    path = HOOKS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main_with_stdin(module: types.ModuleType, raw: str) -> int:
    with mock.patch.object(sys, "stdin", io.StringIO(raw)):
        return module.main()


class DotfileNormalizationTests(unittest.TestCase):
    """Characterizes the lstrip("./") bug in pre_tool_use.normalise."""

    def setUp(self) -> None:
        self.pre_tool_use = load_hook("v1_pre_tool_use_dotfile", "pre_tool_use.py")

    def test_leading_dot_is_stripped_from_relative_dotfile(self) -> None:
        # ".env" should stay ".env"; str.lstrip("./") strips leading '.'
        # and '/' characters one at a time, not the "./" prefix as a unit.
        result = self.pre_tool_use.normalise(".env", Path("/project"))
        self.assertEqual(result, "env")
        self.assertNotEqual(result, ".env")

    def test_ordinary_relative_path_is_unaffected(self) -> None:
        result = self.pre_tool_use.normalise("src/main.py", Path("/project"))
        self.assertEqual(result, "src/main.py")


class DotDotScopeEscapeTests(unittest.TestCase):
    """Characterizes the missing ".." resolution for relative scope paths."""

    def setUp(self) -> None:
        self.pre_tool_use = load_hook("v1_pre_tool_use_dotdot", "pre_tool_use.py")
        self.pre_tool_use.load_scopes = lambda: {"dev": {"allow": ["allowed/"]}}

    def test_relative_dotdot_escape_is_not_blocked(self) -> None:
        tool_input = {"file_path": "allowed/../../outside/evil.py"}
        try:
            self.pre_tool_use.check_scope("dev", tool_input, Path("/project"))
        except SystemExit:
            self.fail(
                "check_scope blocked an escaping relative path; v1 is known "
                "to let 'allowed/../../outside/evil.py' through because "
                "relative paths are never resolve()'d before the prefix check."
            )

    def test_absolute_dotdot_escape_is_blocked(self) -> None:
        # Contrast case: the absolute-path branch does call resolve(), so
        # an absolute escape is correctly rejected today.
        tool_input = {"file_path": "/project/allowed/../../outside/evil.py"}
        with self.assertRaises(SystemExit):
            self.pre_tool_use.check_scope("dev", tool_input, Path("/project"))


class GitDashCPushBypassTests(unittest.TestCase):
    """Characterizes `\\bgit\\s+push\\b` missing `git -C <dir> push`."""

    def setUp(self) -> None:
        self.pre_tool_use = load_hook("v1_pre_tool_use_dashc", "pre_tool_use.py")

    def test_git_dash_c_push_is_not_checked(self) -> None:
        self.pre_tool_use.latest_commit_subject = lambda: "fix typo, no story ref"
        try:
            self.pre_tool_use.check_bash("git -C /some/repo push origin main")
        except SystemExit:
            self.fail(
                "check_bash blocked 'git -C <dir> push'; v1 is known to miss "
                "this form because the regex requires 'git' and 'push' to be "
                "separated only by whitespace."
            )

    def test_plain_git_push_without_story_is_blocked(self) -> None:
        # Contrast case: the exact adjacent form IS caught today.
        self.pre_tool_use.latest_commit_subject = lambda: "fix typo, no story ref"
        with self.assertRaises(SystemExit):
            self.pre_tool_use.check_bash("git push origin main")


class StoryTokenOutsideMessageTests(unittest.TestCase):
    """Characterizes STORY-XXX matching anywhere in the command line."""

    def setUp(self) -> None:
        self.pre_tool_use = load_hook("v1_pre_tool_use_token", "pre_tool_use.py")

    def test_story_token_in_unrelated_argument_satisfies_the_check(self) -> None:
        # The actual -m message has no story reference; the token only
        # appears in an unrelated --file argument.
        command = 'git commit --file=STORY-001.md -m "no story reference at all"'
        try:
            self.pre_tool_use.check_bash(command)
        except SystemExit:
            self.fail(
                "check_bash blocked a commit whose message lacks a STORY-XXX "
                "reference; v1 is known to accept a token found anywhere in "
                "the raw command string, not just inside the message."
            )

    def test_commit_with_no_story_token_anywhere_is_blocked(self) -> None:
        with self.assertRaises(SystemExit):
            self.pre_tool_use.check_bash('git commit -m "no story reference at all"')


class BashWriteScopeBypassTests(unittest.TestCase):
    """Characterizes scope enforcement never inspecting Bash tool calls."""

    def setUp(self) -> None:
        self.pre_tool_use = load_hook("v1_pre_tool_use_bashwrite", "pre_tool_use.py")
        self.pre_tool_use.load_scopes = lambda: {"dev": {"allow": ["allowed/"]}}

    def test_bash_redirection_outside_scope_is_not_checked(self) -> None:
        payload = {
            "tool_name": "Bash",
            "agent_type": "dev",
            "cwd": "/project",
            "tool_input": {"command": "echo secret > outside/evil.txt"},
        }
        result = run_main_with_stdin(self.pre_tool_use, json.dumps(payload))
        self.assertEqual(
            result,
            0,
            "main() blocked a Bash write outside the agent's scope; v1 is "
            "known to only scope-check structured Write/Edit/MultiEdit/"
            "NotebookEdit/apply_patch tool calls, never Bash.",
        )

    def test_structured_write_outside_scope_is_checked(self) -> None:
        # Contrast case: the same escaping path IS blocked through Write.
        payload = {
            "tool_name": "Write",
            "agent_type": "dev",
            "cwd": "/project",
            "tool_input": {"file_path": "outside/evil.py"},
        }
        with self.assertRaises(SystemExit):
            run_main_with_stdin(self.pre_tool_use, json.dumps(payload))


class MalformedJsonFailsOpenTests(unittest.TestCase):
    """Characterizes load_payload() swallowing JSON errors and allowing."""

    def test_malformed_json_on_stdin_is_allowed_not_blocked(self) -> None:
        pre_tool_use = load_hook("v1_pre_tool_use_badjson", "pre_tool_use.py")
        result = run_main_with_stdin(pre_tool_use, "{not valid json")
        self.assertEqual(
            result,
            0,
            "pre_tool_use.main() is expected to fail open (return 0) on "
            "malformed JSON today; it is a hard-block hook that should "
            "eventually fail closed instead.",
        )

    def test_empty_stdin_is_also_allowed(self) -> None:
        pre_tool_use = load_hook("v1_pre_tool_use_emptystdin", "pre_tool_use.py")
        result = run_main_with_stdin(pre_tool_use, "")
        self.assertEqual(result, 0)


class PreCompactLogNotRestoredTests(unittest.TestCase):
    """Characterizes the PreCompact log being write-only.

    pre_compact.py appends a COMPACT record to session-log.txt, but
    session_start.py never opens that file — it only re-derives the active
    story from `git branch --show-current` / `git log -1`. If git can no
    longer supply a story id (detached HEAD, branch renamed, squashed
    commit, ...), the compaction record is unrecoverable even though it
    was faithfully written.
    """

    def setUp(self) -> None:
        self.pre_compact = load_hook("v1_pre_compact_restore", "pre_compact.py")
        self.session_start = load_hook("v1_session_start_restore", "session_start.py")

    def test_session_start_source_never_reads_the_precompact_log(self) -> None:
        import inspect

        source = inspect.getsource(self.session_start)
        self.assertNotIn(
            "session-log",
            source,
            "session_start.py now references session-log.txt; if this "
            "starts passing, PreCompact's record is being restored and "
            "this characterization test (and STORY-009's scope) should "
            "be revisited.",
        )

    def test_precompact_record_is_unrecoverable_once_git_cannot_supply_a_story(self) -> None:
        # Simulate: pre_compact ran earlier and captured STORY-042 from git,
        # but by the time session_start runs (e.g. after a branch rename or
        # detached HEAD), git can no longer supply any story id.
        self.pre_compact.git_output = lambda args, fallback: (
            "STORY-042: implement the thing" if args[:1] == ["log"] else "feature/renamed"
        )
        # session_start's own git_output has a different signature (no
        # fallback arg) — simulate git giving up entirely, which is exactly
        # the scenario where the earlier PreCompact record would matter.
        self.session_start.git_output = lambda args: ""

        log_lines_before = []
        log_path = HOOKS_DIR.parent / "session-log.txt"
        if log_path.exists():
            log_lines_before = log_path.read_text(encoding="utf-8").splitlines()

        try:
            with mock.patch.object(sys, "stdin", io.StringIO("")):
                self.pre_compact.main()
            additional_context = self._session_start_context()
        finally:
            # Clean up any record this test appended to the real repo tree.
            if log_path.exists():
                current = log_path.read_text(encoding="utf-8").splitlines()
                restored = "\n".join(
                    current[: len(log_lines_before)]
                ) + ("\n" if log_lines_before else "")
                if log_lines_before:
                    log_path.write_text(restored, encoding="utf-8")
                else:
                    log_path.unlink()

        self.assertIsNone(
            additional_context,
            "session_start produced additionalContext derived from the "
            "PreCompact log; v1 is known to have no such recovery path, so "
            "with git unable to supply a story id the session should start "
            "with nothing.",
        )

    def _session_start_context(self):
        result = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO("")), mock.patch.object(
            sys, "stdout", result
        ):
            self.session_start.main()
        text = result.getvalue().strip()
        if not text:
            return None
        return json.loads(text)


if __name__ == "__main__":
    unittest.main()
