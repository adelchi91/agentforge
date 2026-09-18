"""Tests for STORY-019: migrating an existing AgentForge v1 project to v2
(`scripts/migrate_v1.py`).

Fixtures live under `tests/fixtures/v1_projects/` (this story's own,
modeled on the real, frozen `examples/` trees -- never touching or
depending on mutating those). Six kinds, per the acceptance criteria:
`minimal_claude`, `minimal_codex`, `lagrangia_style` (complex,
multi-story, multi-agent), `hand_edited` (human-added prose and a
renamed/added custom agent), `partial` (interrupted bootstrap), and
`already_migrated` (a project that is already v2 -- migrating it again
must be a safe no-op).

Rollback-specific tests live in `tests/test_migration_rollback.py`.
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

from scripts import config as config_module  # noqa: E402
from scripts import migrate_v1  # noqa: E402
from scripts import work_items as work_items_module  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "v1_projects"
FIXTURE_NAMES = (
    "minimal_claude",
    "minimal_codex",
    "lagrangia_style",
    "hand_edited",
    "partial",
    "already_migrated",
)


def _copy_fixture(name: str, dest: Path) -> Path:
    shutil.copytree(FIXTURES_DIR / name, dest, dirs_exist_ok=True)
    return dest


def _snapshot(root: Path) -> dict:
    """Path (relative, posix) -> raw bytes, for every regular file under
    root, skipping VCS/cache noise. Used for byte-exact before/after
    comparisons (dry-run zero-change, idempotence, no-content-loss)."""
    return {
        str(p.relative_to(root).as_posix()): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def _plan(root, **kwargs):
    return migrate_v1.plan_migration(root, **kwargs)


def _plan_and_apply(root, **kwargs):
    plan = migrate_v1.plan_migration(root, **kwargs)
    if plan.status != "ok":
        return plan
    return migrate_v1.apply_migration(root, approved_plan_id=plan.plan_id, **kwargs)


class DetectionTests(unittest.TestCase):
    def test_detects_minimal_claude_scaffold(self) -> None:
        detection = migrate_v1.detect_v1(FIXTURES_DIR / "minimal_claude")
        self.assertTrue(detection.has_claude)
        self.assertFalse(detection.has_codex)
        self.assertFalse(detection.is_mixed)
        self.assertTrue(detection.has_any_v1)
        self.assertFalse(detection.already_v2)
        self.assertIsNotNone(detection.claude_constitution)
        self.assertEqual(len(detection.claude_stories), 1)

    def test_detects_minimal_codex_scaffold(self) -> None:
        detection = migrate_v1.detect_v1(FIXTURES_DIR / "minimal_codex")
        self.assertTrue(detection.has_codex)
        self.assertFalse(detection.has_claude)
        self.assertIsNotNone(detection.codex_constitution)
        self.assertIsNotNone(detection.codex_hooks_json)
        self.assertEqual(len(detection.codex_stories), 1)

    def test_bare_agents_md_with_no_codex_dir_is_not_treated_as_v1(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("# Just a normal AGENTS.md\n", encoding="utf-8")
            detection = migrate_v1.detect_v1(root)
            self.assertIsNone(detection.codex_constitution)
            self.assertFalse(detection.has_any_v1)

    def test_detects_mixed_scaffold(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_fixture("minimal_claude", root)
            _copy_fixture("minimal_codex", root)
            detection = migrate_v1.detect_v1(root)
            self.assertTrue(detection.has_claude)
            self.assertTrue(detection.has_codex)
            self.assertTrue(detection.is_mixed)

    def test_already_migrated_project_has_no_v1_artifacts(self) -> None:
        detection = migrate_v1.detect_v1(FIXTURES_DIR / "already_migrated")
        self.assertTrue(detection.already_v2)
        self.assertFalse(detection.has_any_v1)

    def test_partial_scaffold_is_detected_without_crashing(self) -> None:
        detection = migrate_v1.detect_v1(FIXTURES_DIR / "partial")
        self.assertTrue(detection.has_any_v1)
        self.assertIsNotNone(detection.claude_constitution)
        self.assertEqual(detection.claude_hook_files, ())
        self.assertEqual(detection.claude_stories, ())


class ReportCompletenessTests(unittest.TestCase):
    """Every detected v1 artifact must appear in the report with exactly
    one of the five categories -- 'never silently drop something into a
    bucket without it appearing in the report'."""

    def test_every_v1_file_in_each_fixture_appears_in_the_report(self) -> None:
        # "already_migrated" has no v1 artifacts at all by construction --
        # its safe-no-op behavior is covered by AlreadyMigratedNoOpTests.
        for name in [n for n in FIXTURE_NAMES if n != "already_migrated"]:
            with self.subTest(fixture=name):
                with TemporaryDirectory() as tmp:
                    root = _copy_fixture(name, Path(tmp))
                    plan = _plan(root)
                    reported_paths = {item.path.split("#", 1)[0] for item in plan.items}
                    for item in plan.items:
                        self.assertIn(item.category, migrate_v1.CATEGORIES)
                    original_files = {
                        p.relative_to(root).as_posix()
                        for p in root.rglob("*")
                        if p.is_file()
                    }
                    missing = original_files - reported_paths
                    self.assertEqual(
                        missing, set(), f"{name}: files never classified in the report: {missing}"
                    )


