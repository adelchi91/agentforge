"""Tests for the STORY-011 commit-message traceability policy
(scripts/git_policy.py).

Covers the STORY-011 acceptance criteria that do not require a real Git
repository (see tests/test_git_hook_installation.py for the real-repo,
real-`git commit` scenarios):

  - valid/invalid commit-message fixtures behave correctly for GitHub,
    GitLab, and local identifier.pattern configurations;
  - an identifier is only accepted as a whole token (fullmatch semantics),
    never a substring embedded in an unrelated word;
  - Git's own auto-generated merge-commit messages are exempt, narrowly;
    a GitHub "Merge pull request" message and a `git revert` message are
    NOT exempt;
  - `core.commentChar` comment lines (and the `git commit -v` scissors
    line) are stripped before checking, but a real "#123 ..." subject
    is not mistaken for a comment;
  - `traceability.mode` off/observe/enforce each behave as documented;
  - a missing or invalid `.agentforge/config.json` behaves as documented
    (skip vs. fail closed).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config as agentforge_config  # noqa: E402
from scripts import git_policy  # noqa: E402

LOCAL_CFG = {
    "schema_version": 1,
    "tracker": {"type": "local", "local_root": "docs/work-items"},
    "identifier": {"pattern": "^STORY-\\d{3,}$", "examples": ["STORY-001", "STORY-042"]},
    "context": {"max_bytes": 8000},
    "traceability": {"mode": "enforce"},
    "scope": {"mode": "off", "agents": {}},
    "migration_policy": {"enabled": False},
    "quality": {"post_edit": "off"},
}

GITHUB_CFG = {
    **LOCAL_CFG,
    "tracker": {"type": "github", "repository": "adelchi91/agentforge"},
    "identifier": {"pattern": "^#\\d+$", "examples": ["#1", "#123"]},
}

GITLAB_CFG = {
    **LOCAL_CFG,
    "tracker": {"type": "gitlab", "repository": "adelchi91-group/agentforge"},
    "identifier": {"pattern": "^#\\d+$", "examples": ["#1", "#123"]},
}


def _with_mode(cfg: dict, mode: str) -> dict:
    return {**cfg, "traceability": {"mode": mode}}


class CommentAndScissorsStrippingTests(unittest.TestCase):
    def test_default_git_template_comment_lines_are_removed(self) -> None:
        raw = (
            "STORY-001: fix the thing\n"
            "\n"
            "# Please enter the commit message for your changes. Lines starting\n"
            "# with '#' will be ignored, and an empty message aborts the commit.\n"
            "#\n"
            "# On branch main\n"
        )
        cleaned = git_policy.strip_comment_lines(raw)
        self.assertNotIn("Please enter", cleaned)
        self.assertIn("STORY-001: fix the thing", cleaned)

    def test_scissors_line_and_everything_after_is_removed(self) -> None:
        raw = (
            "STORY-001: fix the thing\n"
            "# ------------------------ >8 ------------------------\n"
            "# Do not modify or remove the line above.\n"
            "diff --git a/f b/f\n"
            "+STORY-999 leaked from a diff hunk, not the real message\n"
        )
        cleaned = git_policy.strip_comment_lines(raw)
        self.assertNotIn("STORY-999", cleaned)
        self.assertIn("STORY-001", cleaned)

    def test_hash_number_subject_is_not_mistaken_for_a_comment(self) -> None:
        # A GitHub-style "#123 ..." subject starts with the comment
        # character but has no space after it -- Git's own template
        # comments always write "# " with a space.
        raw = "#123 fix the thing\n"
        cleaned = git_policy.strip_comment_lines(raw)
        self.assertIn("#123", cleaned)

    def test_hash_space_number_is_treated_as_a_comment(self) -> None:
        raw = "# 123 this looks like a comment because of the space\nSTORY-001: real subject\n"
        cleaned = git_policy.strip_comment_lines(raw)
        self.assertNotIn("this looks like a comment", cleaned)
        self.assertIn("STORY-001", cleaned)


class IdentifierTokenMatchingTests(unittest.TestCase):
    def test_exact_token_matches(self) -> None:
        found = git_policy.find_identifier_reference("STORY-042: fix the bug", r"^STORY-\d{3,}$")
        self.assertEqual(found, "STORY-042")

    def test_trailing_punctuation_is_stripped_before_matching(self) -> None:
        found = git_policy.find_identifier_reference("See (STORY-042).", r"^STORY-\d{3,}$")
        self.assertEqual(found, "STORY-042")

    def test_substring_inside_a_larger_word_does_not_match(self) -> None:
        # "MYSTORY-001" must never satisfy a check meant for "STORY-001" --
        # this is the fullmatch-on-whole-token guarantee, the opposite of
        # v1's "token anywhere in the string" bug.
        found = git_policy.find_identifier_reference("MYSTORY-001 refactor", r"^STORY-\d{3,}$")
        self.assertIsNone(found)

    def test_hash_number_pattern_matches_github_style(self) -> None:
        found = git_policy.find_identifier_reference("Fixes #123 for real", r"^#\d+$")
        self.assertEqual(found, "#123")

    def test_owner_repo_hash_number_pattern_is_driven_by_config_not_hardcoded(self) -> None:
        # STORY-011: "owner/repo#123" is supported when a project's own
        # identifier.pattern says so -- never a hardcoded provider rule.
        pattern = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+$"
        found = git_policy.find_identifier_reference(
            "Cross-repo fix, see adelchi91/agentforge#123", pattern
        )
        self.assertEqual(found, "adelchi91/agentforge#123")

    def test_no_reference_returns_none(self) -> None:
        found = git_policy.find_identifier_reference("just a plain commit message", r"^STORY-\d{3,}$")
        self.assertIsNone(found)

    def test_invalid_pattern_returns_none_rather_than_raising(self) -> None:
        found = git_policy.find_identifier_reference("STORY-001", "(unterminated")
        self.assertIsNone(found)


class MergeCommitExemptionTests(unittest.TestCase):
    def test_git_merge_branch_message_is_exempt(self) -> None:
        self.assertTrue(git_policy.is_git_merge_commit("Merge branch 'feature/x' into main"))

    def test_git_merge_remote_tracking_branch_is_exempt(self) -> None:
        self.assertTrue(
            git_policy.is_git_merge_commit("Merge remote-tracking branch 'origin/main'")
        )

    def test_git_merge_tag_is_exempt(self) -> None:
        self.assertTrue(git_policy.is_git_merge_commit("Merge tag 'v1.2.3'"))

    def test_git_octopus_merge_branches_is_exempt(self) -> None:
        # Regression test (found in code review): `git merge --no-ff
        # --no-edit b1 b2` generates the PLURAL subject "Merge branches
        # 'b1' and 'b2'" (confirmed by actually running it) -- an earlier
        # version of the pattern only matched the singular "branch" and
        # would have wrongly required a traceability reference here.
        self.assertTrue(git_policy.is_git_merge_commit("Merge branches 'b1' and 'b2'"))

    def test_github_pull_request_merge_is_not_exempt(self) -> None:
        # A hosting-provider convention, not something Git itself
        # generates -- the default exemption is deliberately narrower.
        self.assertFalse(
            git_policy.is_git_merge_commit("Merge pull request #42 from someone/branch")
        )

    def test_revert_commit_is_not_exempt(self) -> None:
        self.assertFalse(
            git_policy.is_git_merge_commit('Revert "STORY-001: add the thing"')
        )

    def test_ordinary_commit_is_not_exempt(self) -> None:
        self.assertFalse(git_policy.is_git_merge_commit("fix the merge conflict resolution logic"))


class ValidateCommitMessageTests(unittest.TestCase):
    def test_off_mode_always_passes_without_checking(self) -> None:
        cfg = _with_mode(LOCAL_CFG, "off")
        result = git_policy.validate_commit_message("no reference at all", cfg)
        self.assertTrue(result.ok)
        self.assertFalse(result.blocking)

    def test_enforce_mode_passes_with_a_valid_local_reference(self) -> None:
        result = git_policy.validate_commit_message("STORY-001: add the thing", LOCAL_CFG)
        self.assertTrue(result.ok)
        self.assertTrue(result.blocking)

    def test_enforce_mode_fails_without_a_reference(self) -> None:
        result = git_policy.validate_commit_message("no reference at all", LOCAL_CFG)
        self.assertFalse(result.ok)
        self.assertTrue(result.blocking)

    def test_enforce_mode_fails_for_a_token_only_in_an_unrelated_word(self) -> None:
        # Characterizes the FIX for v1's StoryTokenOutsideMessageTests bug:
        # the token must be the actual reference, not embedded in a larger
        # word that happens to contain it.
        result = git_policy.validate_commit_message("XSTORY-001-suffix nothing real", LOCAL_CFG)
        self.assertFalse(result.ok)

    def test_observe_mode_never_blocks_even_without_a_reference(self) -> None:
        cfg = _with_mode(LOCAL_CFG, "observe")
        result = git_policy.validate_commit_message("no reference at all", cfg)
        self.assertFalse(result.ok)
        self.assertFalse(result.blocking)

    def test_github_pattern_accepts_hash_number(self) -> None:
        result = git_policy.validate_commit_message("Fixes #123 in prod", GITHUB_CFG)
        self.assertTrue(result.ok)

    def test_github_pattern_rejects_missing_reference(self) -> None:
        result = git_policy.validate_commit_message("no issue reference", GITHUB_CFG)
        self.assertFalse(result.ok)

    def test_gitlab_pattern_accepts_hash_number(self) -> None:
        result = git_policy.validate_commit_message("Closes #7", GITLAB_CFG)
        self.assertTrue(result.ok)

    def test_merge_commit_is_exempt_under_enforce(self) -> None:
        result = git_policy.validate_commit_message("Merge branch 'develop'", LOCAL_CFG)
        self.assertTrue(result.ok)
        self.assertTrue(result.exempt)

    def test_revert_commit_still_requires_a_reference_under_enforce(self) -> None:
        result = git_policy.validate_commit_message('Revert "some change"', LOCAL_CFG)
        self.assertFalse(result.ok)
        self.assertFalse(result.exempt)

    def test_comment_lines_are_not_scanned_for_a_reference(self) -> None:
        # A STORY token that only appears in a comment line (e.g. because
        # it happened to be part of a listed filename in a `git commit -v`
        # template) must not satisfy the check.
        raw = "no real reference\n# leftover note: see STORY-001.md in the diff\n"
        result = git_policy.validate_commit_message(raw, LOCAL_CFG)
        self.assertFalse(result.ok)

    def test_missing_identifier_pattern_fails_closed_under_enforce(self) -> None:
        cfg = {**LOCAL_CFG, "identifier": {"pattern": "", "examples": ["x"]}}
        result = git_policy.validate_commit_message("anything", cfg)
        self.assertFalse(result.ok)
        self.assertTrue(result.blocking)


class LoadProjectConfigTests(unittest.TestCase):
    def test_missing_config_returns_none_none(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, error = git_policy.load_project_config(Path(tmp))
            self.assertIsNone(cfg)
            self.assertIsNone(error)

    def test_valid_config_loads(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agentforge").mkdir()
            import json

            (root / ".agentforge" / "config.json").write_text(
                json.dumps(LOCAL_CFG), encoding="utf-8"
            )
            cfg, error = git_policy.load_project_config(root)
            self.assertIsNone(error)
            self.assertEqual(cfg["traceability"]["mode"], "enforce")

    def test_invalid_config_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agentforge").mkdir()
            (root / ".agentforge" / "config.json").write_text("{not valid json", encoding="utf-8")
            cfg, error = git_policy.load_project_config(root)
            self.assertIsNone(cfg)
            self.assertIsNotNone(error)

    @unittest.skipIf(
        os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
        "chmod-based unreadability is not enforced on Windows or for root",
    )
    def test_unreadable_config_fails_closed_rather_than_raising(self) -> None:
        # Regression test (found in code review): load_project_config only
        # caught ConfigValidationError; an OSError (permission-denied, or
        # a TOCTOU race after the is_file() check) used to propagate
        # uncaught instead of the documented fail-closed (None, error)
        # result.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agentforge").mkdir()
            config_path = root / ".agentforge" / "config.json"
            config_path.write_text('{"schema_version": 1}', encoding="utf-8")
            config_path.chmod(0)
            try:
                cfg, error = git_policy.load_project_config(root)
            finally:
                config_path.chmod(0o644)
            self.assertIsNone(cfg)
            self.assertIsNotNone(error)


class CheckCommitMessageFileTests(unittest.TestCase):
    def test_no_config_skips_the_check(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            msg_path = root / "COMMIT_EDITMSG"
            msg_path.write_text("no reference at all", encoding="utf-8")
            result = git_policy.check_commit_message_file(msg_path, root)
            self.assertTrue(result.ok)
            self.assertFalse(result.blocking)

    def test_invalid_config_fails_closed_regardless_of_message(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agentforge").mkdir()
            (root / ".agentforge" / "config.json").write_text("{not valid json", encoding="utf-8")
            msg_path = root / "COMMIT_EDITMSG"
            msg_path.write_text("STORY-001: fine", encoding="utf-8")
            result = git_policy.check_commit_message_file(msg_path, root)
            self.assertFalse(result.ok)
            self.assertTrue(result.blocking)

    def test_valid_config_and_compliant_message_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            import json

            (root / ".agentforge").mkdir()
            (root / ".agentforge" / "config.json").write_text(
                json.dumps(LOCAL_CFG), encoding="utf-8"
            )
            msg_path = root / "COMMIT_EDITMSG"
            msg_path.write_text("STORY-001: add the thing", encoding="utf-8")
            result = git_policy.check_commit_message_file(msg_path, root)
            self.assertTrue(result.ok)

    def test_valid_config_and_noncompliant_message_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            import json

            (root / ".agentforge").mkdir()
            (root / ".agentforge" / "config.json").write_text(
                json.dumps(LOCAL_CFG), encoding="utf-8"
            )
            msg_path = root / "COMMIT_EDITMSG"
            msg_path.write_text("no reference at all", encoding="utf-8")
            result = git_policy.check_commit_message_file(msg_path, root)
            self.assertFalse(result.ok)


class NoShellTextInferenceTests(unittest.TestCase):
    """STORY-011: never infer compliance from arbitrary shell-command text
    -- only the actual message file. These tests document that the public
    API here has no notion of a shell command at all."""

    def test_module_has_no_bash_command_parsing_surface(self) -> None:
        self.assertFalse(hasattr(git_policy, "check_bash"))
        self.assertFalse(hasattr(git_policy, "classify_bash_command"))


class CommitMessageTests(unittest.TestCase):
    """Aggregate smoke test named exactly as the story's verification
    command (`tests.test_git_policy.CommitMessageTests`) expects, covering
    one representative case per acceptance criterion in a single place in
    addition to the focused classes above."""

    def test_local_provider_valid_and_invalid(self) -> None:
        self.assertTrue(git_policy.validate_commit_message("STORY-001: ok", LOCAL_CFG).ok)
        self.assertFalse(git_policy.validate_commit_message("nope", LOCAL_CFG).ok)

    def test_github_provider_valid_and_invalid(self) -> None:
        self.assertTrue(git_policy.validate_commit_message("fix #1", GITHUB_CFG).ok)
        self.assertFalse(git_policy.validate_commit_message("nope", GITHUB_CFG).ok)

    def test_gitlab_provider_valid_and_invalid(self) -> None:
        self.assertTrue(git_policy.validate_commit_message("fix #1", GITLAB_CFG).ok)
        self.assertFalse(git_policy.validate_commit_message("nope", GITLAB_CFG).ok)

    def test_merge_commit_exempt_across_providers(self) -> None:
        for cfg in (LOCAL_CFG, GITHUB_CFG, GITLAB_CFG):
            with self.subTest(tracker=cfg["tracker"]["type"]):
                result = git_policy.validate_commit_message("Merge branch 'x'", cfg)
                self.assertTrue(result.ok)
                self.assertTrue(result.exempt)


if __name__ == "__main__":
    unittest.main()
