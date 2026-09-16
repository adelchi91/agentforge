"""Tests for the STORY-005 idempotent, non-destructive setup transaction
(scripts/setup.py).

Covers the STORY-005 acceptance criteria:
  - empty repo (neither CLAUDE.md nor AGENTS.md) requires an explicit
    constitution-target choice;
  - CLAUDE-only and AGENTS-only projects are edited without asking;
  - both files present requires an explicit choice, unless exactly one
    already carries a well-formed AgentForge block;
  - an existing Matt (or any other) block is left untouched, never
    duplicated;
  - an existing, up-to-date AgentForge block plans no change;
  - malformed/duplicate/nested AgentForge markers block the whole
    transaction with a precise diagnostic and no write;
  - an existing, valid `.agentforge/config.json` is left untouched; an
    existing, invalid one blocks the transaction and is never replaced;
  - pre-existing `.claude/settings*.json` and Git hook configuration
    (`core.hooksPath`, `commit-msg`) are reported, never written to;
  - `plan_setup` never mutates the filesystem (covers cancellation writing
    nothing);
  - a second identical `apply_setup` call reports every change as "none".
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import setup  # noqa: E402

CONFIG_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "config"


def _snapshot(root: Path) -> dict:
    """Path (relative, posix) -> raw bytes, for every regular file under
    root. Used to assert that planning (and a blocked/needs_choice apply)
    mutates nothing at all."""
    return {
        str(p.relative_to(root).as_posix()): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def _plan_and_apply(root, **kwargs):
    """plan_setup then apply_setup with the freshly computed plan_id — the
    normal, non-stale path a caller who approves immediately takes. For a
    blocked/needs_choice plan, apply_setup returns it unchanged regardless
    of approved_plan_id, so this is also safe to use in tests that only
    care about the blocked/needs_choice status."""
    plan = setup.plan_setup(root, **kwargs)
    return setup.apply_setup(root, approved_plan_id=plan.plan_id, **kwargs)


class EmptyRepoTests(unittest.TestCase):
    def test_neither_file_needs_a_choice(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = setup.plan_setup(root)
            self.assertEqual(plan.status, "needs_choice")
            self.assertEqual(set(plan.choices), {"CLAUDE.md", "AGENTS.md"})
            self.assertEqual(_snapshot(root), {})

    def test_choosing_claude_creates_it_and_the_config(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertTrue((root / "CLAUDE.md").exists())
            self.assertTrue((root / ".agentforge" / "config.json").exists())
            claude_change = plan.change_for("CLAUDE.md")
            self.assertEqual(claude_change.action, "create")
            config_change = plan.change_for(".agentforge/config.json")
            self.assertEqual(config_change.action, "create")

    def test_choosing_agents_creates_only_agents_md(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _plan_and_apply(root, constitution_target="AGENTS.md")
            self.assertTrue((root / "AGENTS.md").exists())
            self.assertFalse((root / "CLAUDE.md").exists())

    def test_plan_never_writes_anything(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(_snapshot(root), {})


class SingleFileTests(unittest.TestCase):
    def test_claude_only_is_edited_without_asking(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# My project\n\nSome rules.\n", encoding="utf-8")
            plan = setup.plan_setup(root)
            self.assertEqual(plan.status, "ok")
            self.assertFalse((root / "AGENTS.md").exists())
            change = plan.change_for("CLAUDE.md")
            self.assertEqual(change.action, "update")
            self.assertIn("# My project", change.after)
            self.assertIn(setup.MARKER_START, change.after)

    def test_agents_only_is_edited_without_asking(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("# Agents rules\n", encoding="utf-8")
            plan = setup.plan_setup(root)
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.change_for("AGENTS.md").action, "update")

    def test_mismatched_explicit_target_is_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("hello\n", encoding="utf-8")
            plan = setup.plan_setup(root, constitution_target="AGENTS.md")
            self.assertEqual(plan.status, "blocked")
            self.assertEqual(_snapshot(root), {"CLAUDE.md": b"hello\n"})


class BothFilesTests(unittest.TestCase):
    def test_both_present_with_no_block_needs_a_choice(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("claude rules\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("agents rules\n", encoding="utf-8")
            plan = setup.plan_setup(root)
            self.assertEqual(plan.status, "needs_choice")

    def test_both_present_edits_only_the_chosen_one(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("claude rules\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("agents rules\n", encoding="utf-8")
            plan = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertIn(setup.MARKER_START, (root / "CLAUDE.md").read_text(encoding="utf-8"))
            self.assertEqual((root / "AGENTS.md").read_text(encoding="utf-8"), "agents rules\n")

    def test_both_present_one_already_has_block_is_inferred(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude_text = "claude rules\n\n" + setup.AGENTFORGE_BLOCK + "\n"
            (root / "CLAUDE.md").write_text(claude_text, encoding="utf-8")
            (root / "AGENTS.md").write_text("agents rules\n", encoding="utf-8")
            plan = setup.plan_setup(root)
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.change_for("CLAUDE.md").action, "none")
            self.assertIsNone(plan.change_for("AGENTS.md"))

    def test_both_present_both_already_have_block_is_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            block = "\n\n" + setup.AGENTFORGE_BLOCK + "\n"
            (root / "CLAUDE.md").write_text("claude rules" + block, encoding="utf-8")
            (root / "AGENTS.md").write_text("agents rules" + block, encoding="utf-8")
            plan = setup.plan_setup(root)
            self.assertEqual(plan.status, "blocked")
            self.assertTrue(plan.blocking_issues)


class ExistingMattBlockTests(unittest.TestCase):
    def test_other_delimited_content_is_preserved_and_not_duplicated(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            matt_block = (
                "# Project constitution\n\n"
                "<!-- mattpocock:start -->\n"
                "Matt's engineering discipline pointers go here.\n"
                "<!-- mattpocock:end -->\n"
            )
            (root / "CLAUDE.md").write_text(matt_block, encoding="utf-8")
            plan = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            final = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn(matt_block.rstrip("\n"), final)
            self.assertEqual(final.count("<!-- mattpocock:start -->"), 1)
            self.assertEqual(final.count(setup.MARKER_START), 1)
            # Matt's block content never appears inside AgentForge's own block.
            self.assertNotIn("mattpocock", setup.AGENTFORGE_BLOCK.lower())


class ExistingAgentForgeBlockTests(unittest.TestCase):
    def test_up_to_date_block_plans_no_change(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = "# Rules\n\n" + setup.AGENTFORGE_BLOCK + "\n"
            (root / "CLAUDE.md").write_text(text, encoding="utf-8")
            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            change = plan.change_for("CLAUDE.md")
            self.assertEqual(change.action, "none")
            self.assertIsNone(change.diff)


class MalformedMarkerTests(unittest.TestCase):
    def _assert_blocked_and_untouched(self, content: str) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_bytes(content.encode("utf-8"))
            before = _snapshot(root)
            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "blocked")
            self.assertTrue(plan.blocking_issues)
            applied = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(applied.status, "blocked")
            self.assertEqual(_snapshot(root), before)

    def test_unmatched_start_only(self) -> None:
        self._assert_blocked_and_untouched(f"prose\n{setup.MARKER_START}\nmore\n")

    def test_unmatched_end_only(self) -> None:
        self._assert_blocked_and_untouched(f"prose\n{setup.MARKER_END}\nmore\n")

    def test_duplicated_pair(self) -> None:
        block = f"{setup.MARKER_START}\nx\n{setup.MARKER_END}\n"
        self._assert_blocked_and_untouched(block + block)

    def test_nested_markers(self) -> None:
        nested = (
            f"{setup.MARKER_START}\n"
            f"{setup.MARKER_START}\n"
            "x\n"
            f"{setup.MARKER_END}\n"
            f"{setup.MARKER_END}\n"
        )
        self._assert_blocked_and_untouched(nested)

    def test_end_before_start(self) -> None:
        self._assert_blocked_and_untouched(f"{setup.MARKER_END}\nx\n{setup.MARKER_START}\n")


class AgentForgeConfigTests(unittest.TestCase):
    def test_missing_config_is_created_from_template(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            written = json.loads((root / ".agentforge" / "config.json").read_text(encoding="utf-8"))
            template = json.loads(
                (REPO_ROOT / "templates" / "agentforge-config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(written, template)

    def test_existing_valid_config_is_left_untouched(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            agentforge_dir = root / ".agentforge"
            agentforge_dir.mkdir()
            valid_text = (CONFIG_FIXTURES / "valid_github.json").read_bytes()
            (agentforge_dir / "config.json").write_bytes(valid_text)

            plan = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.change_for(".agentforge/config.json").action, "none")
            self.assertEqual((agentforge_dir / "config.json").read_bytes(), valid_text)

    def test_existing_invalid_config_blocks_and_is_never_replaced(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            agentforge_dir = root / ".agentforge"
            agentforge_dir.mkdir()
            invalid_text = (CONFIG_FIXTURES / "invalid_regex.json").read_bytes()
            (agentforge_dir / "config.json").write_bytes(invalid_text)

            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "blocked")
            self.assertTrue(
                any("identifier.pattern" in issue for issue in plan.blocking_issues),
                plan.blocking_issues,
            )

            applied = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(applied.status, "blocked")
            self.assertEqual((agentforge_dir / "config.json").read_bytes(), invalid_text)
            self.assertFalse((root / "CLAUDE.md").exists())

    def test_malformed_json_config_blocks(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            agentforge_dir = root / ".agentforge"
            agentforge_dir.mkdir()
            malformed_text = (CONFIG_FIXTURES / "malformed.json").read_bytes()
            (agentforge_dir / "config.json").write_bytes(malformed_text)

            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "blocked")


class SettingsAndGitHookReportingTests(unittest.TestCase):
    def test_existing_claude_settings_are_reported_and_untouched(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude_dir = root / ".claude"
            claude_dir.mkdir()
            (claude_dir / "settings.json").write_text('{"foo": "bar"}', encoding="utf-8")
            (claude_dir / "settings.local.json").write_text('{"baz": 1}', encoding="utf-8")

            plan = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertTrue(any("settings.json" in note for note in plan.notes))
            self.assertTrue(any("settings.local.json" in note for note in plan.notes))
            self.assertEqual(
                (claude_dir / "settings.json").read_text(encoding="utf-8"), '{"foo": "bar"}'
            )
            self.assertIsNone(plan.change_for(".claude/settings.json"))

    @unittest.skipUnless(shutil.which("git"), "git executable not available")
    def test_existing_git_hooks_path_is_reported_and_untouched(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "config", "core.hooksPath", ".githooks"], cwd=str(root), check=True
            )
            before = (root / ".git" / "config").read_bytes()

            plan = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertTrue(any(".githooks" in note for note in plan.notes), plan.notes)
            self.assertEqual((root / ".git" / "config").read_bytes(), before)

    def test_existing_commit_msg_hook_is_reported_and_untouched(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hooks_dir = root / ".git" / "hooks"
            hooks_dir.mkdir(parents=True)
            (hooks_dir / "commit-msg").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

            plan = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertTrue(any("commit-msg" in note for note in plan.notes))
            self.assertEqual(
                (hooks_dir / "commit-msg").read_text(encoding="utf-8"), "#!/bin/sh\nexit 0\n"
            )

    def test_available_git_hook_integration_modes_are_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertTrue(
                any("integration modes" in note for note in plan.notes), plan.notes
            )
            self.assertTrue(
                any("chained installation" in note for note in plan.notes), plan.notes
            )
            self.assertTrue(any("CI-only" in note for note in plan.notes), plan.notes)


class SecondRunIdempotenceTests(unittest.TestCase):
    def test_second_identical_apply_reports_every_change_as_none(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# Project\n\nRules.\n", encoding="utf-8")
            first = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(first.status, "ok")
            self.assertTrue(any(c.action != "none" for c in first.changes))

            before_bytes = _snapshot(root)
            second = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(second.status, "ok")
            for change in second.changes:
                self.assertEqual(change.action, "none", change.path)
            self.assertEqual(_snapshot(root), before_bytes)

    def test_second_run_from_empty_repo_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _plan_and_apply(root, constitution_target="AGENTS.md")
            second = _plan_and_apply(root, constitution_target="AGENTS.md")
            self.assertEqual(second.status, "ok")
            for change in second.changes:
                self.assertEqual(change.action, "none", change.path)


class CancellationTests(unittest.TestCase):
    def test_planning_only_never_writes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("existing\n", encoding="utf-8")
            setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(
                (root / "CLAUDE.md").read_text(encoding="utf-8"), "existing\n"
            )
            self.assertFalse((root / ".agentforge").exists())


class CliSmokeTests(unittest.TestCase):
    def test_plan_subcommand_prints_json_and_exits_nonzero_when_not_ok(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "setup.py"), "plan", "--project-root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "needs_choice")

    def test_apply_subcommand_writes_files_and_exits_zero(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "setup.py"),
                    "plan",
                    "--project-root",
                    str(root),
                    "--constitution-target",
                    "CLAUDE.md",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(plan_result.returncode, 0, plan_result.stdout + plan_result.stderr)
            plan_payload = json.loads(plan_result.stdout)
            self.assertEqual(plan_payload["status"], "ok")
            self.assertTrue(plan_payload["plan_id"])

            apply_result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "setup.py"),
                    "apply",
                    "--project-root",
                    str(root),
                    "--constitution-target",
                    "CLAUDE.md",
                    "--approved-plan-id",
                    plan_payload["plan_id"],
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(apply_result.returncode, 0, apply_result.stdout + apply_result.stderr)
            apply_payload = json.loads(apply_result.stdout)
            self.assertEqual(apply_payload["status"], "ok")
            self.assertTrue((root / "CLAUDE.md").exists())

    def test_apply_subcommand_requires_approved_plan_id_flag(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "setup.py"),
                    "apply",
                    "--project-root",
                    str(root),
                    "--constitution-target",
                    "CLAUDE.md",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "CLAUDE.md").exists())


class ApprovalBindingTests(unittest.TestCase):
    """Approval-binding/TOCTOU fix: apply_setup must apply only the exact
    plan the user approved (identified by plan_id), and must report status
    "stale" with a freshly recomputed plan — writing nothing — whenever
    project state changed between plan_setup and apply_setup."""

    def test_plan_output_includes_a_plan_id(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            ok_plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(ok_plan.status, "ok")
            self.assertIsNotNone(ok_plan.plan_id)
            self.assertIn("plan_id", ok_plan.to_dict())

            needs_choice_plan = setup.plan_setup(root)
            self.assertEqual(needs_choice_plan.status, "needs_choice")
            self.assertIsNone(needs_choice_plan.plan_id)

    def test_unchanged_plan_applies_successfully(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# Title\n\nBody.\n", encoding="utf-8")
            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")

            applied = setup.apply_setup(
                root, constitution_target="CLAUDE.md", approved_plan_id=plan.plan_id
            )
            self.assertEqual(applied.status, "ok")
            self.assertIn(setup.MARKER_START, (root / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_missing_approved_plan_id_is_treated_as_stale(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = _snapshot(root)
            applied = setup.apply_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(applied.status, "stale")
            self.assertEqual(_snapshot(root), before)

    def test_constitution_changed_after_approval_but_still_valid_is_stale(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("original prose\n", encoding="utf-8")
            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")

            # Someone else edits CLAUDE.md after the user approved this
            # plan. The file is still perfectly valid -- just different
            # content than what was approved.
            (root / "CLAUDE.md").write_text("different prose entirely\n", encoding="utf-8")
            before = _snapshot(root)

            applied = setup.apply_setup(
                root, constitution_target="CLAUDE.md", approved_plan_id=plan.plan_id
            )
            self.assertEqual(applied.status, "stale")
            self.assertEqual(_snapshot(root), before)
            self.assertIn("different prose entirely", applied.change_for("CLAUDE.md").before)
            self.assertIsNotNone(applied.plan_id)
            self.assertNotEqual(applied.plan_id, plan.plan_id)

    def test_config_created_after_approval_is_stale(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.change_for(".agentforge/config.json").action, "create")

            agentforge_dir = root / ".agentforge"
            agentforge_dir.mkdir()
            other_valid = (CONFIG_FIXTURES / "valid_local.json").read_bytes()
            (agentforge_dir / "config.json").write_bytes(other_valid)
            before = _snapshot(root)

            applied = setup.apply_setup(
                root, constitution_target="CLAUDE.md", approved_plan_id=plan.plan_id
            )
            self.assertEqual(applied.status, "stale")
            self.assertEqual(_snapshot(root), before)
            self.assertEqual((agentforge_dir / "config.json").read_bytes(), other_valid)

    def test_config_modified_after_approval_is_stale(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            agentforge_dir = root / ".agentforge"
            agentforge_dir.mkdir()
            original_valid = (CONFIG_FIXTURES / "valid_local.json").read_bytes()
            (agentforge_dir / "config.json").write_bytes(original_valid)

            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.change_for(".agentforge/config.json").action, "none")

            other_valid = (CONFIG_FIXTURES / "valid_github.json").read_bytes()
            (agentforge_dir / "config.json").write_bytes(other_valid)
            before = _snapshot(root)

            applied = setup.apply_setup(
                root, constitution_target="CLAUDE.md", approved_plan_id=plan.plan_id
            )
            self.assertEqual(applied.status, "stale")
            self.assertEqual(_snapshot(root), before)

    def test_selected_constitution_target_changed_is_stale(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            before = _snapshot(root)

            applied = setup.apply_setup(
                root, constitution_target="AGENTS.md", approved_plan_id=plan.plan_id
            )
            self.assertEqual(applied.status, "stale")
            self.assertEqual(_snapshot(root), before)
            self.assertEqual(applied.change_for("AGENTS.md").action, "create")

    def test_config_template_version_changed_is_stale(self) -> None:
        with TemporaryDirectory() as project_tmp, TemporaryDirectory() as template_tmp:
            root = Path(project_tmp)
            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            before = _snapshot(root)

            # Simulate a plugin upgrade changing the shipped config
            # template between plan and apply. The alternate template
            # lives outside `root` -- only the project directory's
            # contents matter for the "nothing was written" assertion.
            alt_template = Path(template_tmp) / "alt-template.json"
            alt_template.write_text('{"schema_version": 1, "different": true}', encoding="utf-8")
            with mock.patch.object(setup, "_CONFIG_TEMPLATE_PATH", alt_template):
                applied = setup.apply_setup(
                    root, constitution_target="CLAUDE.md", approved_plan_id=plan.plan_id
                )
            self.assertEqual(applied.status, "stale")
            self.assertEqual(_snapshot(root), before)


class TransactionHonestyTests(unittest.TestCase):
    """Requirement 8/9: apply_setup is one approved transaction with
    stale-plan protection, NOT a filesystem-atomic multi-file transaction.
    This proves that honestly: a failure writing the second file in a plan
    leaves the first file's write in place rather than rolling it back."""

    def test_partial_write_on_second_file_failure_leaves_first_file_written(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Sabotage: .agentforge is a plain file, not a directory, so the
            # config.json write (the plan's second change) cannot succeed.
            (root / ".agentforge").write_text("not a directory", encoding="utf-8")

            plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.change_for("CLAUDE.md").action, "create")
            self.assertEqual(plan.change_for(".agentforge/config.json").action, "create")

            with self.assertRaises(OSError):
                setup.apply_setup(
                    root, constitution_target="CLAUDE.md", approved_plan_id=plan.plan_id
                )

            # The first file in the plan (CLAUDE.md) was fully written...
            self.assertTrue((root / "CLAUDE.md").exists())
            self.assertIn(setup.MARKER_START, (root / "CLAUDE.md").read_text(encoding="utf-8"))
            # ...but the second (config.json) never was -- this transaction
            # is not atomic across files, by design. Re-running setup
            # afterward is always safe (it will simply report the
            # remaining file that still needs the change).
            self.assertEqual((root / ".agentforge").read_text(encoding="utf-8"), "not a directory")


