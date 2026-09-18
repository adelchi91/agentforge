"""Cross-harness parity tests for STORY-018 ("Provide tested Codex parity
without duplicating policy code").

STORY-018 requires that `scripts/context.py` (STORY-009/010) and
`scripts/scope_policy.py` (STORY-013/014) -- the same modules Claude Code's
`hooks/hooks.json` already wires -- produce identical behavior when fed a
Codex-shaped hook payload, not just a Claude-shaped one, and that neither
module requires any Claude-only environment variable or path to resolve the
project root. This module never re-implements policy: every assertion below
calls straight into `scripts/context.py`/`scripts/scope_policy.py`'s own
public functions and `main()` entry points -- there is no second Codex code
path.

Payload shapes are drawn from the current Codex hooks documentation
(https://learn.chatgpt.com/docs/hooks, fetched 2026-09-17 -- see
docs/codex-compatibility.md for the full citation and quoted fields):
every Codex hook payload carries `session_id`, `transcript_path`, `cwd`,
`hook_event_name`, `model`, and `permission_mode` in addition to whatever
fields are specific to that event (`source` for SessionStart, `prompt` for
UserPromptSubmit, `tool_name`/`tool_input`/`tool_use_id` for PreToolUse), and
turn-scoped events add `turn_id`. A "Claude-shaped" payload in this module is
exactly the shape already used throughout `tests/test_context_hooks.py` and
`tests/test_hook_protocol.py` -- `cwd`, `hook_event_name`, and only the
event-specific fields those hooks read, with no `model`/`permission_mode`/
`transcript_path`/`tool_use_id`/`turn_id` present at all. The two shapes
overlap on every field the shared logic actually reads (`cwd`,
`hook_event_name`, `prompt`, `tool_name`, `tool_input`, `agent_type`) and
differ only in extra fields Codex adds that AgentForge's shared logic must
simply ignore.
"""

from __future__ import annotations

import io
import json
import os
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
from scripts import scope_policy  # noqa: E402

VALID_SNAPSHOT = {
    "schema_version": 1,
    "canonical_id": "local:STORY-042",
    "title": "Add the widget exporter",
    "source": "docs/work-items/STORY-042.md",
    "content_digest": "deadbeef",
    "prepared_at": "2026-09-17T00:00:00Z",
    "allowed_paths": ["src/widget_exporter.py"],
    "forbidden_paths": ["src/secrets.py"],
    "verification_commands": ["python3 -m unittest tests.test_widget_exporter -v"],
    "out_of_scope_summary": "Does not cover the legacy CSV exporter.",
}

# Codex-only fields present on every hook payload per the current Codex
# hooks documentation, deliberately absent from every "Claude-shaped"
# payload constructed below.
_CODEX_ONLY_COMMON_FIELDS = {
    "transcript_path": None,
    "model": "gpt-5.5",
    "permission_mode": "default",
}


def _claude_payload(event_name: str, **fields) -> dict:
    payload = {"hook_event_name": event_name, "session_id": "claude-session"}
    payload.update(fields)
    return payload


def _codex_payload(event_name: str, *, turn_scoped: bool = False, **fields) -> dict:
    payload = {"hook_event_name": event_name, "session_id": "codex-session"}
    payload.update(_CODEX_ONLY_COMMON_FIELDS)
    if turn_scoped:
        payload["turn_id"] = "turn-1"
    payload.update(fields)
    return payload


def write_config(project_dir: Path, **overrides) -> None:
    cfg = json.loads(json.dumps(agentforge_config.DEFAULT_CONFIG))
    for key, value in overrides.items():
        cfg[key] = value
    config_dir = project_dir / ".agentforge"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


def write_snapshot(project_dir: Path, snapshot: dict) -> None:
    state_dir = project_dir / ".agentforge"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "active-work.json").write_text(json.dumps(snapshot), encoding="utf-8")


def run_context_hook(raw_stdin: str) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO(raw_stdin)):
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = context.main()
    return exit_code, out.getvalue(), err.getvalue()


def run_scope_hook(raw_stdin: str) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO(raw_stdin)):
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = scope_policy.main()
    return exit_code, out.getvalue(), err.getvalue()


