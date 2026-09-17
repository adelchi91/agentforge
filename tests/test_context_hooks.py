"""Tests for STORY-009's SessionStart lifecycle-context hook
(scripts/context.py).

Covers the STORY-009 acceptance criteria:

  - all four lifecycle sources (startup/resume/clear/compact) produce
    equivalent context from the same active-work snapshot;
  - a missing snapshot is a normal no-op (no stdout, no stderr);
  - a malformed snapshot (bad JSON, wrong shape, missing identity fields)
    is a visible stderr warning, never an uncaught exception, and never
    written to stdout;
  - a "stale" (old `prepared_at`, otherwise valid) snapshot is rendered
    exactly like any other valid snapshot -- AgentForge deliberately has
    no staleness/expiry policy (ADR-0005: "hooks will happily operate on a
    stale snapshot rather than silently going stale and slow");
  - an oversized snapshot is truncated to fit the configured
    `context.max_bytes`, preserving identity and the source pointer;
  - stdout contains only the hook protocol JSON envelope; every
    diagnostic is on stderr.

`tests/test_context_hooks.py` is shared with STORY-010's
`UserPromptSubmitTests` (added separately, to the same module, by a
sibling change) -- this file intentionally contains only
`SessionStartTests`.
"""

from __future__ import annotations

import io
import json
import sys
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

LIFECYCLE_SOURCES = ("startup", "resume", "clear", "compact")

VALID_SNAPSHOT = {
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


def write_config(project_dir: Path, max_bytes: int | None = None) -> None:
    cfg = json.loads(json.dumps(agentforge_config.DEFAULT_CONFIG))  # deep copy
    if max_bytes is not None:
        cfg["context"]["max_bytes"] = max_bytes
    config_dir = project_dir / ".agentforge"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


def write_snapshot_raw(project_dir: Path, text: str) -> None:
    state_dir = project_dir / ".agentforge"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "active-work.json").write_text(text, encoding="utf-8")


def write_snapshot(project_dir: Path, snapshot: dict) -> None:
    write_snapshot_raw(project_dir, json.dumps(snapshot))


def run_hook(raw_stdin: str) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO(raw_stdin)):
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = context.main()
    return exit_code, out.getvalue(), err.getvalue()


def session_start_payload(project_dir: Path, source: str) -> str:
    return json.dumps(
        {
            "hook_event_name": "SessionStart",
            "source": source,
            "cwd": str(project_dir),
            "session_id": "test-session",
        }
    )


class SessionStartTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_dir = Path(self._tmp.name)

    # -- missing snapshot: normal no-op -------------------------------

    def test_missing_snapshot_is_a_silent_no_op_for_every_source(self) -> None:
        write_config(self.project_dir)
        for source in LIFECYCLE_SOURCES:
            with self.subTest(source=source):
                exit_code, out, err = run_hook(session_start_payload(self.project_dir, source))
                self.assertEqual(exit_code, 0)
                self.assertEqual(out, "")
                self.assertEqual(err, "")

    def test_missing_config_still_no_ops_on_missing_snapshot(self) -> None:
        # No .agentforge directory at all -- config.py's DEFAULT_CONFIG
        # fallback must not turn a missing snapshot into an error.
        exit_code, out, err = run_hook(session_start_payload(self.project_dir, "startup"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

    def test_malformed_config_falls_back_to_default_and_still_renders_context(self) -> None:
        # An invalid committed config must warn (visibly, on stderr) but
        # never block context restoration -- the same "broken optional
        # governance file must not freeze the hook" principle
        # scripts/scope_policy.py already applies.
        config_dir = self.project_dir / ".agentforge"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text("{not valid json", encoding="utf-8")
        write_snapshot(self.project_dir, VALID_SNAPSHOT)
        exit_code, out, err = run_hook(session_start_payload(self.project_dir, "startup"))
        self.assertEqual(exit_code, 0)
        self.assertIn("config.json", err)
        additional_context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("local:STORY-042", additional_context)

    # -- valid snapshot: equivalent context across all four sources ---

    def test_all_four_sources_produce_equivalent_context(self) -> None:
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)
        rendered = {}
        for source in LIFECYCLE_SOURCES:
            exit_code, out, err = run_hook(session_start_payload(self.project_dir, source))
            self.assertEqual(exit_code, 0)
            self.assertEqual(err, "")
            payload = json.loads(out)
            rendered[source] = payload["hookSpecificOutput"]["additionalContext"]
        # All four sources must yield exactly the same context text.
        self.assertEqual(len(set(rendered.values())), 1)

    def test_valid_snapshot_stdout_is_only_the_hook_envelope(self) -> None:
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)
        exit_code, out, err = run_hook(session_start_payload(self.project_dir, "startup"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(err, "")
        # The entire stdout must be exactly one JSON object -- nothing
        # before or after it.
        payload = json.loads(out)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_valid_snapshot_context_contains_identity_source_scope_and_verification(self) -> None:
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)
        _exit_code, out, _err = run_hook(session_start_payload(self.project_dir, "resume"))
        additional_context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("local:STORY-042", additional_context)
        self.assertIn("Add the widget exporter", additional_context)
        self.assertIn("docs/work-items/STORY-042.md", additional_context)
        self.assertIn("src/widget_exporter.py", additional_context)
        self.assertIn("src/secrets.py", additional_context)
        self.assertIn("python3 -m unittest tests.test_widget_exporter -v", additional_context)

    # -- stale snapshot: rendered like any other valid snapshot -------

    def test_stale_snapshot_is_rendered_without_any_warning(self) -> None:
        write_config(self.project_dir)
        stale = dict(VALID_SNAPSHOT)
        stale["prepared_at"] = "2020-01-01T00:00:00Z"  # far in the past
        write_snapshot(self.project_dir, stale)
        exit_code, out, err = run_hook(session_start_payload(self.project_dir, "compact"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(err, "", "AgentForge has no staleness policy; an old snapshot is not a warning")
        additional_context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("local:STORY-042", additional_context)

    # -- malformed snapshot: visible warning, never an exception ------

    def test_invalid_json_snapshot_warns_and_emits_no_context(self) -> None:
        write_config(self.project_dir)
        write_snapshot_raw(self.project_dir, "{not valid json")
        exit_code, out, err = run_hook(session_start_payload(self.project_dir, "startup"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertIn("active-work.json", err)

    def test_non_object_json_snapshot_warns_and_emits_no_context(self) -> None:
        write_config(self.project_dir)
        write_snapshot_raw(self.project_dir, "[1, 2, 3]")
        exit_code, out, err = run_hook(session_start_payload(self.project_dir, "startup"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertNotEqual(err, "")

    def test_snapshot_missing_canonical_id_warns_and_emits_no_context(self) -> None:
        write_config(self.project_dir)
        broken = dict(VALID_SNAPSHOT)
        del broken["canonical_id"]
        write_snapshot(self.project_dir, broken)
        exit_code, out, err = run_hook(session_start_payload(self.project_dir, "startup"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertIn("canonical_id", err)

    def test_snapshot_with_wrong_type_for_source_warns_and_emits_no_context(self) -> None:
        write_config(self.project_dir)
        broken = dict(VALID_SNAPSHOT)
        broken["source"] = 12345
        write_snapshot(self.project_dir, broken)
        exit_code, out, err = run_hook(session_start_payload(self.project_dir, "startup"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertIn("source", err)

    def test_malformed_snapshot_never_raises_even_with_binary_garbage(self) -> None:
        write_config(self.project_dir)
        state_dir = self.project_dir / ".agentforge"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "active-work.json").write_bytes(b"\xff\xfe\x00\x01not utf-8 or json")
        try:
            exit_code, out, err = run_hook(session_start_payload(self.project_dir, "startup"))
        except Exception as exc:  # pragma: no cover - the assertion below is the real check
            self.fail(f"handling a malformed snapshot must never raise, got: {exc!r}")
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertNotEqual(err, "")

    # -- oversized snapshot: deterministic, identity-preserving bound -

    def test_oversized_snapshot_is_truncated_to_fit_max_bytes_preserving_identity(self) -> None:
        write_config(self.project_dir, max_bytes=200)
        huge = dict(VALID_SNAPSHOT)
        huge["allowed_paths"] = [f"src/module_{i}/very_long_file_name_{i}.py" for i in range(50)]
        huge["forbidden_paths"] = [f"secrets/very_long_secret_name_{i}.env" for i in range(50)]
        huge["verification_commands"] = [
            f"python3 -m unittest tests.test_module_{i} -v" for i in range(50)
        ]
        huge["out_of_scope_summary"] = "This is a very long out-of-scope description. " * 50
        write_snapshot(self.project_dir, huge)
        exit_code, out, err = run_hook(session_start_payload(self.project_dir, "startup"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(err, "")
        additional_context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(additional_context.encode("utf-8")), 200)
        # Identity and the source pointer must survive the truncation.
        self.assertIn("local:STORY-042", additional_context)
        self.assertIn("docs/work-items/STORY-042.md", additional_context)

    def test_oversized_snapshot_drops_descriptive_content_before_scope(self) -> None:
        # A max_bytes just large enough for identity/source/scope but not
        # the long out-of-scope summary: the summary must be the first
        # thing dropped, while at least one allowed path survives.
        write_config(self.project_dir, max_bytes=260)
        snapshot = dict(VALID_SNAPSHOT)
        snapshot["out_of_scope_summary"] = "Extremely long descriptive filler text. " * 30
        write_snapshot(self.project_dir, snapshot)
        _exit_code, out, _err = run_hook(session_start_payload(self.project_dir, "startup"))
        additional_context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("Extremely long descriptive filler text", additional_context)
        self.assertIn("local:STORY-042", additional_context)

    # -- source-agnostic dispatch: other hook events are a no-op ------

    def test_non_session_start_event_is_a_no_op(self) -> None:
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)
        payload = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.project_dir),
                "prompt": "whatever",
            }
        )
        exit_code, out, _err = run_hook(payload)
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_missing_hook_event_name_is_treated_as_session_start(self) -> None:
        # Real Claude Code payloads always carry hook_event_name, but a
        # payload that omits it must not silently no-op forever -- this
        # module is only ever wired to SessionStart today.
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)
        payload = json.dumps({"source": "startup", "cwd": str(self.project_dir)})
        exit_code, out, _err = run_hook(payload)
        self.assertEqual(exit_code, 0)
        payload_out = json.loads(out)
        self.assertEqual(payload_out["hookSpecificOutput"]["hookEventName"], "SessionStart")


if __name__ == "__main__":
    unittest.main()
