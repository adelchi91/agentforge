"""AgentForge version synchronization check (STORY-020).

STORY-002 established `VERSION` at the repository root as "a single
machine-readable version source, kept in sync with
`.claude-plugin/plugin.json`'s `version` field" -- but nothing ever
enforced that claim mechanically; keeping the two files aligned was a
matter of remembering to edit both. This script is that enforcement: a
real check with real failure modes, run as one of STORY-020's own listed
verification commands (`python3 scripts/check_version_sync.py`) and
wired into CI (`.github/workflows/ci.yml`).

What it checks, every run:

  1. `VERSION` contains exactly one PEP 440 / SemVer-shaped version
     string (`X.Y.Z` optionally followed by `-<prerelease>`), on its own
     line, with no other content.
  2. `.claude-plugin/plugin.json`'s `"version"` field is present and
     byte-identical to `VERSION`'s contents.
  3. `CHANGELOG.md`'s first `## [...]` release heading names the same
     version. The heading may carry a trailing `- Unreleased` /
     `- YYYY-MM-DD` annotation (Keep a Changelog style, as already used
     in this file) after the bracketed version -- only the bracketed
     version itself must match.
  4. If `.claude-plugin/marketplace.json` ever adds a top-level
     `"version"` field (it does not today -- a plugin marketplace entry
     is not required to carry one, and this repo's currently does not),
     it must also match. Its absence is not an error.

Every failure is reported (not just the first one found), each naming
the exact file, the exact value read, and what it was compared against,
so a human fixing this never has to re-run the script to discover a
second mismatch. Exit 0 with no output when everything is in sync; exit
1 with every mismatch printed to stderr otherwise. No network access, no
third-party dependency -- stdlib `json`/`re` only, matching every other
script in this directory (ADR-0004/ADR-0005).

This script intentionally does not *write* any file -- bumping the
version for a release is a deliberate, reviewed edit (see
"Release process" in `docs/release-v2.md`), not something a CI check
should do on a maintainer's behalf.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# X.Y.Z, optionally with a -prerelease suffix (e.g. "2.0.0-dev",
# "2.0.0-rc.1"). Deliberately stricter than PEP 440's full grammar --
# this repo only ever needs to author a handful of shapes, and a looser
# pattern would let a typo like "2.0" or "v2.0.0" silently pass.
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")

# Matches "## [2.0.0-dev] - Unreleased" or "## [1.2.3] - 2026-01-01" --
# the bracketed version is capture group 1; everything after the closing
# bracket is free-form and not checked here.
CHANGELOG_HEADING_PATTERN = re.compile(r"^##\s*\[([^\]]+)\]")


@dataclass(frozen=True)
class VersionIssue:
    location: str
    detail: str

    def format(self) -> str:
        return f"{self.location}: {self.detail}"


def _read_text(path: Path, display_name: str) -> tuple[Optional[str], list[VersionIssue]]:
    """Reads `path` as UTF-8 text. On any OSError (missing file, is a
    directory, permission denied, ...), reports the issue against
    `display_name` -- the project-relative label callers want in output
    -- rather than the resolved absolute path."""
    try:
        return path.read_text(encoding="utf-8"), []
    except OSError as exc:
        return None, [VersionIssue(display_name, f"cannot read file: {exc.strerror or exc}")]


def read_version_file(root: Path) -> tuple[Optional[str], list[VersionIssue]]:
    """Reads VERSION. Requires exactly one non-blank line shaped like a
    version string -- trailing whitespace/newline is tolerated, but a
    second non-blank line or extra content on the version line is not
    (both indicate the file was edited by hand incorrectly)."""
    path = root / "VERSION"
    text, issues = _read_text(path, "VERSION")
    if text is None:
        return None, issues

    lines = [line for line in text.splitlines() if line.strip() != ""]
    if len(lines) != 1:
        return None, [
            VersionIssue(
                "VERSION",
                f"expected exactly one non-blank line containing the version, found {len(lines)}",
            )
        ]

    version = lines[0].strip()
    if not VERSION_PATTERN.match(version):
        return None, [
            VersionIssue(
                "VERSION",
                f"{version!r} is not a valid X.Y.Z or X.Y.Z-prerelease version string",
            )
        ]
    return version, []


def read_plugin_manifest_version(root: Path) -> tuple[Optional[str], list[VersionIssue]]:
    path = root / ".claude-plugin" / "plugin.json"
    text, issues = _read_text(path, ".claude-plugin/plugin.json")
    if text is None:
        return None, issues

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [VersionIssue(".claude-plugin/plugin.json", f"invalid JSON: {exc}")]

    if not isinstance(data, dict) or "version" not in data:
        return None, [
            VersionIssue(".claude-plugin/plugin.json", 'missing required "version" field')
        ]

    version = data["version"]
    if not isinstance(version, str) or not VERSION_PATTERN.match(version):
        return None, [
            VersionIssue(
                ".claude-plugin/plugin.json",
                f'"version" field {version!r} is not a valid X.Y.Z or X.Y.Z-prerelease string',
            )
        ]
    return version, []


def read_marketplace_manifest_version(root: Path) -> tuple[Optional[str], list[VersionIssue]]:
    """Returns (None, []) when the field is simply absent -- a
    marketplace entry carrying no top-level version is not itself an
    error; only a *present but mismatched* value is."""
    path = root / ".claude-plugin" / "marketplace.json"
    text, issues = _read_text(path, ".claude-plugin/marketplace.json")
    if text is None:
        return None, issues

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [VersionIssue(".claude-plugin/marketplace.json", f"invalid JSON: {exc}")]

    if not isinstance(data, dict) or "version" not in data:
        return None, []

    version = data["version"]
    if not isinstance(version, str) or not VERSION_PATTERN.match(version):
        return None, [
            VersionIssue(
                ".claude-plugin/marketplace.json",
                f'"version" field {version!r} is not a valid X.Y.Z or X.Y.Z-prerelease string',
            )
        ]
    return version, []


def read_changelog_version(root: Path) -> tuple[Optional[str], list[VersionIssue]]:
    path = root / "CHANGELOG.md"
    text, issues = _read_text(path, "CHANGELOG.md")
    if text is None:
        return None, issues

    for line in text.splitlines():
        match = CHANGELOG_HEADING_PATTERN.match(line)
        if match:
            heading_version = match.group(1).strip()
            if not VERSION_PATTERN.match(heading_version):
                return None, [
                    VersionIssue(
                        "CHANGELOG.md",
                        f"first release heading {line.strip()!r} does not name a valid "
                        "X.Y.Z or X.Y.Z-prerelease version",
                    )
                ]
            return heading_version, []

    return None, [VersionIssue("CHANGELOG.md", "no '## [<version>]' release heading found")]


def check_version_sync(root: Path) -> list[VersionIssue]:
    """Runs every check and returns every mismatch found (never stops at
    the first one)."""
    issues: list[VersionIssue] = []

    version_file_value, file_issues = read_version_file(root)
    issues.extend(file_issues)

    plugin_value, plugin_issues = read_plugin_manifest_version(root)
    issues.extend(plugin_issues)

    marketplace_value, marketplace_issues = read_marketplace_manifest_version(root)
    issues.extend(marketplace_issues)

    changelog_value, changelog_issues = read_changelog_version(root)
    issues.extend(changelog_issues)

    # Only compare values we actually managed to read; a read/parse
    # failure above already produced its own issue and comparing a
    # missing value again here would just be noise.
    if version_file_value is not None and plugin_value is not None:
        if version_file_value != plugin_value:
            issues.append(
                VersionIssue(
                    "version sync",
                    f"VERSION is {version_file_value!r} but .claude-plugin/plugin.json's "
                    f'"version" is {plugin_value!r}',
                )
            )

    if version_file_value is not None and changelog_value is not None:
        if version_file_value != changelog_value:
            issues.append(
                VersionIssue(
                    "version sync",
                    f"VERSION is {version_file_value!r} but CHANGELOG.md's most recent "
                    f"release heading names {changelog_value!r}",
                )
            )

    if version_file_value is not None and marketplace_value is not None:
        if version_file_value != marketplace_value:
            issues.append(
                VersionIssue(
                    "version sync",
                    f"VERSION is {version_file_value!r} but "
                    f'.claude-plugin/marketplace.json\'s "version" is {marketplace_value!r}',
                )
            )

    return issues


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_version_sync.py",
        description="Verify VERSION, plugin.json, marketplace.json (if versioned), and "
        "CHANGELOG.md all name the same AgentForge version.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to check (default: this script's repository).",
    )
    args = parser.parse_args(argv)

    issues = check_version_sync(args.root)
    for issue in issues:
        print(issue.format(), file=sys.stderr)

    if issues:
        return 1

    print(f"version sync OK: all sources agree on {read_version_file(args.root)[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
