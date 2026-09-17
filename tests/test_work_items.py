"""Tests for the STORY-006 WorkItem record and local Markdown adapter
(scripts/work_items.py).

Covers:
  - the normalized WorkItem record's shape;
  - the syntactic identifier-shape classifier (repository vs. work-item
    identifier vs. path vs. opaque local slug) named in STORY-006's
    "precise distinction" requirement;
  - local Markdown resolution: no network access, IDs and paths resolving
    to the same canonical identity, traversal/absolute-path rejection,
    identifier.pattern enforcement, malformed-item detection;
  - sanitize + context.max_bytes truncation tying into the STORY-004
    `context.max_bytes` config field;
  - the "reject ambiguous bare numbers when the provider is not known"
    requirement (no config / no configured tracker at all).

GitHub/GitLab adapter behavior (mocked subprocess calls) lives in
tests/test_tracker_adapters.py, not here.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config, work_items  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "work_items"
LOCAL_ROOT_REL = "tests/fixtures/work_items/local_root"


def _local_config(max_bytes: int = 8000) -> dict:
    cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    cfg["tracker"] = {"type": "local", "local_root": LOCAL_ROOT_REL}
    cfg["context"] = {"max_bytes": max_bytes}
    return cfg


class WorkItemRecordTests(unittest.TestCase):
    def test_work_item_has_required_fields(self) -> None:
        item = work_items.WorkItem(
            provider="local",
            canonical_id="local:STORY-100",
            title="Fixture",
            source="tests/fixtures/work_items/local_root/STORY-100.md",
            body="body text",
            state="open",
            blockers=("local:STORY-050",),
            updated_at="2026-01-01T00:00:00Z",
            content_digest="abc123",
        )
        self.assertEqual(item.provider, "local")
        self.assertEqual(item.canonical_id, "local:STORY-100")
        self.assertEqual(item.blockers, ("local:STORY-050",))
        self.assertFalse(item.truncated)

    def test_work_item_is_immutable(self) -> None:
        item = work_items.WorkItem(
            provider="local",
            canonical_id="local:STORY-100",
            title="Fixture",
            source="x",
            body="y",
            state="open",
            blockers=(),
            updated_at=None,
            content_digest="abc123",
        )
        with self.assertRaises(Exception):
            item.title = "mutated"  # type: ignore[misc]


class IdentifierShapeTests(unittest.TestCase):
    def test_hash_number_is_issue_reference(self) -> None:
        self.assertEqual(work_items.classify_identifier_shape("#123"), "issue_reference")

    def test_bare_number_is_issue_reference(self) -> None:
        self.assertEqual(work_items.classify_identifier_shape("123"), "issue_reference")

    def test_owner_slash_repo_is_repository(self) -> None:
        self.assertEqual(work_items.classify_identifier_shape("acme/widgets"), "repository")

    def test_markdown_path_is_path(self) -> None:
        self.assertEqual(
            work_items.classify_identifier_shape("docs/work-items/STORY-006.md"), "path"
        )

    def test_bare_slug_is_opaque(self) -> None:
        self.assertEqual(work_items.classify_identifier_shape("STORY-006"), "opaque")


class AmbiguousBareNumberTests(unittest.TestCase):
    """STORY-006: 'reject ambiguous bare numbers when the provider is not
    known' — no config / no configured tracker at all."""

    def test_bare_number_with_no_config_is_ambiguous(self) -> None:
        result = work_items.resolve_work_item("123", None)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_AMBIGUOUS_IDENTIFIER)

    def test_hash_number_with_no_config_is_ambiguous(self) -> None:
        result = work_items.resolve_work_item("#123", None)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_AMBIGUOUS_IDENTIFIER)

    def test_non_numeric_identifier_with_no_config_is_unsupported_not_ambiguous(self) -> None:
        result = work_items.resolve_work_item("STORY-100", None)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_UNSUPPORTED_TRACKER)

    def test_bare_number_with_malformed_tracker_type_is_ambiguous(self) -> None:
        cfg = _local_config()
        cfg["tracker"] = {"type": "not-a-real-provider"}
        result = work_items.resolve_work_item("123", cfg)
        self.assertEqual(result.error.kind, work_items.ERROR_AMBIGUOUS_IDENTIFIER)


class UnsupportedTrackerTests(unittest.TestCase):
    def test_unknown_tracker_type_is_rejected(self) -> None:
        cfg = _local_config()
        cfg["tracker"] = {"type": "jira"}
        result = work_items.resolve_work_item("PROJ-1", cfg)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_UNSUPPORTED_TRACKER)

    def test_missing_tracker_section_is_rejected(self) -> None:
        cfg = _local_config()
        del cfg["tracker"]
        result = work_items.resolve_work_item("STORY-100", cfg)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_UNSUPPORTED_TRACKER)


