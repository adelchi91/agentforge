"""Tests for STORY-005 requirement 14: surrounding user content is
preserved byte-for-byte, including exact line endings and final-newline
state, when `scripts/setup.py` inserts or updates the AgentForge block.

These tests read and write raw bytes throughout (never `str`-mode file
handles) so a Python-level newline translation could never mask a real
preservation bug.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import setup  # noqa: E402


def _plan_and_apply(root, **kwargs):
    """plan_setup then apply_setup with the freshly computed plan_id — the
    normal, non-stale path a caller who approves immediately takes."""
    plan = setup.plan_setup(root, **kwargs)
    return setup.apply_setup(root, approved_plan_id=plan.plan_id, **kwargs)


class LfPreservationTests(unittest.TestCase):
    def test_existing_lf_prose_prefix_is_byte_identical_after_insert(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = b"# Title\n\nSome LF-only prose.\nSecond line.\n"
            (root / "CLAUDE.md").write_bytes(original)

            _plan_and_apply(root, constitution_target="CLAUDE.md")

            final = (root / "CLAUDE.md").read_bytes()
            self.assertTrue(final.startswith(original), final)

    def test_missing_final_newline_is_preserved_before_the_inserted_block(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = b"# Title\n\nNo trailing newline here"
            (root / "CLAUDE.md").write_bytes(original)

            _plan_and_apply(root, constitution_target="CLAUDE.md")

            final = (root / "CLAUDE.md").read_bytes()
            self.assertTrue(final.startswith(original), final)
            # Exactly one newline was added to separate the prefix from our
            # block — the original bytes up to and including "here" are
            # untouched, never rstripped.
            self.assertEqual(final[: len(original)], original)

    def test_no_carriage_returns_are_introduced_into_an_lf_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_bytes(b"# Title\n\nBody.\n")
            _plan_and_apply(root, constitution_target="CLAUDE.md")
            final = (root / "CLAUDE.md").read_bytes()
            self.assertNotIn(b"\r", final)


class CrlfPreservationTests(unittest.TestCase):
    def test_existing_crlf_prose_prefix_is_byte_identical_after_insert(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = b"# Title\r\n\r\nSome CRLF prose.\r\nSecond line.\r\n"
            (root / "CLAUDE.md").write_bytes(original)

            _plan_and_apply(root, constitution_target="CLAUDE.md")

            final = (root / "CLAUDE.md").read_bytes()
            self.assertTrue(final.startswith(original), final)

    def test_inserted_block_uses_crlf_to_match_the_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_bytes(b"# Title\r\n\r\nBody.\r\n")

            _plan_and_apply(root, constitution_target="CLAUDE.md")

            final_text = (root / "CLAUDE.md").read_bytes().decode("utf-8")
            appended = final_text[final_text.index(setup.MARKER_START) :]
            self.assertNotIn("\n", appended.replace("\r\n", ""))

    def test_crlf_file_missing_final_newline_preserves_prefix(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = b"# Title\r\n\r\nNo trailing newline here (CRLF file)"
            (root / "CLAUDE.md").write_bytes(original)

            _plan_and_apply(root, constitution_target="CLAUDE.md")

            final = (root / "CLAUDE.md").read_bytes()
            self.assertEqual(final[: len(original)], original)


class BlockUpdatePreservationTests(unittest.TestCase):
    def test_replacing_a_stale_block_touches_only_the_marker_span(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale_block = (
                f"{setup.MARKER_START}\nold stale content\n{setup.MARKER_END}"
            )
            original = (
                b"# Title\n\nBefore.\n\n"
                + stale_block.encode("utf-8")
                + b"\n\nAfter.\n"
            )
            (root / "CLAUDE.md").write_bytes(original)

            plan = _plan_and_apply(root, constitution_target="CLAUDE.md")
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.change_for("CLAUDE.md").action, "update")

            final = (root / "CLAUDE.md").read_bytes().decode("utf-8")
            self.assertTrue(final.startswith("# Title\n\nBefore.\n\n"))
            self.assertTrue(final.endswith("\n\nAfter.\n"))
            self.assertNotIn("old stale content", final)
            self.assertEqual(final.count(setup.MARKER_START), 1)


class OtherConstitutionFilePreservationTests(unittest.TestCase):
    def test_unselected_file_is_completely_unchanged(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude_bytes = b"claude prose\r\nwith CRLF\r\n"
            agents_bytes = b"agents prose without trailing newline"
            (root / "CLAUDE.md").write_bytes(claude_bytes)
            (root / "AGENTS.md").write_bytes(agents_bytes)

            _plan_and_apply(root, constitution_target="CLAUDE.md")

            self.assertEqual((root / "AGENTS.md").read_bytes(), agents_bytes)


class RepeatedApplyByteEqualityTests(unittest.TestCase):
    def test_second_apply_produces_byte_identical_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_bytes(b"# Title\n\nBody.\n")

            _plan_and_apply(root, constitution_target="CLAUDE.md")
            after_first = (root / "CLAUDE.md").read_bytes()

            _plan_and_apply(root, constitution_target="CLAUDE.md")
            after_second = (root / "CLAUDE.md").read_bytes()

            self.assertEqual(after_first, after_second)

    def test_second_apply_config_json_is_byte_identical(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _plan_and_apply(root, constitution_target="CLAUDE.md")
            after_first = (root / ".agentforge" / "config.json").read_bytes()

            _plan_and_apply(root, constitution_target="CLAUDE.md")
            after_second = (root / ".agentforge" / "config.json").read_bytes()

            self.assertEqual(after_first, after_second)


if __name__ == "__main__":
    unittest.main()
