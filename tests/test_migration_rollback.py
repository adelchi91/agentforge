"""Rollback tests for STORY-019 (`scripts/migrate_v1.py::rollback_migration`).

Verifies the acceptance criterion "Rollback restores the previous hook
registration and active files exactly" -- byte-for-byte, not merely
"close enough" -- for every kind of change the migration can make:
created files, updated files, and moved (archived) files.
"""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import migrate_v1  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "v1_projects"


def _copy_fixture(name: str, dest: Path) -> Path:
    shutil.copytree(FIXTURES_DIR / name, dest, dirs_exist_ok=True)
    return dest


def _snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root).as_posix()): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def _apply(root, **kwargs):
    plan = migrate_v1.plan_migration(root, **kwargs)
    assert plan.status == "ok", plan.status
    return migrate_v1.apply_migration(root, approved_plan_id=plan.plan_id, **kwargs)


class RollbackExactnessTests(unittest.TestCase):
    def test_rollback_restores_the_exact_pre_migration_tree(self) -> None:
        for name in ("minimal_claude", "minimal_codex", "lagrangia_style", "hand_edited", "partial"):
            with self.subTest(fixture=name):
                with TemporaryDirectory() as tmp:
                    root = _copy_fixture(name, Path(tmp))
                    before = _snapshot(root)

                    applied = _apply(root)
                    self.assertEqual(applied.status, "ok")
                    self.assertNotEqual(_snapshot(root), before)  # sanity: something changed

                    timestamp = Path(applied.manifest_path).parent.name
                    result = migrate_v1.rollback_migration(root, timestamp)
                    self.assertEqual(result.status, "ok")

                    after_rollback = _snapshot(root)
                    # Every file that existed before migration is restored exactly.
                    for rel_path, content in before.items():
                        self.assertIn(rel_path, after_rollback, f"{name}: {rel_path} missing after rollback")
                        self.assertEqual(
                            after_rollback[rel_path], content,
                            f"{name}: {rel_path} not restored byte-for-byte",
                        )
                    # Every file the migration created no longer exists (except the
                    # archive directory itself, which rollback intentionally keeps
                    # as an audit trail rather than deleting).
                    created_paths = {
                        p for p in after_rollback
                        if p not in before and ".agentforge/migration-archive" not in p
                    }
                    self.assertEqual(
                        created_paths, set(),
                        f"{name}: migration-created files survive rollback: {created_paths}",
                    )

    def test_rollback_with_hooks_validated_restores_settings_json_and_hook_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            before_settings = (root / ".claude" / "settings.json").read_bytes()
            before_hooks = {
                p.name: p.read_bytes() for p in (root / ".claude" / "hooks").glob("*.py")
            }

            applied = _apply(root, v2_hooks_validated=True)
            self.assertEqual(applied.status, "ok")
            self.assertNotIn("hooks", json.loads((root / ".claude" / "settings.json").read_text()))
            for name in before_hooks:
                self.assertFalse((root / ".claude" / "hooks" / name).exists())

            timestamp = Path(applied.manifest_path).parent.name
            result = migrate_v1.rollback_migration(root, timestamp)
            self.assertEqual(result.status, "ok")

            self.assertEqual((root / ".claude" / "settings.json").read_bytes(), before_settings)
            for name, content in before_hooks.items():
                self.assertEqual((root / ".claude" / "hooks" / name).read_bytes(), content)

    def test_rollback_of_unknown_timestamp_reports_not_found(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            result = migrate_v1.rollback_migration(root, "19700101T000000Z")
            self.assertEqual(result.status, "not_found")

    def test_rollback_lists_every_restored_path(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            # scopes.json is only archived once v2 hooks are validated (it
            # is still read by the still-active v1 pre_tool_use.py hook
            # otherwise); exercise the full path here.
            applied = _apply(root, v2_hooks_validated=True)
            timestamp = Path(applied.manifest_path).parent.name
            result = migrate_v1.rollback_migration(root, timestamp)
            self.assertIn("CLAUDE.md", result.restored)
            self.assertIn(".agentforge/config.json", result.restored)
            self.assertIn("docs/work-items/STORY-001.md", result.restored)
            self.assertIn(".claude/CLAUDE.md", result.restored)
            self.assertIn(".claude/hooks/scopes.json", result.restored)
            self.assertIn(".claude/stories/STORY-001.md", result.restored)
            self.assertIn(".claude/settings.json", result.restored)
            for name in ("pre_tool_use.py", "post_tool_use.py", "session_start.py"):
                self.assertIn(f".claude/hooks/{name}", result.restored)

    def test_two_sequential_migrations_each_roll_back_independently(self) -> None:
        """Applying the hook-validated pass in a second, separate apply
        produces a second, independent archive timestamp; rolling back
        only that one must not disturb the first migration's results."""
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            first = _apply(root)
            after_first = _snapshot(root)

            second = _apply(root, v2_hooks_validated=True)
            self.assertNotEqual(first.manifest_path, second.manifest_path)

            second_timestamp = Path(second.manifest_path).parent.name
            result = migrate_v1.rollback_migration(root, second_timestamp)
            self.assertEqual(result.status, "ok")

            after_second_rollback = _snapshot(root)
            for rel_path, content in after_first.items():
                self.assertEqual(
                    after_second_rollback.get(rel_path), content,
                    f"{rel_path} differs after rolling back only the second migration",
                )

    def test_rollback_is_idempotent_when_run_twice(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            applied = _apply(root)
            timestamp = Path(applied.manifest_path).parent.name
            migrate_v1.rollback_migration(root, timestamp)
            once = _snapshot(root)
            result_again = migrate_v1.rollback_migration(root, timestamp)
            self.assertEqual(result_again.status, "ok")
            self.assertEqual(_snapshot(root), once)

    def test_cli_rollback_subcommand(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            before = _snapshot(root)
            applied = _apply(root)
            timestamp = Path(applied.manifest_path).parent.name

            exit_code = migrate_v1.main(
                ["rollback", "--project-root", str(root), "--timestamp", timestamp]
            )
            self.assertEqual(exit_code, 0)
            after_rollback = _snapshot(root)
            for rel_path, content in before.items():
                self.assertEqual(after_rollback.get(rel_path), content)


if __name__ == "__main__":
    unittest.main()