class SessionStartCrossHarnessTests(unittest.TestCase):
    """STORY-018 acceptance criterion: "Shared hook fixtures pass against
    Claude and Codex payload shapes" -- SessionStart / scripts/context.py."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_dir = Path(self._tmp.name)
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)

    def test_claude_and_codex_session_start_payloads_produce_identical_context(self) -> None:
        claude_payload = _claude_payload("SessionStart", source="startup", cwd=str(self.project_dir))
        codex_payload = _codex_payload("SessionStart", source="startup", cwd=str(self.project_dir))

        _exit_claude, out_claude, _err_claude = run_context_hook(json.dumps(claude_payload))
        _exit_codex, out_codex, _err_codex = run_context_hook(json.dumps(codex_payload))

        self.assertEqual(out_claude, out_codex)
        additional_context = json.loads(out_claude)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("local:STORY-042", additional_context)

    def test_codex_session_start_covers_all_four_documented_sources(self) -> None:
        # https://learn.chatgpt.com/docs/hooks: SessionStart's `source` is
        # documented as startup|resume|clear|compact for Codex, the exact
        # same enum STORY-009 already requires of Claude.
        outputs = []
        for source in ("startup", "resume", "clear", "compact"):
            payload = _codex_payload("SessionStart", source=source, cwd=str(self.project_dir))
            _exit_code, out, _err = run_context_hook(json.dumps(payload))
            outputs.append(out)
        self.assertTrue(all(out == outputs[0] for out in outputs))

    def test_missing_snapshot_is_a_silent_noop_under_codex_shape_too(self) -> None:
        empty_dir = Path(self._tmp.name) / "empty-project"
        empty_dir.mkdir()
        write_config(empty_dir)
        payload = _codex_payload("SessionStart", source="startup", cwd=str(empty_dir))
        exit_code, out, err = run_context_hook(json.dumps(payload))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")


class UserPromptSubmitCrossHarnessTests(unittest.TestCase):
    """STORY-018 acceptance criterion, UserPromptSubmit / scripts/context.py."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_dir = Path(self._tmp.name)
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)

    def test_matching_identifier_produces_identical_context_both_shapes(self) -> None:
        prompt = "Please continue STORY-042 from where we left off."
        claude_payload = _claude_payload("UserPromptSubmit", prompt=prompt, cwd=str(self.project_dir))
        codex_payload = _codex_payload(
            "UserPromptSubmit", prompt=prompt, cwd=str(self.project_dir), turn_scoped=True
        )

        _exit_claude, out_claude, _err_claude = run_context_hook(json.dumps(claude_payload))
        _exit_codex, out_codex, _err_codex = run_context_hook(json.dumps(codex_payload))

        self.assertEqual(out_claude, out_codex)
        self.assertNotEqual(out_claude, "")

    def test_mismatched_identifier_produces_identical_prepare_work_notice(self) -> None:
        prompt = "Let's look at STORY-999 instead."
        claude_payload = _claude_payload("UserPromptSubmit", prompt=prompt, cwd=str(self.project_dir))
        codex_payload = _codex_payload(
            "UserPromptSubmit", prompt=prompt, cwd=str(self.project_dir), turn_scoped=True
        )

        _exit_claude, out_claude, _err_claude = run_context_hook(json.dumps(claude_payload))
        _exit_codex, out_codex, _err_codex = run_context_hook(json.dumps(codex_payload))

        self.assertEqual(out_claude, out_codex)
        self.assertIn("STORY-999", out_claude)
        self.assertIn("/agentforge:prepare-work", out_claude)

    def test_no_identifier_is_a_silent_noop_both_shapes(self) -> None:
        prompt = "What does this function do?"
        for payload in (
            _claude_payload("UserPromptSubmit", prompt=prompt, cwd=str(self.project_dir)),
            _codex_payload("UserPromptSubmit", prompt=prompt, cwd=str(self.project_dir), turn_scoped=True),
        ):
            exit_code, out, err = run_context_hook(json.dumps(payload))
            self.assertEqual(exit_code, 0)
            self.assertEqual(out, "")
            self.assertEqual(err, "")


