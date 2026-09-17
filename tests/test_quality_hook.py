"""Tests for the STORY-015 PostToolUse quality-report hook
(templates/shared/hooks/post_tool_use.py).

STORY-015 deletes v1's silent `ruff --fix` / `eslint --fix` behavior. These
tests prove the replacement:

  - never mutates the edited file, even when the installed tool would
    happily rewrite it under `--fix` (the checksum-equality acceptance
    criterion, demonstrated against a fake `ruff` that only rewrites the
    file when given `--fix` — proving the hook never passes that flag);
  - is off by default and stays off for a missing/invalid/undecodable
    config, matching the STORY-004 default (`quality.post_edit: "off"`);
  - only reads the single explicit path a structured Write/Edit/MultiEdit
    tool call names in its own `tool_input` (accepting the lowercase
    `write`/`edit` Codex variants too), never scanning Bash commands,
    apply_patch hunks, or other free-text tool input for path-like tokens;
  - reports command, exit status, and bounded output back to the agent as
    `hookSpecificOutput.additionalContext`, never by mutating the file;
  - covers a missing tool, a command timeout, a nonzero exit status,
    multiple candidate files in one patch-style call, and an unknown tool
    name, per the story's acceptance criteria;
  - never crashes (always exits 0) on a malformed `cwd`, undecodable tool
    output, or an unrecognized internal report shape.
"""

from __future__ import annotations

import importlib.util
import io
import json
import stat
import subprocess as real_subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any, Optional
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "templates" / "shared" / "hooks"

_load_counter = 0


def load_hook() -> types.ModuleType:
    global _load_counter
    _load_counter += 1
    path = HOOKS_DIR / "post_tool_use.py"
    spec = importlib.util.spec_from_file_location(f"quality_hook_{_load_counter}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main_with_stdin(module: types.ModuleType, raw: str) -> int:
    with mock.patch.object(sys, "stdin", io.StringIO(raw)):
        return module.main()


def write_config(target_dir: Path, post_edit: str) -> None:
    config_dir = target_dir / ".agentforge"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tracker": {"type": "local", "local_root": "docs/work-items"},
                "identifier": {"pattern": "^STORY-\\d{3,}$", "examples": ["STORY-001"]},
                "context": {"max_bytes": 8000},
                "traceability": {"mode": "off"},
                "scope": {"mode": "off", "agents": {}},
                "migration_policy": {"enabled": False},
                "quality": {"post_edit": post_edit},
            }
        ),
        encoding="utf-8",
    )


FAKE_RUFF_SCRIPT = """#!/bin/sh
# Fake ruff: only "fixes" (mutates) the target file when given --fix.
# In check mode it never touches the file, prints a lint finding, and
# exits 1 (a real lint failure), so tests can prove the hook (a) never
# passes --fix and (b) faithfully reports a nonzero exit status.
for arg in "$@"; do
  if [ "$arg" = "--fix" ]; then
    for a in "$@"; do
      case "$a" in
        --fix|check|--quiet) ;;
        *) echo "FIXED" > "$a" ;;
      esac
    done
    exit 0
  fi
done
echo "target.py:1:1: F401 'os' imported but unused"
exit 1
"""


