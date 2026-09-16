"""AgentForge project configuration contract (STORY-004).

Validates the committed `.agentforge/config.json` policy file described in
`docs/agentforge-config.md`. This module has no third-party runtime
dependency (stdlib `json`/`re` only) and performs no network access or
filesystem writes.

Two call shapes, matching the STORY-004 requirement that "enforcement
callers must receive a hard validation failure" while "observation callers
may report a diagnostic and continue":

  - `load_for_enforcement(path)` raises `ConfigValidationError` on any
    parse or schema problem. Use this wherever an invalid config must stop
    the operation (e.g. a Git-hook policy check).
  - `load_for_observation(path)` never raises for a config problem; it
    returns `(None, issues)` so the caller can log the diagnostics and
    proceed (e.g. with `DEFAULT_CONFIG` or simply skipped behavior).

Forward-compatibility policy: this is a *closed* schema. Every field name
at every level must be one this module recognizes; an unrecognized field
is a validation issue, not silently ignored or passed through. Schema
evolution happens by bumping `schema_version` and updating
`SUPPORTED_SCHEMA_VERSIONS`/the validators together, not by accepting
fields an older validator does not understand. See
`docs/agentforge-config.md` for the rationale.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

DEFAULT_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = (1,)

TRACKER_TYPES = ("github", "gitlab", "local")

# Traceability, scope, and quality each grade a different axis of
# enforcement (commit/push policy, structured-write policy, post-edit
# reporting) and are deliberately three separate enums, not one shared
# "policy mode" type — the execution plan's grading table assigns each
# axis its own distinct set of valid modes (ADR-0004).
TRACEABILITY_MODES = ("off", "observe", "enforce")
SCOPE_MODES = ("off", "observe", "ask", "deny-structured", "strict-agent")
QUALITY_POST_EDIT_MODES = ("off", "report")

# Generous but bounded ceiling for context injected into a hook response
# (STORY-009). Not a tuning knob for large payloads; a config asking for
# more than this is almost certainly a mistake.
MAX_CONTEXT_BYTES_CEILING = 65536

TOP_LEVEL_KEYS = {
    "schema_version",
    "tracker",
    "identifier",
    "context",
    "traceability",
    "scope",
    "migration_policy",
    "quality",
}

# Fully non-destructive out of the box: every policy mode is "off", so
# installing AgentForge's config never silently enables blocking or
# mutating behavior (STORY-004 acceptance criteria).
DEFAULT_CONFIG: dict = {
    "schema_version": DEFAULT_SCHEMA_VERSION,
    "tracker": {
        "type": "local",
        "local_root": "docs/work-items",
    },
    "identifier": {
        "pattern": "^STORY-\\d{3,}$",
        "examples": ["STORY-001", "STORY-042"],
    },
    "context": {
        "max_bytes": 8000,
    },
    "traceability": {
        "mode": "off",
    },
    "scope": {
        "mode": "off",
        "agents": {},
    },
    "migration_policy": {
        "enabled": False,
    },
    "quality": {
        "post_edit": "off",
    },
}

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class ConfigIssue:
    """One validation problem, anchored to a dotted config field path.

    `value` is the offending value from the config file itself (a small
    JSON scalar/short string) — never environment or filesystem data
    outside the config being validated.
    """

    path: str
    message: str
    value: Any = None

    def format(self) -> str:
        if self.value is None:
            return f"{self.path}: {self.message}"
        return f"{self.path}: {self.message} (got: {self.value!r})"


class ConfigValidationError(Exception):
    """Raised by enforcement callers when a config fails validation."""

    def __init__(self, issues: list[ConfigIssue]):
        self.issues = list(issues)
        super().__init__("; ".join(issue.format() for issue in self.issues))


def _relative_path_issue(value: Any) -> Optional[str]:
    """Return a reason `value` is unsafe as a relative project path, or
    None if it is fine. Never uses str.lstrip("./") (the v1 dotfile bug
    characterized in tests/test_v1_characterization.py) — a leading dot
    component is preserved and only exact ".." components are rejected."""
    if not isinstance(value, str):
        return "must be a string"
    if value == "":
        return "must not be empty"
    if value.startswith("/") or value.startswith("\\"):
        return "must be a relative path (absolute paths are not allowed)"
    if _WINDOWS_DRIVE_RE.match(value):
        return "must be a relative path (Windows drive-letter paths are not allowed)"
    if value.startswith("~"):
        return "must be a relative path (home-directory expansion is not allowed)"
    parts = re.split(r"[\\/]+", value)
    if any(part == ".." for part in parts):
        return "must not contain '..' path traversal components"
    return None


def _check_unknown_keys(
    obj: dict, allowed: set, path_prefix: str, issues: list[ConfigIssue]
) -> None:
    for key in obj.keys():
        if key not in allowed:
            path = f"{path_prefix}.{key}" if path_prefix else str(key)
            issues.append(
                ConfigIssue(
                    path,
                    "unknown field is not permitted under the closed-schema "
                    "forward-compatibility policy (see docs/agentforge-config.md)",
                )
            )


def _get_section(data: dict, key: str, issues: list[ConfigIssue]) -> Optional[dict]:
    if key not in data:
        issues.append(ConfigIssue(key, "is required"))
        return None
    value = data[key]
    if not isinstance(value, dict):
        issues.append(ConfigIssue(key, "must be an object", value=value))
        return None
    return value


def _validate_tracker(section: dict, issues: list[ConfigIssue]) -> None:
    _check_unknown_keys(section, {"type", "repository", "local_root"}, "tracker", issues)

    if "type" not in section:
        issues.append(ConfigIssue("tracker.type", "is required"))
        return
    tracker_type = section["type"]
    if tracker_type not in TRACKER_TYPES:
        issues.append(
            ConfigIssue("tracker.type", f"must be one of {TRACKER_TYPES}", value=tracker_type)
        )
        return

    if tracker_type in ("github", "gitlab"):
        if "local_root" in section:
            issues.append(
                ConfigIssue(
                    "tracker.local_root",
                    f"is not allowed when tracker.type is {tracker_type!r}",
                    value=section["local_root"],
                )
            )
        if "repository" not in section:
            issues.append(
                ConfigIssue(
                    "tracker.repository",
                    "is required when tracker.type is 'github' or 'gitlab'",
                )
            )
        else:
            repo = section["repository"]
            if not isinstance(repo, str) or not _REPO_PATTERN.match(repo):
                issues.append(
                    ConfigIssue("tracker.repository", "must look like 'owner/repo'", value=repo)
                )
    else:  # local
        if "repository" in section:
            issues.append(
                ConfigIssue(
                    "tracker.repository",
                    "is not allowed when tracker.type is 'local'",
                    value=section["repository"],
                )
            )
        if "local_root" not in section:
            issues.append(
                ConfigIssue("tracker.local_root", "is required when tracker.type is 'local'")
            )
        else:
            reason = _relative_path_issue(section["local_root"])
            if reason:
                issues.append(
                    ConfigIssue("tracker.local_root", reason, value=section["local_root"])
                )


def _validate_identifier(section: dict, issues: list[ConfigIssue]) -> None:
    _check_unknown_keys(section, {"pattern", "examples"}, "identifier", issues)

    compiled = None
    if "pattern" not in section:
        issues.append(ConfigIssue("identifier.pattern", "is required"))
    else:
        pattern = section["pattern"]
        if not isinstance(pattern, str) or not pattern:
            issues.append(
                ConfigIssue("identifier.pattern", "must be a non-empty string", value=pattern)
            )
        else:
            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                issues.append(
                    ConfigIssue(
                        "identifier.pattern",
                        f"is not a valid regular expression: {exc}",
                        value=pattern,
                    )
                )

    if "examples" not in section:
        issues.append(ConfigIssue("identifier.examples", "is required"))
        return
    examples = section["examples"]
    if not isinstance(examples, list) or not examples:
        issues.append(
            ConfigIssue(
                "identifier.examples", "must be a non-empty array of strings", value=examples
            )
        )
        return
    for i, example in enumerate(examples):
        path = f"identifier.examples[{i}]"
        if not isinstance(example, str):
            issues.append(ConfigIssue(path, "must be a string", value=example))
        elif compiled is not None and not compiled.fullmatch(example):
            issues.append(ConfigIssue(path, "does not match identifier.pattern", value=example))


def _validate_context(section: dict, issues: list[ConfigIssue]) -> None:
    _check_unknown_keys(section, {"max_bytes"}, "context", issues)

    if "max_bytes" not in section:
        issues.append(ConfigIssue("context.max_bytes", "is required"))
        return
    value = section["max_bytes"]
    if isinstance(value, bool) or not isinstance(value, int):
        issues.append(ConfigIssue("context.max_bytes", "must be an integer", value=value))
    elif value <= 0:
        issues.append(ConfigIssue("context.max_bytes", "must be greater than 0", value=value))
    elif value > MAX_CONTEXT_BYTES_CEILING:
        issues.append(
            ConfigIssue(
                "context.max_bytes",
                f"must not exceed {MAX_CONTEXT_BYTES_CEILING}",
                value=value,
            )
        )


def _validate_enum_field(
    section: dict,
    key: str,
    allowed: tuple,
    section_path: str,
    issues: list[ConfigIssue],
) -> None:
    if key not in section:
        issues.append(ConfigIssue(f"{section_path}.{key}", "is required"))
        return
    value = section[key]
    if value not in allowed:
        issues.append(
            ConfigIssue(f"{section_path}.{key}", f"must be one of {allowed}", value=value)
        )


def _validate_traceability(section: dict, issues: list[ConfigIssue]) -> None:
    _check_unknown_keys(section, {"mode"}, "traceability", issues)
    _validate_enum_field(section, "mode", TRACEABILITY_MODES, "traceability", issues)


def _validate_quality(section: dict, issues: list[ConfigIssue]) -> None:
    _check_unknown_keys(section, {"post_edit"}, "quality", issues)
    _validate_enum_field(section, "post_edit", QUALITY_POST_EDIT_MODES, "quality", issues)


def _validate_scope(section: dict, issues: list[ConfigIssue]) -> None:
    _check_unknown_keys(section, {"mode", "agents"}, "scope", issues)
    _validate_enum_field(section, "mode", SCOPE_MODES, "scope", issues)

    if "agents" not in section:
        issues.append(ConfigIssue("scope.agents", "is required"))
        return
    agents = section["agents"]
    if not isinstance(agents, dict):
        issues.append(
            ConfigIssue(
                "scope.agents",
                "must be an object mapping agent name to its allow-list",
                value=agents,
            )
        )
        return

    for name, agent_cfg in agents.items():
        agent_path = f"scope.agents.{name}"
        if not isinstance(name, str) or not _AGENT_NAME_PATTERN.match(name):
            issues.append(
                ConfigIssue(
                    agent_path,
                    "agent name must match ^[A-Za-z][A-Za-z0-9_-]*$",
                    value=name,
                )
            )
        if not isinstance(agent_cfg, dict):
            issues.append(ConfigIssue(agent_path, "must be an object", value=agent_cfg))
            continue
        _check_unknown_keys(agent_cfg, {"allow"}, agent_path, issues)
        if "allow" not in agent_cfg:
            issues.append(ConfigIssue(f"{agent_path}.allow", "is required"))
            continue
        allow = agent_cfg["allow"]
        if not isinstance(allow, list):
            issues.append(
                ConfigIssue(
                    f"{agent_path}.allow", "must be an array of relative paths", value=allow
                )
            )
            continue
        for i, entry in enumerate(allow):
            reason = _relative_path_issue(entry)
            if reason:
                issues.append(ConfigIssue(f"{agent_path}.allow[{i}]", reason, value=entry))


def _validate_migration_policy(section: dict, issues: list[ConfigIssue]) -> None:
    _check_unknown_keys(section, {"enabled"}, "migration_policy", issues)
    if "enabled" not in section:
        issues.append(ConfigIssue("migration_policy.enabled", "is required"))
        return
    if not isinstance(section["enabled"], bool):
        issues.append(
            ConfigIssue(
                "migration_policy.enabled", "must be a boolean", value=section["enabled"]
            )
        )


def validate_config(data: Any) -> list[ConfigIssue]:
    """Validate a parsed config object. Pure function: never raises for a
    data-shape problem, always returns the full list of issues found (not
    just the first one) so a single run reports every offending field."""
    issues: list[ConfigIssue] = []

    if not isinstance(data, dict):
        issues.append(ConfigIssue("<root>", "configuration must be a JSON object", value=data))
        return issues

    _check_unknown_keys(data, TOP_LEVEL_KEYS, "", issues)

    if "schema_version" not in data:
        issues.append(ConfigIssue("schema_version", "is required"))
    else:
        version = data["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int):
            issues.append(ConfigIssue("schema_version", "must be an integer", value=version))
        elif version not in SUPPORTED_SCHEMA_VERSIONS:
            issues.append(
                ConfigIssue(
                    "schema_version",
                    f"is not a supported schema version (supported: {SUPPORTED_SCHEMA_VERSIONS})",
                    value=version,
                )
            )

    section = _get_section(data, "tracker", issues)
    if section is not None:
        _validate_tracker(section, issues)

    section = _get_section(data, "identifier", issues)
    if section is not None:
        _validate_identifier(section, issues)

    section = _get_section(data, "context", issues)
    if section is not None:
        _validate_context(section, issues)

    section = _get_section(data, "traceability", issues)
    if section is not None:
        _validate_traceability(section, issues)

    section = _get_section(data, "scope", issues)
    if section is not None:
        _validate_scope(section, issues)

    section = _get_section(data, "migration_policy", issues)
    if section is not None:
        _validate_migration_policy(section, issues)

    section = _get_section(data, "quality", issues)
    if section is not None:
        _validate_quality(section, issues)

    return issues


def parse_config_text(text: str) -> tuple[Optional[Any], list[ConfigIssue]]:
    """Parse JSON text. Malformed JSON becomes a ConfigIssue instead of a
    raw exception, so both loading paths below can treat it uniformly."""
    try:
        return json.loads(text), []
    except json.JSONDecodeError as exc:
        return None, [
            ConfigIssue(
                "<root>",
                f"invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}",
            )
        ]


def load_for_enforcement(path: Path) -> dict:
    """Enforcement callers: raise ConfigValidationError on any parse or
    schema problem. Returns the validated config dict on success."""
    text = Path(path).read_text(encoding="utf-8")
    data, issues = parse_config_text(text)
    if issues:
        raise ConfigValidationError(issues)
    issues = validate_config(data)
    if issues:
        raise ConfigValidationError(issues)
    return data


def load_for_observation(path: Path) -> tuple[Optional[dict], list[ConfigIssue]]:
    """Observation callers: never raise for a config problem. Returns
    (config, []) on success or (None, issues) so the caller can report the
    diagnostic and continue (e.g. with DEFAULT_CONFIG)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return None, [ConfigIssue(str(path), f"cannot read config file: {exc.strerror or exc}")]

    data, issues = parse_config_text(text)
    if issues:
        return None, issues
    issues = validate_config(data)
    if issues:
        return None, issues
    return data, []


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="config.py", description="Validate an AgentForge project configuration file."
    )
    parser.add_argument("config_path", type=Path)
    parser.add_argument(
        "--mode",
        choices=("enforce", "observe"),
        default="enforce",
        help="enforce: hard-fail (exit 1) on any issue. observe: report and always exit 0.",
    )
    args = parser.parse_args(argv)

    if args.mode == "enforce":
        try:
            load_for_enforcement(args.config_path)
        except ConfigValidationError as exc:
            for issue in exc.issues:
                print(issue.format(), file=sys.stderr)
            return 1
        return 0

    _, issues = load_for_observation(args.config_path)
    for issue in issues:
        print(issue.format(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
