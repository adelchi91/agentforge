"""AgentForge v1 -> v2 project migration (STORY-019).

Migrates an existing AgentForge v1 (`project-bootstrap`) generated project
toward the v2 architecture described in
`docs/plans/agentforge-v2-execution-plan.md`, without ever deleting a v1
file outright. This module has the same three responsibilities as
`scripts/setup.py` (STORY-005) and reuses that module's tested
constitution-block insertion logic directly (`setup._plan_block_change`)
rather than re-implementing it:

  - **Detection** (`detect_v1`): find every v1 Claude/Codex/mixed artifact
    a project may have, tolerating a partial ("interrupted bootstrap")
    scaffold and recognizing an already-v2 project as nothing to do.
  - **Planning** (`plan_migration`): classify every detected artifact into
    exactly one of five buckets -- `retained`, `transformed`, `archived`,
    `manual_review`, `obsolete` -- and compute the exact file operations
    (create/update/move) migrating it would perform, without writing
    anything. Every classification decision this module makes is
    documented inline at the point it is made; see
    `docs/migration-v1-to-v2.md` for the full mapping table and the
    judgment calls behind it.
  - **Application** (`apply_migration`) and **rollback**
    (`rollback_migration`): the same plan/apply approval-binding shape
    `scripts/setup.py` and `scripts/active_state.py` already use --
    `apply_migration` recomputes the plan immediately before writing and
    refuses a stale approval -- plus a manifest-driven rollback that
    restores every modified/created/moved file to its exact pre-migration
    state.

Non-negotiable safety properties (STORY-019's central risk is irreversible
data loss):

  1. **Nothing is ever deleted.** A v1 file that is superseded is moved
     into a timestamped archive directory
     (`.agentforge/migration-archive/<timestamp>/...`), never removed.
  2. **`plan_migration` never writes to disk** -- this is what makes
     `--dry-run` a zero-filesystem-change guarantee by construction, the
     same guarantee `scripts/setup.py::plan_setup` already provides.
  3. **Every detected v1 artifact appears in the report** with exactly one
     category. Nothing is silently dropped.
  4. **v1 hooks are only disabled once `v2_hooks_validated=True` is
     passed** (the caller's job -- `skills/migrate-v1/SKILL.md` -- is to
     confirm the AgentForge plugin itself is installed/enabled before
     setting this). Until then, hook-registration changes are computed and
     reported but deferred (action `"deferred"`, nothing written), so a
     project is never left with neither the old nor the new hook active.
  5. **A destructive-sounding v1 claim is never carried forward silently.**
     Any detected v1 `pre_tool_use.py` + `scopes.json` pair (the shared v1
     hook template characterized in `tests/test_v1_characterization.py`)
     always produces an explicit warning that its Bash/scope enforcement
     was never a real security boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from . import config as config_module  # imported as scripts.migrate_v1 (e.g. tests)
    from . import setup as setup_module
except ImportError:
    import config as config_module  # executed directly: python3 scripts/migrate_v1.py
    import setup as setup_module

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CATEGORY_RETAINED = "retained"
CATEGORY_TRANSFORMED = "transformed"
CATEGORY_ARCHIVED = "archived"
CATEGORY_MANUAL_REVIEW = "manual_review"
CATEGORY_OBSOLETE = "obsolete"
CATEGORIES = (
    CATEGORY_RETAINED,
    CATEGORY_TRANSFORMED,
    CATEGORY_ARCHIVED,
    CATEGORY_MANUAL_REVIEW,
    CATEGORY_OBSOLETE,
)

ACTION_NONE = "none"
ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_MOVE = "move"
ACTION_DEFERRED = "deferred"

MIGRATED_CONSTRAINTS_START = "<!-- agentforge:migrated-v1-constraints:start -->"
MIGRATED_CONSTRAINTS_END = "<!-- agentforge:migrated-v1-constraints:end -->"

_SECTION_HEADING_RE = re.compile(r"(?m)^##[ \t]+(.+?)[ \t]*$")
_STORY_HEADING_RE = re.compile(r"^#\s+(STORY-\d{3,})\s*(?:—|-{1,2})\s*(.*)$")
# v1's story/constitution header block uses a *different* convention from
# its body sections: "## Label: Value" is one single-line field (the
# value is on the same line as the heading, not a separate body below
# it) -- "## Status: DONE", "## Agent: dev (model: sonnet)", "## Depends
# on: STORY-002 approved and merged". A real body-section heading
# ("## Context", "## Scope", ...) never contains a colon, so this pattern
# never collides with `_SECTION_HEADING_RE`'s heading+body extraction.
_HEADER_FIELD_RE = re.compile(r"(?m)^##[ \t]+([A-Za-z][A-Za-z ]*?):[ \t]*(.*?)[ \t]*$")
_STORY_TOKEN_RE = re.compile(r"STORY-\d{3,}")
_BULLET_OR_LINE_RE = re.compile(r"^[-*][ \t]+(.*)$")

ARCHIVE_ROOT_PARTS = (".agentforge", "migration-archive")
MANIFEST_FILENAME = "manifest.json"


def _parse_v1_header_fields(text: str) -> dict:
    fields: dict = {}
    for match in _HEADER_FIELD_RE.finditer(text):
        fields[match.group(1).strip().lower()] = match.group(2).strip()
    return fields


def _now_timestamp() -> str:
    # Microsecond precision (not just seconds) so two migrations applied
    # in quick succession -- e.g. the ordinary "migrate, then re-run once
    # v2 hooks are validated" flow -- never collide on the same archive
    # directory.
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class V1Detection:
    root: Path
    has_claude: bool
    has_codex: bool
    already_v2: bool
    claude_constitution: Optional[Path]  # .claude/CLAUDE.md
    codex_constitution: Optional[Path]  # AGENTS.md at root, Codex-authored
    claude_settings: Optional[Path]  # .claude/settings.json
    codex_hooks_json: Optional[Path]  # .codex/hooks.json
    claude_hook_files: tuple  # .claude/hooks/*.py
    codex_hook_files: tuple  # .codex/hooks/*.py
    claude_scopes: Optional[Path]  # .claude/hooks/scopes.json
    codex_scopes: Optional[Path]  # .codex/hooks/scopes.json
    claude_stories: tuple  # .claude/stories/STORY-*.md
    codex_stories: tuple  # .agents/stories/STORY-*.md
    claude_agents: tuple  # .claude/agents/*.md
    codex_agents: tuple  # .codex/agents/*.toml
    claude_skills: tuple  # .claude/skills/*/SKILL.md
    codex_skills: tuple  # .agents/skills/*/SKILL.md
    session_log: Optional[Path]  # .claude/session-log.txt (write-only v1 log)
    project_context: Optional[Path]
    roadmap: Optional[Path]

    @property
    def is_mixed(self) -> bool:
        return self.has_claude and self.has_codex

    @property
    def has_any_v1(self) -> bool:
        return bool(
            self.claude_constitution
            or self.codex_constitution
            or self.claude_settings
            or self.codex_hooks_json
            or self.claude_hook_files
            or self.codex_hook_files
            or self.claude_stories
            or self.codex_stories
            or self.claude_agents
            or self.codex_agents
        )


def _glob_files(directory: Path, pattern: str) -> tuple:
    if not directory.is_dir():
        return ()
    return tuple(sorted(p for p in directory.glob(pattern) if p.is_file()))


def _codex_authored_agents_md(root: Path) -> Optional[Path]:
    """Root `AGENTS.md` counts as a v1 *Codex* constitution only when a
    `.codex/` directory sits alongside it -- an `AGENTS.md` with no
    `.codex/` at all is just an ordinary (non-AgentForge) project file and
    must never be treated as a v1 artifact to migrate."""
    agents_path = root / "AGENTS.md"
    if agents_path.is_file() and (root / ".codex").is_dir():
        return agents_path
    return None


def detect_v1(project_root: Path) -> V1Detection:
    root = Path(project_root)
    claude_dir = root / ".claude"
    codex_dir = root / ".codex"

    claude_constitution = claude_dir / "CLAUDE.md"
    if not claude_constitution.is_file():
        claude_constitution = None

    codex_constitution = _codex_authored_agents_md(root)

    claude_settings = claude_dir / "settings.json"
    if not claude_settings.is_file():
        claude_settings = None

    codex_hooks_json = codex_dir / "hooks.json"
    if not codex_hooks_json.is_file():
        codex_hooks_json = None

    claude_hook_files = _glob_files(claude_dir / "hooks", "*.py")
    codex_hook_files = _glob_files(codex_dir / "hooks", "*.py")

    claude_scopes = claude_dir / "hooks" / "scopes.json"
    claude_scopes = claude_scopes if claude_scopes.is_file() else None
    codex_scopes = codex_dir / "hooks" / "scopes.json"
    codex_scopes = codex_scopes if codex_scopes.is_file() else None

    claude_stories = _glob_files(claude_dir / "stories", "STORY-*.md")
    codex_stories = _glob_files(root / ".agents" / "stories", "STORY-*.md")

    claude_agents = _glob_files(claude_dir / "agents", "*.md")
    codex_agents = _glob_files(codex_dir / "agents", "*.toml")

    claude_skills = tuple(
        sorted((claude_dir / "skills").glob("*/SKILL.md"))
    ) if (claude_dir / "skills").is_dir() else ()
    codex_skills = tuple(
        sorted((root / ".agents" / "skills").glob("*/SKILL.md"))
    ) if (root / ".agents" / "skills").is_dir() else ()

    session_log = claude_dir / "session-log.txt"
    session_log = session_log if session_log.is_file() else None

    project_context = root / "project_context.md"
    project_context = project_context if project_context.is_file() else None
    roadmap = root / "roadmap.md"
    roadmap = roadmap if roadmap.is_file() else None

    config_path = root / ".agentforge" / "config.json"
    already_v2 = False
    if config_path.is_file():
        try:
            config_module.load_for_enforcement(config_path)
            already_v2 = True
        except (config_module.ConfigValidationError, OSError):
            already_v2 = False

    return V1Detection(
        root=root,
        has_claude=bool(
            claude_constitution
            or claude_settings
            or claude_hook_files
            or claude_stories
            or claude_agents
            or claude_skills
        ),
        has_codex=bool(
            codex_constitution
            or codex_hooks_json
            or codex_hook_files
            or codex_stories
            or codex_agents
            or codex_skills
        ),
        already_v2=already_v2,
        claude_constitution=claude_constitution,
        codex_constitution=codex_constitution,
        claude_settings=claude_settings,
        codex_hooks_json=codex_hooks_json,
        claude_hook_files=claude_hook_files,
        codex_hook_files=codex_hook_files,
        claude_scopes=claude_scopes,
        codex_scopes=codex_scopes,
        claude_stories=claude_stories,
        codex_stories=codex_stories,
        claude_agents=claude_agents,
        codex_agents=codex_agents,
        claude_skills=claude_skills,
        codex_skills=codex_skills,
        session_log=session_log,
        project_context=project_context,
        roadmap=roadmap,
    )


# ---------------------------------------------------------------------------
# Report / operation records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MigrationItem:
    """One row of the migration report. Every detected v1 artifact gets
    exactly one of these -- this is the "never silently drop something
    into a bucket without it appearing in the report" contract."""

    path: str
    category: str
    action: str
    target: Optional[str]
    reason: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "category": self.category,
            "action": self.action,
            "target": self.target,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FileOp:
    """One concrete filesystem operation `apply_migration` performs.
    `kind` is `"write"` (create or update `path` with `content`) or
    `"move"` (rename `src` to `dest`, both project-relative -- used to
    send a superseded v1 file into the archive)."""

    kind: str
    path: Optional[str] = None
    content: Optional[bytes] = None
    existed_before: Optional[bool] = None
    before_content: Optional[bytes] = None
    src: Optional[str] = None
    dest: Optional[str] = None