class PreToolUseCrossHarnessTests(unittest.TestCase):
    """STORY-018 acceptance criterion, PreToolUse / scripts/scope_policy.py."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_dir = Path(self._tmp.name)

    def _write_scope_config(self, mode: str, agents: dict | None = None) -> None:
        write_config(self.project_dir, scope={"mode": mode, "agents": agents or {}})

    def test_ask_mode_destructive_bash_asks_under_both_shapes(self) -> None:
        self._write_scope_config("ask")
        claude_payload = _claude_payload(
            "PreToolUse",
            cwd=str(self.project_dir),
            tool_name="Bash",
            tool_input={"command": "git push --force origin main"},
        )
        codex_payload = _codex_payload(
            "PreToolUse",
            cwd=str(self.project_dir),
            tool_name="Bash",
            tool_input={"command": "git push --force origin main"},
            tool_use_id="tu_1",
            turn_scoped=True,
        )

        _exit_claude, out_claude, _err_claude = run_scope_hook(json.dumps(claude_payload))
        _exit_codex, out_codex, _err_codex = run_scope_hook(json.dumps(codex_payload))

        self.assertEqual(out_claude, out_codex)
        decision = json.loads(out_claude)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "ask")

    def test_strict_agent_mode_attribution_identical_under_both_shapes(self) -> None:
        self._write_scope_config("strict-agent", agents={"dev": {"allow": ["src/"]}})
        for agent_type, expected in (("dev", "allow"), (None, "deny"), ("unknown-agent", "deny")):
            claude_payload = _claude_payload(
                "PreToolUse",
                cwd=str(self.project_dir),
                tool_name="Bash",
                tool_input={"command": "git status"},
            )
            codex_payload = _codex_payload(
                "PreToolUse",
                cwd=str(self.project_dir),
                tool_name="Bash",
                tool_input={"command": "git status"},
                tool_use_id="tu_2",
                turn_scoped=True,
            )
            if agent_type is not None:
                claude_payload["agent_type"] = agent_type
                codex_payload["agent_type"] = agent_type

            _exit_claude, out_claude, _err_claude = run_scope_hook(json.dumps(claude_payload))
            _exit_codex, out_codex, _err_codex = run_scope_hook(json.dumps(codex_payload))

            self.assertEqual(out_claude, out_codex, f"agent_type={agent_type!r}")
            decision = json.loads(out_claude)["hookSpecificOutput"]
            self.assertEqual(decision["permissionDecision"], expected, f"agent_type={agent_type!r}")

    def test_deny_structured_path_enforcement_identical_under_both_shapes(self) -> None:
        self._write_scope_config("deny-structured", agents={"dev": {"allow": ["src/"]}})
        for target, expected in (("src/main.py", "allow"), ("etc/passwd", "deny")):
            claude_payload = _claude_payload(
                "PreToolUse",
                cwd=str(self.project_dir),
                tool_name="Write",
                tool_input={"file_path": target},
                agent_type="dev",
            )
            codex_payload = _codex_payload(
                "PreToolUse",
                cwd=str(self.project_dir),
                tool_name="apply_patch",
                tool_input={"path": target},
                agent_type="dev",
                tool_use_id="tu_3",
                turn_scoped=True,
            )

            _exit_claude, out_claude, _err_claude = run_scope_hook(json.dumps(claude_payload))
            _exit_codex, out_codex, _err_codex = run_scope_hook(json.dumps(codex_payload))

            decision_claude = json.loads(out_claude)["hookSpecificOutput"]
            decision_codex = json.loads(out_codex)["hookSpecificOutput"]
            self.assertEqual(decision_claude["permissionDecision"], expected, target)
            self.assertEqual(decision_codex["permissionDecision"], expected, target)


class GoldenProtocolOutputTests(unittest.TestCase):
    """STORY-018 acceptance criterion: "Platform-specific protocol output
    has golden tests" -- pin the exact JSON shape `scripts/context.py` and
    `scripts/scope_policy.py` emit, for a Claude-shaped and a Codex-shaped
    payload alike, so an accidental future format change is caught.

    Both harnesses are documented (https://learn.chatgpt.com/docs/hooks,
    fetched 2026-09-17) to accept the exact same `hookSpecificOutput`
    envelope on stdout -- there is no per-platform branching in
    `scripts/context.py`/`scripts/scope_policy.py`'s response-building code,
    and these tests exist to catch it if that ever silently changes.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_dir = Path(self._tmp.name)

    def test_session_start_golden_shape(self) -> None:
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)
        payload = _codex_payload("SessionStart", source="startup", cwd=str(self.project_dir))
        _exit_code, out, _err = run_context_hook(json.dumps(payload))
        parsed = json.loads(out)
        self.assertEqual(set(parsed.keys()), {"hookSpecificOutput"})
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(set(inner.keys()), {"hookEventName", "additionalContext"})
        self.assertEqual(inner["hookEventName"], "SessionStart")
        self.assertIsInstance(inner["additionalContext"], str)

    def test_pretooluse_golden_shape(self) -> None:
        write_config(self.project_dir, scope={"mode": "ask", "agents": {}})
        payload = _codex_payload(
            "PreToolUse",
            cwd=str(self.project_dir),
            tool_name="Bash",
            tool_input={"command": "git push --force origin main"},
            tool_use_id="tu_1",
            turn_scoped=True,
        )
        _exit_code, out, _err = run_scope_hook(json.dumps(payload))
        parsed = json.loads(out)
        self.assertEqual(set(parsed.keys()), {"hookSpecificOutput"})
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(
            set(inner.keys()), {"hookEventName", "permissionDecision", "permissionDecisionReason"}
        )
        self.assertEqual(inner["hookEventName"], "PreToolUse")
        self.assertIn(inner["permissionDecision"], ("allow", "deny", "ask"))

    def test_stdout_is_exactly_one_json_line_for_both_hooks(self) -> None:
        write_config(self.project_dir, scope={"mode": "ask", "agents": {}})
        payload = _codex_payload(
            "PreToolUse",
            cwd=str(self.project_dir),
            tool_name="Bash",
            tool_input={"command": "git status"},
            tool_use_id="tu_1",
        )
        _exit_code, out, _err = run_scope_hook(json.dumps(payload))
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)


