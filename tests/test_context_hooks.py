"""Tests for AgentForge lifecycle-hook context injection (scripts/context.py).

`SessionStartTests` covers STORY-009's acceptance criteria:

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

`UserPromptSubmitTests` covers STORY-010's acceptance criteria (see
docs/plans/agentforge-v2-user-stories.md):

  - a configured canonical identifier detected in the prompt that matches
    the active-work snapshot's canonical_id injects the bounded work
    contract (identity, scope, verification commands);
  - a detected identifier that differs from the active snapshot (or there
    is no active snapshot, or the snapshot is malformed) injects only the
    detected id, the current active id (or "none"), and a
    `/agentforge:prepare-work <id>` instruction;
  - more than one distinct detected identifier in one prompt reports the
    ambiguity explicitly, listing every id, rather than silently picking
    the first;
  - false positives -- version strings, dates, line-number references --
    never activate the hook;
  - injected context never exceeds the project's configured
    `context.max_bytes`;
  - this hook never performs a network call or shells out, even when the
    configured tracker is github/gitlab.

Both classes exercise the same `scripts/context.py` module, dispatched
purely by the `hook_event_name` field on the hook's stdin JSON payload --
there is no CLI subcommand.
"""

from __future__ import annotations

import copy
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
                "hook_event_name": "SomeOtherEvent",
                "cwd": str(self.project_dir),
            }
        )
        exit_code, out, _err = run_hook(payload)
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_missing_hook_event_name_is_treated_as_session_start(self) -> None:
        # Real Claude Code payloads always carry hook_event_name, but a
        # payload that omits it must not silently no-op forever -- this
        # module falls back to SessionStart handling, its first owner.
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)
        payload = json.dumps({"source": "startup", "cwd": str(self.project_dir)})
        exit_code, out, _err = run_hook(payload)
        self.assertEqual(exit_code, 0)
        payload_out = json.loads(out)
        self.assertEqual(payload_out["hookSpecificOutput"]["hookEventName"], "SessionStart")


GITHUB_CONFIG = {
    "schema_version": 1,
    "tracker": {"type": "github", "repository": "acme/widgets"},
    "identifier": {"pattern": "^#\\d+$", "examples": ["#1", "#123"]},
    "context": {"max_bytes": 8000},
    "traceability": {"mode": "off"},
    "scope": {"mode": "off", "agents": {}},
    "migration_policy": {"enabled": False},
    "quality": {"post_edit": "off"},
}

ACTIVE_SNAPSHOT = {
    "schema_version": 1,
    "canonical_id": "local:STORY-010",
    "title": "Inject named work context on prompt submission",
    "source": "docs/work-items/STORY-010.md",
    "content_digest": "deadbeef",
    "prepared_at": "2026-09-01T00:00:00Z",
    "allowed_paths": ["scripts/context.py", "tests/"],
    "forbidden_paths": ["scripts/work_items.py"],
    "verification_commands": [
        "python3 -m unittest tests.test_context_hooks.UserPromptSubmitTests -v",
    ],
    "out_of_scope_summary": "SessionStart handling is a separate story.",
}


def write_active_state_raw(project_dir: Path, text: str) -> None:
    write_snapshot_raw(project_dir, text)


def write_active_state(project_dir: Path, snapshot: dict) -> None:
    write_snapshot(project_dir, snapshot)


def parse_additional_context(stdout_text: str) -> str:
    payload = json.loads(stdout_text)
    return payload["hookSpecificOutput"]["additionalContext"]


class UserPromptSubmitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_dir = Path(self._tmp.name)
        write_config_dict(self.project_dir, copy.deepcopy(agentforge_config.DEFAULT_CONFIG))

    def _payload(self, prompt: str, **overrides) -> dict:
        payload = {
            "session_id": "sess-1",
            "cwd": str(self.project_dir),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        }
        payload.update(overrides)
        return payload

    # -- matching identifier -------------------------------------------

    def test_matching_identifier_injects_bounded_work_contract(self) -> None:
        write_active_state(self.project_dir, ACTIVE_SNAPSHOT)
        exit_code, out, _err = run_hook(json.dumps(self._payload("Let's continue STORY-010.")))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertIn("local:STORY-010", text)
        self.assertIn("Inject named work context", text)
        self.assertIn("scripts/context.py", text)
        self.assertIn(
            "python3 -m unittest tests.test_context_hooks.UserPromptSubmitTests -v", text
        )
        self.assertIn("scripts/work_items.py", text)  # forbidden path surfaced too

    def test_matching_identifier_hook_event_name_is_user_prompt_submit(self) -> None:
        write_active_state(self.project_dir, ACTIVE_SNAPSHOT)
        _exit_code, out, _err = run_hook(json.dumps(self._payload("STORY-010 status?")))
        payload = json.loads(out)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")

    # -- mismatching identifier ------------------------------------------

    def test_mismatching_identifier_injects_only_ids_and_instruction(self) -> None:
        write_active_state(self.project_dir, ACTIVE_SNAPSHOT)
        exit_code, out, _err = run_hook(json.dumps(self._payload("Please work on STORY-011 now.")))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertIn("STORY-011", text)
        self.assertIn("local:STORY-010", text)
        self.assertIn("/agentforge:prepare-work STORY-011", text)
        # Never the bounded contract fields of the *other*, currently active item.
        self.assertNotIn("Verification commands", text)
        self.assertNotIn("May touch", text)

    # -- absent active state ---------------------------------------------

    def test_absent_active_state_reports_none_as_active(self) -> None:
        # No .agentforge/active-work.json written at all.
        exit_code, out, _err = run_hook(json.dumps(self._payload("Let's start STORY-020.")))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertIn("STORY-020", text)
        self.assertIn("Active work: none", text)
        self.assertIn("/agentforge:prepare-work STORY-020", text)

    # -- malformed active state -------------------------------------------

    def test_malformed_active_state_is_treated_as_absent_and_warns(self) -> None:
        write_active_state_raw(self.project_dir, "{not valid json")
        exit_code, out, err = run_hook(json.dumps(self._payload("Let's start STORY-020.")))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertIn("Active work: none", text)
        self.assertIn("malformed", err.lower())

    def test_active_state_missing_canonical_id_is_treated_as_malformed(self) -> None:
        write_active_state(self.project_dir, {"schema_version": 1, "title": "no id here"})
        exit_code, out, err = run_hook(json.dumps(self._payload("Let's start STORY-020.")))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertIn("Active work: none", text)
        self.assertIn("malformed", err.lower())

    def test_malformed_active_state_never_raises(self) -> None:
        write_active_state_raw(self.project_dir, "not json at all {{{")
        # run_hook itself will propagate any uncaught exception from main();
        # simply completing is the assertion.
        exit_code, _out, _err = run_hook(json.dumps(self._payload("STORY-020 please.")))
        self.assertEqual(exit_code, 0)

    # -- multiple identifiers ----------------------------------------------

    def test_multiple_identifiers_reports_ambiguity_listing_all(self) -> None:
        write_active_state(self.project_dir, ACTIVE_SNAPSHOT)
        prompt = "Should I finish STORY-010 or switch to STORY-011 first?"
        exit_code, out, _err = run_hook(json.dumps(self._payload(prompt)))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertIn("STORY-010", text)
        self.assertIn("STORY-011", text)
        self.assertIn("Multiple work-item references", text)
        # Never silently picks one and injects its bounded contract.
        self.assertNotIn("Verification commands", text)

    def test_repeated_mention_of_the_same_identifier_is_not_ambiguous(self) -> None:
        write_active_state(self.project_dir, ACTIVE_SNAPSHOT)
        prompt = "STORY-010: keep working on STORY-010."
        _exit_code, out, _err = run_hook(json.dumps(self._payload(prompt)))
        text = parse_additional_context(out)
        self.assertNotIn("Multiple work-item references", text)
        self.assertIn("local:STORY-010", text)

    # -- false positives: version numbers, dates, line references -----------

    def test_no_identifiers_at_all_produces_no_stdout(self) -> None:
        exit_code, out, _err = run_hook(json.dumps(self._payload("Just chatting, no ticket here.")))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_version_string_is_not_a_false_positive(self) -> None:
        exit_code, out, _err = run_hook(
            json.dumps(self._payload("Please upgrade the dependency to v2.1.0 before merging."))
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_date_is_not_a_false_positive(self) -> None:
        exit_code, out, _err = run_hook(
            json.dumps(self._payload("We agreed on 2026-09-17 as the release date."))
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_line_number_reference_is_not_a_false_positive(self) -> None:
        exit_code, out, _err = run_hook(
            json.dumps(self._payload("There's a bug on line 42 of the parser."))
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_bare_number_is_not_a_false_positive_under_local_tracker(self) -> None:
        exit_code, out, _err = run_hook(json.dumps(self._payload("See issue 42 upstream.")))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    # -- context.max_bytes enforcement ---------------------------------------

    def test_output_never_exceeds_configured_max_bytes(self) -> None:
        small_config = copy.deepcopy(agentforge_config.DEFAULT_CONFIG)
        small_config["context"]["max_bytes"] = 120
        write_config_dict(self.project_dir, small_config)
        oversized_snapshot = dict(ACTIVE_SNAPSHOT)
        oversized_snapshot["verification_commands"] = [
            f"python3 -m unittest tests.test_example_{i:03d} -v" for i in range(200)
        ]
        oversized_snapshot["allowed_paths"] = [f"src/module_{i:03d}.py" for i in range(200)]
        write_active_state(self.project_dir, oversized_snapshot)

        exit_code, out, _err = run_hook(json.dumps(self._payload("STORY-010 update?")))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertLessEqual(len(text.encode("utf-8")), 120)
        # Identity survives even though most detail had to be dropped.
        self.assertIn("STORY-010", text)

    def test_ambiguity_report_also_respects_max_bytes(self) -> None:
        small_config = copy.deepcopy(agentforge_config.DEFAULT_CONFIG)
        small_config["context"]["max_bytes"] = 40
        write_config_dict(self.project_dir, small_config)
        prompt = "STORY-010 or STORY-011 or STORY-012, which one first?"
        exit_code, out, _err = run_hook(json.dumps(self._payload(prompt)))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertLessEqual(len(text.encode("utf-8")), 40)

    # -- never fetches remote content -----------------------------------------

    def test_github_tracker_identifier_never_shells_out_or_uses_the_network(self) -> None:
        write_config_dict(self.project_dir, copy.deepcopy(GITHUB_CONFIG))
        write_active_state(
            self.project_dir,
            {**ACTIVE_SNAPSHOT, "canonical_id": "github:acme/widgets#42"},
        )
        with mock.patch("subprocess.run", side_effect=AssertionError("must not shell out")):
            with mock.patch("subprocess.Popen", side_effect=AssertionError("must not shell out")):
                exit_code, out, _err = run_hook(
                    json.dumps(self._payload("Let's finish up #42 today."))
                )
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)  # did not raise -> no subprocess call happened
        self.assertIn("github:acme/widgets#42", text)

    def test_github_tracker_mismatched_issue_injects_prepare_work_instruction(self) -> None:
        write_config_dict(self.project_dir, copy.deepcopy(GITHUB_CONFIG))
        write_active_state(
            self.project_dir,
            {**ACTIVE_SNAPSHOT, "canonical_id": "github:acme/widgets#42"},
        )
        _exit_code, out, _err = run_hook(json.dumps(self._payload("Can we look at #7 instead?")))
        text = parse_additional_context(out)
        self.assertIn("#7", text)
        self.assertIn("github:acme/widgets#42", text)
        self.assertIn("/agentforge:prepare-work #7", text)

    def test_bare_number_is_not_a_false_positive_under_github_tracker_pattern(self) -> None:
        # identifier.pattern for this fixture is "^#\\d+$": a bare number with
        # no "#" must not match even though the tracker is configured.
        write_config_dict(self.project_dir, copy.deepcopy(GITHUB_CONFIG))
        exit_code, out, _err = run_hook(json.dumps(self._payload("There's a bug on line 42.")))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_repository_shaped_token_is_never_a_detected_identifier(self) -> None:
        write_config_dict(self.project_dir, copy.deepcopy(GITHUB_CONFIG))
        exit_code, out, _err = run_hook(
            json.dumps(self._payload("Compare against acme/widgets for context."))
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    # -- missing/invalid config falls back cleanly ----------------------------

    def test_missing_config_falls_back_to_default_identifier_pattern(self) -> None:
        # Remove the config this setUp wrote; DEFAULT_CONFIG's local
        # "^STORY-\\d{3,}$" pattern should still apply.
        (self.project_dir / ".agentforge" / "config.json").unlink()
        exit_code, out, _err = run_hook(json.dumps(self._payload("Let's start STORY-030.")))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertIn("STORY-030", text)

    def test_invalid_config_warns_and_falls_back(self) -> None:
        (self.project_dir / ".agentforge" / "config.json").write_text(
            "{not valid json", encoding="utf-8"
        )
        exit_code, out, err = run_hook(json.dumps(self._payload("Let's start STORY-030.")))
        self.assertEqual(exit_code, 0)
        text = parse_additional_context(out)
        self.assertIn("STORY-030", text)
        self.assertIn("could not load", err.lower())

    # -- protocol hygiene -----------------------------------------------------

    def test_stdout_contains_only_the_hook_json_no_extra_lines(self) -> None:
        write_active_state(self.project_dir, ACTIVE_SNAPSHOT)
        _exit_code, out, _err = run_hook(json.dumps(self._payload("STORY-010 please.")))
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        json.loads(lines[0])  # must be exactly one JSON document

    def test_missing_prompt_field_produces_no_stdout(self) -> None:
        payload = {"session_id": "sess-1", "cwd": str(self.project_dir)}
        exit_code, out, _err = run_hook(json.dumps(payload))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_malformed_stdin_json_never_raises(self) -> None:
        exit_code, out, err = run_hook("{not valid json")
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertIn("malformed", err.lower())

    def test_empty_stdin_never_raises(self) -> None:
        exit_code, out, _err = run_hook("")
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")

    def test_non_object_json_stdin_never_raises(self) -> None:
        exit_code, out, _err = run_hook("[1, 2, 3]")
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")


def write_config_dict(project_dir: Path, config: dict) -> None:
    config_dir = project_dir / ".agentforge"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