def install_fake_tool(bin_dir: Path, name: str, script: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    tool_path = bin_dir / name
    tool_path.write_text(script, encoding="utf-8")
    tool_path.chmod(tool_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class QualityHookTestCase(unittest.TestCase):
    """Shared fixture for every test below: a fresh module load (hook
    scripts are stateless, but each test gets its own module object to
    mock independently), a temp project directory, and helpers for writing
    `.agentforge/config.json` and target files, and for invoking the hook
    with stdout captured and parsed as JSON."""

    def setUp(self) -> None:
        self.module = load_hook()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project_dir = Path(self.tmp.name)

    def write_config(self, post_edit: str, *, at: Optional[Path] = None) -> None:
        write_config(at if at is not None else self.project_dir, post_edit)

    def write_target(self, name: str = "target.py", content: str = "import os\n") -> Path:
        target = self.project_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def run_hook(self, payload: dict[str, Any]) -> tuple[int, Optional[dict]]:
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdout", stdout):
            result = run_main_with_stdin(self.module, json.dumps(payload))
        text = stdout.getvalue().strip()
        emitted = json.loads(text) if text else None
        return result, emitted

    @staticmethod
    def context_of(emitted: dict) -> str:
        return emitted["hookSpecificOutput"]["additionalContext"]

    def payload(self, tool_name: str, file_path: Path, **extra_tool_input: Any) -> dict[str, Any]:
        tool_input = {"file_path": str(file_path), **extra_tool_input}
        return {"tool_name": tool_name, "cwd": str(self.project_dir), "tool_input": tool_input}


class ChecksumUnchangedTests(QualityHookTestCase):
    """The acceptance criterion: file checksums identical before and after
    the quality hook runs, even against a tool that WOULD have mutated the
    file if invoked with --fix (the deleted v1 behavior)."""

    def setUp(self) -> None:
        super().setUp()
        self.write_config("report")
        self.bin_dir = self.project_dir / "fakebin"
        install_fake_tool(self.bin_dir, "ruff", FAKE_RUFF_SCRIPT)
        self.target = self.write_target()

    def test_file_bytes_are_unchanged_after_report_mode_check(self) -> None:
        before = self.target.read_bytes()

        with mock.patch.dict(
            "os.environ", {"PATH": f"{self.bin_dir}:{__import__('os').environ.get('PATH', '')}"}
        ):
            result, _ = self.run_hook(self.payload("Write", self.target))

        after = self.target.read_bytes()
        self.assertEqual(result, 0)
        self.assertEqual(before, after, "quality hook must never mutate the edited file")
        self.assertEqual(after, b"import os\n")


class DefaultOffTests(QualityHookTestCase):
    """Default configuration must not run a linter on every edit."""

    def setUp(self) -> None:
        super().setUp()
        self.target = self.write_target()

    def test_missing_config_file_does_not_run_a_check(self) -> None:
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(self.payload("Write", self.target))
        run.assert_not_called()
        self.assertEqual(result, 0)

    def test_explicit_off_config_does_not_run_a_check(self) -> None:
        self.write_config("off")
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(self.payload("Write", self.target))
        run.assert_not_called()
        self.assertEqual(result, 0)

    def test_malformed_config_json_fails_safe_to_off(self) -> None:
        config_dir = self.project_dir / ".agentforge"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text("{not valid json", encoding="utf-8")
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(self.payload("Write", self.target))
        run.assert_not_called()
        self.assertEqual(result, 0)

    def test_unrecognised_post_edit_value_fails_safe_to_off(self) -> None:
        self.write_config("fix")  # not a valid mode; never mutate
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(self.payload("Write", self.target))
        run.assert_not_called()
        self.assertEqual(result, 0)

    def test_config_with_invalid_utf8_bytes_fails_safe_to_off(self) -> None:
        # Reported by code review: read_text(encoding="utf-8") alone raises
        # UnicodeDecodeError on undecodable bytes; the hook must catch that
        # too, not just OSError, and still exit 0 with no check run.
        config_dir = self.project_dir / ".agentforge"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_bytes(b"\xff\xfe{not even close to json")
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(self.payload("Write", self.target))
        run.assert_not_called()
        self.assertEqual(result, 0)


class ConfigDiscoveryTests(QualityHookTestCase):
    """`.agentforge/config.json` is found by walking upward from `cwd`,
    mirroring how Git locates `.git` from a subdirectory — e.g. a monorepo
    package whose hook payload `cwd` is not the repository root."""

    def test_config_in_an_ancestor_directory_is_found_from_a_nested_cwd(self) -> None:
        self.write_config("report")  # lives at self.project_dir/.agentforge/config.json
        nested = self.project_dir / "packages" / "app"
        nested.mkdir(parents=True)
        target = nested / "target.py"
        target.write_text("import os\n", encoding="utf-8")

        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/ruff"):
            with mock.patch.object(self.module.subprocess, "run", return_value=completed) as run:
                payload = {
                    "tool_name": "Write",
                    "cwd": str(nested),
                    "tool_input": {"file_path": str(target)},
                }
                result, _ = self.run_hook(payload)
        self.assertEqual(result, 0)
        run.assert_called_once()

    def test_no_config_anywhere_above_cwd_stays_off(self) -> None:
        # self.project_dir has no .agentforge/ at all, nor (presumably) does
        # any of its ancestors up to the filesystem root.
        target = self.write_target()
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(self.payload("Write", target))
        run.assert_not_called()
        self.assertEqual(result, 0)


class MalformedCwdTests(QualityHookTestCase):
    """A `cwd` that is present but not a string must not crash the hook."""

    def test_non_string_cwd_falls_back_without_crashing(self) -> None:
        target = self.write_target()
        payload = {
            "tool_name": "Write",
            "cwd": 12345,
            "tool_input": {"file_path": str(target)},
        }
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(payload)
        run.assert_not_called()  # no config found relative to "."; fails safe to off
        self.assertEqual(result, 0)

    def test_missing_cwd_falls_back_without_crashing(self) -> None:
        target = self.write_target()
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(target)}}
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(payload)
        run.assert_not_called()
        self.assertEqual(result, 0)