# ---------------------------------------------------------------------------
# Small Markdown helpers (story parsing)
# ---------------------------------------------------------------------------


def _parse_v1_sections(text: str) -> dict:
    """Split a v1 CLAUDE.md/AGENTS.md/STORY body into {lowercased heading:
    content}, using the same `^##[ \\t]+heading$` convention
    `scripts/active_state.py::parse_sections` already relies on for v2
    ticket bodies -- v1's own generated Markdown uses the identical
    convention for both its constitution files and its story files."""
    sections: dict = {}
    matches = list(_SECTION_HEADING_RE.finditer(text))
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end]
        # Strip a lone horizontal-rule line ("---") v1's template inserts
        # between sections; it carries no content of its own.
        lines = [line for line in content.split("\n") if line.strip() != "---"]
        sections[heading.lower()] = "\n".join(lines).strip("\n").strip()
    return sections


def _extract_bullets(text: Optional[str]) -> list:
    if not text:
        return []
    items = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            if line:
                items.append(line)
            continue
        match = _BULLET_OR_LINE_RE.match(line)
        if match:
            items.append(match.group(1).strip())
    return items


def _split_scope_block(content: Optional[str]) -> tuple:
    """Split a v1 story's `## Scope` content into (may_touch_text,
    must_not_touch_text) using the `**May touch:**` / `**Must NOT
    touch:**` sub-headers v1's story template always uses."""
    if not content:
        return "", ""
    match = re.search(
        r"\*\*May touch:?\*\*(.*?)(?:\*\*Must NOT touch:?\*\*(.*))?$",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return content.strip(), ""
    may_touch = (match.group(1) or "").strip()
    must_not_touch = (match.group(2) or "").strip()
    return may_touch, must_not_touch


def _render_bullets(items: list) -> str:
    if not items:
        return "None."
    return "\n".join(f"- {item}" for item in items)


@dataclass(frozen=True)
class ParsedV1Story:
    story_id: str
    title: str
    status: str
    depends_on: str
    what_to_build: str
    acceptance_criteria: str
    may_touch: list
    must_not_touch: list
    verification_commands: str
    out_of_scope: str


def parse_v1_story(text: str) -> Optional[ParsedV1Story]:
    """Parse a v1 story file's structured fields. Returns None if the file
    does not even carry a recognizable `# STORY-XXX — Title` heading (an
    unrecognizable file is reported as `manual_review`, never guessed
    at)."""
    lines = text.splitlines()
    story_id, title = None, ""
    for line in lines:
        match = _STORY_HEADING_RE.match(line.strip())
        if match:
            story_id, title = match.group(1), match.group(2).strip()
            break
    if story_id is None:
        return None

    sections = _parse_v1_sections(text)
    header_fields = _parse_v1_header_fields(text)
    may_touch_text, must_not_touch_text = _split_scope_block(sections.get("scope"))

    return ParsedV1Story(
        story_id=story_id,
        title=title,
        status=header_fields.get("status", "").strip(),
        depends_on=header_fields.get("depends on", "").strip(),
        what_to_build=sections.get("context", "").strip(),
        acceptance_criteria=sections.get("acceptance criteria", "").strip(),
        may_touch=_extract_bullets(may_touch_text),
        must_not_touch=_extract_bullets(must_not_touch_text),
        verification_commands=sections.get("verification commands", "").strip(),
        out_of_scope=sections.get("out of scope", "").strip(),
    )


def _render_blocked_by(depends_on: str) -> tuple:
    """Return (rendered_body_text, blockers_front_matter_value).
    A recognizable `STORY-XXX` token becomes a canonical `local:STORY-XXX`
    reference (matching how the `local` tracker adapter already names
    things); anything else is carried through as literal, clearly-labeled
    text rather than silently dropped or guessed at."""
    value = (depends_on or "").strip()
    if not value or value.lower() in ("none", "n/a", "na"):
        return "None", ""
    tokens = _STORY_TOKEN_RE.findall(value)
    if tokens:
        canonical = [f"local:{tok}" for tok in tokens]
        rendered = "\n".join(f"- {c}" for c in canonical)
        if value not in tokens:
            rendered += f"\n\n(migrated from v1 \"Depends on: {value}\")"
        return rendered, ", ".join(canonical)
    return f"(migrated from v1, unverified reference) {value}", ""


def render_local_work_item(
    parsed: ParsedV1Story, source_path: str, agent_field: str
) -> str:
    """Render a v2 local work-item Markdown file from a parsed v1 story,
    following `templates/local-work-item.md`'s exact section order and
    headings. `migrated_from`/`migrated_v1_agent` are extra front-matter
    fields the local tracker's parser (`scripts/work_items.py::
    _parse_local_markdown`) tolerates harmlessly (it only reads
    `state`/`blockers`/`updated_at` structurally) -- this is how the v1
    story's original identity is preserved in the new item's metadata."""
    state = "done" if "done" in parsed.status.lower() else "draft"
    blocked_by_body, blockers_value = _render_blocked_by(parsed.depends_on)

    what_to_build = parsed.what_to_build or f"(migrated from v1; no Context section found in {source_path})"
    acceptance = parsed.acceptance_criteria or "(migrated from v1; no Acceptance Criteria section found)"
    verification = parsed.verification_commands or (
        "No automated verification was recorded in the v1 story. Re-validate manually before "
        "trusting this item's status."
    )
    out_of_scope = parsed.out_of_scope or "None recorded in the v1 story."
    completion = (
        "Migrated from v1 with Status: DONE — original verification evidence was not "
        "re-captured by the migration; re-verify before trusting this as fresh completion "
        "evidence."
        if state == "done"
        else "Pending — filled in after execution."
    )

    lines = [
        "---",
        "state: draft" if state != "done" else "state: done",
        f"blockers: {blockers_value}",
        "updated_at:",
        f"migrated_from: {source_path}",
        f"migrated_v1_agent: {agent_field}" if agent_field else "migrated_v1_agent:",
        "---",
        f"# {parsed.story_id} — {parsed.title}",
        "",
        "## What to build",
        "",
        what_to_build,
        "",
        "## Blocked by",
        "",
        blocked_by_body,
        "",
        "## Acceptance criteria",
        "",
        acceptance,
        "",
        "## May touch",
        "",
        _render_bullets(parsed.may_touch),
        "",
        "## Must not touch",
        "",
        _render_bullets(parsed.must_not_touch),
        "",
        "## Verification commands",
        "",
        verification,
        "",
        "## Out of scope",
        "",
        out_of_scope,
        "",
        "## Completion evidence",
        "",
        completion,
        "",
    ]
    return "\n".join(lines)


def _extract_v1_agent_field(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## agent:"):
            return stripped.split(":", 1)[1].strip()
    return ""


# ---------------------------------------------------------------------------
# Constitution planning
# ---------------------------------------------------------------------------


def _extract_golden_rule_and_constraints(text: str) -> Optional[str]:
    sections = _parse_v1_sections(text)
    golden_rule = sections.get("golden rule", "").strip()
    hard_constraints = sections.get("hard constraints", "").strip()
    if not golden_rule and not hard_constraints:
        return None
    parts = []
    if golden_rule:
        parts.append(f"### Golden Rule (v1)\n\n{golden_rule}")
    if hard_constraints:
        parts.append(f"### Hard Constraints (v1)\n\n{hard_constraints}")
    return "\n\n".join(parts)


def _insert_marked_block(text: str, start: str, end: str, rendered: str) -> tuple:
    """Insert-or-replace-in-place a `start`/`end`-delimited block,
    appending it (with a blank-line separator) when absent. Mirrors
    `scripts.setup.find_agentforge_block`'s single-well-formed-pair
    contract for a distinct marker pair, so the migration's own
    "extracted v1 constraints" block never collides with -- or is
    scanned for by -- `scripts/setup.py`'s AgentForge-block logic."""
    starts = [m.start() for m in re.finditer(re.escape(start), text)]
    ends = [m.start() for m in re.finditer(re.escape(end), text)]
    block = f"{start}\n{rendered}\n{end}"

    if len(starts) == 1 and len(ends) == 1 and starts[0] < ends[0]:
        span_start, span_end = starts[0], ends[0] + len(end)
        existing = text[span_start:span_end]
        if existing == block:
            return text, False
        return text[:span_start] + block + text[span_end:], True

    separator = "" if (not text or text.endswith("\n")) else "\n"
    if text and not text.endswith("\n\n"):
        separator += "\n"
    return text + separator + block + "\n", True


def plan_constitution_item(
    detection: V1Detection,
) -> tuple:
    """Plan the constitution transformation. Returns
    (items: list[MigrationItem], ops: list[FileOp], warnings: list[str]).

    Handles the Codex side (v1 `AGENTS.md`) and the Claude side (v1
    `.claude/CLAUDE.md`) independently and unconditionally -- a mixed
    scaffold can have both at once, and every detected constitution
    artifact must appear in the report regardless of what the other one
    is doing (never an early return that silently skips one side):

      - v1 Codex `AGENTS.md` (already at the v2 location): add the
        standard AgentForge block in place via
        `setup._plan_block_change`; no archiving, no extracted-constraints
        block (nothing is being relocated away from another file).
      - v1 Claude `.claude/CLAUDE.md`, no root CLAUDE.md/AGENTS.md yet:
        the v1 file's full content becomes the new root CLAUDE.md, with
        the AgentForge block appended and an extracted-constraints block
        (Golden Rule/Hard Constraints, verbatim) appended after it; the
        original nested file is archived.
      - A root constitution file already exists (whether because a v1
        Codex `AGENTS.md` sits there, or a human created one by hand) at
        the same time as a nested `.claude/CLAUDE.md`: refuse to guess
        which is authoritative -- `manual_review`, nothing touched for
        the Claude side.
    """
    root = detection.root
    items: list = []
    ops: list = []
    warnings: list = []

    root_claude = root / "CLAUDE.md"
    root_agents = root / "AGENTS.md"

    if detection.codex_constitution is not None:
        # Already at the correct v2 location.
        original_text = _read_text(detection.codex_constitution)
        change = setup_module._plan_block_change("AGENTS.md", original_text, exists=True)
        if change.action == "none":
            items.append(
                MigrationItem(
                    "AGENTS.md", CATEGORY_TRANSFORMED, ACTION_NONE, "AGENTS.md",
                    "AgentForge managed block already present and up to date.",
                )
            )
        else:
            items.append(
                MigrationItem(
                    "AGENTS.md", CATEGORY_TRANSFORMED, ACTION_UPDATE, "AGENTS.md",
                    "Adding the AgentForge managed pointer block; all existing prose "
                    "(including v1's Golden Rule/Hard Constraints/Codex Workflow Rules) "
                    "is preserved unchanged.",
                )
            )
            ops.append(
                FileOp(
                    "write",
                    path="AGENTS.md",
                    content=change.after.encode("utf-8"),
                    existed_before=True,
                    before_content=original_text.encode("utf-8"),
                )
            )
        if "codex workflow rules" in original_text.lower():
            items.append(
                MigrationItem(
                    "AGENTS.md#Codex Workflow Rules",
                    CATEGORY_MANUAL_REVIEW,
                    ACTION_NONE,
                    None,
                    "This section describes v1's checkpoint ceremony (\"Show a checkpoint "
                    "... wait for GO\"). The v2 execution plan removes checkpoint ceremony "
                    "as a default; this text is left in place for you to remove by hand if "
                    "you agree it no longer applies.",
                )
            )

    if detection.claude_constitution is None:
        return items, ops, warnings

    if root_claude.exists() or root_agents.exists():
        existing = "CLAUDE.md" if root_claude.exists() else "AGENTS.md"
        items.append(
            MigrationItem(
                ".claude/CLAUDE.md",
                CATEGORY_MANUAL_REVIEW,
                ACTION_NONE,
                None,
                f"Both .claude/CLAUDE.md (v1) and a root {existing} already exist. "
                "AgentForge does not guess which one is authoritative -- merge them "
                "by hand, then re-run the migration.",
            )
        )
        return items, ops, warnings

    v1_text = _read_text(detection.claude_constitution)
    change = setup_module._plan_block_change("CLAUDE.md", v1_text, exists=False)
    new_text = change.after
    constraints = _extract_golden_rule_and_constraints(v1_text)
    if constraints:
        rendered = (
            f"Migrated from v1 (`.claude/CLAUDE.md`) by AgentForge's v1-migration skill -- "
            f"preserved verbatim below. Do not hand-edit this block; edit the constraints "
            f"directly elsewhere in this file and remove this notice once you have.\n\n"
            f"{constraints}"
        )
        new_text, _ = _insert_marked_block(
            new_text, MIGRATED_CONSTRAINTS_START, MIGRATED_CONSTRAINTS_END, rendered
        )
    else:
        warnings.append(
            f".claude/CLAUDE.md has no 'Golden Rule' or 'Hard Constraints' heading to "
            "extract; its full prose was still copied to the new CLAUDE.md verbatim."
        )

    archive_dest = ".claude/CLAUDE.md"
    items.append(
        MigrationItem(
            ".claude/CLAUDE.md",
            CATEGORY_TRANSFORMED,
            ACTION_CREATE,
            "CLAUDE.md",
            "Content copied to the v2 constitution location (project root CLAUDE.md), "
            "with the AgentForge managed block and an extracted Golden Rule/Hard "
            "Constraints block appended. The original is archived, not left duplicated.",
        )
    )
    ops.append(FileOp("write", path="CLAUDE.md", content=new_text.encode("utf-8"), existed_before=False))
    items.append(
        MigrationItem(
            ".claude/CLAUDE.md",
            CATEGORY_ARCHIVED,
            ACTION_MOVE,
            None,  # filled in with the timestamped archive path at apply time
            "Superseded by the new root CLAUDE.md; archived rather than left duplicated "
            "or deleted.",
        )
    )
    ops.append(FileOp("move", src=".claude/CLAUDE.md", dest=archive_dest))

    return items, ops, warnings


# ---------------------------------------------------------------------------
# Story planning
# ---------------------------------------------------------------------------


def plan_stories_items(detection: V1Detection, cfg: dict) -> tuple:
    """Plan converting every v1 story into a v2 local work item. Returns
    (items, ops, warnings)."""
    items: list = []
    ops: list = []
    warnings: list = []

    story_files = tuple(detection.claude_stories) + tuple(detection.codex_stories)
    if not story_files:
        return items, ops, warnings

    tracker = cfg.get("tracker", {}) if isinstance(cfg, dict) else {}
    tracker_type = tracker.get("type")
    local_root = tracker.get("local_root") or "docs/work-items"

    # A mixed scaffold can have the same STORY-NNN id under both
    # .claude/stories/ and .agents/stories/ (v1 never deduplicated across
    # harnesses). Track which target path this *same planning pass* has
    # already claimed so a second story never silently overwrites the
    # first's freshly-converted work item -- checking only the pre
    # -existing filesystem state (as `target_path.exists()` below does)
    # would miss this, since neither file exists on disk until apply.
    claimed_targets: dict = {}

    for story_path in story_files:
        rel_source = str(story_path.relative_to(detection.root).as_posix())
        text = _read_text(story_path)
        parsed = parse_v1_story(text)
        if parsed is None:
            items.append(
                MigrationItem(
                    rel_source,
                    CATEGORY_MANUAL_REVIEW,
                    ACTION_NONE,
                    None,
                    "Could not recognize a '# STORY-XXX — Title' heading; migrate this "
                    "story by hand.",
                )
            )
            continue

        if tracker_type not in (None, "local"):
            items.append(
                MigrationItem(
                    rel_source,
                    CATEGORY_MANUAL_REVIEW,
                    ACTION_NONE,
                    None,
                    f"This project's configured tracker is {tracker_type!r}. AgentForge's "
                    f"{tracker_type} adapter has no write path (fetch-only); recreate "
                    f"{parsed.story_id} as a {tracker_type} issue by hand, or switch "
                    "tracker.type to 'local' before migrating.",
                )
            )
            continue

        target_rel = f"{local_root}/{parsed.story_id}.md"
        target_path = detection.root / target_rel
        agent_field = _extract_v1_agent_field(text)
        rendered = render_local_work_item(parsed, rel_source, agent_field)

        if target_rel in claimed_targets:
            items.append(
                MigrationItem(
                    rel_source,
                    CATEGORY_MANUAL_REVIEW,
                    ACTION_NONE,
                    target_rel,
                    f"{target_rel} would also be claimed by {claimed_targets[target_rel]!r} "
                    f"(same {parsed.story_id} id under a different v1 harness directory). "
                    "AgentForge never lets a second story silently overwrite the first's "
                    "converted work item; reconcile the two by hand.",
                )
            )
            continue
        claimed_targets[target_rel] = rel_source

        if target_path.exists():
            existing_text = _read_text(target_path)
            if existing_text == rendered:
                items.append(
                    MigrationItem(
                        rel_source, CATEGORY_TRANSFORMED, ACTION_NONE, target_rel,
                        "Already migrated to this exact local work item.",
                    )
                )
                continue
            items.append(
                MigrationItem(
                    rel_source,
                    CATEGORY_MANUAL_REVIEW,
                    ACTION_NONE,
                    target_rel,
                    f"{target_rel} already exists with different content; AgentForge "
                    "never overwrites an existing local work item. Merge by hand.",
                )
            )
            continue

        items.append(
            MigrationItem(
                rel_source,
                CATEGORY_TRANSFORMED,
                ACTION_CREATE,
                target_rel,
                f"Converted to a v2 local work item, preserving the original id "
                f"({parsed.story_id}) and v1 agent assignment in front matter "
                "(migrated_from/migrated_v1_agent).",
            )
        )
        ops.append(FileOp("write", path=target_rel, content=rendered.encode("utf-8"), existed_before=False))
        items.append(
            MigrationItem(
                rel_source,
                CATEGORY_ARCHIVED,
                ACTION_MOVE,
                None,
                f"Superseded by {target_rel}; archived rather than left duplicated.",
            )
        )
        ops.append(FileOp("move", src=rel_source, dest=rel_source))

    return items, ops, warnings


# ---------------------------------------------------------------------------
# Scope / config planning
# ---------------------------------------------------------------------------

_AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def _load_v1_scopes(path: Path) -> dict:
    try:
        data = json.loads(_read_text(path))
    except (json.JSONDecodeError, OSError):
        return {}
    agents = data.get("agents") if isinstance(data, dict) else None
    return agents if isinstance(agents, dict) else {}


def plan_scope_and_config_items(detection: V1Detection) -> tuple:
    """Plan `.agentforge/config.json` creation/merge from v1's
    `scopes.json`. Returns (items, ops, warnings, resulting_config)."""
    items: list = []
    ops: list = []
    warnings: list = []

    root = detection.root
    config_path = root / ".agentforge" / "config.json"
    v1_scopes_paths = [p for p in (detection.claude_scopes, detection.codex_scopes) if p]

    v1_agents: dict = {}
    for scopes_path in v1_scopes_paths:
        for name, entry in _load_v1_scopes(scopes_path).items():
            if not isinstance(entry, dict):
                continue
            v1_agents.setdefault(name, entry)

    if config_path.exists():
        try:
            existing_config = config_module.load_for_enforcement(config_path)
        except config_module.ConfigValidationError:
            # Signal "blocked" to the caller: an existing, invalid
            # .agentforge/config.json is never silently replaced or
            # merged into (mirrors scripts.setup.plan_agentforge_config).
            return [], [], [], None
        base_config = json.loads(json.dumps(existing_config))  # deep copy
        existed_before = True
    else:
        base_config = json.loads(json.dumps(config_module.DEFAULT_CONFIG))
        existed_before = False

    scope_agents = base_config.setdefault("scope", {}).setdefault("agents", {})
    added_any = False
    for name, entry in v1_agents.items():
        if not isinstance(name, str) or not _AGENT_NAME_PATTERN.match(name):
            items.append(
                MigrationItem(
                    "scopes.json#" + str(name),
                    CATEGORY_MANUAL_REVIEW,
                    ACTION_NONE,
                    None,
                    f"Agent name {name!r} does not match AgentForge's allowed pattern "
                    "(^[A-Za-z][A-Za-z0-9_-]*$); add it to .agentforge/config.json by hand.",
                )
            )
            continue
        allow = [p for p in entry.get("allow", []) if isinstance(p, str)]
        bad = [p for p in allow if config_module._relative_path_issue(p)]
        allow = [p for p in allow if p not in bad]
        if bad:
            warnings.append(
                f"scopes.json agent {name!r}: dropped unsafe path(s) {bad!r} while "
                "migrating to .agentforge/config.json's scope.agents."
            )
        if name in scope_agents:
            continue  # never overwrite an existing, already-configured agent
        scope_agents[name] = {"allow": allow}
        added_any = True

    if added_any and base_config["scope"].get("mode") == "off":
        # Never silently jump to a blocking mode -- "observe" is the
        # honest, non-blocking acknowledgment that this project now has
        # agent-scope intent recorded, without AgentForge claiming any new
        # enforcement it has not been explicitly asked to perform.
        base_config["scope"]["mode"] = "observe"

    after_text = json.dumps(base_config, indent=2, sort_keys=True) + "\n"
    rel_path = ".agentforge/config.json"

    if not existed_before:
        items.append(
            MigrationItem(
                rel_path, CATEGORY_TRANSFORMED, ACTION_CREATE, rel_path,
                "Created from the v2 template" + (
                    ", populated with scope.agents migrated from v1's scopes.json"
                    if added_any else ""
                ) + ".",
            )
        )
        ops.append(FileOp("write", path=rel_path, content=after_text.encode("utf-8"), existed_before=False))
    elif added_any:
        before_text = _read_text(config_path)
        items.append(
            MigrationItem(
                rel_path, CATEGORY_TRANSFORMED, ACTION_UPDATE, rel_path,
                "Merged v1 scopes.json agents into the existing scope.agents (existing "
                "entries and every other field left untouched).",
            )
        )
        ops.append(
            FileOp(
                "write",
                path=rel_path,
                content=after_text.encode("utf-8"),
                existed_before=True,
                before_content=before_text.encode("utf-8"),
            )
        )
    else:
        items.append(
            MigrationItem(
                rel_path, CATEGORY_TRANSFORMED, ACTION_NONE, rel_path,
                "Already up to date; nothing to migrate from v1 scopes." if not v1_agents
                else "Every v1 scopes.json agent is already present; nothing to change.",
            )
        )

    # The Bash/scope-enforcement overclaim warning always fires whenever a
    # v1 scopes.json is found, regardless of whether it is archived yet --
    # this is informational text, not a filesystem action, and
    # requirement 5 asks for the warning wherever the v1 claim was made,
    # not only once the file is actually removed.
    #
    # Archiving the scopes.json *file* itself, however, is intentionally
    # NOT done here -- it happens in plan_hooks_items, gated on
    # v2_hooks_validated alongside pre_tool_use.py. v1's hook fails open
    # (treats a missing scopes.json as "nothing configured", i.e.
    # unrestricted) when the file it reads is gone, so archiving it while
    # pre_tool_use.py is still wired would silently disable v1's own (if
    # weak) functional scope restriction ahead of any explicit validation
    # -- exactly the unvalidated intermediate state this story's hook
    # -gating exists to prevent.
    for scopes_path in v1_scopes_paths:
        rel = str(scopes_path.relative_to(root).as_posix())
        warnings.append(
            f"{rel} (v1) is paired with a pre_tool_use.py hook that claimed to enforce "
            "destructive-command blocking and per-agent file scopes via Bash regex "
            "matching. This was never a real security boundary -- it is bypassable via "
            "shell indirection, `git -C <dir> push`, a STORY-XXX token anywhere on the "
            "command line, and unresolved '..'/dotfile paths (see "
            "tests/test_v1_characterization.py). v2's scope.mode is honest about its "
            "narrower, real coverage (structured Write/Edit only under 'deny-structured' "
            "/'strict-agent'; Bash is classified best-effort, never a security boundary) "
            "-- see docs/threat-model.md before choosing a mode stronger than 'observe'."
        )

    return items, ops, warnings, base_config


# ---------------------------------------------------------------------------
# Hook / settings planning
# ---------------------------------------------------------------------------


def _strip_v1_hook_registrations(data: dict, needle: str) -> tuple:
    """Remove hook-matcher entries whose command references `needle`
    (`.claude/hooks/` or `.codex/hooks/`) from a parsed settings.json /
    hooks.json document. Returns (new_data, changed, fully_empty) --
    `fully_empty` is True when every event's hook list became empty,
    meaning nothing but v1's own hook wiring lived in this file's "hooks"
    key at all."""
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return data, False, False

    new_hooks: dict = {}
    changed = False
    for event_name, matchers in hooks.items():
        if not isinstance(matchers, list):
            new_hooks[event_name] = matchers
            continue
        kept_matchers = []
        for matcher_entry in matchers:
            inner_hooks = matcher_entry.get("hooks") if isinstance(matcher_entry, dict) else None
            if not isinstance(inner_hooks, list):
                kept_matchers.append(matcher_entry)
                continue
            kept_inner = [
                h for h in inner_hooks
                if not (isinstance(h, dict) and needle in str(h.get("command", "")))
            ]
            if len(kept_inner) != len(inner_hooks):
                changed = True
            if kept_inner:
                new_entry = dict(matcher_entry)
                new_entry["hooks"] = kept_inner
                kept_matchers.append(new_entry)
        if kept_matchers:
            new_hooks[event_name] = kept_matchers
        else:
            changed = True

    new_data = dict(data)
    if new_hooks:
        new_data["hooks"] = new_hooks
    else:
        new_data.pop("hooks", None)
    fully_empty = not new_hooks
    return new_data, changed, fully_empty


def plan_hooks_items(detection: V1Detection, *, v2_hooks_validated: bool) -> tuple:
    """Plan archiving v1 hook scripts and disabling their registration.
    Returns (items, ops, warnings). Every hook-registration change's
    action is `"deferred"` (computed, reported, but not written by
    `apply_migration`) unless `v2_hooks_validated` is True -- STORY-019's
    "never leave neither hook active" requirement."""
    items: list = []
    ops: list = []
    warnings: list = []
    root = detection.root

    def _plan_registration_file(path: Optional[Path], needle: str, kind: str) -> None:
        if path is None:
            return
        rel = str(path.relative_to(root).as_posix())
        try:
            data = json.loads(_read_text(path))
        except (json.JSONDecodeError, OSError):
            items.append(
                MigrationItem(
                    rel, CATEGORY_MANUAL_REVIEW, ACTION_NONE, None,
                    f"{rel} is not valid JSON; disable its v1 hook registration by hand.",
                )
            )
            return
        if not isinstance(data, dict):
            items.append(
                MigrationItem(
                    rel, CATEGORY_MANUAL_REVIEW, ACTION_NONE, None,
                    f"{rel} is valid JSON but not a JSON object; disable its v1 hook "
                    "registration by hand.",
                )
            )
            return
        new_data, changed, fully_empty = _strip_v1_hook_registrations(data, needle)
        if not changed:
            # Present, but carries no v1 hook registration to remove (e.g. hand
            # -edited down to nothing v1-related already) -- still reported, per
            # the "every detected artifact appears in the report" contract.
            items.append(
                MigrationItem(
                    rel, CATEGORY_RETAINED, ACTION_NONE, None,
                    f"No v1 hook registration referencing {needle!r} found in {rel}; "
                    "left as-is.",
                )
            )
            return

        action = ACTION_UPDATE if v2_hooks_validated else ACTION_DEFERRED
        reason = (
            "Removing v1 hook registrations now that v2 hooks (this AgentForge plugin's "
            "own hooks/hooks.json) are confirmed installed and enabled."
            if v2_hooks_validated
            else "v1 hook registrations would be removed here, but this is deferred until "
            "the AgentForge v2 plugin is confirmed installed/enabled (re-run with "
            "--v2-hooks-validated once it is) -- a project must never be left with "
            "neither the old nor the new hook active."
        )
        if fully_empty and kind == "codex_hooks_json":
            # Nothing but v1's own wiring lived in this file; archive the
            # whole file instead of leaving a degenerate {} residue.
            items.append(
                MigrationItem(rel, CATEGORY_ARCHIVED, action, None, reason)
            )
            if v2_hooks_validated:
                ops.append(FileOp("move", src=rel, dest=rel))
        else:
            items.append(
                MigrationItem(rel, CATEGORY_TRANSFORMED, action, rel, reason)
            )
            if v2_hooks_validated:
                ops.append(
                    FileOp(
                        "write",
                        path=rel,
                        content=(json.dumps(new_data, indent=2) + "\n").encode("utf-8"),
                        existed_before=True,
                        before_content=path.read_bytes(),
                    )
                )

    _plan_registration_file(detection.claude_settings, ".claude/hooks/", "claude_settings")
    _plan_registration_file(detection.codex_hooks_json, ".codex/hooks/", "codex_hooks_json")

    if detection.codex_hooks_json is not None:
        try:
            codex_hooks_data = json.loads(_read_text(detection.codex_hooks_json))
        except (json.JSONDecodeError, OSError):
            codex_hooks_data = {}
        if isinstance(codex_hooks_data, dict) and "Stop" in codex_hooks_data.get("hooks", {}):
            warnings.append(
                ".codex/hooks.json registers session_end.py on the 'Stop' event because v1's "
                "documentation claimed Codex had no SessionEnd event. Current Codex "
                "documentation confirms SessionEnd exists as a real, distinct event (see "
                "docs/codex-compatibility.md's 'Corrections to this repository's own prior "
                "Codex claims'); this mapping is stale. AgentForge v2 does not need this "
                "wiring at all (it has no SessionEnd-triggered behavior), so no replacement "
                "registration is created -- but if you keep using this file's hooks "
                "independently of the AgentForge plugin, change 'Stop' to 'SessionEnd' by hand."
            )

    for scopes_path in (detection.claude_scopes, detection.codex_scopes):
        if scopes_path is None:
            continue
        rel = str(scopes_path.relative_to(root).as_posix())
        action = ACTION_MOVE if v2_hooks_validated else ACTION_DEFERRED
        reason = (
            "Superseded by .agentforge/config.json's scope.agents; archived now that "
            "v2 hooks are confirmed active."
            if v2_hooks_validated
            else "Superseded by .agentforge/config.json's scope.agents, but left in place "
            "until v2 hooks are confirmed installed/enabled -- pre_tool_use.py (still "
            "active until then) treats a missing scopes.json as unrestricted, so "
            "archiving it early would silently disable v1's own scope restriction."
        )
        items.append(MigrationItem(rel, CATEGORY_ARCHIVED, action, None, reason))
        if v2_hooks_validated:
            ops.append(FileOp("move", src=rel, dest=rel))

    for hook_path in (detection.claude_hook_files, detection.codex_hook_files):
        for path in hook_path:
            rel = str(path.relative_to(root).as_posix())
            action = ACTION_MOVE if v2_hooks_validated else ACTION_DEFERRED
            reason = (
                "Superseded by AgentForge v2's own plugin-level hooks "
                "(scripts/scope_policy.py, scripts/context.py); archived now that v2 "
                "hooks are confirmed active."
                if v2_hooks_validated
                else "Superseded by AgentForge v2's own plugin-level hooks, but left in "
                "place until v2 hooks are confirmed installed/enabled (see the "
                "settings.json/hooks.json note above)."
            )
            items.append(MigrationItem(rel, CATEGORY_ARCHIVED, action, None, reason))
            if v2_hooks_validated:
                ops.append(FileOp("move", src=rel, dest=rel))

    if detection.session_log is not None:
        rel = str(detection.session_log.relative_to(root).as_posix())
        action = ACTION_MOVE if v2_hooks_validated else ACTION_DEFERRED
        reason = (
            "Write-only v1 PreCompact log; session_start.py never reads it back "
            "(tests/test_v1_characterization.py::PreCompactLogNotRestoredTests). "
            "v2's active-work snapshot (.agentforge/active-work.json) replaces this "
            "mechanism entirely."
            + (
                " Archived, not deleted."
                if v2_hooks_validated
                else " Left in place until v2 hooks are confirmed installed/enabled, since "
                "pre_compact.py (still active until then) writes to it."
            )
        )
        items.append(MigrationItem(rel, CATEGORY_OBSOLETE, action, None, reason))
        if v2_hooks_validated:
            ops.append(FileOp("move", src=rel, dest=rel))

    return items, ops, warnings


# ---------------------------------------------------------------------------
# Retained items
# ---------------------------------------------------------------------------


def plan_retained_items(detection: V1Detection) -> list:
    items: list = []
    root = detection.root

    for path in (detection.project_context, detection.roadmap):
        if path is not None:
            rel = str(path.relative_to(root).as_posix())
            items.append(
                MigrationItem(
                    rel, CATEGORY_RETAINED, ACTION_NONE, None,
                    "Domain content AgentForge v2 does not own or replace; left in place.",
                )
            )

    for group in (detection.claude_skills, detection.codex_skills):
        for path in group:
            rel = str(path.relative_to(root).as_posix())
            items.append(
                MigrationItem(
                    rel, CATEGORY_RETAINED, ACTION_NONE, None,
                    "Ordinary project skill, unrelated to AgentForge's own skills; left "
                    "in place and untouched.",
                )
            )

    known_bundled = {"independent-reviewer", "verifier"}
    for group in (detection.claude_agents, detection.codex_agents):
        for path in group:
            rel = str(path.relative_to(root).as_posix())
            name = path.stem
            text = _read_text(path)
            note = (
                "Continues to function as an ordinary custom subagent under v2; "
                "AgentForge does not manage custom personas."
            )
            if name not in known_bundled:
                note += (
                    " If you want its file scope enforced by v2's scope policy, add a "
                    f"'{name}' entry under .agentforge/config.json's scope.agents "
                    "(scopes.json migration above may have already done this)."
                )
            items.append(MigrationItem(rel, CATEGORY_RETAINED, ACTION_NONE, None, note))
            if "checkpoint" in text.lower() and "go" in text.lower():
                items.append(
                    MigrationItem(
                        rel + "#Behaviour Rules",
                        CATEGORY_MANUAL_REVIEW,
                        ACTION_NONE,
                        None,
                        "This persona describes v1's CHECKPOINT/'wait for GO' ceremony. "
                        "The v2 execution plan removes checkpoint ceremony as a default; "
                        "edit this persona by hand if you agree it no longer applies.",
                    )
                )

    return items


# ---------------------------------------------------------------------------
# Plan / apply
# ---------------------------------------------------------------------------


@dataclass
class MigrationPlan:
    status: str  # "no_change" | "ok" | "blocked" | "stale"
    project_root: str
    items: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    blocking_issues: list = field(default_factory=list)
    plan_id: Optional[str] = None
    v2_hooks_validated: bool = False
    rollback_steps: list = field(default_factory=list)
    manifest_path: Optional[str] = None
    _ops: list = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "project_root": self.project_root,
            "plan_id": self.plan_id,
            "v2_hooks_validated": self.v2_hooks_validated,
            "items": [item.to_dict() for item in self.items],
            "warnings": list(self.warnings),
            "blocking_issues": list(self.blocking_issues),
            "rollback_steps": list(self.rollback_steps),
            "manifest_path": self.manifest_path,
        }


def _compute_plan_id(root: Path, items: list, ops: list) -> str:
    payload = {
        "items": [
            {"path": i.path, "category": i.category, "action": i.action, "target": i.target}
            for i in items
        ],
        "ops": [
            {
                "kind": op.kind,
                "path": op.path,
                "content_sha256": _sha256_hex(op.content) if op.content is not None else None,
                "src": op.src,
                "dest": op.dest,
            }
            for op in ops
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _sha256_hex(canonical.encode("utf-8"))


def plan_migration(project_root: Any, *, v2_hooks_validated: bool = False) -> MigrationPlan:
    """Never writes to disk. Detects every v1 artifact, classifies each
    into exactly one of the five categories, and computes the exact file
    operations `apply_migration` would perform."""
    root = Path(project_root)
    detection = detect_v1(root)

    if not detection.has_any_v1:
        # Either nothing v1 was ever here, or a prior migration already
        # archived everything -- both are the same true no-op.
        retained = plan_retained_items(detection)
        return MigrationPlan(
            "no_change", str(root), items=retained, plan_id=_compute_plan_id(root, retained, []),
            v2_hooks_validated=v2_hooks_validated,
        )

    all_items: list = []
    all_ops: list = []
    all_warnings: list = []

    constitution_items, constitution_ops, constitution_warnings = plan_constitution_item(detection)
    all_items += constitution_items
    all_ops += constitution_ops
    all_warnings += constitution_warnings

    config_path = root / ".agentforge" / "config.json"
    if config_path.exists():
        try:
            config_module.load_for_enforcement(config_path)
        except config_module.ConfigValidationError as exc:
            return MigrationPlan(
                "blocked",
                str(root),
                blocking_issues=[f".agentforge/config.json: {issue.format()}" for issue in exc.issues],
                v2_hooks_validated=v2_hooks_validated,
            )

    scope_items, scope_ops, scope_warnings, resulting_config_after_scope = (
        plan_scope_and_config_items(detection)
    )
    all_items += scope_items
    all_ops += scope_ops
    all_warnings += scope_warnings

    story_items, story_ops, story_warnings = plan_stories_items(detection, resulting_config_after_scope)
    all_items += story_items
    all_ops += story_ops
    all_warnings += story_warnings

    hooks_items, hooks_ops, hooks_warnings = plan_hooks_items(
        detection, v2_hooks_validated=v2_hooks_validated
    )
    all_items += hooks_items
    all_ops += hooks_ops
    all_warnings += hooks_warnings

    all_items += plan_retained_items(detection)

    has_pending_write = any(op.kind in ("write", "move") for op in all_ops)
    status = "ok" if has_pending_write else "no_change"

    plan_id = _compute_plan_id(root, all_items, all_ops)
    return MigrationPlan(
        status,
        str(root),
        items=all_items,
        warnings=all_warnings,
        plan_id=plan_id,
        v2_hooks_validated=v2_hooks_validated,
        _ops=all_ops,
    )


def _archive_dir_rel(timestamp: str) -> str:
    return "/".join(ARCHIVE_ROOT_PARTS) + "/" + timestamp


def apply_migration(
    project_root: Any,
    *,
    approved_plan_id: Optional[str],
    v2_hooks_validated: bool = False,
    clock: Optional[Any] = None,
) -> MigrationPlan:
    """Recompute the plan fresh and, only if its `plan_id` matches
    `approved_plan_id` exactly, write every operation -- moves land under
    a fresh timestamped archive directory, writes land at their target
    path -- and record a manifest that makes `rollback_migration` exact.
    """
    root = Path(project_root)
    plan = plan_migration(root, v2_hooks_validated=v2_hooks_validated)
    if plan.status != "ok":
        return plan

    if not approved_plan_id or approved_plan_id != plan.plan_id:
        return MigrationPlan(
            "stale",
            plan.project_root,
            items=plan.items,
            warnings=plan.warnings,
            plan_id=plan.plan_id,
            v2_hooks_validated=v2_hooks_validated,
        )

    timestamp = (clock or _now_timestamp)()
    archive_rel = _archive_dir_rel(timestamp)
    archive_dir = root / archive_rel
    # Microsecond-precision timestamps make a collision very unlikely, but
    # never bet a data-safety guarantee on "very unlikely": disambiguate
    # rather than let a second migration overwrite (or interleave with) an
    # earlier one's still-unread archive.
    suffix = 1
    while archive_dir.exists():
        timestamp = f"{(clock or _now_timestamp)()}-{suffix}"
        archive_rel = _archive_dir_rel(timestamp)
        archive_dir = root / archive_rel
        suffix += 1

    manifest_entries: list = []
    rollback_steps: list = []

    for op in plan._ops:
        if op.kind == "write":
            target = root / op.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(op.content)
            manifest_entries.append(
                {
                    "kind": "write",
                    "path": op.path,
                    "existed_before": bool(op.existed_before),
                    "before_sha256": _sha256_hex(op.before_content) if op.before_content else None,
                }
            )
            if op.existed_before and op.before_content is not None:
                backup_path = archive_dir / "before" / op.path
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_bytes(op.before_content)
                manifest_entries[-1]["backup"] = str((Path("before") / op.path).as_posix())
                rollback_steps.append(
                    f"cp {archive_rel}/before/{op.path} {op.path}   # restore pre-migration content"
                )
            else:
                rollback_steps.append(f"rm {op.path}   # remove file created by migration")
        elif op.kind == "move":
            src_path = root / op.src
            if not src_path.is_file():
                continue
            dest_path = archive_dir / "moved" / op.dest
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            src_path.replace(dest_path)
            manifest_entries.append(
                {
                    "kind": "move",
                    "src": op.src,
                    "archived_to": str((Path("moved") / op.dest).as_posix()),
                }
            )
            rollback_steps.append(
                f"mv {archive_rel}/moved/{op.dest} {op.src}   # restore archived file"
            )

    manifest = {
        "schema_version": 1,
        "timestamp": timestamp,
        "project_root": str(root),
        "v2_hooks_validated": v2_hooks_validated,
        "entries": manifest_entries,
    }
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = archive_dir / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    rollback_steps.insert(
        0,
        f"# Rollback for the migration applied at {timestamp}. Run from {root}:",
    )
    rollback_steps.append(
        f"# Or, equivalently: python3 scripts/migrate_v1.py rollback --project-root . "
        f"--timestamp {timestamp}"
    )

    plan.rollback_steps = rollback_steps
    plan.manifest_path = str((Path(archive_rel) / MANIFEST_FILENAME).as_posix())
    return plan


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RollbackResult:
    status: str  # "ok" | "not_found" | "already_rolled_back"
    restored: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"status": self.status, "restored": list(self.restored)}


def rollback_migration(project_root: Any, timestamp: str) -> RollbackResult:
    """Read the manifest written by `apply_migration` at `timestamp` and
    restore every entry to its exact pre-migration state: a modified file
    is restored from its `before/` backup (or deleted, if migration
    created it); a moved file is moved back from `moved/` to its original
    location."""
    root = Path(project_root)
    archive_dir = root / _archive_dir_rel(timestamp)
    manifest_path = archive_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return RollbackResult("not_found")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list = []
    for entry in reversed(manifest.get("entries", [])):
        if entry["kind"] == "write":
            target = root / entry["path"]
            if entry["existed_before"] and entry.get("backup"):
                backup = archive_dir / entry["backup"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(backup.read_bytes())
                restored.append(entry["path"])
            elif not entry["existed_before"] and target.exists():
                target.unlink()
                restored.append(entry["path"])
        elif entry["kind"] == "move":
            archived = archive_dir / entry["archived_to"]
            original = root / entry["src"]
            if archived.is_file():
                original.parent.mkdir(parents=True, exist_ok=True)
                archived.replace(original)
                restored.append(entry["src"])

    return RollbackResult("ok", restored=restored)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_v1.py", description="Migrate an AgentForge v1 project to v2 (STORY-019)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_p = subparsers.add_parser("plan", help="Detect and classify v1 artifacts; never writes.")
    plan_p.add_argument("--project-root", type=Path, default=Path("."))
    plan_p.add_argument("--v2-hooks-validated", action="store_true")

    apply_p = subparsers.add_parser("apply", help="Apply an approved migration plan.")
    apply_p.add_argument("--project-root", type=Path, default=Path("."))
    apply_p.add_argument("--approved-plan-id", required=True)
    apply_p.add_argument("--v2-hooks-validated", action="store_true")

    rollback_p = subparsers.add_parser("rollback", help="Undo a previously applied migration.")
    rollback_p.add_argument("--project-root", type=Path, default=Path("."))
    rollback_p.add_argument("--timestamp", required=True)

    args = parser.parse_args(argv)

    if args.command == "plan":
        plan = plan_migration(args.project_root, v2_hooks_validated=args.v2_hooks_validated)
        print(json.dumps(plan.to_dict(), indent=2))
        return 0 if plan.status in ("ok", "no_change") else 1

    if args.command == "apply":
        plan = apply_migration(
            args.project_root,
            approved_plan_id=args.approved_plan_id,
            v2_hooks_validated=args.v2_hooks_validated,
        )
        print(json.dumps(plan.to_dict(), indent=2))
        for line in plan.rollback_steps:
            print(line, file=sys.stderr)
        return 0 if plan.status in ("ok", "no_change") else 1

    if args.command == "rollback":
        result = rollback_migration(args.project_root, args.timestamp)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.status == "ok" else 1

    return 1  # pragma: no cover - argparse enforces a valid subcommand


if __name__ == "__main__":
    sys.exit(main())
