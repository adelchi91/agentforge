"""AgentForge tracker identifiers and local/remote adapters (STORY-006).

Resolves one normalized `WorkItem` identity from exactly the tracker a
project has configured (ADR-0002: one tracker is the source of truth per
project). This module never guesses a provider — a bare `#123` with no
configured tracker context is rejected as ambiguous rather than assumed to
mean GitHub, GitLab, or a local slug.

Three adapters, one shared record:

  - **local** — reads a Markdown file under `tracker.local_root`. Zero
    network access, the deterministic reference implementation. Both a
    bare ID (`STORY-006`) and an explicit path
    (`docs/work-items/STORY-006.md`) resolve to the same canonical
    identity.
  - **github** / **gitlab** — shell out to the `gh` / `glab` CLIs
    (see `docs/agents/issue-tracker.md` for the exact command contract and
    authentication assumptions). Every external command is invoked through
    the injectable `runner` parameter so callers/tests never need a real
    network connection or a real CLI binary on PATH.

Network code paths in this module (`_resolve_github`, `_resolve_gitlab`)
must only ever be reached from explicit, user-invoked skill operations —
`/agentforge:setup` and `/agentforge:prepare-work` — never from a lifecycle
hook entry point (ADR-0005). This module does not enforce that by itself;
it is a property of *who imports this module for what*, documented here
and in `docs/agents/issue-tracker.md` for whoever wires the next story's
hook entry points.

Errors are always a value, never an exception that reaches a caller.
`resolve_work_item` returns a `WorkItemResult` — either `.item` (a
`WorkItem`) or `.error` (a `WorkItemError` naming one of the `ERROR_*`
kinds below) is set, never both, and this function does not raise for any
recognized failure mode (missing CLI, auth failure, not found, malformed
item, unsupported tracker, ambiguous identifier). This is what lets a
remote fetch failure be handled by the caller instead of corrupting
whatever active-work snapshot already exists (ADR-0002) — snapshot
writing itself is STORY-008, out of scope here.

This is deliberately a single "always return a value" entry point, not
the enforce-vs-observe dual entry point `scripts/config.py` documents.
Identifier resolution has no policy stance to enforce (it is asked "what
is this?", not "is this allowed?"); every caller — a hard-stop skill
step or a soft diagnostic — makes that decision itself by branching on
`WorkItemResult.ok`.

Remote content is untrusted: `_sanitize_text` strips control characters
before any GitHub/GitLab title/body is placed on a `WorkItem`, and every
adapter (local included, for uniformity) bounds body size using the
STORY-004 `context.max_bytes` config field
(`scripts.config.DEFAULT_CONFIG["context"]["max_bytes"]` is the fallback
when a caller's config omits the `context` section).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from . import config as config_module  # imported as scripts.work_items (e.g. tests)
except ImportError:
    import config as config_module  # executed directly: python3 scripts/work_items.py

DEFAULT_CONFIG = config_module.DEFAULT_CONFIG

PROVIDER_LOCAL = "local"
PROVIDER_GITHUB = "github"
PROVIDER_GITLAB = "gitlab"
PROVIDERS = (PROVIDER_LOCAL, PROVIDER_GITHUB, PROVIDER_GITLAB)

# The five structured-error categories STORY-006 requires, plus two this
# module needs to express its own additional guarantees:
#   - "ambiguous_identifier": a bare number with no known provider
#     (STORY-006's "reject ambiguous bare numbers" requirement) — distinct
#     from "unsupported_tracker" because the *identifier* is the problem
#     here, not the tracker configuration.
#   - "cli_error": an external command failed in a way that is neither a
#     recognized auth failure nor a recognized not-found response (e.g. a
#     transient network error, a timeout, or an unexpected CLI exit). This
#     still reaches the caller as a structured value, never a traceback.
ERROR_MISSING_CLI = "missing_cli"
ERROR_AUTH_FAILED = "auth_failed"
ERROR_NOT_FOUND = "not_found"
ERROR_MALFORMED_ITEM = "malformed_item"
ERROR_UNSUPPORTED_TRACKER = "unsupported_tracker"
ERROR_AMBIGUOUS_IDENTIFIER = "ambiguous_identifier"
ERROR_CLI_ERROR = "cli_error"

ERROR_KINDS = (
    ERROR_MISSING_CLI,
    ERROR_AUTH_FAILED,
    ERROR_NOT_FOUND,
    ERROR_MALFORMED_ITEM,
    ERROR_UNSUPPORTED_TRACKER,
    ERROR_AMBIGUOUS_IDENTIFIER,
    ERROR_CLI_ERROR,
)

DEFAULT_MAX_BYTES: int = DEFAULT_CONFIG["context"]["max_bytes"]

_BARE_OR_HASH_NUMBER_RE = re.compile(r"^#?(\d+)$")
_REPO_SHAPE_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_FALLBACK_LOCAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_FRONT_MATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


@dataclass(frozen=True)
class WorkItem:
    """A normalized work-item identity, independent of which tracker it
    came from. `canonical_id` is provider-qualified
    (`local:STORY-006`, `github:owner/repo#123`, `gitlab:group/project#123`)
    so the same textual identifier under two different providers never
    collides."""

    provider: str
    canonical_id: str
    title: str
    source: str
    body: str
    state: str
    blockers: tuple
    updated_at: Optional[str]
    content_digest: str
    truncated: bool = False


@dataclass(frozen=True)
class WorkItemError:
    """A structured failure. `kind` is always one of `ERROR_KINDS`."""

    kind: str
    message: str
    identifier: Optional[str] = None
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in ERROR_KINDS:
            raise ValueError(f"unknown WorkItemError kind: {self.kind!r}")


@dataclass(frozen=True)
class WorkItemResult:
    """Exactly one of `item`/`error` is set. Never raise `resolve_work_item`
    for a recognized failure mode — return a `WorkItemResult` instead."""

    item: Optional[WorkItem] = None
    error: Optional[WorkItemError] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @classmethod
    def ok_item(cls, item: WorkItem) -> "WorkItemResult":
        return cls(item=item, error=None)

    @classmethod
    def fail(cls, kind: str, message: str, **details: Any) -> "WorkItemResult":
        return cls(item=None, error=WorkItemError(kind, message, **details))


def classify_identifier_shape(raw: str) -> str:
    """Classify the *syntactic* shape of a raw identifier, independent of
    any configured provider:

      - "issue_reference": `#123` or `123` — a GitHub/GitLab-style number.
      - "repository": `owner/repo` — a repository identifier, never a
        work-item identifier (STORY-006's "precise distinction"
        requirement: these must never be conflated).
      - "path": contains a path separator, or ends in `.md`, and is not
        exactly `owner/repo` shape — a local Markdown path.
      - "opaque": anything else (e.g. a local slug like `STORY-006`).
    """
    raw = raw.strip()
    if _BARE_OR_HASH_NUMBER_RE.match(raw):
        return "issue_reference"
    if raw.count("/") == 1 and _REPO_SHAPE_RE.match(raw) and not raw.lower().endswith(".md"):
        return "repository"
    if "/" in raw or "\\" in raw or raw.lower().endswith(".md"):
        return "path"
    return "opaque"


def _looks_like_bare_number(raw: str) -> bool:
    return bool(_BARE_OR_HASH_NUMBER_RE.match(raw.strip()))


def _parse_issue_number(raw: str) -> Optional[int]:
    match = _BARE_OR_HASH_NUMBER_RE.match(raw.strip())
    if not match:
        return None
    return int(match.group(1))


def _known_provider(config: Optional[dict]) -> Optional[str]:
    if not isinstance(config, dict):
        return None
    tracker_cfg = config.get("tracker")
    if not isinstance(tracker_cfg, dict):
        return None
    provider = tracker_cfg.get("type")
    return provider if provider in PROVIDERS else None


def _extract_max_bytes(config: Optional[dict]) -> int:
    if isinstance(config, dict):
        context_cfg = config.get("context")
        if isinstance(context_cfg, dict):
            value = context_cfg.get("max_bytes")
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
    return DEFAULT_MAX_BYTES


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sanitize_text(text: Optional[str], max_bytes: Optional[int]) -> tuple:
    """Strip control characters and normalize line endings, then bound the
    result to `max_bytes` (UTF-8 encoded), truncating on a safe character
    boundary. Returns (sanitized_text, was_truncated)."""
    if not text:
        return "", False
    cleaned = _CONTROL_CHARS_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    if not max_bytes or max_bytes <= 0:
        return cleaned, False
    encoded = cleaned.encode("utf-8")
    if len(encoded) <= max_bytes:
        return cleaned, False
    truncated_text = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated_text, True


def resolve_work_item(
    raw_identifier: str,
    config: Optional[dict],
    *,
    project_root: Optional[Path] = None,
    runner: Callable[..., "subprocess.CompletedProcess"] = subprocess.run,
) -> WorkItemResult:
    """Resolve `raw_identifier` under the single tracker `config` names
    (`config["tracker"]["type"]`). Never raises for a recognized failure —
    see the module docstring.

    `config=None` (or a config with no recognizable `tracker.type`) means
    no provider is known at all: a bare-number identifier is rejected as
    `ambiguous_identifier` rather than guessed; anything else is
    `unsupported_tracker`.
    """
    if not isinstance(raw_identifier, str) or not raw_identifier.strip():
        return WorkItemResult.fail(
            ERROR_MALFORMED_ITEM, "identifier must be a non-empty string", identifier=raw_identifier
        )

    provider = _known_provider(config)
    if provider is None:
        if _looks_like_bare_number(raw_identifier):
            return WorkItemResult.fail(
                ERROR_AMBIGUOUS_IDENTIFIER,
                f"'{raw_identifier}' is a bare number and no tracker is configured; "
                "GitHub, GitLab, and local identifiers are never guessed from shape alone",
                identifier=raw_identifier,
            )
        return WorkItemResult.fail(
            ERROR_UNSUPPORTED_TRACKER,
            "no tracker is configured (config.tracker.type is missing or unrecognized)",
            identifier=raw_identifier,
        )

    tracker_cfg = config["tracker"]
    max_bytes = _extract_max_bytes(config)

    if provider == PROVIDER_LOCAL:
        return _resolve_local(
            raw_identifier,
            tracker_cfg,
            config.get("identifier") if isinstance(config, dict) else None,
            project_root or Path.cwd(),
            max_bytes,
        )
    if provider == PROVIDER_GITHUB:
        return _resolve_github(raw_identifier, tracker_cfg, max_bytes, runner)
    if provider == PROVIDER_GITLAB:
        return _resolve_gitlab(raw_identifier, tracker_cfg, max_bytes, runner)

    return WorkItemResult.fail(  # pragma: no cover - _known_provider already filters this
        ERROR_UNSUPPORTED_TRACKER, f"unsupported tracker.type: {provider!r}", identifier=raw_identifier
    )


# ---------------------------------------------------------------------------
# Local Markdown adapter — no network access.
# ---------------------------------------------------------------------------


def _is_unsafe_relative_path(raw: str) -> bool:
    """Delegate to `scripts.config`'s already-tested safe-relative-path
    check (absolute/`~`/drive-letter/`..`-component rejection, and never
    `str.lstrip("./")` — the exact v1 dotfile bug
    `tests/test_v1_characterization.py` characterizes) instead of
    re-deriving the same rules here."""
    return config_module._relative_path_issue(raw) is not None


def _resolve_local_path(
    raw_identifier: str, local_root: Path, project_root: Path, identifier_cfg: Optional[dict]
):
    """Return (file_path, canonical_id) or (None, None) if the identifier's
    shape/safety is invalid. Both a bare ID and an explicit path resolve
    through here so they land on the same canonical identity when they
    name the same file — and, symmetrically, two *different* files never
    collapse onto the same canonical identity: a path identifier's
    canonical id is its full location relative to `local_root` (e.g.
    "epics/STORY-100"), not just the filename stem, so
    "epics/STORY-100.md" and "archive/STORY-100.md" stay distinct. A bare
    ID always names a root-level file, so its canonical id (the id itself)
    already agrees with this scheme.

    A path identifier is accepted in either of two equally valid forms —
    relative to the project root (`docs/work-items/STORY-006.md`, matching
    how `tracker.local_root` itself is expressed) or relative to
    `local_root` directly (`STORY-006.md`) — provided it resolves inside
    `local_root` either way. Safety is re-checked here against the
    resolved path (not just the raw string via `_is_unsafe_relative_path`
    above) so a resolved ".." or symlink can never land outside
    `local_root`."""
    raw = raw_identifier.strip()
    if _is_unsafe_relative_path(raw):
        return None, None

    shape = classify_identifier_shape(raw)
    if shape == "repository":
        # "owner/repo"-shaped text is still a legitimate two-segment local
        # path (e.g. "epics/STORY-006"); treat it like any other path here.
        shape = "path"

    if shape == "path":
        candidate = Path(raw)
        if candidate.is_absolute():
            return None, None
        local_root_resolved = local_root.resolve()
        for base in (project_root, local_root):
            file_path = base / candidate
            try:
                relative = file_path.resolve().relative_to(local_root_resolved)
            except (ValueError, OSError):
                continue
            canonical_id = relative.with_suffix("").as_posix()
            return file_path, canonical_id
        return None, None

    # "issue_reference" or "opaque": treat as a bare local ID.
    if identifier_cfg and isinstance(identifier_cfg.get("pattern"), str):
        try:
            pattern = re.compile(identifier_cfg["pattern"])
        except re.error:
            pattern = None
    else:
        pattern = None

    if pattern is not None:
        if not pattern.fullmatch(raw):
            return None, None
    elif not _FALLBACK_LOCAL_ID_RE.match(raw):
        return None, None

    return local_root / f"{raw}.md", raw


def _parse_local_markdown(text: str) -> dict:
    meta: dict = {}
    body_start = 0
    match = _FRONT_MATTER_RE.match(text)
    if match:
        for line in match.group(1).splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip()
        body_start = match.end()

    title = ""
    body_lines = []
    heading_consumed = False
    for line in text[body_start:].splitlines():
        if not heading_consumed and line.strip().startswith("#"):
            title = line.strip().lstrip("#").strip()
            heading_consumed = True
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip("\n")

    blockers_raw = meta.get("blockers", "")
    blockers = tuple(b.strip() for b in blockers_raw.split(",") if b.strip())

    return {
        "title": title,
        "body": body,
        "state": meta.get("state", "unknown"),
        "blockers": blockers,
        "updated_at": meta.get("updated_at") or None,
    }


def _resolve_local(
    raw_identifier: str,
    tracker_cfg: dict,
    identifier_cfg: Optional[dict],
    project_root: Path,
    max_bytes: int,
) -> WorkItemResult:
    local_root_str = tracker_cfg.get("local_root")
    if not local_root_str or not isinstance(local_root_str, str):
        return WorkItemResult.fail(
            ERROR_UNSUPPORTED_TRACKER, "tracker.local_root is required when tracker.type is 'local'"
        )
    local_root = (project_root / local_root_str).resolve()

    file_path, canonical = _resolve_local_path(raw_identifier, local_root, project_root, identifier_cfg)
    if file_path is None:
        return WorkItemResult.fail(
            ERROR_MALFORMED_ITEM,
            f"'{raw_identifier}' is not a safe or recognizable local work-item identifier",
            identifier=raw_identifier,
            provider=PROVIDER_LOCAL,
        )

    if not file_path.is_file():
        return WorkItemResult.fail(
            ERROR_NOT_FOUND,
            f"local work item not found: {file_path}",
            identifier=raw_identifier,
            provider=PROVIDER_LOCAL,
        )

    try:
        raw_bytes = file_path.read_bytes()
    except OSError as exc:
        return WorkItemResult.fail(
            ERROR_NOT_FOUND, f"could not read local work item: {exc}", identifier=raw_identifier
        )

    text = raw_bytes.decode("utf-8", errors="replace")
    parsed = _parse_local_markdown(text)

    sanitized_title, _ = _sanitize_text(parsed["title"], max_bytes)
    sanitized_body, truncated = _sanitize_text(parsed["body"], max_bytes)

    if not sanitized_title.strip() and not sanitized_body.strip():
        return WorkItemResult.fail(
            ERROR_MALFORMED_ITEM,
            f"local work item has no title or body content: {file_path}",
            identifier=raw_identifier,
            provider=PROVIDER_LOCAL,
        )

    try:
        source = str(file_path.relative_to(project_root.resolve()))
    except ValueError:
        source = str(file_path)

    item = WorkItem(
        provider=PROVIDER_LOCAL,
        canonical_id=f"{PROVIDER_LOCAL}:{canonical}",
        title=sanitized_title or canonical,
        source=source,
        body=sanitized_body,
        state=parsed["state"],
        blockers=parsed["blockers"],
        updated_at=parsed["updated_at"],
        content_digest=_digest(sanitized_title + "\n" + sanitized_body),
        truncated=truncated,
    )
    return WorkItemResult.ok_item(item)


# ---------------------------------------------------------------------------
# Remote adapters — explicit setup/skill operations only (ADR-0005).
# ---------------------------------------------------------------------------


def _classify_cli_failure(stderr: str) -> str:
    lower = (stderr or "").lower()
    not_found_markers = ("could not resolve", "not found", "404", "couldn't find", "no such issue")
    auth_markers = ("auth", "unauthorized", "401", "403", "not logged in", "permission denied")
    if any(marker in lower for marker in not_found_markers):
        return ERROR_NOT_FOUND
    if any(marker in lower for marker in auth_markers):
        return ERROR_AUTH_FAILED
    return ERROR_CLI_ERROR


def _run_cli(
    args: list, runner: Callable[..., "subprocess.CompletedProcess"], provider: str
):
    """Invoke `args` through `runner`, mapping every non-recognized-output
    failure to a structured (kind, message) pair instead of letting an
    exception escape — including an unexpected exception raised by `runner`
    itself (e.g. a broken CI environment), which becomes `ERROR_CLI_ERROR`
    rather than propagating. This is what makes a remote failure something
    a caller can branch on instead of a traceback that could interrupt an
    in-progress active-state write (ADR-0002). Returns (completed_process,
    None) on a clean invocation, or (None, WorkItemError) otherwise."""
    try:
        completed = runner(args, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return None, WorkItemError(
            ERROR_MISSING_CLI, f"the '{args[0]}' CLI is not installed or not on PATH", provider=provider
        )
    except subprocess.TimeoutExpired:
        return None, WorkItemError(
            ERROR_CLI_ERROR, f"'{args[0]}' timed out", provider=provider
        )
    except Exception as exc:  # noqa: BLE001 - deliberately broad: see docstring
        return None, WorkItemError(ERROR_CLI_ERROR, str(exc) or repr(exc), provider=provider)

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        kind = _classify_cli_failure(stderr)
        message = stderr or f"'{' '.join(args)}' exited with status {completed.returncode}"
        return None, WorkItemError(kind, message, provider=provider)

    return completed, None


@dataclass(frozen=True)
class _RemoteProviderSpec:
    """The only thing that differs between the GitHub and GitLab adapters:
    which CLI to invoke, which JSON field names it uses, and the fallback
    URL shape. `_resolve_remote` is the one shared implementation; adding a
    third CLI-backed tracker means adding a spec here, not a third copy of
    the resolve/parse/sanitize pipeline."""

    provider: str
    build_args: Callable[[int, str], list]
    number_field: str
    body_field: str
    url_field: str
    updated_field: str
    url_template: str
    repository_shape_noun: str


def _github_args(number: int, repository: str) -> list:
    return [
        "gh",
        "issue",
        "view",
        str(number),
        "--repo",
        repository,
        "--json",
        "number,title,body,state,url,updatedAt",
    ]


def _gitlab_args(number: int, repository: str) -> list:
    return ["glab", "issue", "view", str(number), "--repo", repository, "--output", "json"]


_GITHUB_SPEC = _RemoteProviderSpec(
    provider=PROVIDER_GITHUB,
    build_args=_github_args,
    number_field="number",
    body_field="body",
    url_field="url",
    updated_field="updatedAt",
    url_template="https://github.com/{repository}/issues/{number}",
    repository_shape_noun="owner/repo",
)

_GITLAB_SPEC = _RemoteProviderSpec(
    provider=PROVIDER_GITLAB,
    build_args=_gitlab_args,
    number_field="iid",
    body_field="description",
    url_field="web_url",
    updated_field="updated_at",
    url_template="https://gitlab.com/{repository}/-/issues/{number}",
    repository_shape_noun="group/project",
)


def _resolve_remote(
    raw_identifier: str,
    tracker_cfg: dict,
    max_bytes: int,
    runner: Callable,
    spec: _RemoteProviderSpec,
) -> WorkItemResult:
    repository = tracker_cfg.get("repository")
    if not repository or not isinstance(repository, str):
        return WorkItemResult.fail(
            ERROR_UNSUPPORTED_TRACKER,
            f"tracker.repository is required when tracker.type is '{spec.provider}'",
        )

    if classify_identifier_shape(raw_identifier) == "repository":
        return WorkItemResult.fail(
            ERROR_MALFORMED_ITEM,
            f"'{raw_identifier}' looks like a repository identifier ({spec.repository_shape_noun}), "
            "not a work-item identifier (expected e.g. '#123')",
            identifier=raw_identifier,
            provider=spec.provider,
        )

    number = _parse_issue_number(raw_identifier)
    if number is None:
        return WorkItemResult.fail(
            ERROR_MALFORMED_ITEM,
            f"'{raw_identifier}' is not a valid {spec.provider} issue identifier (expected e.g. '#123')",
            identifier=raw_identifier,
            provider=spec.provider,
        )

    args = spec.build_args(number, repository)
    completed, error = _run_cli(args, runner, spec.provider)
    if error is not None:
        return WorkItemResult(item=None, error=error)

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return WorkItemResult.fail(
            ERROR_MALFORMED_ITEM,
            f"{args[0]} returned output that is not valid JSON",
            identifier=raw_identifier,
            provider=spec.provider,
        )

    if not isinstance(data, dict) or spec.number_field not in data:
        return WorkItemResult.fail(
            ERROR_MALFORMED_ITEM,
            f"{args[0]} returned JSON missing the expected '{spec.number_field}' field",
            identifier=raw_identifier,
            provider=spec.provider,
        )

    title, _ = _sanitize_text(data.get("title", ""), max_bytes)
    body, truncated = _sanitize_text(data.get(spec.body_field, ""), max_bytes)
    item_number = data[spec.number_field]

    item = WorkItem(
        provider=spec.provider,
        canonical_id=f"{spec.provider}:{repository}#{item_number}",
        title=title,
        source=data.get(spec.url_field)
        or spec.url_template.format(repository=repository, number=item_number),
        body=body,
        state=str(data.get("state", "unknown")),
        blockers=(),
        updated_at=data.get(spec.updated_field),
        content_digest=_digest(title + "\n" + body),
        truncated=truncated,
    )
    return WorkItemResult.ok_item(item)


def _resolve_github(
    raw_identifier: str, tracker_cfg: dict, max_bytes: int, runner: Callable
) -> WorkItemResult:
    return _resolve_remote(raw_identifier, tracker_cfg, max_bytes, runner, _GITHUB_SPEC)


def _resolve_gitlab(
    raw_identifier: str, tracker_cfg: dict, max_bytes: int, runner: Callable
) -> WorkItemResult:
    return _resolve_remote(raw_identifier, tracker_cfg, max_bytes, runner, _GITLAB_SPEC)