class StructuredPathOnlyTests(QualityHookTestCase):
    """Only the explicit path in Write/Edit/MultiEdit tool_input is used;
    Bash and other free-text tool input are never scanned for path-like
    tokens, even when they obviously contain one."""

    def setUp(self) -> None:
        super().setUp()
        self.write_config("report")
        self.target = self.write_target()

    def test_bash_command_mentioning_a_path_is_not_scanned(self) -> None:
        payload = {
            "tool_name": "Bash",
            "cwd": str(self.project_dir),
            "tool_input": {"command": f"ruff check {self.target}"},
        }
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(payload)
        run.assert_not_called()
        self.assertEqual(result, 0)

    def test_unsupported_tool_name_is_skipped_with_diagnostic(self) -> None:
        payload = {
            "tool_name": "NotebookEdit",
            "cwd": str(self.project_dir),
            "tool_input": {"notebook_path": str(self.target)},
        }
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, emitted = self.run_hook(payload)
        run.assert_not_called()
        self.assertEqual(result, 0)
        self.assertIn("skipped", self.context_of(emitted).lower())

    def test_apply_patch_touching_multiple_files_is_skipped_not_guessed(self) -> None:
        payload = {
            "tool_name": "apply_patch",
            "cwd": str(self.project_dir),
            "tool_input": {
                "patch": (
                    "*** Begin Patch\n"
                    "*** Update File: target.py\n"
                    "*** Update File: other.py\n"
                    "*** End Patch\n"
                )
            },
        }
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, emitted = self.run_hook(payload)
        run.assert_not_called()
        self.assertEqual(result, 0)
        self.assertIn("skipped", self.context_of(emitted).lower())

    def test_multiedit_uses_its_own_structured_file_path(self) -> None:
        payload = {
            "tool_name": "MultiEdit",
            "cwd": str(self.project_dir),
            "tool_input": {
                "file_path": str(self.target),
                "edits": [{"old_string": "import os", "new_string": "import sys"}],
            },
        }
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/ruff"):
            with mock.patch.object(self.module.subprocess, "run", return_value=completed) as run:
                result, _ = self.run_hook(payload)
        self.assertEqual(result, 0)
        run.assert_called_once()
        command = run.call_args[0][0]
        self.assertIn(str(self.target), command)

    def test_lowercase_write_tool_name_is_supported(self) -> None:
        # Codex sends lowercase tool names for the same operations
        # (pre_tool_use.py's FILE_WRITE_TOOLS already accounts for this).
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/ruff"):
            with mock.patch.object(self.module.subprocess, "run", return_value=completed) as run:
                result, _ = self.run_hook(self.payload("write", self.target))
        self.assertEqual(result, 0)
        run.assert_called_once()

    def test_lowercase_edit_tool_name_is_supported(self) -> None:
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/ruff"):
            with mock.patch.object(self.module.subprocess, "run", return_value=completed) as run:
                result, _ = self.run_hook(self.payload("edit", self.target))
        self.assertEqual(result, 0)
        run.assert_called_once()


class NonMutatingCommandTests(QualityHookTestCase):
    """The check command itself must never carry a mutating flag, and must
    separate the path argument with `--` so a dash-prefixed filename can
    never be parsed as an option."""

    def setUp(self) -> None:
        super().setUp()
        self.write_config("report")

    def _run(self, target: Path):
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/tool"):
            with mock.patch.object(self.module.subprocess, "run", return_value=completed) as run:
                self.run_hook(self.payload("Write", target))
        return run

    def test_python_check_command_has_no_fix_flag(self) -> None:
        target = self.write_target("target.py")
        run = self._run(target)
        run.assert_called_once()
        command = run.call_args[0][0]
        self.assertNotIn("--fix", command)
        self.assertNotIn("-fix", command)

    def test_javascript_check_command_has_no_fix_flag(self) -> None:
        target = self.write_target("target.js", "var x = 1;\n")
        run = self._run(target)
        run.assert_called_once()
        command = run.call_args[0][0]
        self.assertNotIn("--fix", command)

    def test_command_separates_path_with_double_dash(self) -> None:
        target = self.write_target("target.py")
        run = self._run(target)
        command = run.call_args[0][0]
        self.assertIn("--", command)
        self.assertEqual(command[-1], str(target))
        self.assertEqual(command[-2], "--")

    def test_dash_prefixed_filename_is_still_passed_safely(self) -> None:
        target = self.write_target("-rf.py")
        run = self._run(target)
        command = run.call_args[0][0]
        # The dash-prefixed name must appear only after the "--" separator.
        self.assertEqual(command.index("--") + 1, command.index(str(target)))

    def test_uppercase_suffix_is_still_recognized(self) -> None:
        target = self.write_target("Script.PY")
        run = self._run(target)
        run.assert_called_once()
        command = run.call_args[0][0]
        self.assertIn(str(target), command)