class EffectiveHooksPathTests(unittest.TestCase):
    """Requirement 10-12: git core.hooksPath reporting uses the *effective*
    Git-resolved value (local/worktree/global/system combined) via a
    read-only `git config --show-origin --get core.hooksPath` call, falling
    back to a direct local `.git/config` parse only when the git executable
    itself cannot be run."""

    def test_effective_non_local_hooks_path_is_reported(self) -> None:
        fake_result = subprocess.CompletedProcess(
            args=["git", "config", "--show-origin", "--get", "core.hooksPath"],
            returncode=0,
            stdout="file:/home/user/.gitconfig\t.githooks-global\n",
            stderr="",
        )
        with mock.patch.object(
            setup, "_run_git_config_show_origin", return_value=fake_result
        ) as mocked:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
        mocked.assert_called_once()
        self.assertEqual(plan.status, "ok")
        self.assertTrue(
            any(
                ".githooks-global" in note and "/home/user/.gitconfig" in note
                for note in plan.notes
            ),
            plan.notes,
        )

    def test_no_configured_value_is_handled_normally(self) -> None:
        fake_result = subprocess.CompletedProcess(
            args=["git", "config", "--show-origin", "--get", "core.hooksPath"],
            returncode=1,
            stdout="",
            stderr="",
        )
        with mock.patch.object(setup, "_run_git_config_show_origin", return_value=fake_result):
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
        self.assertEqual(plan.status, "ok")
        self.assertFalse(any("hooksPath" in note for note in plan.notes), plan.notes)

    def test_git_unavailable_uses_local_config_fallback(self) -> None:
        with mock.patch.object(
            setup, "_run_git_config_show_origin", side_effect=FileNotFoundError()
        ):
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                git_dir = root / ".git"
                git_dir.mkdir()
                (git_dir / "config").write_text(
                    "[core]\n\thooksPath = .githooks-local-only\n", encoding="utf-8"
                )
                plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
        self.assertTrue(
            any(".githooks-local-only" in note for note in plan.notes), plan.notes
        )

    def test_git_call_timeout_falls_back_instead_of_crashing(self) -> None:
        # subprocess.TimeoutExpired is a SubprocessError, not an OSError —
        # a hung `git config` call must still degrade gracefully (to the
        # local-config fallback) rather than propagate out of plan_setup.
        timeout_error = subprocess.TimeoutExpired(cmd=["git", "config"], timeout=5)
        with mock.patch.object(
            setup, "_run_git_config_show_origin", side_effect=timeout_error
        ):
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                git_dir = root / ".git"
                git_dir.mkdir()
                (git_dir / "config").write_text(
                    "[core]\n\thooksPath = .githooks-after-timeout\n", encoding="utf-8"
                )
                plan = setup.plan_setup(root, constitution_target="CLAUDE.md")
        self.assertEqual(plan.status, "ok")
        self.assertTrue(
            any(".githooks-after-timeout" in note for note in plan.notes), plan.notes
        )

    @unittest.skipUnless(shutil.which("git"), "git executable not available")
    def test_inspection_never_writes_git_configuration(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "config", "core.hooksPath", ".githooks"], cwd=str(root), check=True
            )
            before = (root / ".git" / "config").read_bytes()
            setup.plan_setup(root, constitution_target="CLAUDE.md")
            after = (root / ".git" / "config").read_bytes()
        self.assertEqual(before, after)


class TemplateFileTests(unittest.TestCase):
    """The shipped templates/claude-agent-skills-block.md must match
    setup.py's AGENTFORGE_BLOCK exactly, the same way
    templates/agentforge-config.json is kept in sync with config.py's
    DEFAULT_CONFIG (tests/test_config.py::TemplateFileTests)."""

    def test_template_file_matches_block_constant(self) -> None:
        path = REPO_ROOT / "templates" / "claude-agent-skills-block.md"
        text = path.read_bytes().decode("utf-8")
        self.assertEqual(text, setup.AGENTFORGE_BLOCK + "\n")

    def test_block_constant_contains_matched_markers(self) -> None:
        span = setup.find_agentforge_block(setup.AGENTFORGE_BLOCK)
        self.assertIsNotNone(span)
        self.assertEqual(span, (0, len(setup.AGENTFORGE_BLOCK)))


if __name__ == "__main__":
    unittest.main()
