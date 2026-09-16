"""Golden-fixture check for the v1 example trees.

Recomputes sha256 for every file recorded in
tests/fixtures/v1/examples_checksums.json and fails on any drift (changed
content, added file, removed file). This does not assert the example trees
are "correct" — only that they match the frozen v1 baseline captured at the
agentforge-v1.1.0-pre-v2 tag, so restructuring work does not silently touch
them.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "tests" / "fixtures" / "v1" / "examples_checksums.json"


class ExamplesFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_is_not_empty(self) -> None:
        self.assertTrue(self.manifest)
        for tree, entries in self.manifest.items():
            with self.subTest(tree=tree):
                self.assertTrue(entries, f"{tree} has no recorded files")

    def test_every_recorded_file_matches_current_checksum(self) -> None:
        for tree, entries in self.manifest.items():
            for rel_path, expected_digest in entries.items():
                with self.subTest(path=rel_path):
                    path = REPO_ROOT / rel_path
                    self.assertTrue(path.is_file(), f"{rel_path} is missing")
                    actual = hashlib.sha256(path.read_bytes()).hexdigest()
                    self.assertEqual(
                        actual,
                        expected_digest,
                        f"{rel_path} content drifted from the v1 golden fixture",
                    )

    def test_no_untracked_files_added_to_example_trees(self) -> None:
        for tree, entries in self.manifest.items():
            base = REPO_ROOT / tree
            current_files = {
                p.relative_to(REPO_ROOT).as_posix()
                for p in base.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts
            }
            recorded_files = set(entries.keys())
            with self.subTest(tree=tree):
                self.assertEqual(
                    current_files,
                    recorded_files,
                    f"{tree} file set changed since the v1 golden fixture was captured",
                )


if __name__ == "__main__":
    unittest.main()