class LocalResolutionTests(unittest.TestCase):
    def test_resolve_by_id(self) -> None:
        cfg = _local_config()
        result = work_items.resolve_work_item("STORY-100", cfg, project_root=REPO_ROOT)
        self.assertTrue(result.ok, result.error)
        item = result.item
        self.assertEqual(item.provider, "local")
        self.assertEqual(item.canonical_id, "local:STORY-100")
        self.assertEqual(item.state, "in_progress")
        self.assertEqual(item.blockers, ("STORY-050", "STORY-051"))
        self.assertEqual(item.updated_at, "2026-01-01T00:00:00Z")
        self.assertIn("Fixture work item with front matter", item.title)
        self.assertFalse(item.truncated)

    def test_resolve_by_path_matches_resolve_by_id(self) -> None:
        cfg = _local_config()
        by_id = work_items.resolve_work_item("STORY-100", cfg, project_root=REPO_ROOT)
        by_path = work_items.resolve_work_item(
            f"{LOCAL_ROOT_REL}/STORY-100.md", cfg, project_root=REPO_ROOT
        )
        self.assertTrue(by_id.ok and by_path.ok)
        self.assertEqual(by_id.item.canonical_id, by_path.item.canonical_id)
        self.assertEqual(by_id.item.content_digest, by_path.item.content_digest)

    def test_resolve_without_front_matter_uses_defaults(self) -> None:
        cfg = _local_config()
        result = work_items.resolve_work_item("STORY-101", cfg, project_root=REPO_ROOT)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.item.state, "unknown")
        self.assertEqual(result.item.blockers, ())
        self.assertIsNone(result.item.updated_at)

    def test_missing_local_item_is_not_found(self) -> None:
        cfg = _local_config()
        result = work_items.resolve_work_item("STORY-999", cfg, project_root=REPO_ROOT)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_NOT_FOUND)

    def test_empty_local_item_is_malformed(self) -> None:
        cfg = _local_config()
        result = work_items.resolve_work_item("STORY-102", cfg, project_root=REPO_ROOT)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_MALFORMED_ITEM)

    def test_identifier_not_matching_pattern_is_malformed(self) -> None:
        cfg = _local_config()
        result = work_items.resolve_work_item("not_a_story_id!!", cfg, project_root=REPO_ROOT)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_MALFORMED_ITEM)

    def test_path_traversal_is_rejected_as_malformed(self) -> None:
        cfg = _local_config()
        result = work_items.resolve_work_item(
            f"{LOCAL_ROOT_REL}/../../../../../etc/passwd", cfg, project_root=REPO_ROOT
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_MALFORMED_ITEM)

    def test_absolute_path_is_rejected_as_malformed(self) -> None:
        cfg = _local_config()
        result = work_items.resolve_work_item("/etc/passwd", cfg, project_root=REPO_ROOT)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_MALFORMED_ITEM)

    def test_same_basename_in_different_subdirectories_does_not_collide(self) -> None:
        # STORY-006 code-review finding: canonical_id must be derived from
        # the full path relative to local_root, not just the filename
        # stem, or "epics/STORY-200.md" and "archive/STORY-200.md" would
        # silently collapse onto the same canonical identity.
        cfg = _local_config()
        epics = work_items.resolve_work_item(
            f"{LOCAL_ROOT_REL}/epics/STORY-200.md", cfg, project_root=REPO_ROOT
        )
        archive = work_items.resolve_work_item(
            f"{LOCAL_ROOT_REL}/archive/STORY-200.md", cfg, project_root=REPO_ROOT
        )
        self.assertTrue(epics.ok and archive.ok)
        self.assertNotEqual(epics.item.canonical_id, archive.item.canonical_id)
        self.assertEqual(epics.item.canonical_id, "local:epics/STORY-200")
        self.assertEqual(archive.item.canonical_id, "local:archive/STORY-200")

    def test_no_network_access_local_resolution_never_imports_subprocess_call(self) -> None:
        # Local resolution must never shell out. Patch subprocess.run to
        # raise if it is ever called during a local resolution.
        import subprocess

        def _boom(*args, **kwargs):  # pragma: no cover - only hit on regression
            raise AssertionError("local resolution must never call subprocess.run")

        original = subprocess.run
        subprocess.run = _boom
        try:
            cfg = _local_config()
            result = work_items.resolve_work_item("STORY-100", cfg, project_root=REPO_ROOT)
            self.assertTrue(result.ok, result.error)
        finally:
            subprocess.run = original

    def test_sanitize_strips_control_characters(self) -> None:
        sanitized, truncated = work_items._sanitize_text("hello\x00\x07world", None)
        self.assertEqual(sanitized, "helloworld")
        self.assertFalse(truncated)

    def test_max_bytes_truncates_large_body(self) -> None:
        cfg = _local_config(max_bytes=200)
        result = work_items.resolve_work_item("STORY-103", cfg, project_root=REPO_ROOT)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.item.truncated)
        self.assertLessEqual(len(result.item.body.encode("utf-8")), 200)

    def test_max_bytes_ties_into_story_004_context_field(self) -> None:
        # context.max_bytes is the STORY-004 config field (scripts/config.py
        # DEFAULT_CONFIG["context"]["max_bytes"]); confirm the field exists
        # and this module reads it rather than inventing a parallel knob.
        self.assertIn("max_bytes", config.DEFAULT_CONFIG["context"])
        cfg = _local_config(max_bytes=config.DEFAULT_CONFIG["context"]["max_bytes"])
        result = work_items.resolve_work_item("STORY-100", cfg, project_root=REPO_ROOT)
        self.assertTrue(result.ok, result.error)
        self.assertFalse(result.item.truncated)


if __name__ == "__main__":
    unittest.main()
