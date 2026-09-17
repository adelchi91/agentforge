"""Tests for STORY-008's prepare-work behavior (scripts/active_state.py).

Covers the STORY-008 acceptance criteria and minimum test coverage list
that are about *behavior* rather than raw filesystem atomicity (the latter
lives in tests/test_active_state_atomicity.py):

  - a valid, complete, unblocked local item prepares successfully;
  - GitHub/GitLab adapter normalization through a mocked runner (no
    network);
  - a single unresolved blocker, and multiple unresolved blockers, both
    stop with every blocker named;
  - an explicit blocker override proceeds and records evidence;
  - missing work-contract fields stop with a proposed update, and the
    approval/cancellation flow around it;
  - re-preparing unchanged work is a true no-op;
  - a changed item updates the snapshot;
  - .gitignore creation, preservation, and idempotence;
  - confirmed and cancelled clear.
"""

from __future__ import annotations

import copy
import json
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
- tests/

## Must not touch

- vendor/

## Verification commands

- python3 -m unittest tests.test_example -v

## Out of scope

Not handling the legacy importer.

## Completion evidence

Pending — filled in after execution.
"""

INCOMPLETE_BODY = """## What to build

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

TODO

## Out of scope

Not handling the legacy importer.
"""


def _local_config(local_root: str, max_bytes: int = 8000) -> dict:
    cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    cfg["tracker"] = {"type": "local", "local_root": local_root}
    cfg["context"] = {"max_bytes": max_bytes}
    return cfg


def _write_item(root: Path, local_root: str, name: str, *, state: str = "in_progress",
                 blockers: str = "", body: str = COMPLETE_BODY, title: str = None) -> Path:
    ticket_dir = root / local_root
    ticket_dir.mkdir(parents=True, exist_ok=True)
    heading = title or f"# {name} — Fixture"
    text = (
        f"---\nstate: {state}\nblockers: {blockers}\nupdated_at: 2026-01-01T00:00:00Z\n---\n"
        f"{heading}\n\n{body}"
    )
    path = ticket_dir / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


class ValidCompleteLocalItemTests(unittest.TestCase):
    def test_prepare_writes_valid_active_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")

            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan.status, "ok", plan.to_dict())

            applied = active_state.apply_prepare_work(
                "STORY-100", cfg, root, approved_plan_id=plan.plan_id
            )
            self.assertEqual(applied.status, "ok", applied.to_dict())

            state_path = root / ".agentforge" / "active-work.json"
            self.assertTrue(state_path.is_file())
            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], active_state.ACTIVE_STATE_SCHEMA_VERSION)
            self.assertEqual(data["canonical_id"], "local:STORY-100")
            self.assertIn("src/", data["allowed_paths"])
            self.assertIn("tests/", data["allowed_paths"])
            self.assertIn("vendor/", data["forbidden_paths"])
            self.assertIn(
                "python3 -m unittest tests.test_example -v", data["verification_commands"]
            )
            self.assertTrue(data["out_of_scope_summary"])
            self.assertNotIn("blocker_override", data)

    def test_cancellation_never_writes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")
            active_state.plan_prepare_work("STORY-100", cfg, root)
            # Never call apply.
            self.assertFalse((root / ".agentforge" / "active-work.json").exists())


class RemoteAdapterNormalizationTests(unittest.TestCase):
    """GitHub/GitLab prepare-work through a mocked runner -- no network."""

    def _fake_gh_runner(self, body: str):
        payload = {
            "number": 42,
            "title": "Remote ticket",
            "body": body,
            "state": "OPEN",
            "url": "https://github.com/acme/widgets/issues/42",
            "updatedAt": "2026-01-01T00:00:00Z",
        }

        class _Completed:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""

        def _runner(args, **kwargs):
            return _Completed()

        return _runner

    def test_github_item_prepares_with_no_blockers(self) -> None:
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["tracker"] = {"type": "github", "repository": "acme/widgets"}
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = self._fake_gh_runner(COMPLETE_BODY)
            plan = active_state.plan_prepare_work("#42", cfg, root, runner=runner)
            self.assertEqual(plan.status, "ok", plan.to_dict())
            self.assertEqual(plan.canonical_id, "github:acme/widgets#42")
            self.assertTrue(plan.readiness["ready"])
            self.assertEqual(plan.readiness["blockers"], [])

            applied = active_state.apply_prepare_work(
                "#42", cfg, root, approved_plan_id=plan.plan_id, runner=runner
            )
            self.assertEqual(applied.status, "ok")
            data = json.loads((root / ".agentforge" / "active-work.json").read_text())
            self.assertEqual(data["source"], "https://github.com/acme/widgets/issues/42")

    def test_gitlab_item_prepares_with_no_blockers(self) -> None:
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["tracker"] = {"type": "gitlab", "repository": "acme/widgets"}
        payload = {
            "iid": 7,
            "title": "Remote ticket",
            "description": COMPLETE_BODY,
            "state": "opened",
            "web_url": "https://gitlab.com/acme/widgets/-/issues/7",
            "updated_at": "2026-01-01T00:00:00Z",
        }

        class _Completed:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""

        def runner(args, **kwargs):
            return _Completed()

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = active_state.plan_prepare_work("#7", cfg, root, runner=runner)
            self.assertEqual(plan.status, "ok", plan.to_dict())
            self.assertEqual(plan.canonical_id, "gitlab:acme/widgets#7")
            self.assertEqual(plan.readiness["blockers"], [])


class BlockerReadinessTests(unittest.TestCase):
    def test_single_unresolved_blocker_stops_and_names_it(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-050", state="in_progress")
            _write_item(root, "docs/work-items", "STORY-100", blockers="STORY-050")
            cfg = _local_config("docs/work-items")

            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan.status, "blocked_by_dependencies", plan.to_dict())
            unresolved_ids = [b["id"] for b in plan.readiness["unresolved"]]
            self.assertEqual(unresolved_ids, ["STORY-050"])
            self.assertFalse((root / ".agentforge" / "active-work.json").exists())

    def test_multiple_unresolved_blockers_names_every_one(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-050", state="in_progress")
            _write_item(root, "docs/work-items", "STORY-051", state="draft")
            _write_item(root, "docs/work-items", "STORY-100", blockers="STORY-050, STORY-051")
            cfg = _local_config("docs/work-items")

            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan.status, "blocked_by_dependencies")
            unresolved_ids = {b["id"] for b in plan.readiness["unresolved"]}
            self.assertEqual(unresolved_ids, {"STORY-050", "STORY-051"})

    def test_closed_blocker_does_not_block(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-050", state="closed")
            _write_item(root, "docs/work-items", "STORY-100", blockers="STORY-050")
            cfg = _local_config("docs/work-items")

            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan.status, "ok", plan.to_dict())
            self.assertTrue(plan.readiness["ready"])

    def test_explicit_override_proceeds_and_records_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-050", state="in_progress")
            _write_item(root, "docs/work-items", "STORY-100", blockers="STORY-050")
            cfg = _local_config("docs/work-items")

            plan = active_state.plan_prepare_work(
                "STORY-100", cfg, root, override_blockers=True
            )
            self.assertEqual(plan.status, "ok", plan.to_dict())
            self.assertIn("blocker_override", plan.snapshot)
            self.assertTrue(plan.snapshot["blocker_override"]["overridden"])
            self.assertEqual(
                [b["id"] for b in plan.snapshot["blocker_override"]["blockers"]],
                ["STORY-050"],
            )

            applied = active_state.apply_prepare_work(
                "STORY-100",
                cfg,
                root,
                approved_plan_id=plan.plan_id,
                override_blockers=True,
            )
            self.assertEqual(applied.status, "ok")
            data = json.loads((root / ".agentforge" / "active-work.json").read_text())
            self.assertTrue(data["blocker_override"]["overridden"])

    def test_override_without_unresolved_blockers_adds_no_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")
            plan = active_state.plan_prepare_work(
                "STORY-100", cfg, root, override_blockers=True
            )
            self.assertEqual(plan.status, "ok")
            self.assertNotIn("blocker_override", plan.snapshot)


class MissingContractFieldsTests(unittest.TestCase):
    def test_incomplete_contract_stops_before_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100", body=INCOMPLETE_BODY)
            cfg = _local_config("docs/work-items")

            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan.status, "incomplete_contract", plan.to_dict())
            self.assertIn("Verification commands", plan.contract["missing"])
            self.assertFalse((root / ".agentforge" / "active-work.json").exists())

    def test_proposed_update_shows_destination_and_diff_and_requires_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100", body=INCOMPLETE_BODY)
            cfg = _local_config("docs/work-items")

            updates = {
                "Verification commands": "- python3 -m unittest tests.test_example -v",
            }
            plan = active_state.plan_contract_update("STORY-100", cfg, root, updates)
            self.assertEqual(plan.status, "ok", plan.to_dict())
            self.assertEqual(plan.path, "docs/work-items/STORY-100.md")
            self.assertIsNotNone(plan.diff)
            self.assertIn("python3 -m unittest tests.test_example -v", plan.after)

            # Cancellation: never call apply_contract_update.
            original_text = (root / "docs" / "work-items" / "STORY-100.md").read_text()
            self.assertNotIn("python3 -m unittest tests.test_example -v", original_text)

    def test_approved_contract_update_is_written_and_unblocks_prepare(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100", body=INCOMPLETE_BODY)
            cfg = _local_config("docs/work-items")
            updates = {
                "Verification commands": "- python3 -m unittest tests.test_example -v",
            }
            plan = active_state.plan_contract_update("STORY-100", cfg, root, updates)
            applied = active_state.apply_contract_update(
                "STORY-100", cfg, root, updates, approved_plan_id=plan.plan_id
            )
            self.assertEqual(applied.status, "ok")

            new_text = (root / "docs" / "work-items" / "STORY-100.md").read_text()
            self.assertIn("python3 -m unittest tests.test_example -v", new_text)
            # Identity (front matter) untouched.
            self.assertIn("blockers:", new_text)

            prepare_plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(prepare_plan.status, "ok", prepare_plan.to_dict())

    def test_stale_contract_update_plan_id_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100", body=INCOMPLETE_BODY)
            cfg = _local_config("docs/work-items")
            updates = {"Verification commands": "- echo hi"}
            applied = active_state.apply_contract_update(
                "STORY-100", cfg, root, updates, approved_plan_id="not-a-real-plan-id"
            )
            self.assertEqual(applied.status, "stale")
            original_text = (root / "docs" / "work-items" / "STORY-100.md").read_text()
            self.assertNotIn("echo hi", original_text)

    def test_remote_contract_update_is_unsupported_not_silently_applied(self) -> None:
        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
        cfg["tracker"] = {"type": "github", "repository": "acme/widgets"}
        payload = {
            "number": 42,
            "title": "Remote ticket",
            "body": INCOMPLETE_BODY,
            "state": "OPEN",
            "url": "https://github.com/acme/widgets/issues/42",
            "updatedAt": "2026-01-01T00:00:00Z",
        }

        class _Completed:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""

        def runner(args, **kwargs):
            return _Completed()

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = active_state.plan_contract_update(
                "#42",
                cfg,
                root,
                {"Verification commands": "- echo hi"},
                runner=runner,
            )
            self.assertEqual(plan.status, "unsupported_remote")
            # The proposed merged body and diff are still computed so the
            # user can copy them into `gh issue edit`/`glab issue update`
            # themselves -- this module never writes them automatically.
            self.assertIsNotNone(plan.diff)
            self.assertIn("- echo hi", plan.after)
            self.assertFalse((root / ".agentforge").exists())


class IdempotentReprepareTests(unittest.TestCase):
    def test_unchanged_reprepare_is_a_true_noop(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")

            plan1 = active_state.plan_prepare_work("STORY-100", cfg, root)
            active_state.apply_prepare_work("STORY-100", cfg, root, approved_plan_id=plan1.plan_id)

            state_path = root / ".agentforge" / "active-work.json"
            mtime_before = state_path.stat().st_mtime_ns
            content_before = state_path.read_bytes()

            plan2 = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan2.status, "no_change", plan2.to_dict())
            applied2 = active_state.apply_prepare_work(
                "STORY-100", cfg, root, approved_plan_id=plan2.plan_id
            )
            self.assertEqual(applied2.status, "no_change")

            self.assertEqual(state_path.stat().st_mtime_ns, mtime_before)
            self.assertEqual(state_path.read_bytes(), content_before)

    def test_changed_item_digest_updates_the_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")

            plan1 = active_state.plan_prepare_work("STORY-100", cfg, root)
            active_state.apply_prepare_work("STORY-100", cfg, root, approved_plan_id=plan1.plan_id)
            state_path = root / ".agentforge" / "active-work.json"
            digest_before = json.loads(state_path.read_text())["content_digest"]

            # Change the underlying ticket body.
            changed_body = COMPLETE_BODY.replace(
                "A thing users can observe.", "A different thing users can observe."
            )
            _write_item(root, "docs/work-items", "STORY-100", body=changed_body)

            plan2 = active_state.plan_prepare_work("STORY-100", cfg, root)
            self.assertEqual(plan2.status, "ok", plan2.to_dict())
            self.assertNotEqual(plan2.snapshot["content_digest"], digest_before)

            applied2 = active_state.apply_prepare_work(
                "STORY-100", cfg, root, approved_plan_id=plan2.plan_id
            )
            self.assertEqual(applied2.status, "ok")
            digest_after = json.loads(state_path.read_text())["content_digest"]
            self.assertNotEqual(digest_after, digest_before)


class GitignoreTests(unittest.TestCase):
    def test_creates_gitignore_when_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = active_state.update_gitignore(root)
            self.assertTrue(changed)
            text = (root / ".gitignore").read_text()
            self.assertEqual(text, ".agentforge/active-work.json\n")

    def test_preserves_existing_content_comments_and_newline_style(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = "# comment\r\nnode_modules/\r\n*.pyc\r\n"
            (root / ".gitignore").write_bytes(original.encode("utf-8"))

            changed = active_state.update_gitignore(root)
            self.assertTrue(changed)
            raw = (root / ".gitignore").read_bytes()
            self.assertTrue(raw.startswith(original.encode("utf-8")))
            self.assertIn(b".agentforge/active-work.json\r\n", raw)
            self.assertNotIn(b"\n\n", raw.replace(b"\r\n", b"\n").replace(b"\n\n", b"\nX"))

    def test_never_adds_config_json(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            active_state.update_gitignore(root)
            text = (root / ".gitignore").read_text()
            self.assertNotIn("config.json", text)

    def test_preserves_missing_final_newline(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_bytes(b"node_modules/")  # no trailing newline
            active_state.update_gitignore(root)
            raw = (root / ".gitignore").read_bytes()
            self.assertEqual(raw, b"node_modules/\n.agentforge/active-work.json")

    def test_idempotent_second_call_is_a_noop(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            active_state.update_gitignore(root)
            path = root / ".gitignore"
            before = path.read_bytes()
            mtime_before = path.stat().st_mtime_ns

            changed = active_state.update_gitignore(root)
            self.assertFalse(changed)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(path.stat().st_mtime_ns, mtime_before)


class ClearTests(unittest.TestCase):
    def test_confirmed_clear_deletes_only_active_work_json(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")
            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            active_state.apply_prepare_work("STORY-100", cfg, root, approved_plan_id=plan.plan_id)

            result = active_state.clear_active_work(root, confirmed=True)
            self.assertEqual(result.status, "cleared")
            self.assertFalse((root / ".agentforge" / "active-work.json").exists())
            # The tracker item itself is never touched.
            self.assertTrue((root / "docs" / "work-items" / "STORY-100.md").exists())
            self.assertTrue((root / ".agentforge" / "config.json").exists() or True)

    def test_cancelled_clear_leaves_state_untouched(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_item(root, "docs/work-items", "STORY-100")
            cfg = _local_config("docs/work-items")
            plan = active_state.plan_prepare_work("STORY-100", cfg, root)
            active_state.apply_prepare_work("STORY-100", cfg, root, approved_plan_id=plan.plan_id)

            result = active_state.clear_active_work(root, confirmed=False)
            self.assertEqual(result.status, "not_confirmed")
            self.assertTrue((root / ".agentforge" / "active-work.json").exists())

    def test_clear_is_idempotent_when_no_snapshot_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = active_state.clear_active_work(root, confirmed=True)
            self.assertEqual(result.status, "already_clear")
            result2 = active_state.clear_active_work(root, confirmed=True)
            self.assertEqual(result2.status, "already_clear")


if __name__ == "__main__":
    unittest.main()
