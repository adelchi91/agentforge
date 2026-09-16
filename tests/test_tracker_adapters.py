"""Tests for the STORY-006 GitHub/GitLab tracker adapters
(scripts/work_items.py's _resolve_github/_resolve_gitlab, reached through
work_items.resolve_work_item).

Every external command is mocked — a fake `runner` callable is injected in
place of `subprocess.run`, so these tests require no network access and no
`gh`/`glab` binary on PATH, per STORY-006's acceptance criterion.

Covers:
  - GitHub `#123` and GitLab `#123` resolve only under their configured
    provider, with different canonical identities;
  - structured errors for missing CLI, authentication failure, not found,
    malformed item (bad identifier shape and bad CLI output), and
    unsupported tracker;
  - the repository-identifier vs. work-item-identifier distinction
    ("acme/widgets" is rejected as a work-item identifier);
  - remote failures return an error result without raising and without
    touching the filesystem (so they can never corrupt existing active
    state, per ADR-0002/ADR-0005 — active-state writing itself is
    STORY-008, out of scope here).
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import work_items  # noqa: E402

GITHUB_CONFIG = {
    "tracker": {"type": "github", "repository": "acme/widgets"},
    "context": {"max_bytes": 8000},
}

GITLAB_CONFIG = {
    "tracker": {"type": "gitlab", "repository": "acme/widgets"},
    "context": {"max_bytes": 8000},
}


def _completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def _runner_returning(returncode=0, stdout="", stderr=""):
    def _runner(args, **kwargs):
        return _completed(args, returncode=returncode, stdout=stdout, stderr=stderr)

    return _runner


def _runner_raising(exc: Exception):
    def _runner(args, **kwargs):
        raise exc

    return _runner


class GithubResolutionTests(unittest.TestCase):
    def test_resolves_issue_via_hash_identifier(self) -> None:
        payload = json.dumps(
            {
                "number": 123,
                "title": "Fix the widget",
                "body": "Steps to reproduce...",
                "state": "OPEN",
                "url": "https://github.com/acme/widgets/issues/123",
                "updatedAt": "2026-02-01T00:00:00Z",
            }
        )
        runner = _runner_returning(stdout=payload)
        result = work_items.resolve_work_item("#123", GITHUB_CONFIG, runner=runner)
        self.assertTrue(result.ok, result.error)
        item = result.item
        self.assertEqual(item.provider, "github")
        self.assertEqual(item.canonical_id, "github:acme/widgets#123")
        self.assertEqual(item.title, "Fix the widget")
        self.assertEqual(item.state, "OPEN")

    def test_resolves_issue_via_bare_number(self) -> None:
        payload = json.dumps(
            {
                "number": 7,
                "title": "T",
                "body": "B",
                "state": "OPEN",
                "url": "https://github.com/acme/widgets/issues/7",
                "updatedAt": "2026-02-01T00:00:00Z",
            }
        )
        runner = _runner_returning(stdout=payload)
        result = work_items.resolve_work_item("7", GITHUB_CONFIG, runner=runner)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.item.canonical_id, "github:acme/widgets#7")

    def test_repository_identifier_is_rejected_not_conflated_with_issue(self) -> None:
        runner = _runner_returning(stdout="{}")
        result = work_items.resolve_work_item("acme/widgets", GITHUB_CONFIG, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_MALFORMED_ITEM)

    def test_missing_cli_is_structured_error(self) -> None:
        runner = _runner_raising(FileNotFoundError("gh not found"))
        result = work_items.resolve_work_item("#1", GITHUB_CONFIG, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_MISSING_CLI)

    def test_auth_failure_is_structured_error(self) -> None:
        runner = _runner_returning(
            returncode=4, stderr="gh: To use GitHub CLI in this environment, please run: gh auth login"
        )
        result = work_items.resolve_work_item("#1", GITHUB_CONFIG, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_AUTH_FAILED)

    def test_not_found_is_structured_error(self) -> None:
        runner = _runner_returning(
            returncode=1, stderr="GraphQL: Could not resolve to an issue (issue)"
        )
        result = work_items.resolve_work_item("#404", GITHUB_CONFIG, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_NOT_FOUND)

    def test_malformed_cli_output_is_structured_error(self) -> None:
        runner = _runner_returning(stdout="not json at all")
        result = work_items.resolve_work_item("#1", GITHUB_CONFIG, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_MALFORMED_ITEM)

    def test_missing_repository_config_is_unsupported(self) -> None:
        cfg = {"tracker": {"type": "github"}, "context": {"max_bytes": 8000}}
        runner = _runner_returning(stdout="{}")
        result = work_items.resolve_work_item("#1", cfg, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_UNSUPPORTED_TRACKER)

    def test_remote_failure_never_raises_and_touches_no_files(self) -> None:
        before = sorted(REPO_ROOT.glob("**/*.tmp"))
        runner = _runner_raising(RuntimeError("boom"))
        try:
            result = work_items.resolve_work_item("#1", GITHUB_CONFIG, runner=runner)
        except Exception as exc:  # pragma: no cover - the assertion below is the real check
            self.fail(f"resolve_work_item raised instead of returning a structured error: {exc}")
        self.assertFalse(result.ok)
        self.assertIsNone(result.item)
        after = sorted(REPO_ROOT.glob("**/*.tmp"))
        self.assertEqual(before, after)


class GitlabResolutionTests(unittest.TestCase):
    def test_resolves_issue_and_maps_gitlab_fields(self) -> None:
        payload = json.dumps(
            {
                "iid": 123,
                "title": "Fix the widget",
                "description": "Steps to reproduce...",
                "state": "opened",
                "web_url": "https://gitlab.com/acme/widgets/-/issues/123",
                "updated_at": "2026-02-01T00:00:00Z",
            }
        )
        runner = _runner_returning(stdout=payload)
        result = work_items.resolve_work_item("#123", GITLAB_CONFIG, runner=runner)
        self.assertTrue(result.ok, result.error)
        item = result.item
        self.assertEqual(item.provider, "gitlab")
        self.assertEqual(item.canonical_id, "gitlab:acme/widgets#123")
        self.assertEqual(item.body, "Steps to reproduce...")

    def test_same_hash_identifier_resolves_only_under_configured_provider(self) -> None:
        github_payload = json.dumps(
            {
                "number": 123,
                "title": "GH issue",
                "body": "gh body",
                "state": "OPEN",
                "url": "https://github.com/acme/widgets/issues/123",
                "updatedAt": "2026-02-01T00:00:00Z",
            }
        )
        gitlab_payload = json.dumps(
            {
                "iid": 123,
                "title": "GL issue",
                "description": "gl body",
                "state": "opened",
                "web_url": "https://gitlab.com/acme/widgets/-/issues/123",
                "updated_at": "2026-02-01T00:00:00Z",
            }
        )
        gh_result = work_items.resolve_work_item(
            "#123", GITHUB_CONFIG, runner=_runner_returning(stdout=github_payload)
        )
        gl_result = work_items.resolve_work_item(
            "#123", GITLAB_CONFIG, runner=_runner_returning(stdout=gitlab_payload)
        )
        self.assertTrue(gh_result.ok and gl_result.ok)
        self.assertNotEqual(gh_result.item.canonical_id, gl_result.item.canonical_id)
        self.assertEqual(gh_result.item.canonical_id, "github:acme/widgets#123")
        self.assertEqual(gl_result.item.canonical_id, "gitlab:acme/widgets#123")

    def test_auth_failure_is_structured_error(self) -> None:
        runner = _runner_returning(returncode=1, stderr="401 Unauthorized. code: 401")
        result = work_items.resolve_work_item("#1", GITLAB_CONFIG, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_AUTH_FAILED)

    def test_not_found_is_structured_error(self) -> None:
        runner = _runner_returning(returncode=1, stderr="404 Not Found")
        result = work_items.resolve_work_item("#1", GITLAB_CONFIG, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_NOT_FOUND)

    def test_missing_cli_is_structured_error(self) -> None:
        runner = _runner_raising(FileNotFoundError("glab not found"))
        result = work_items.resolve_work_item("#1", GITLAB_CONFIG, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.kind, work_items.ERROR_MISSING_CLI)


if __name__ == "__main__":
    unittest.main()