class NoClaudeOnlyEnvironmentDependencyTests(unittest.TestCase):
    """STORY-018 acceptance criterion: "No Claude-only path or environment
    variable is required by shared logic." `${CLAUDE_PLUGIN_ROOT}` only ever
    appears in `hooks/hooks.json`'s *command string* (how Claude Code locates
    the script file to invoke) and in `scripts/git_policy.py`'s
    installer-instruction text (documentation strings shown to a human, never
    read back) -- never as an `os.environ` read inside the request-handling
    code path itself. These tests prove `scripts/context.py` and
    `scripts/scope_policy.py`'s project-root resolution (and therefore every
    behavior derived from it) is identical with `CLAUDE_PLUGIN_ROOT` absent
    from the environment entirely, using only the payload's own `cwd` field
    -- the one mechanism both Claude Code and Codex document on every hook
    payload.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_dir = Path(self._tmp.name)
        write_config(self.project_dir)
        write_snapshot(self.project_dir, VALID_SNAPSHOT)

    def _without_claude_plugin_root(self):
        env = dict(os.environ)
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env.pop("CLAUDE_PLUGIN_DATA", None)
        env.pop("PLUGIN_ROOT", None)
        env.pop("PLUGIN_DATA", None)
        return mock.patch.dict(os.environ, env, clear=True)

    def test_session_start_resolves_project_root_from_cwd_field_alone(self) -> None:
        payload = _codex_payload("SessionStart", source="startup", cwd=str(self.project_dir))
        with self._without_claude_plugin_root():
            exit_code, out, err = run_context_hook(json.dumps(payload))
        self.assertEqual(exit_code, 0)
        self.assertIn("local:STORY-042", out)
        self.assertEqual(err, "")

    def test_scope_policy_resolves_project_root_from_cwd_field_alone(self) -> None:
        write_config(self.project_dir, scope={"mode": "ask", "agents": {}})
        payload = _codex_payload(
            "PreToolUse",
            cwd=str(self.project_dir),
            tool_name="Bash",
            tool_input={"command": "git push --force origin main"},
            tool_use_id="tu_1",
        )
        with self._without_claude_plugin_root():
            exit_code, out, _err = run_scope_hook(json.dumps(payload))
        self.assertEqual(exit_code, 0)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "ask")

    def test_neither_module_reads_a_claude_or_plugin_environment_variable(self) -> None:
        # Defense-in-depth static check alongside the behavioral tests
        # above: neither module's *executable* source (module docstrings
        # and comments deliberately excluded, since scripts/git_policy.py's
        # human-facing installer instructions legitimately mention
        # ${CLAUDE_PLUGIN_ROOT} as text shown to a person, not a value the
        # code reads) contains an `os.environ`/`os.getenv` lookup at all --
        # every path this story's shared logic needs comes from the hook
        # payload itself.
        for module in (context, scope_policy):
            source_path = Path(module.__file__)
            source = source_path.read_text(encoding="utf-8")
            code_lines = [
                line
                for line in source.splitlines()
                if not line.strip().startswith("#")
            ]
            code_only = "\n".join(code_lines)
            self.assertNotIn("os.environ", code_only, source_path)
            self.assertNotIn("os.getenv", code_only, source_path)


if __name__ == "__main__":
    unittest.main()