class MissingToolTests(QualityHookTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_config("report")
        self.target = self.write_target()

    def test_missing_ruff_is_reported_not_crashed(self) -> None:
        with mock.patch.object(self.module.shutil, "which", return_value=None):
            with mock.patch.object(self.module.subprocess, "run") as run:
                result, emitted = self.run_hook(self.payload("Write", self.target))
        run.assert_not_called()
        self.assertEqual(result, 0)
        self.assertIn("not installed", self.context_of(emitted).lower())


class TimeoutTests(QualityHookTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_config("report")
        self.target = self.write_target()

    def test_timeout_is_reported_not_crashed(self) -> None:
        with mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/ruff"):
            with mock.patch.object(
                self.module.subprocess,
                "run",
                side_effect=real_subprocess.TimeoutExpired(cmd=["ruff"], timeout=15),
            ):
                result, emitted = self.run_hook(self.payload("Write", self.target))
        self.assertEqual(result, 0)
        self.assertIn("timed out", self.context_of(emitted).lower())
        self.assertEqual(self.target.read_bytes(), b"import os\n")


class UndecodableToolOutputTests(QualityHookTestCase):
    """The checked tool's own stdout/stderr may not be valid UTF-8; that
    must be reported gracefully, never crash the hook."""

    def setUp(self) -> None:
        super().setUp()
        self.write_config("report")
        self.target = self.write_target()

    def test_non_utf8_tool_output_does_not_crash(self) -> None:
        real_run = self.module.subprocess.run

        def fake_run(command, **kwargs):
            # Exercise the real subprocess machinery (including its
            # encoding/errors handling) against a tool that emits invalid
            # UTF-8 bytes on stdout, instead of mocking away the decode step.
            return real_run(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.buffer.write(b'\\xff\\xfe bad bytes'); sys.exit(1)",
                ],
                **kwargs,
            )

        with mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/ruff"):
            with mock.patch.object(self.module.subprocess, "run", side_effect=fake_run):
                result, emitted = self.run_hook(self.payload("Write", self.target))
        self.assertEqual(result, 0)
        self.assertIsNotNone(emitted)
        self.assertEqual(self.target.read_bytes(), b"import os\n")


class NonzeroExitTests(QualityHookTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_config("report")
        self.target = self.write_target()

    def test_nonzero_exit_is_reported_with_command_status_and_output(self) -> None:
        completed = mock.Mock(
            returncode=1, stdout="target.py:1:1: F401 'os' imported but unused\n", stderr=""
        )
        with mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/ruff"):
            with mock.patch.object(self.module.subprocess, "run", return_value=completed):
                result, emitted = self.run_hook(self.payload("Write", self.target))
        self.assertEqual(result, 0)
        context = self.context_of(emitted)
        self.assertIn("1", context)
        self.assertIn("F401", context)
        self.assertEqual(self.target.read_bytes(), b"import os\n")

    def test_bounded_output_is_truncated(self) -> None:
        huge_output = "x" * 50000
        completed = mock.Mock(returncode=1, stdout=huge_output, stderr="")
        with mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/ruff"):
            with mock.patch.object(self.module.subprocess, "run", return_value=completed):
                _, emitted = self.run_hook(self.payload("Write", self.target))
        context = self.context_of(emitted)
        self.assertLess(len(context), 50000)


class MissingFileTests(QualityHookTestCase):
    """A structured tool_input path that no longer exists on disk is
    reported, not crashed on."""

    def setUp(self) -> None:
        super().setUp()
        self.write_config("report")

    def test_nonexistent_path_is_reported_not_crashed(self) -> None:
        missing = self.project_dir / "gone.py"
        with mock.patch.object(self.module.subprocess, "run") as run:
            result, _ = self.run_hook(self.payload("Write", missing))
        run.assert_not_called()
        self.assertEqual(result, 0)


class FormatReportDefensiveTests(unittest.TestCase):
    """`format_report` must never raise on an unrecognized/renamed report
    shape — the "kind" discriminator is the single source of truth for how
    to render a report, with a safe fallback for anything else."""

    def setUp(self) -> None:
        self.module = load_hook()

    def test_unknown_kind_does_not_raise(self) -> None:
        text = self.module.format_report(Path("x.py"), {"kind": "totally-unknown"})
        self.assertIn("unrecognized", text.lower())

    def test_missing_kind_does_not_raise(self) -> None:
        text = self.module.format_report(Path("x.py"), {})
        self.assertIn("unrecognized", text.lower())


class NoPayloadTests(unittest.TestCase):
    def test_empty_stdin_is_a_no_op(self) -> None:
        module = load_hook()
        with mock.patch.object(module.subprocess, "run") as run:
            result = run_main_with_stdin(module, "")
        run.assert_not_called()
        self.assertEqual(result, 0)

    def test_malformed_json_stdin_is_a_no_op(self) -> None:
        module = load_hook()
        with mock.patch.object(module.subprocess, "run") as run:
            result = run_main_with_stdin(module, "{not valid")
        run.assert_not_called()
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
