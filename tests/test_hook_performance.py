"""Performance test for STORY-009's SessionStart hook (scripts/context.py).

Execution-plan "Definition of done" / STORY-009 acceptance criteria: the
hook completes within 100ms on fixture data. Timed in-process (the same
way tests/test_hook_protocol.py drives scripts/scope_policy.main()) so the
measurement reflects the hook's own read/render work rather than Python
interpreter startup, which the real subprocess invocation also pays but
which this repo's other hook scripts are not held to either.
"""

from __future__ import annotations

import io
import json
import sys
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config as agentforge_config  # noqa: E402
from scripts import context  # noqa: E402

MAX_SECONDS = 0.1  # 100ms


class SessionStartHookPerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_dir = Path(self._tmp.name)

        cfg = json.loads(json.dumps(agentforge_config.DEFAULT_CONFIG))
        config_dir = self.project_dir / ".agentforge"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

        snapshot = {
            "schema_version": 1,
            "canonical_id": "local:STORY-042",
            "title": "Add the widget exporter",
            "source": "docs/work-items/STORY-042.md",
            "content_digest": "deadbeef",
            "prepared_at": "2026-09-17T00:00:00Z",
            "allowed_paths": ["src/widget_exporter.py", "tests/test_widget_exporter.py"],
            "forbidden_paths": ["src/secrets.py"],
            "verification_commands": ["python3 -m unittest tests.test_widget_exporter -v"],
            "out_of_scope_summary": "Does not cover the legacy CSV exporter.",
        }
        (config_dir / "active-work.json").write_text(json.dumps(snapshot), encoding="utf-8")

        self.payload = json.dumps(
            {
                "hook_event_name": "SessionStart",
                "source": "startup",
                "cwd": str(self.project_dir),
                "session_id": "perf-test-session",
            }
        )

    def _run_once(self) -> float:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(self.payload)):
            with redirect_stdout(out), redirect_stderr(err):
                start = time.perf_counter()
                exit_code = context.main()
                elapsed = time.perf_counter() - start
        self.assertEqual(exit_code, 0)
        return elapsed

    def test_session_start_completes_within_100ms_on_fixture_data(self) -> None:
        # A single cold call, plus a couple of warm repeats to guard
        # against one-off scheduling noise -- every call must be within
        # budget, not just an average.
        for _ in range(3):
            elapsed = self._run_once()
            self.assertLess(
                elapsed,
                MAX_SECONDS,
                f"SessionStart hook took {elapsed * 1000:.2f}ms, budget is {MAX_SECONDS * 1000:.0f}ms",
            )


if __name__ == "__main__":
    unittest.main()
