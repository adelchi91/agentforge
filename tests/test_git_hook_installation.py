"""Real-Git-repository tests for the STORY-011 commit-msg hook installer
and the installed hook itself (scripts/git_policy.py,
templates/git-hooks/commit-msg).

Unlike tests/test_git_policy.py (pure-Python validation logic only), every
test here `git init`s (or `git worktree add`s) a real temporary
repository, installs the hook for real, and runs real `git commit` /
`git merge` / `git -C` invocations end-to-end, asserting on Git's own exit
code -- this is what actually proves "GUI/direct-terminal commit
scenarios ... are covered by Git-level enforcement" (the acceptance
criterion this suite exists for), rather than only unit-testing the
Python function in isolation.

Every test is skipped if `git` is not on PATH (matching the existing
convention in tests/test_setup_idempotence.py).
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import git_policy  # noqa: E402

SCRIPTS_DIR = REPO_ROOT / "scripts"

LOCAL_ENFORCE_CFG = {
    "schema_version": 1,
    "tracker": {"type": "local", "local_root": "docs/work-items"},
    "identifier": {"pattern": "^STORY-\\d{3,}$", "examples": ["STORY-001", "STORY-042"]},
    "context": {"max_bytes": 8000},
    "traceability": {"mode": "enforce"},
    "scope": {"mode": "off", "agents": {}},
    "migration_policy": {"enabled": False},
    "quality": {"post_edit": "off"},
}

_GIT_AVAILABLE = shutil.which("git") is not None


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


def _commit(root: Path, message: str, *, allow_empty: bool = True) -> subprocess.CompletedProcess:
    args = ["commit", "-q", "-m", message]
    if allow_empty:
        args.insert(1, "--allow-empty")
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )


def _commit_sha(root: Path, message: str) -> str:
    """Like `_commit`, but for STORY-012's pre-push tests, which need the
    resulting commit's SHA (to build pre-push stdin lines) rather than the
    raw `CompletedProcess` -- and always succeeds unconditionally (no
    commit-msg hook is installed in any of those tests, only pre-push), so
    asserting on the result here would be redundant."""
    result = subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", message],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return _git(root, "rev-parse", "HEAD").stdout.strip()


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class ChainedInstallTests(unittest.TestCase):
    def test_plan_reports_chained_with_no_existing_hook(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            plan = git_policy.plan_hook_install(root)
            self.assertEqual(plan.status, git_policy.INSTALL_CHAINED)
            self.assertIsNone(plan.existing_hook_path)

    def test_apply_writes_an_executable_managed_hook(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            plan = git_policy.apply_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_CHAINED)
            hook_path = root / ".git" / "hooks" / "commit-msg"
            self.assertTrue(hook_path.is_file())
            self.assertTrue(hook_path.stat().st_mode & stat.S_IXUSR)
            text = hook_path.read_text(encoding="utf-8")
            self.assertIn(str(SCRIPTS_DIR), text)
            self.assertIn("Managed by AgentForge", text)

    def test_commit_with_valid_reference_succeeds(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            result = _commit(root, "STORY-001: add the thing")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_commit_without_reference_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            result = _commit(root, "no reference at all")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("identifier.pattern", result.stderr)

    def test_commit_is_allowed_when_traceability_is_off(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, {**LOCAL_ENFORCE_CFG, "traceability": {"mode": "off"}})
            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            result = _commit(root, "no reference at all")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_commit_is_allowed_when_no_agentforge_config_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            result = _commit(root, "no reference and no config at all")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_git_dash_c_invocation_is_covered(self) -> None:
        # v1's bug (GitDashCPushBypassTests) was a regex missing `git -C
        # <dir> push`. A real Git hook has no such gap: Git invokes it
        # regardless of how the command was spelled.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            result = subprocess.run(
                ["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "no reference"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_alias_invocation_is_covered(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            _git(root, "config", "alias.ci", "commit -q --allow-empty")
            result = _git(root, "ci", "-m", "no reference", check=False)
            self.assertNotEqual(result.returncode, 0)

    def test_gui_style_commit_via_message_file_is_covered(self) -> None:
        # Simulates a GUI client / `git commit -F <file>` flow: the
        # message is written to a file first, rather than passed as -m.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            msg_file = root / "gui-message.txt"
            msg_file.write_text("no reference at all", encoding="utf-8")
            result = _git(root, "commit", "-q", "--allow-empty", "-F", str(msg_file), check=False)
            self.assertNotEqual(result.returncode, 0)

    def test_reinstall_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            first = (root / ".git" / "hooks" / "commit-msg").read_text(encoding="utf-8")
            plan2 = git_policy.apply_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan2.status, git_policy.INSTALL_CHAINED)
            second = (root / ".git" / "hooks" / "commit-msg").read_text(encoding="utf-8")
            self.assertEqual(first, second)
            self.assertFalse((root / ".git" / "hooks" / git_policy.CHAINED_HOOK_BACKUP_NAME).exists())


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class ExistingHookChainingTests(unittest.TestCase):
    def _write_marker_hook(self, root: Path, marker: Path, exit_code: int = 0) -> None:
        hooks_dir = root / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook = hooks_dir / "commit-msg"
        hook.write_text(
            "#!/bin/sh\n"
            f"echo ran >> {marker}\n"
            f"exit {exit_code}\n",
            encoding="utf-8",
        )
        hook.chmod(hook.stat().st_mode | 0o111)

    def test_preexisting_hook_is_detected_and_never_silently_overwritten(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            self._write_marker_hook(root, root / "marker.txt")
            plan = git_policy.plan_hook_install(root)
            self.assertEqual(plan.status, git_policy.INSTALL_CHAINED)
            self.assertIsNotNone(plan.existing_hook_path)
            self.assertFalse(plan.existing_hook_is_ours)

    def test_preexisting_hook_is_preserved_and_chain_called(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            marker = root / "marker.txt"
            self._write_marker_hook(root, marker)
            _write_config(root, LOCAL_ENFORCE_CFG)

            git_policy.apply_hook_install(root, SCRIPTS_DIR)

            backup = root / ".git" / "hooks" / git_policy.CHAINED_HOOK_BACKUP_NAME
            self.assertTrue(backup.is_file())

            result = _commit(root, "STORY-001: valid reference")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(marker.exists())
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), "ran")

    def test_preexisting_hook_failure_blocks_the_commit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            self._write_marker_hook(root, root / "marker.txt", exit_code=1)
            _write_config(root, LOCAL_ENFORCE_CFG)

            git_policy.apply_hook_install(root, SCRIPTS_DIR)

            # Even a fully compliant AgentForge-valid message must still be
            # rejected because the chained, pre-existing hook itself fails
            # -- AgentForge must never silently override another hook's
            # veto.
            result = _commit(root, "STORY-001: valid reference")
            self.assertNotEqual(result.returncode, 0)

    def test_non_executable_preexisting_hook_is_not_reactivated(self) -> None:
        # Regression test (found in code review): Git silently ignores a
        # non-executable commit-msg hook (it prints a warning and the
        # commit proceeds normally). Installing AgentForge's hook must not
        # turn a previously-inert script back on by force-chmodding the
        # backup executable -- that would reject an otherwise-compliant
        # commit purely because AgentForge reactivated dormant behavior.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            hooks_dir = root / ".git" / "hooks"
            hooks_dir.mkdir(parents=True, exist_ok=True)
            dormant = hooks_dir / "commit-msg"
            dormant.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            dormant.chmod(dormant.stat().st_mode & ~0o111)  # explicitly non-executable
            _write_config(root, LOCAL_ENFORCE_CFG)

            # Sanity check: before AgentForge is installed, Git already
            # ignores this dormant hook -- a compliant commit succeeds.
            baseline = _commit(root, "STORY-001: before install")
            self.assertEqual(baseline.returncode, 0, baseline.stderr)

            git_policy.apply_hook_install(root, SCRIPTS_DIR)

            backup = hooks_dir / git_policy.CHAINED_HOOK_BACKUP_NAME
            self.assertTrue(backup.is_file())
            self.assertFalse(
                backup.stat().st_mode & 0o111,
                "backup of a previously non-executable hook must not be made executable",
            )

            result = _commit(root, "STORY-002: after install, still compliant")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_reinstall_does_not_stack_backups(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            self._write_marker_hook(root, root / "marker.txt")

            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            backup_mtime = (root / ".git" / "hooks" / git_policy.CHAINED_HOOK_BACKUP_NAME).read_text(
                encoding="utf-8"
            )
            git_policy.apply_hook_install(root, SCRIPTS_DIR)
            backup_mtime_2 = (root / ".git" / "hooks" / git_policy.CHAINED_HOOK_BACKUP_NAME).read_text(
                encoding="utf-8"
            )
            self.assertEqual(backup_mtime, backup_mtime_2)
            # The installed hook itself (not the backup) must be the one
            # recognized as AgentForge-managed on the second pass.
            plan = git_policy.plan_hook_install(root)
            self.assertTrue(plan.existing_hook_is_ours)


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class HookManagerDetectionTests(unittest.TestCase):
    def test_husky_present_yields_manual_plan_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / ".husky").mkdir()

            plan = git_policy.apply_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_MANUAL)
            self.assertIn("Husky", plan.reason)
            self.assertFalse((root / ".git" / "hooks" / "commit-msg").exists())

    def test_pre_commit_config_present_yields_manual_plan_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

            plan = git_policy.apply_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_MANUAL)
            self.assertIn("pre-commit", plan.reason)
            self.assertFalse((root / ".git" / "hooks" / "commit-msg").exists())

    def test_custom_core_hooks_path_is_respected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _git(root, "config", "core.hooksPath", ".githooks")

            plan = git_policy.apply_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_CHAINED)
            self.assertTrue((root / ".githooks" / "commit-msg").is_file())
            self.assertFalse((root / ".git" / "hooks" / "commit-msg").exists())

    def test_custom_core_hooks_path_end_to_end_commit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _git(root, "config", "core.hooksPath", ".githooks")
            _write_config(root, LOCAL_ENFORCE_CFG)

            git_policy.apply_hook_install(root, SCRIPTS_DIR)

            result = _commit(root, "no reference at all")
            self.assertNotEqual(result.returncode, 0)
            result_ok = _commit(root, "STORY-001: fine")
            self.assertEqual(result_ok.returncode, 0, result_ok.stderr)


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class WorktreeTests(unittest.TestCase):
    """STORY-011 is itself being implemented inside a Git worktree, where
    `.git` is a file (not a directory) pointing at the real gitdir -- this
    class tests that layout explicitly, as the task requires."""

    def _make_worktree(self, tmp: Path):
        main = tmp / "main"
        _init_repo(main)
        _write_config(main, LOCAL_ENFORCE_CFG)
        # Stage and commit the config so it is actually present in the
        # committed tree -- otherwise `git worktree add` (which only
        # populates a new worktree from committed content) would leave
        # the second worktree with no .agentforge/config.json at all.
        _git(main, "add", ".agentforge/config.json")
        _commit(main, "STORY-001: initial commit", allow_empty=False)
        _git(main, "branch", "feature")
        worktree = tmp / "feature-wt"
        _git(main, "worktree", "add", str(worktree), "feature")
        return main, worktree

    def test_dot_git_is_a_file_not_a_directory_in_the_worktree(self) -> None:
        with TemporaryDirectory() as tmp:
            _main, worktree = self._make_worktree(Path(tmp))
            self.assertTrue((worktree / ".git").is_file())

    def test_resolved_hooks_dir_is_the_shared_main_repo_hooks_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            main, worktree = self._make_worktree(Path(tmp))
            main_hooks = git_policy._resolve_hooks_dir(main)
            worktree_hooks = git_policy._resolve_hooks_dir(worktree)
            self.assertEqual(main_hooks, worktree_hooks)
            self.assertEqual(main_hooks, (main / ".git" / "hooks").resolve())

    def test_install_from_worktree_applies_to_commits_in_both_worktrees(self) -> None:
        with TemporaryDirectory() as tmp:
            main, worktree = self._make_worktree(Path(tmp))
            plan = git_policy.apply_hook_install(worktree, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_CHAINED)

            # Installed once from the worktree, but hooks are shared: a
            # commit in the main checkout is covered too.
            bad_in_main = _commit(main, "no reference at all")
            self.assertNotEqual(bad_in_main.returncode, 0)

            bad_in_worktree = _commit(worktree, "no reference at all")
            self.assertNotEqual(bad_in_worktree.returncode, 0)

            good_in_worktree = _commit(worktree, "STORY-002: fix in the worktree")
            self.assertEqual(good_in_worktree.returncode, 0, good_in_worktree.stderr)

    def test_worktree_commit_reads_its_own_working_directory_config(self) -> None:
        # Each worktree has its own working-directory copy of files,
        # including .agentforge/config.json -- the hook must validate
        # against whichever worktree the commit is actually happening in.
        with TemporaryDirectory() as tmp:
            main, worktree = self._make_worktree(Path(tmp))
            git_policy.apply_hook_install(main, SCRIPTS_DIR)

            # Turn traceability off only in the worktree's own config.
            _write_config(worktree, {**LOCAL_ENFORCE_CFG, "traceability": {"mode": "off"}})

            result = _commit(worktree, "no reference at all, but traceability is off here")
            self.assertEqual(result.returncode, 0, result.stderr)

            still_enforced = _commit(main, "no reference at all")
            self.assertNotEqual(still_enforced.returncode, 0)


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class CiOnlyFallbackTests(unittest.TestCase):
    def test_non_git_directory_yields_ci_only_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(exist_ok=True)
            plan = git_policy.apply_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_CI_ONLY)
            self.assertIn("check-commit", plan.instructions)

    def test_check_commit_validates_a_specific_sha_without_any_local_hook(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            # No hook installed at all -- commits succeed locally...
            good = _commit(root, "STORY-001: good commit")
            self.assertEqual(good.returncode, 0, good.stderr)
            bad = _commit(root, "no reference at all")
            self.assertEqual(bad.returncode, 0, bad.stderr)  # not blocked locally

            good_sha = _git(root, "rev-parse", "HEAD~1").stdout.strip()
            bad_sha = _git(root, "rev-parse", "HEAD").stdout.strip()

            # ...but CI can still catch the noncompliant one after the fact.
            good_result = git_policy.check_commit(good_sha, root)
            self.assertTrue(good_result.ok)
            bad_result = git_policy.check_commit(bad_sha, root)
            self.assertFalse(bad_result.ok)

    def test_check_commit_does_not_crash_on_non_utf8_message_bytes(self) -> None:
        # Regression test (found in code review): a commit message
        # containing non-UTF-8 bytes must produce a clean ValidationResult
        # from the CI-only fallback, not an uncaught UnicodeDecodeError.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            msg_file = root / "latin1-message.txt"
            msg_file.write_bytes("STORY-001: caf\xe9 non-UTF-8 byte".encode("latin-1"))
            commit = subprocess.run(
                ["git", "-C", str(root), "commit", "-q", "--allow-empty", "-F", str(msg_file)],
                capture_output=True,
            )
            self.assertEqual(commit.returncode, 0, commit.stderr)

            try:
                result = git_policy.check_commit("HEAD", root)
            except UnicodeDecodeError:  # pragma: no cover - the bug this guards against
                self.fail("check_commit raised UnicodeDecodeError on a non-UTF-8 message")
            self.assertIsInstance(result, git_policy.ValidationResult)


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class MergeCommitEndToEndTests(unittest.TestCase):
    def test_real_merge_commit_is_exempt_end_to_end(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_hook_install(root, SCRIPTS_DIR)

            _commit(root, "STORY-001: base commit")
            base_branch = _git(root, "branch", "--show-current").stdout.strip()
            _git(root, "branch", "feature")
            _git(root, "checkout", "-q", "feature")
            _commit(root, "STORY-002: feature commit")
            _git(root, "checkout", "-q", base_branch)
            merge = subprocess.run(
                ["git", "-C", str(root), "merge", "--no-ff", "feature"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(merge.returncode, 0, merge.stderr)


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class CliSubprocessTests(unittest.TestCase):
    """Exercises scripts/git_policy.py as an actual subprocess (not just
    an imported module) for the two entry points the installed hook and a
    CI pipeline invoke, matching the subprocess-level convention already
    used in tests/test_setup_idempotence.py."""

    def test_check_message_file_cli_exit_codes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)

            good_msg = root / "good.txt"
            good_msg.write_text("STORY-001: fine", encoding="utf-8")
            good = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "git_policy.py"), "check-message-file",
                 str(good_msg), "--project-root", str(root)],
                capture_output=True, text=True,
            )
            self.assertEqual(good.returncode, 0, good.stderr)

            bad_msg = root / "bad.txt"
            bad_msg.write_text("no reference", encoding="utf-8")
            bad = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "git_policy.py"), "check-message-file",
                 str(bad_msg), "--project-root", str(root)],
                capture_output=True, text=True,
            )
            self.assertEqual(bad.returncode, 1)

    def test_install_cli_exit_codes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            chained = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "git_policy.py"), "install",
                 "--project-root", str(root), "--scripts-dir", str(SCRIPTS_DIR)],
                capture_output=True, text=True,
            )
            self.assertEqual(chained.returncode, 0, chained.stderr)
            self.assertTrue((root / ".git" / "hooks" / "commit-msg").is_file())

            (root / ".husky").mkdir()
            manual = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "git_policy.py"), "install",
                 "--project-root", str(root), "--scripts-dir", str(SCRIPTS_DIR)],
                capture_output=True, text=True,
            )
            self.assertEqual(manual.returncode, 2)

    def test_check_pre_push_cli_exit_codes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)

            good_old = _commit_sha(root, "STORY-001: base")
            good_new = _commit_sha(root, "STORY-002: fine")
            good = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "git_policy.py"), "check-pre-push",
                 "origin", "file:///nonexistent", "--project-root", str(root)],
                input=f"refs/heads/main {good_new} refs/heads/main {good_old}\n",
                capture_output=True, text=True,
            )
            self.assertEqual(good.returncode, 0, good.stderr)

            bad_new = _commit_sha(root, "no reference at all")
            bad = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "git_policy.py"), "check-pre-push",
                 "origin", "file:///nonexistent", "--project-root", str(root)],
                input=f"refs/heads/main {bad_new} refs/heads/main {good_new}\n",
                capture_output=True, text=True,
            )
            self.assertEqual(bad.returncode, 1)
            self.assertIn(bad_new[:12], bad.stderr)


# ---------------------------------------------------------------------------
# STORY-012: the `pre-push` hook installer and installed hook, extending
# STORY-011's chained/manual/ci_only installation mechanism for a second,
# independent hook file rather than overwriting it.
# ---------------------------------------------------------------------------


def _run_pre_push_hook(root: Path, stdin_text: str) -> subprocess.CompletedProcess:
    """Invoke the *installed* pre-push hook script directly with hand
    -built stdin, exactly as Git would invoke it -- but without ever
    running `git push`, `git fetch`, or `git clone` against any remote,
    real or simulated (this story's explicit "no network access, no real
    remote pushes" requirement)."""
    hook_path = root / ".git" / "hooks" / "pre-push"
    return subprocess.run(
        [str(hook_path), "origin", "file:///nonexistent-remote"],
        cwd=str(root),
        input=stdin_text,
        capture_output=True,
        text=True,
    )


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class PrePushInstallationTests(unittest.TestCase):
    def test_plan_reports_chained_with_no_existing_hook(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            plan = git_policy.plan_pre_push_hook_install(root)
            self.assertEqual(plan.status, git_policy.INSTALL_CHAINED)
            self.assertIsNone(plan.existing_hook_path)

    def test_apply_writes_an_executable_managed_hook(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            plan = git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_CHAINED)
            hook_path = root / ".git" / "hooks" / "pre-push"
            self.assertTrue(hook_path.is_file())
            self.assertTrue(hook_path.stat().st_mode & stat.S_IXUSR)
            text = hook_path.read_text(encoding="utf-8")
            self.assertIn(str(SCRIPTS_DIR), text)
            self.assertIn("Managed by AgentForge", text)

    def test_hook_allows_a_compliant_push_range(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            old_tip = _commit_sha(root, "STORY-001: base")
            new_tip = _commit_sha(root, "STORY-002: more")
            result = _run_pre_push_hook(root, f"refs/heads/main {new_tip} refs/heads/main {old_tip}\n")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_hook_rejects_a_noncompliant_outgoing_commit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            old_tip = _commit_sha(root, "STORY-001: base")
            new_tip = _commit_sha(root, "no reference at all")
            result = _run_pre_push_hook(root, f"refs/heads/main {new_tip} refs/heads/main {old_tip}\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(new_tip[:12], result.stderr)

    def test_hook_catches_an_older_noncompliant_commit_behind_a_compliant_head(self) -> None:
        # The pushed-commit analog of tests/test_git_policy.py's
        # PrePushTests::test_compliant_head_does_not_mask_an_older_
        # noncompliant_commit, but exercised through the real installed
        # hook script end to end.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            remote_tip = _commit_sha(root, "STORY-001: already on the remote")
            bad = _commit_sha(root, "no reference, buried in the middle")
            head = _commit_sha(root, "STORY-002: compliant HEAD")
            result = _run_pre_push_hook(root, f"refs/heads/main {head} refs/heads/main {remote_tip}\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(bad[:12], result.stderr)
            self.assertNotIn(head[:12], result.stderr)

    def test_hook_allows_deletion_even_under_enforce(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _write_config(root, LOCAL_ENFORCE_CFG)
            git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            some_sha = _commit_sha(root, "STORY-001: whatever")
            zero = "0" * 40
            result = _run_pre_push_hook(root, f"(delete) {zero} refs/heads/old {some_sha}\n")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_reinstall_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            first = (root / ".git" / "hooks" / "pre-push").read_text(encoding="utf-8")
            plan2 = git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan2.status, git_policy.INSTALL_CHAINED)
            second = (root / ".git" / "hooks" / "pre-push").read_text(encoding="utf-8")
            self.assertEqual(first, second)
            self.assertFalse(
                (root / ".git" / "hooks" / git_policy.PRE_PUSH_CHAINED_HOOK_BACKUP_NAME).exists()
            )


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class ExistingPrePushHookChainingTests(unittest.TestCase):
    """STORY-012's analog of ExistingHookChainingTests above: an
    unrecognized, pre-existing `pre-push` hook (the "existing pre-push
    manager" scenario the story's minimum test coverage calls for) must be
    preserved and chain-called, never silently overwritten."""

    def _write_marker_hook(self, root: Path, marker: Path, exit_code: int = 0) -> None:
        hooks_dir = root / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook = hooks_dir / "pre-push"
        hook.write_text(
            "#!/bin/sh\n"
            "cat > /dev/null\n"
            f"echo ran >> {marker}\n"
            f"exit {exit_code}\n",
            encoding="utf-8",
        )
        hook.chmod(hook.stat().st_mode | 0o111)

    def test_preexisting_hook_is_detected_and_never_silently_overwritten(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            self._write_marker_hook(root, root / "marker.txt")
            plan = git_policy.plan_pre_push_hook_install(root)
            self.assertEqual(plan.status, git_policy.INSTALL_CHAINED)
            self.assertIsNotNone(plan.existing_hook_path)
            self.assertFalse(plan.existing_hook_is_ours)

    def test_preexisting_hook_is_preserved_and_chain_called(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            marker = root / "marker.txt"
            self._write_marker_hook(root, marker)
            _write_config(root, LOCAL_ENFORCE_CFG)

            git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)

            backup = root / ".git" / "hooks" / git_policy.PRE_PUSH_CHAINED_HOOK_BACKUP_NAME
            self.assertTrue(backup.is_file())

            old_tip = _commit_sha(root, "STORY-001: base")
            new_tip = _commit_sha(root, "STORY-002: valid reference")
            result = _run_pre_push_hook(root, f"refs/heads/main {new_tip} refs/heads/main {old_tip}\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(marker.exists())
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), "ran")

    def test_preexisting_hook_failure_blocks_the_push(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            self._write_marker_hook(root, root / "marker.txt", exit_code=1)
            _write_config(root, LOCAL_ENFORCE_CFG)

            git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)

            old_tip = _commit_sha(root, "STORY-001: base")
            new_tip = _commit_sha(root, "STORY-002: valid reference")
            # Even a fully compliant AgentForge-valid range must still be
            # rejected because the chained, pre-existing hook itself fails
            # -- AgentForge must never silently override another hook's
            # veto (matching ExistingHookChainingTests's commit-msg
            # equivalent above).
            result = _run_pre_push_hook(root, f"refs/heads/main {new_tip} refs/heads/main {old_tip}\n")
            self.assertNotEqual(result.returncode, 0)

    def test_reinstall_does_not_stack_backups(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            self._write_marker_hook(root, root / "marker.txt")

            git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            backup_text = (root / ".git" / "hooks" / git_policy.PRE_PUSH_CHAINED_HOOK_BACKUP_NAME).read_text(
                encoding="utf-8"
            )
            git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            backup_text_2 = (root / ".git" / "hooks" / git_policy.PRE_PUSH_CHAINED_HOOK_BACKUP_NAME).read_text(
                encoding="utf-8"
            )
            self.assertEqual(backup_text, backup_text_2)
            plan = git_policy.plan_pre_push_hook_install(root)
            self.assertTrue(plan.existing_hook_is_ours)


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class PrePushHookManagerDetectionTests(unittest.TestCase):
    def test_husky_present_yields_manual_plan_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / ".husky").mkdir()

            plan = git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_MANUAL)
            self.assertIn("Husky", plan.reason)
            self.assertFalse((root / ".git" / "hooks" / "pre-push").exists())

    def test_pre_commit_config_present_yields_manual_plan_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

            plan = git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_MANUAL)
            self.assertIn("pre-commit", plan.reason)
            self.assertFalse((root / ".git" / "hooks" / "pre-push").exists())

    def test_custom_core_hooks_path_is_respected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            _git(root, "config", "core.hooksPath", ".githooks")

            plan = git_policy.apply_pre_push_hook_install(root, SCRIPTS_DIR)
            self.assertEqual(plan.status, git_policy.INSTALL_CHAINED)
            self.assertTrue((root / ".githooks" / "pre-push").is_file())
            self.assertFalse((root / ".git" / "hooks" / "pre-push").exists())


@unittest.skipUnless(_GIT_AVAILABLE, "git executable not available")
class CombinedInstallCliTests(unittest.TestCase):
    """The single `install` CLI subcommand extended to install both
    `commit-msg` (STORY-011) and `pre-push` (STORY-012) hooks in one call,
    without either one overwriting the other or an unrelated hook
    manager."""

    def test_install_cli_installs_both_hooks(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "git_policy.py"), "install",
                 "--project-root", str(root), "--scripts-dir", str(SCRIPTS_DIR)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / ".git" / "hooks" / "commit-msg").is_file())
            self.assertTrue((root / ".git" / "hooks" / "pre-push").is_file())

    def test_install_cli_reports_manual_for_both_when_husky_present(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / ".husky").mkdir()
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "git_policy.py"), "install",
                 "--project-root", str(root), "--scripts-dir", str(SCRIPTS_DIR)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse((root / ".git" / "hooks" / "commit-msg").exists())
            self.assertFalse((root / ".git" / "hooks" / "pre-push").exists())


if __name__ == "__main__":
    unittest.main()
