"""Tests for STORY-008's atomicity/safety guarantees
(scripts/active_state.py):

  - oversized state is rejected (or deterministically reduced) rather than
    truncated into invalid JSON;
  - a failed fetch, contract validation, or write preserves whatever valid
    snapshot already existed;
  - a malformed previous snapshot never crashes a subsequent successful
    prepare;
  - the runtime-state destination is resolved through symlinks and
    refuses to write outside the project root.

tests/test_prepare_work.py covers the business-logic acceptance criteria
(readiness, contract completeness, gitignore, clear); this file is
specifically about "what happens when something goes wrong."
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import active_state, config  # noqa: E402

COMPLETE_BODY = """## What to build

A thing users can observe.

## Blocked by

None

## Acceptance criteria

- Running the CLI with --help prints usage.

## May touch

- src/

## Must not touch

- vendor/

## Verification commands

- python3 -m unittest tests.test_example_one -v
- python3 -m unittest tests.test_example_two -v
- python3 -m unittest tests.test_example_three -v
- python3 -m unittest tests.test_example_four -v

## Out of scope

Not handling the legacy importer.

## Completion evidence

Pending — filled in after execution.
"""


def _local_config(local_root: str, max_bytes: int = 8000) -> dict:
    cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    cfg["tracker"] = {"type": "local", "local_root": local_root}
    cfg["context"] = {"max_bytes": max_bytes}
    return cfg


def _write_item(root: Path, local_root: str, name: str, *, state: str = "in_progress",
                 blockers: str = "", body: str = COMPLETE_BODY, out_of_scope_extra: str = "") -> Path:
    ticket_dir = root / local_root
    ticket_dir.mkdir(parents=True, exist_ok=True)
    body_text = body
    if out_of_scope_extra:
        body_text = body.replace(
            "Not handling the legacy importer.",
            "Not handling the legacy importer. " + out_of_scope_extra,
        )
    text = (
        f"---\nstate: {state}\nblockers: {blockers}\nupdated_at: 2026-01-01T00:00:00Z\n---\n"
        f"# {name} — Fixture\n\n{body_text}"
    )
    path = ticket_dir / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


class OversizedStateTests(unittest.TestCase):
    def test_oversized_snapshot_is_rejected_not_truncated_invalid(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # A full, complete contract (kept well under max_bytes at the
            # raw-body/resolve stage) whose four real verification commands
            # alone -- a field this module never reduces -- push the final
            # serialized snapshot's fixed overhead (schema_version,
            # canonical_id, content_digest, timestamp, ...) past max_bytes
            # even after title/out_of_scope_summary are shrunk to nothing.
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items", max_bytes=600)

            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan.status, "oversized", plan.to_dict())
            self.assertIsNone(plan.snapshot)
            self.assertFalse((root / ".agentforge" / "active-work.json").exists())

    def test_reducible_snapshot_shrinks_descriptive_fields_and_stays_valid_json(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            moderately_long_out_of_scope = "y" * 400
            _write_item(
                root,
                "docs/work-items",
                "STORY-100",
                out_of_scope_extra=moderately_long_out_of_scope,
            )
            cfg = _local_config("docs/work-items", max_bytes=900)

            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan.status, "ok", plan.to_dict())
            serialized = json.dumps(plan.snapshot, indent=2, sort_keys=True) + "\n"
            self.assertLessEqual(len(serialized.encode("utf-8")), 900)
            # Identity, source, scope, and verification are never touched by
            # size reduction.
            self.assertEqual(plan.snapshot["canonical_id"], "local:STORY-100")
            self.assertIn("src/", plan.snapshot["allowed_paths"])
            self.assertIn("vendor/", plan.snapshot["forbidden_paths"])
            self.assertTrue(plan.snapshot["verification_commands"])
            # The still-valid JSON was parsed above without raising.

    def test_oversized_state_preserves_previous_valid_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")
            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            active_state.apply_prepare_work("STORY-100", cfg, root, approved_plan_id=plan.plan_id)
            state_path = root / ".agentforge" / "active-work.json"
            previous_bytes = state_path.read_bytes()

            tiny_cfg = _local_config("docs/work-items", max_bytes=600)
            plan2 = active_state.plan_prepare_work("STORY-100", tiny_cfg, root)
            self.assertEqual(plan2.status, "oversized")
            applied2 = active_state.apply_prepare_work(
                "STORY-100", tiny_cfg, root, approved_plan_id=plan2.plan_id
            )
            self.assertEqual(applied2.status, "oversized")
            self.assertEqual(state_path.read_bytes(), previous_bytes)


class FetchAndWriteFailureTests(unittest.TestCase):
    def test_resolve_failure_preserves_previous_valid_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")
            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            active_state.apply_prepare_work("STORY-100", cfg, root, approved_plan_id=plan.plan_id)
            state_path = root / ".agentforge" / "active-work.json"
            previous_bytes = state_path.read_bytes()

            # Delete the underlying ticket so resolution now fails.
            (root / "docs" / "work-items" / "STORY-100.md").unlink()

            plan2 = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan2.status, "resolve_error", plan2.to_dict())
            applied2 = active_state.apply_prepare_work(
                "STORY-100", cfg, root, approved_plan_id="whatever"
            )
            self.assertEqual(applied2.status, "resolve_error")
            self.assertEqual(state_path.read_bytes(), previous_bytes)

    def test_write_failure_preserves_previous_valid_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")
            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            active_state.apply_prepare_work("STORY-100", cfg, root, approved_plan_id=plan.plan_id)
            state_path = root / ".agentforge" / "active-work.json"
            previous_bytes = state_path.read_bytes()

            # Change the item so a real "ok" plan would be produced, then
            # sabotage the write by replacing .agentforge with a read-only
            # directory (permission denied on the temp file creation).
            changed_body = COMPLETE_BODY.replace(
                "A thing users can observe.", "A changed thing users can observe."
            )
            _write_item(root, "docs/work-items", "STORY-100", body=changed_body)

            agentforge_dir = root / ".agentforge"
            original_mode = agentforge_dir.stat().st_mode
            os.chmod(agentforge_dir, 0o500)  # read + execute, no write
            try:
                plan2 = active_state.plan_prepare_work("STORY-100", cfg, root)
                self.assertEqual(plan2.status, "ok", plan2.to_dict())
                applied2 = active_state.apply_prepare_work(
                    "STORY-100", cfg, root, approved_plan_id=plan2.plan_id
                )
                self.assertEqual(applied2.status, "write_error", applied2.to_dict())
            finally:
                os.chmod(agentforge_dir, original_mode)

            self.assertEqual(state_path.read_bytes(), previous_bytes)
            # No stray temp files left behind by the failed write.
            leftovers = [p for p in agentforge_dir.iterdir() if p.name.startswith(".active-work.json.")]
            self.assertEqual(leftovers, [])


class MalformedPreviousStateTests(unittest.TestCase):
    def test_malformed_previous_state_does_not_crash_and_is_overwritten(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")

            state_dir = root / ".agentforge"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "active-work.json").write_text("{not valid json!!", encoding="utf-8")

            previous = active_state.read_previous_snapshot(root)
            self.assertIsNone(previous)

            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan.status, "ok", plan.to_dict())
            applied = active_state.apply_prepare_work(
                "STORY-100", cfg, root, approved_plan_id=plan.plan_id
            )
            self.assertEqual(applied.status, "ok")

            data = json.loads((state_dir / "active-work.json").read_text())
            self.assertEqual(data["canonical_id"], "local:STORY-100")

    def test_malformed_previous_state_is_not_an_object_returns_none(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".agentforge"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "active-work.json").write_text("[1, 2, 3]", encoding="utf-8")
            self.assertIsNone(active_state.read_previous_snapshot(root))


class AtomicWriteTests(unittest.TestCase):
    def test_write_uses_temp_file_and_replace_no_partial_file_visible(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")
            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            active_state.apply_prepare_work("STORY-100", cfg, root, approved_plan_id=plan.plan_id)

            agentforge_dir = root / ".agentforge"
            leftovers = [p for p in agentforge_dir.iterdir() if p.name.startswith(".active-work.json.")]
            self.assertEqual(leftovers, [])
            data = json.loads((agentforge_dir / "active-work.json").read_text())
            self.assertEqual(data["canonical_id"], "local:STORY-100")


class SymlinkPathSafetyTests(unittest.TestCase):
    def test_symlinked_agentforge_dir_escaping_project_root_is_refused(self) -> None:
        with TemporaryDirectory() as outside_tmp, TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = Path(outside_tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")

            # .agentforge is a symlink pointing outside the project root.
            outside_target = outside / "escaped-agentforge"
            outside_target.mkdir()
            (root / ".agentforge").symlink_to(outside_target, target_is_directory=True)

            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan.status, "ok", plan.to_dict())
            applied = active_state.apply_prepare_work(
                "STORY-100", cfg, root, approved_plan_id=plan.plan_id
            )
            self.assertEqual(applied.status, "write_error", applied.to_dict())
            self.assertEqual(list(outside_target.iterdir()), [])

    def test_clear_refuses_to_follow_an_escaping_symlink(self) -> None:
        with TemporaryDirectory() as outside_tmp, TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = Path(outside_tmp)
            outside_target = outside / "escaped-agentforge"
            outside_target.mkdir()
            canary = outside_target / "active-work.json"
            canary.write_text("do not delete me", encoding="utf-8")
            (root / ".agentforge").symlink_to(outside_target, target_is_directory=True)

            result = active_state.clear_active_work(root, confirmed=True)
            self.assertEqual(result.status, "already_clear")
            self.assertTrue(canary.exists())
            self.assertEqual(canary.read_text(), "do not delete me")


if __name__ == "__main__":
    unittest.main()
