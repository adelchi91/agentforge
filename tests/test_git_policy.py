"""Tests for the STORY-011 commit-message traceability policy and the
STORY-012 pre-push/range validation built on top of it
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

`RangeValidationTests`, `PrePushTests`, and `CheckRangeCommandTests` below
cover STORY-012: every outgoing commit (not just each ref's HEAD) is
validated before a push, across new branches, updated branches, deleted
refs, force pushes/non-ancestor tips, multiple refs in one push, missing
remote bases, and duplicate commits shared by more than one pushed ref.
These necessarily exercise real temporary Git repositories (real commit
graphs, real `git rev-list` range computation) rather than pure-Python
fixtures, but never run `git push`, `git fetch`, or `git clone` against
any real or simulated remote -- every stdin record a real `pre-push` hook
would receive is instead hand-constructed from real local SHAs
(`git rev-parse`) and fed directly to `git_policy.run_pre_push_check`/the
installed hook script, matching this story's "no network access, no real
remote pushes" requirement while still exercising real Git range
computation end to end.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config as agentforge_config  # noqa: E402
from scripts import git_policy  # noqa: E402

_GIT_AVAILABLE = shutil.which("git") is not None
_ZERO_SHA = "0" * 40


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    _git(root, "config", "commit.gpgsign", "false")


def _write_config(root: Path, cfg: dict) -> None:
    agentforge_dir = root / ".agentforge"
    agentforge_dir.mkdir(parents=True, exist_ok=True)
    (agentforge_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


def _commit(root: Path, message: str) -> str:
    """Create an --allow-empty commit with `message` (bypassing any hook
    entirely, since these tests exercise git_policy's own functions
    directly rather than the installed hook) and return its full SHA."""
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "--allow-empty", "--no-verify", "-m", message],
        capture_output=True,
        text=True,
        check=True,
    )
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _sha(root: Path, ref: str) -> str:
    return _git(root, "rev-parse", ref).stdout.strip()

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


# ---------------------------------------------------------------------------
# STORY-012: pre-push / range validation.
# ---------------------------------------------------------------------------


class ParsePrePushStdinTests(unittest.TestCase):
    """Pure parsing logic -- no real repository needed."""

    def test_updated_branch_line_parses(self) -> None:
        sha_a = "a" * 40
        sha_b = "b" * 40
        result = git_policy.parse_pre_push_stdin(f"refs/heads/main {sha_b} refs/heads/main {sha_a}\n")
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.updates), 1)
        update = result.updates[0]
        self.assertEqual(update.local_sha, sha_b)
        self.assertEqual(update.remote_sha, sha_a)
        self.assertFalse(update.is_deletion)
        self.assertFalse(update.is_new_ref)

    def test_new_branch_line_has_zero_remote_sha(self) -> None:
        sha = "c" * 40
        result = git_policy.parse_pre_push_stdin(
            f"refs/heads/feature {sha} refs/heads/feature {_ZERO_SHA}\n"
        )
        update = result.updates[0]
        self.assertTrue(update.is_new_ref)
        self.assertFalse(update.is_deletion)

    def test_deletion_line_has_zero_local_sha(self) -> None:
        sha = "d" * 40
        result = git_policy.parse_pre_push_stdin(
            f"(delete) {_ZERO_SHA} refs/heads/old {sha}\n"
        )
        update = result.updates[0]
        self.assertTrue(update.is_deletion)
        self.assertFalse(update.is_new_ref)

    def test_multiple_lines_parse_into_multiple_updates(self) -> None:
        sha_a, sha_b, sha_c, sha_d = ("1" * 40, "2" * 40, "3" * 40, "4" * 40)
        text = (
            f"refs/heads/main {sha_b} refs/heads/main {sha_a}\n"
            f"refs/heads/feature {sha_d} refs/heads/feature {sha_c}\n"
        )
        result = git_policy.parse_pre_push_stdin(text)
        self.assertEqual(len(result.updates), 2)
        self.assertEqual(result.updates[0].local_ref, "refs/heads/main")
        self.assertEqual(result.updates[1].local_ref, "refs/heads/feature")

    def test_blank_lines_are_ignored(self) -> None:
        sha_a, sha_b = "1" * 40, "2" * 40
        text = f"\nrefs/heads/main {sha_b} refs/heads/main {sha_a}\n\n"
        result = git_policy.parse_pre_push_stdin(text)
        self.assertEqual(len(result.updates), 1)
        self.assertEqual(result.errors, [])

    def test_malformed_line_wrong_field_count_reports_error_and_is_skipped(self) -> None:
        sha_a, sha_b = "1" * 40, "2" * 40
        text = (
            "not-a-valid-line-at-all\n"
            f"refs/heads/main {sha_b} refs/heads/main {sha_a}\n"
        )
        result = git_policy.parse_pre_push_stdin(text)
        self.assertEqual(len(result.updates), 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("expected 4", result.errors[0])

    def test_malformed_line_non_hex_sha_reports_error(self) -> None:
        text = "refs/heads/main not-a-sha refs/heads/main also-not-a-sha\n"
        result = git_policy.parse_pre_push_stdin(text)
        self.assertEqual(result.updates, [])
        self.assertEqual(len(result.errors), 1)
        self.assertIn("does not look like a hex object id", result.errors[0])

    def test_completely_malformed_input_yields_no_updates_and_all_errors(self) -> None:
        text = "garbage\nmore garbage here\n"
        result = git_policy.parse_pre_push_stdin(text)
        self.assertEqual(result.updates, [])
        self.assertEqual(len(result.errors), 2)

    def test_zero_sha_is_only_all_zero_hex(self) -> None:
        self.assertTrue(git_policy._is_zero_sha(_ZERO_SHA))
        self.assertFalse(git_policy._is_zero_sha("a" * 40))
        self.assertFalse(git_policy._is_zero_sha("0" * 39 + "1"))
        self.assertFalse(git_policy._is_zero_sha(""))


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class RangeValidationTests(unittest.TestCase):
    """Range computation against real temporary Git repositories -- no
    network access, and `git push`/`git fetch`/`git clone` are never
    invoked (every ref update is hand-constructed from real local SHAs)."""

    def test_updated_branch_range_excludes_the_old_tip(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            old_tip = _commit(root, "STORY-001: base")
            new_tip = _commit(root, "STORY-002: more")
            update = git_policy.RefUpdate("refs/heads/main", new_tip, "refs/heads/main", old_tip)
            outcome = git_policy.compute_outgoing_range(root, update)
            self.assertIsNone(outcome.error)
            self.assertEqual(outcome.shas, [new_tip])

    def test_new_branch_range_includes_every_ancestor(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            first = _commit(root, "STORY-001: init")
            second = _commit(root, "STORY-002: more")
            update = git_policy.RefUpdate("refs/heads/feature", second, "refs/heads/feature", _ZERO_SHA)
            outcome = git_policy.compute_outgoing_range(root, update)
            self.assertIsNone(outcome.error)
            self.assertEqual(set(outcome.shas), {first, second})

    def test_deletion_range_is_empty_and_never_shells_out(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Deliberately never `git init` here: a deletion must be
            # resolved without ever invoking `git rev-list` at all.
            sha = "a" * 40
            update = git_policy.RefUpdate("(delete)", _ZERO_SHA, "refs/heads/gone", sha)
            outcome = git_policy.compute_outgoing_range(root, update)
            self.assertIsNone(outcome.error)
            self.assertEqual(outcome.shas, [])

    def test_force_push_non_ancestor_tip_is_still_computed_correctly(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            base = _commit(root, "STORY-001: base")
            _git(root, "branch", "old-tip")
            remote_tip = _commit(root, "STORY-002: old history")
            _git(root, "reset", "--hard", base)
            new_tip = _commit(root, "STORY-003: rewritten history")
            # `new_tip` is not a descendant of `remote_tip` -- a genuine
            # force-push shape.
            update = git_policy.RefUpdate("refs/heads/main", new_tip, "refs/heads/main", remote_tip)
            outcome = git_policy.compute_outgoing_range(root, update)
            self.assertIsNone(outcome.error)
            self.assertEqual(outcome.shas, [new_tip])

    def test_missing_remote_base_falls_back_to_all_ancestors_with_a_warning(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            first = _commit(root, "STORY-001: init")
            second = _commit(root, "STORY-002: more")
            unknown_remote_sha = "f" * 40
            update = git_policy.RefUpdate(
                "refs/heads/main", second, "refs/heads/main", unknown_remote_sha
            )
            outcome = git_policy.compute_outgoing_range(root, update)
            self.assertIsNone(outcome.error)
            self.assertIsNotNone(outcome.warning)
            self.assertEqual(set(outcome.shas), {first, second})

    def test_completely_unresolvable_range_is_a_hard_error(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _commit(root, "STORY-001: init")
            bogus_local = "e" * 40
            bogus_remote = "f" * 40
            update = git_policy.RefUpdate("refs/heads/main", bogus_local, "refs/heads/main", bogus_remote)
            outcome = git_policy.compute_outgoing_range(root, update)
            self.assertIsNotNone(outcome.error)
            self.assertEqual(outcome.shas, [])

    def test_collect_outgoing_commits_dedupes_a_commit_shared_by_two_refs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            shared = _commit(root, "STORY-001: shared ancestor")
            _git(root, "branch", "branch-a")
            _git(root, "branch", "branch-b")
            _git(root, "checkout", "-q", "branch-a")
            tip_a = _commit(root, "STORY-002: branch a")
            _git(root, "checkout", "-q", "branch-b")
            tip_b = _commit(root, "STORY-003: branch b")

            updates = [
                git_policy.RefUpdate("refs/heads/branch-a", tip_a, "refs/heads/branch-a", _ZERO_SHA),
                git_policy.RefUpdate("refs/heads/branch-b", tip_b, "refs/heads/branch-b", _ZERO_SHA),
            ]
            shas, warnings, errors = git_policy.collect_outgoing_commits(root, updates)
            self.assertEqual(errors, [])
            self.assertEqual(set(shas), {shared, tip_a, tip_b})
            self.assertEqual(len(shas), 3)
            self.assertEqual(shas.count(shared), 1)

    def test_collect_outgoing_commits_reports_per_ref_range_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _commit(root, "STORY-001: init")
            bogus_local = "e" * 40
            bogus_remote = "f" * 40
            updates = [
                git_policy.RefUpdate("refs/heads/main", bogus_local, "refs/heads/main", bogus_remote)
            ]
            shas, warnings, errors = git_policy.collect_outgoing_commits(root, updates)
            self.assertEqual(shas, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("refs/heads/main", errors[0])


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class PrePushTests(unittest.TestCase):
    """End-to-end orchestration tests for `git_policy.run_pre_push_check`
    -- the function the installed `pre-push` hook calls. Every scenario
    hand-builds the exact stdin a real `pre-push` invocation would supply
    from real local SHAs; `git push` itself is never invoked."""

    def _stdin(self, *lines: str) -> str:
        return "\n".join(lines) + "\n"

    def test_updated_branch_all_compliant_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            old_tip = _commit(root, "STORY-001: base")
            new_tip = _commit(root, "STORY-002: more")
            stdin_text = self._stdin(f"refs/heads/main {new_tip} refs/heads/main {old_tip}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_OK)

    def test_updated_branch_with_noncompliant_commit_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            old_tip = _commit(root, "STORY-001: base")
            new_tip = _commit(root, "no reference at all")
            stdin_text = self._stdin(f"refs/heads/main {new_tip} refs/heads/main {old_tip}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)
            joined = "\n".join(result.messages)
            self.assertIn(new_tip[:12], joined)
            self.assertIn("no reference at all", joined)

    def test_new_branch_all_compliant_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            _commit(root, "STORY-001: init")
            tip = _commit(root, "STORY-002: more")
            stdin_text = self._stdin(f"refs/heads/feature {tip} refs/heads/feature {_ZERO_SHA}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_OK)

    def test_new_branch_with_noncompliant_commit_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            _commit(root, "STORY-001: init")
            tip = _commit(root, "no reference here either")
            stdin_text = self._stdin(f"refs/heads/feature {tip} refs/heads/feature {_ZERO_SHA}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)

    def test_multiple_refs_one_offending_commit_fails_overall(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            base = _commit(root, "STORY-001: base")
            _git(root, "branch", "good-branch")
            _git(root, "branch", "bad-branch")
            _git(root, "checkout", "-q", "good-branch")
            good_tip = _commit(root, "STORY-002: good")
            _git(root, "checkout", "-q", "bad-branch")
            bad_tip = _commit(root, "no reference at all")

            stdin_text = self._stdin(
                f"refs/heads/good-branch {good_tip} refs/heads/good-branch {base}",
                f"refs/heads/bad-branch {bad_tip} refs/heads/bad-branch {base}",
            )
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)
            joined = "\n".join(result.messages)
            self.assertIn(bad_tip[:12], joined)
            self.assertNotIn(good_tip[:12], joined)

    def test_force_push_still_validates_the_new_commits(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            base = _commit(root, "STORY-001: base")
            _git(root, "branch", "old-tip")
            remote_tip = _commit(root, "STORY-002: old history")
            _git(root, "reset", "--hard", base)
            new_tip = _commit(root, "no reference in the rewritten history")

            stdin_text = self._stdin(f"refs/heads/main {new_tip} refs/heads/main {remote_tip}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)

    def test_deletion_is_always_allowed_even_under_enforce(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            some_sha = _commit(root, "STORY-001: whatever was on the remote")
            stdin_text = self._stdin(f"(delete) {_ZERO_SHA} refs/heads/old {some_sha}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_OK)

    def test_merge_commit_in_range_is_exempt(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            base = _commit(root, "STORY-001: base")
            base_branch = _git(root, "branch", "--show-current").stdout.strip()
            _git(root, "branch", "feature")
            _git(root, "checkout", "-q", "feature")
            _commit(root, "STORY-002: feature work")
            _git(root, "checkout", "-q", base_branch)
            merge = subprocess.run(
                ["git", "-C", str(root), "merge", "--no-ff", "feature"],
                capture_output=True, text=True,
            )
            self.assertEqual(merge.returncode, 0, merge.stderr)
            merge_tip = _sha(root, "HEAD")

            stdin_text = self._stdin(f"refs/heads/{base_branch} {merge_tip} refs/heads/{base_branch} {base}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_OK)

    def test_empty_range_is_allowed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            tip = _commit(root, "STORY-001: unchanged")
            stdin_text = self._stdin(f"refs/heads/main {tip} refs/heads/main {tip}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_OK)
            self.assertIn("no outgoing commits", "\n".join(result.messages))

    def test_missing_remote_base_still_catches_a_noncompliant_ancestor(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            _commit(root, "no reference at all")
            tip = _commit(root, "STORY-001: fine on its own")
            unknown_remote_sha = "f" * 40
            stdin_text = self._stdin(f"refs/heads/main {tip} refs/heads/main {unknown_remote_sha}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)
            joined = "\n".join(result.messages)
            self.assertIn("not known to this repository", joined)

    def test_duplicate_commit_across_refs_is_reported_once(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            shared_bad = _commit(root, "no reference, shared by two branches")
            _git(root, "branch", "branch-a")
            _git(root, "branch", "branch-b")
            _git(root, "checkout", "-q", "branch-a")
            tip_a = _commit(root, "STORY-001: branch a")
            _git(root, "checkout", "-q", "branch-b")
            tip_b = _commit(root, "STORY-002: branch b")

            stdin_text = self._stdin(
                f"refs/heads/branch-a {tip_a} refs/heads/branch-a {_ZERO_SHA}",
                f"refs/heads/branch-b {tip_b} refs/heads/branch-b {_ZERO_SHA}",
            )
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)
            joined = "\n".join(result.messages)
            self.assertEqual(joined.count(shared_bad[:12]), 1)
            self.assertIn("1 of 3 outgoing commit(s)", joined)

    def test_compliant_head_does_not_mask_an_older_noncompliant_commit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            remote_tip = _commit(root, "STORY-001: already on the remote")
            bad = _commit(root, "no reference, buried in the middle")
            head = _commit(root, "STORY-002: compliant HEAD")

            stdin_text = self._stdin(f"refs/heads/main {head} refs/heads/main {remote_tip}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)
            joined = "\n".join(result.messages)
            self.assertIn(bad[:12], joined)
            self.assertNotIn(head[:12], joined)

    def test_malformed_input_line_is_reported_but_valid_lines_still_processed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            old_tip = _commit(root, "STORY-001: base")
            new_tip = _commit(root, "no reference at all")
            stdin_text = (
                "this line is garbage\n"
                f"refs/heads/main {new_tip} refs/heads/main {old_tip}\n"
            )
            result = git_policy.run_pre_push_check(stdin_text, root)
            joined = "\n".join(result.messages)
            self.assertIn("malformed input ignored", joined)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)
            self.assertIn(new_tip[:12], joined)

    def test_zero_sha_handling_deletion_and_new_branch_in_one_push(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            deleted_remote_sha = _commit(root, "STORY-001: on the remote, being deleted")
            _git(root, "branch", "new-feature")
            _git(root, "checkout", "-q", "new-feature")
            new_tip = _commit(root, "no reference at all")

            stdin_text = self._stdin(
                f"(delete) {_ZERO_SHA} refs/heads/old {deleted_remote_sha}",
                f"refs/heads/new-feature {new_tip} refs/heads/new-feature {_ZERO_SHA}",
            )
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)
            joined = "\n".join(result.messages)
            self.assertIn(new_tip[:12], joined)

    def test_subject_sanitization_strips_control_characters_and_truncates(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            old_tip = _commit(root, "STORY-001: base")
            dirty_subject = "no reference \x1b[31mred\x1b[0m \x01\x02 " + ("x" * 250)
            new_tip = _commit(root, dirty_subject)
            stdin_text = self._stdin(f"refs/heads/main {new_tip} refs/heads/main {old_tip}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)
            joined = "\n".join(result.messages)
            self.assertNotIn("\x1b", joined)
            self.assertNotIn("\x01", joined)
            self.assertIn("…", joined)

    def test_no_agentforge_config_skips_the_check(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            old_tip = _commit(root, "STORY-001: base")
            new_tip = _commit(root, "no reference at all, but no config exists")
            stdin_text = self._stdin(f"refs/heads/main {new_tip} refs/heads/main {old_tip}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_OK)

    def test_traceability_off_skips_the_check(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, {**LOCAL_CFG, "traceability": {"mode": "off"}})
            old_tip = _commit(root, "STORY-001: base")
            new_tip = _commit(root, "no reference at all")
            stdin_text = self._stdin(f"refs/heads/main {new_tip} refs/heads/main {old_tip}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_OK)

    def test_observe_mode_reports_but_never_blocks(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, {**LOCAL_CFG, "traceability": {"mode": "observe"}})
            old_tip = _commit(root, "STORY-001: base")
            new_tip = _commit(root, "no reference at all")
            stdin_text = self._stdin(f"refs/heads/main {new_tip} refs/heads/main {old_tip}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_OK)
            self.assertIn(new_tip[:12], "\n".join(result.messages))

    def test_invalid_agentforge_config_returns_config_error_exit_code(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / ".agentforge").mkdir()
            (root / ".agentforge" / "config.json").write_text("{not valid json", encoding="utf-8")
            tip = _commit(root, "STORY-001: whatever")
            stdin_text = self._stdin(f"refs/heads/main {tip} refs/heads/main {_ZERO_SHA}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_CONFIG_ERROR)

    def test_completely_unresolvable_range_returns_git_range_error_exit_code(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            _commit(root, "STORY-001: init")
            bogus_local = "e" * 40
            bogus_remote = "f" * 40
            stdin_text = self._stdin(f"refs/heads/main {bogus_local} refs/heads/main {bogus_remote}")
            result = git_policy.run_pre_push_check(stdin_text, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_GIT_RANGE_ERROR)


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class CheckRangeCommandTests(unittest.TestCase):
    """The CI-facing `check-range` command (STORY-012 acceptance
    criterion: "Add a CI command that validates a supplied base/head
    range")."""

    def test_check_range_passes_for_compliant_commits(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            base = _commit(root, "STORY-001: base")
            head = _commit(root, "STORY-002: head")
            result = git_policy.run_range_check(base, head, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_OK)

    def test_check_range_fails_for_noncompliant_commit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            base = _commit(root, "STORY-001: base")
            head = _commit(root, "no reference at all")
            result = git_policy.run_range_check(base, head, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)
            self.assertIn(head[:12], "\n".join(result.messages))

    def test_check_range_unresolvable_base_returns_git_range_error(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            head = _commit(root, "STORY-001: head")
            result = git_policy.run_range_check("f" * 40, head, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_GIT_RANGE_ERROR)

    def test_check_range_rejects_a_base_or_head_that_looks_like_a_git_option(self) -> None:
        # Hardening: a `base`/`head` value starting with '-' could be
        # misread as a `git rev-list` flag once concatenated into
        # "base..head"; no legitimate ref or object id starts with '-',
        # so this is rejected before ever reaching the underlying git
        # subprocess call.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            head = _commit(root, "STORY-001: head")
            result = git_policy.run_range_check("--upload-pack=evil", head, root)
            self.assertEqual(result.exit_code, git_policy.PUSH_EXIT_GIT_RANGE_ERROR)
            self.assertIn("never a valid Git ref", "\n".join(result.messages))

    def test_check_range_cli_subprocess_exit_codes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            base = _commit(root, "STORY-001: base")
            good_head = _commit(root, "STORY-002: good")
            good = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "git_policy.py"), "check-range",
                 base, good_head, "--project-root", str(root)],
                capture_output=True, text=True,
            )
            self.assertEqual(good.returncode, 0, good.stderr)

            bad_head = _commit(root, "no reference at all")
            bad = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "git_policy.py"), "check-range",
                 base, bad_head, "--project-root", str(root)],
                capture_output=True, text=True,
            )
            self.assertEqual(bad.returncode, 1, bad.stderr)

    def test_check_range_cli_subprocess_config_error_exit_code(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / ".agentforge").mkdir()
            (root / ".agentforge" / "config.json").write_text("{not valid json", encoding="utf-8")
            head = _commit(root, "STORY-001: whatever")
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "git_policy.py"), "check-range",
                 head, head, "--project-root", str(root)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, git_policy.PUSH_EXIT_CONFIG_ERROR)

    def test_check_range_cli_subprocess_git_range_error_exit_code(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            head = _commit(root, "STORY-001: head")
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "git_policy.py"), "check-range",
                 "f" * 40, head, "--project-root", str(root)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, git_policy.PUSH_EXIT_GIT_RANGE_ERROR)


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class CheckPrePushCliExitCodeTests(unittest.TestCase):
    """CLI-level (real subprocess, real stdin pipe) coverage of all four
    `check-pre-push` exit codes -- complementing `PrePushTests`, which
    exercises `run_pre_push_check` directly as a Python function."""

    def _run_cli(self, root: Path, stdin_text: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "git_policy.py"), "check-pre-push",
             "origin", "file:///nonexistent", "--project-root", str(root)],
            input=stdin_text,
            capture_output=True,
            text=True,
        )

    def test_ok_and_traceability_failure_exit_codes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            old_tip = _commit(root, "STORY-001: base")
            good_tip = _commit(root, "STORY-002: fine")
            good = self._run_cli(root, f"refs/heads/main {good_tip} refs/heads/main {old_tip}\n")
            self.assertEqual(good.returncode, git_policy.PUSH_EXIT_OK, good.stderr)

            bad_tip = _commit(root, "no reference at all")
            bad = self._run_cli(root, f"refs/heads/main {bad_tip} refs/heads/main {good_tip}\n")
            self.assertEqual(bad.returncode, git_policy.PUSH_EXIT_TRACEABILITY_FAILURE)

    def test_config_error_exit_code(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / ".agentforge").mkdir()
            (root / ".agentforge" / "config.json").write_text("{not valid json", encoding="utf-8")
            tip = _commit(root, "STORY-001: whatever")
            result = self._run_cli(root, f"refs/heads/main {tip} refs/heads/main {_ZERO_SHA}\n")
            self.assertEqual(result.returncode, git_policy.PUSH_EXIT_CONFIG_ERROR)

    def test_git_range_error_exit_code(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_CFG)
            _commit(root, "STORY-001: init")
            bogus_local = "e" * 40
            bogus_remote = "f" * 40
            result = self._run_cli(root, f"refs/heads/main {bogus_local} refs/heads/main {bogus_remote}\n")
            self.assertEqual(result.returncode, git_policy.PUSH_EXIT_GIT_RANGE_ERROR)


if __name__ == "__main__":
    unittest.main()