class DryRunTests(unittest.TestCase):
    def test_plan_migration_never_writes_to_disk(self) -> None:
        for name in FIXTURE_NAMES:
            with self.subTest(fixture=name):
                with TemporaryDirectory() as tmp:
                    root = _copy_fixture(name, Path(tmp))
                    before = _snapshot(root)
                    _plan(root)
                    _plan(root, v2_hooks_validated=True)
                    after = _snapshot(root)
                    self.assertEqual(before, after)


class AlreadyMigratedNoOpTests(unittest.TestCase):
    def test_already_migrated_project_is_a_safe_no_op(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("already_migrated", Path(tmp))
            before = _snapshot(root)
            plan = _plan(root)
            self.assertEqual(plan.status, "no_change")
            self.assertEqual(plan.warnings, [])
            self.assertEqual(plan.blocking_issues, [])
            applied = migrate_v1.apply_migration(root, approved_plan_id=plan.plan_id)
            self.assertEqual(applied.status, "no_change")
            self.assertEqual(_snapshot(root), before)


class IdempotenceTests(unittest.TestCase):
    def test_second_plan_after_apply_reports_no_further_changes(self) -> None:
        for name in ("minimal_claude", "minimal_codex", "lagrangia_style", "hand_edited", "partial"):
            with self.subTest(fixture=name):
                with TemporaryDirectory() as tmp:
                    root = _copy_fixture(name, Path(tmp))
                    first = _plan_and_apply(root)
                    self.assertEqual(first.status, "ok")

                    second_plan = _plan(root)
                    self.assertEqual(
                        second_plan.status, "no_change",
                        f"{name}: second plan reported further changes: "
                        f"{[i.to_dict() for i in second_plan.items if i.action not in ('none', 'deferred')]}",
                    )

                    before_second_apply = _snapshot(root)
                    migrate_v1.apply_migration(root, approved_plan_id=second_plan.plan_id)
                    self.assertEqual(_snapshot(root), before_second_apply)

    def test_running_twice_with_hooks_validated_is_also_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            first = _plan_and_apply(root, v2_hooks_validated=True)
            self.assertEqual(first.status, "ok")
            before = _snapshot(root)
            second_plan = _plan(root, v2_hooks_validated=True)
            self.assertEqual(second_plan.status, "no_change")
            migrate_v1.apply_migration(
                root, approved_plan_id=second_plan.plan_id, v2_hooks_validated=True
            )
            self.assertEqual(_snapshot(root), before)


class ConstitutionExtractionTests(unittest.TestCase):
    def test_claude_nested_constitution_is_relocated_and_constraints_extracted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")

            new_claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("<!-- agentforge:start -->", new_claude)
            self.assertIn("<!-- agentforge:migrated-v1-constraints:start -->", new_claude)
            self.assertIn(
                "No direct writes to `main`; every change goes through a reviewed PR.",
                new_claude,
            )
            self.assertIn(
                "All tests must pass before merging. No PR may be merged with failing "
                "or skipped tests.",
                new_claude,
            )
            # Original prose (Project Overview, Repo Ownership, ...) is preserved too --
            # requirement 4: extraction must never overwrite the rest of the file's prose.
            self.assertIn("mylib is a Python utility library for data validation.", new_claude)
            self.assertIn("Repo Ownership", new_claude)

            # The original nested file is archived, never deleted.
            self.assertFalse((root / ".claude" / "CLAUDE.md").exists())
            archive_files = list((root / ".agentforge" / "migration-archive").rglob("CLAUDE.md"))
            self.assertEqual(len(archive_files), 1)

    def test_codex_agents_md_gets_block_appended_without_losing_prose(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_codex", Path(tmp))
            before_text = (root / "AGENTS.md").read_text(encoding="utf-8")
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")
            after_text = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("<!-- agentforge:start -->", after_text)
            # Every line of the original file survives verbatim somewhere in the new one.
            for line in before_text.splitlines():
                if line.strip():
                    self.assertIn(line, after_text)

    def test_mixed_scaffold_reports_both_constitution_sides_independently(self) -> None:
        # A mixed scaffold's Codex AGENTS.md (already at the v2 location)
        # must never cause the Claude-side .claude/CLAUDE.md to silently
        # vanish from the report -- both are classified independently.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_fixture("minimal_claude", root)
            _copy_fixture("minimal_codex", root)
            plan = _plan(root)
            agents_items = [i for i in plan.items if i.path == "AGENTS.md"]
            claude_items = [i for i in plan.items if i.path == ".claude/CLAUDE.md"]
            self.assertEqual(len(agents_items), 1)
            self.assertEqual(agents_items[0].category, migrate_v1.CATEGORY_TRANSFORMED)
            self.assertEqual(len(claude_items), 1)
            self.assertEqual(claude_items[0].category, migrate_v1.CATEGORY_MANUAL_REVIEW)

    def test_both_root_and_nested_constitution_present_is_manual_review_not_guessed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            (root / "CLAUDE.md").write_text("# Hand-written root CLAUDE.md\n", encoding="utf-8")
            plan = _plan(root)
            constitution_items = [i for i in plan.items if i.path == ".claude/CLAUDE.md"]
            self.assertEqual(len(constitution_items), 1)
            self.assertEqual(constitution_items[0].category, migrate_v1.CATEGORY_MANUAL_REVIEW)
            self.assertEqual(constitution_items[0].action, migrate_v1.ACTION_NONE)


class StoryConversionTests(unittest.TestCase):
    def test_story_is_converted_to_a_resolvable_local_work_item(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")

            target = root / "docs" / "work-items" / "STORY-001.md"
            self.assertTrue(target.is_file())
            text = target.read_text(encoding="utf-8")
            self.assertIn("migrated_from: .claude/stories/STORY-001.md", text)
            self.assertIn("migrated_v1_agent: dev (model: sonnet)", text)

            cfg = config_module.load_for_enforcement(root / ".agentforge" / "config.json")
            result = work_items_module.resolve_work_item("STORY-001", cfg, project_root=root)
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.item.canonical_id, "local:STORY-001")

            # Original archived, never deleted.
            self.assertFalse((root / ".claude" / "stories" / "STORY-001.md").exists())
            archived = list((root / ".agentforge" / "migration-archive").rglob("STORY-001.md"))
            # one copy under docs/work-items (final, not archive) + one archived original
            archive_hits = [p for p in archived if "moved" in p.parts]
            self.assertEqual(len(archive_hits), 1)

    def test_multiple_stories_all_convert_with_original_ids_preserved(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("lagrangia_style", Path(tmp))
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")
            for story_id in ("STORY-001", "STORY-003"):
                target = root / "docs" / "work-items" / f"{story_id}.md"
                self.assertTrue(target.is_file(), f"{story_id} was not converted")
                self.assertIn(f"# {story_id} —", target.read_text(encoding="utf-8"))

    def test_done_status_story_gets_honest_completion_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("lagrangia_style", Path(tmp))
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")
            text = (root / "docs" / "work-items" / "STORY-001.md").read_text(encoding="utf-8")
            self.assertIn("state: done", text)
            self.assertIn("re-verify before trusting this as fresh completion evidence", text)

    def test_remote_tracker_defers_story_conversion_to_manual_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            (root / ".agentforge").mkdir(parents=True, exist_ok=True)
            remote_config = {
                "schema_version": 1,
                "tracker": {"type": "github", "repository": "acme/mylib"},
                "identifier": {"pattern": "^#\\d+$", "examples": ["#1"]},
                "context": {"max_bytes": 8000},
                "traceability": {"mode": "off"},
                "scope": {"mode": "off", "agents": {}},
                "migration_policy": {"enabled": False},
                "quality": {"post_edit": "off"},
            }
            (root / ".agentforge" / "config.json").write_text(
                json.dumps(remote_config), encoding="utf-8"
            )
            plan = _plan(root)
            story_items = [i for i in plan.items if i.path == ".claude/stories/STORY-001.md"]
            self.assertEqual(len(story_items), 1)
            self.assertEqual(story_items[0].category, migrate_v1.CATEGORY_MANUAL_REVIEW)
            self.assertFalse((root / "docs").exists())

    def test_existing_local_work_item_collision_is_never_overwritten(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            collide = root / "docs" / "work-items" / "STORY-001.md"
            collide.parent.mkdir(parents=True, exist_ok=True)
            collide.write_text("---\nstate: draft\n---\n# STORY-001 — Unrelated ticket\n", encoding="utf-8")
            before_collision_text = collide.read_text(encoding="utf-8")

            plan = _plan(root)
            story_items = [i for i in plan.items if i.path == ".claude/stories/STORY-001.md"]
            self.assertEqual(story_items[0].category, migrate_v1.CATEGORY_MANUAL_REVIEW)

            migrate_v1.apply_migration(root, approved_plan_id=plan.plan_id)
            self.assertEqual(collide.read_text(encoding="utf-8"), before_collision_text)
            # The original v1 story is not archived either -- it is not safe to
            # discard the only copy of content that could not be transformed.
            self.assertTrue((root / ".claude" / "stories" / "STORY-001.md").exists())


class MixedScaffoldTests(unittest.TestCase):
    """A project with both a v1 Codex AGENTS.md and a v1 Claude nested
    .claude/CLAUDE.md, and/or the same STORY-NNN id under both harnesses'
    story directories."""

    def test_both_constitutions_appear_in_the_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_fixture("minimal_codex", root)
            _copy_fixture("minimal_claude", root)
            plan = _plan(root)
            claude_items = [i for i in plan.items if i.path == ".claude/CLAUDE.md"]
            agents_items = [i for i in plan.items if i.path == "AGENTS.md"]
            self.assertEqual(len(claude_items), 1, "the Claude side must not vanish from the report")
            self.assertEqual(len(agents_items), 1, "the Codex side must not vanish from the report")
            # AGENTS.md already exists (Codex's), so the Claude side cannot be
            # silently merged into it -- manual_review, not guessed at.
            self.assertEqual(claude_items[0].category, migrate_v1.CATEGORY_MANUAL_REVIEW)
            self.assertEqual(agents_items[0].category, migrate_v1.CATEGORY_TRANSFORMED)

    def test_apply_writes_agents_md_and_flags_claude_md_for_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_fixture("minimal_codex", root)
            _copy_fixture("minimal_claude", root)
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")
            self.assertIn("<!-- agentforge:start -->", (root / "AGENTS.md").read_text(encoding="utf-8"))
            # Never touched, never archived -- it is still exactly where it was.
            self.assertTrue((root / ".claude" / "CLAUDE.md").is_file())

    def test_colliding_story_id_across_harnesses_never_silently_overwrites(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_fixture("minimal_codex", root)  # .agents/stories/STORY-001.md
            _copy_fixture("minimal_claude", root)  # .claude/stories/STORY-001.md (different content)

            plan = _plan(root)
            claude_story_items = [i for i in plan.items if i.path == ".claude/stories/STORY-001.md"]
            codex_story_items = [i for i in plan.items if i.path == ".agents/stories/STORY-001.md"]
            # The winning side gets two rows (transformed/create + archived/move,
            # the normal successful-conversion shape); the losing side gets
            # exactly one (manual_review, never touched) -- never two winners.
            lengths = sorted([len(claude_story_items), len(codex_story_items)])
            self.assertEqual(lengths, [1, 2])
            loser_items = claude_story_items if len(claude_story_items) == 1 else codex_story_items
            self.assertEqual(loser_items[0].category, migrate_v1.CATEGORY_MANUAL_REVIEW)

            applied = migrate_v1.apply_migration(root, approved_plan_id=plan.plan_id)
            self.assertEqual(applied.status, "ok")
            target = root / "docs" / "work-items" / "STORY-001.md"
            self.assertTrue(target.is_file())
            final_text = target.read_text(encoding="utf-8")
            # The surviving work item is traceable to exactly one original source.
            self.assertEqual(final_text.count("migrated_from:"), 1)
            # The losing side's original v1 story is never archived/discarded
            # while unconverted -- it is still on disk, untouched.
            still_present = [
                p for p in (".claude/stories/STORY-001.md", ".agents/stories/STORY-001.md")
                if (root / p).is_file()
            ]
            self.assertEqual(len(still_present), 1, still_present)


class ScopeAndPolicyWarningTests(unittest.TestCase):
    def test_scopes_json_is_migrated_into_config_scope_agents(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")
            cfg = json.loads((root / ".agentforge" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(
                set(cfg["scope"]["agents"].keys()), {"dev", "tester", "final-judge"}
            )
            self.assertEqual(
                cfg["scope"]["agents"]["dev"]["allow"],
                ["src/mylib/", "tests/", "pyproject.toml", ".github/workflows/", "README.md"],
            )
            # Never silently escalate to a blocking mode.
            self.assertEqual(cfg["scope"]["mode"], "observe")
            config_module.load_for_enforcement(root / ".agentforge" / "config.json")

    def test_never_silently_downgrades_or_overwrites_an_explicit_existing_mode(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            (root / ".agentforge").mkdir(parents=True, exist_ok=True)
            explicit_config = json.loads(json.dumps(config_module.DEFAULT_CONFIG))
            explicit_config["scope"]["mode"] = "deny-structured"
            explicit_config["scope"]["agents"] = {"dev": {"allow": ["src/"]}}
            (root / ".agentforge" / "config.json").write_text(
                json.dumps(explicit_config), encoding="utf-8"
            )
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")
            cfg = json.loads((root / ".agentforge" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(cfg["scope"]["mode"], "deny-structured")
            # Existing agent entry for "dev" is untouched (not overwritten with v1's paths).
            self.assertEqual(cfg["scope"]["agents"]["dev"]["allow"], ["src/"])
            # New agents from v1 (tester, final-judge) are still merged in.
            self.assertIn("tester", cfg["scope"]["agents"])

    def test_bash_overclaim_warning_present_whenever_pre_tool_use_and_scopes_detected(self) -> None:
        for name in ("minimal_claude", "minimal_codex", "lagrangia_style", "hand_edited"):
            with self.subTest(fixture=name):
                plan = _plan(FIXTURES_DIR / name)
                combined = " ".join(plan.warnings)
                self.assertIn("never a real security boundary", combined)
                self.assertIn("docs/threat-model.md", combined)

    def test_partial_scaffold_with_no_hooks_has_no_bash_overclaim_warning(self) -> None:
        plan = _plan(FIXTURES_DIR / "partial")
        combined = " ".join(plan.warnings)
        self.assertNotIn("never a real security boundary", combined)

    def test_codex_stop_vs_sessionend_stale_claim_is_flagged(self) -> None:
        plan = _plan(FIXTURES_DIR / "minimal_codex")
        combined = " ".join(plan.warnings)
        self.assertIn("SessionEnd", combined)
        self.assertIn("Stop", combined)
        self.assertIn("stale", combined.lower())


class HookGatingTests(unittest.TestCase):
    def test_scopes_json_is_not_archived_before_hooks_are_validated(self) -> None:
        # pre_tool_use.py fails open (unrestricted) when scopes.json is
        # missing; archiving it while the v1 hook is still wired would
        # silently disable v1's own functional scope restriction ahead of
        # any explicit validation.
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")
            self.assertTrue((root / ".claude" / "hooks" / "scopes.json").exists())

    def test_scopes_json_is_archived_once_hooks_are_validated(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            applied = _plan_and_apply(root, v2_hooks_validated=True)
            self.assertEqual(applied.status, "ok")
            self.assertFalse((root / ".claude" / "hooks" / "scopes.json").exists())
            archived = list((root / ".agentforge" / "migration-archive").rglob("scopes.json"))
            self.assertEqual(len(archived), 1)

    def test_settings_json_with_no_v1_hook_registration_is_still_reported(self) -> None:
        # A .claude/settings.json can be present (and thus part of "every
        # detected artifact must appear in the report") without carrying
        # any v1 hook registration to strip at all -- it must still get
        # exactly one report row, never be silently skipped.
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            (root / ".claude" / "settings.json").write_text(
                json.dumps({"permissions": {"allow": [], "deny": []}}), encoding="utf-8"
            )
            plan = _plan(root)
            matches = [i for i in plan.items if i.path == ".claude/settings.json"]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].category, migrate_v1.CATEGORY_RETAINED)
            self.assertEqual(matches[0].action, migrate_v1.ACTION_NONE)

    def test_hooks_are_never_disabled_without_v2_hooks_validated(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")
            # v1 hook files remain, and settings.json still wires them --
            # never leave a project with neither hook active.
            for name in ("pre_tool_use.py", "post_tool_use.py", "session_start.py"):
                self.assertTrue((root / ".claude" / "hooks" / name).exists())
            settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertIn("PreToolUse", settings.get("hooks", {}))

    def test_hooks_are_archived_and_deregistered_once_v2_hooks_validated(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            applied = _plan_and_apply(root, v2_hooks_validated=True)
            self.assertEqual(applied.status, "ok")
            for name in ("pre_tool_use.py", "post_tool_use.py", "session_start.py"):
                self.assertFalse((root / ".claude" / "hooks" / name).exists())
            settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertNotIn("hooks", settings)
            # Non-hook settings (permissions) survive untouched.
            self.assertEqual(settings["permissions"]["deny"], [
                "Bash(rm -rf *)", "Bash(git push --force*)", "Read(./.env)", "Read(./.env.*)",
            ])

    def test_codex_hooks_json_archived_whole_when_it_is_pure_v1_wiring(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_codex", Path(tmp))
            applied = _plan_and_apply(root, v2_hooks_validated=True)
            self.assertEqual(applied.status, "ok")
            self.assertFalse((root / ".codex" / "hooks.json").exists())
            archived = list((root / ".agentforge" / "migration-archive").rglob("hooks.json"))
            self.assertEqual(len(archived), 1)


class NoContentLossTests(unittest.TestCase):
    """The master safety property: every byte of every original v1 file is
    traceable somewhere in the final state after a full apply -- either
    unchanged at its original path, or moved verbatim into the archive."""

    def test_every_original_file_survives_unchanged_or_archived(self) -> None:
        for name in FIXTURE_NAMES:
            with self.subTest(fixture=name):
                with TemporaryDirectory() as tmp:
                    root = _copy_fixture(name, Path(tmp))
                    before = _snapshot(root)
                    _plan_and_apply(root, v2_hooks_validated=True)
                    after = _snapshot(root)
                    after_contents = set(after.values())
                    for rel_path, content in before.items():
                        still_there = after.get(rel_path) == content
                        archived_somewhere = content in after_contents
                        self.assertTrue(
                            still_there or archived_somewhere,
                            f"{name}: {rel_path}'s original content is not traceable anywhere "
                            "in the final state",
                        )

    def test_hand_edited_prose_is_never_lost(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("hand_edited", Path(tmp))
            _plan_and_apply(root, v2_hooks_validated=True)
            after = _snapshot(root)
            combined_text = b"\n".join(after.values()).decode("utf-8", errors="replace")
            self.assertIn("Ping @alice on Slack before merging", combined_text)
            self.assertIn("security-reviewer", combined_text)


class BlockedTests(unittest.TestCase):
    def test_invalid_existing_config_blocks_the_whole_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            (root / ".agentforge").mkdir(parents=True, exist_ok=True)
            (root / ".agentforge" / "config.json").write_text(
                json.dumps({"schema_version": 999}), encoding="utf-8"
            )
            before = _snapshot(root)
            plan = _plan(root)
            self.assertEqual(plan.status, "blocked")
            self.assertTrue(plan.blocking_issues)
            self.assertEqual(_snapshot(root), before)


class StaleApprovalTests(unittest.TestCase):
    def test_apply_with_wrong_plan_id_is_rejected_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            before = _snapshot(root)
            applied = migrate_v1.apply_migration(root, approved_plan_id="not-a-real-plan-id")
            self.assertEqual(applied.status, "stale")
            self.assertEqual(_snapshot(root), before)

    def test_apply_after_project_state_changed_is_stale(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            plan = _plan(root)
            # Simulate the project changing between plan and apply.
            (root / ".claude" / "CLAUDE.md").write_text(
                (root / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") + "\nExtra line.\n",
                encoding="utf-8",
            )
            applied = migrate_v1.apply_migration(root, approved_plan_id=plan.plan_id)
            self.assertEqual(applied.status, "stale")


class RollbackStepsPrintedTests(unittest.TestCase):
    def test_apply_returns_concrete_rollback_steps_and_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _copy_fixture("minimal_claude", Path(tmp))
            applied = _plan_and_apply(root)
            self.assertEqual(applied.status, "ok")
            self.assertTrue(applied.rollback_steps)
            self.assertTrue(any("mv " in step for step in applied.rollback_steps))
            self.assertIsNotNone(applied.manifest_path)
            self.assertTrue((root / applied.manifest_path).is_file())


if __name__ == "__main__":
    unittest.main()
