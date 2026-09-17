"""Structural and behavioral-substitute tests for the STORY-007
`work-contract` discipline: `skills/work-contract/SKILL.md`,
`templates/local-work-item.md`, and the `evals/work-contract/` eval suite.

`claude plugin eval` (the real behavioral check named in STORY-007's
verification commands) is gated behind early access in this environment
("`plugin eval` is currently in early access", the same gate
`tests/test_reconcile_and_migration_skills.py` documented for STORY-016)
and could not be run. These tests are the offline substitute, following
that file's established convention: they mechanically verify the SKILL.md
carries the guidance STORY-007 requires, that `templates/local-work-item.md`
is actually compatible with STORY-006's `scripts/work_items.py` local
adapter (not just superficially similar), and that each eval case
directory is well-formed and actually exercises the distinction its
acceptance criteria call for. They do not invoke a model and cannot
confirm behavioral compliance the way a real eval run would.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import config, work_items  # noqa: E402

SKILLS_DIR = REPO_ROOT / "skills"
TEMPLATES_DIR = REPO_ROOT / "templates"
EVALS_DIR = REPO_ROOT / "evals"

REQUIRED_SECTION_HEADINGS = (
    "what to build",
    "blocked by",
    "acceptance criteria",
    "may touch",
    "must not touch",
    "verification commands",
    "out of scope",
    "completion evidence",
)

# Reserved-name disjointness against Matt Pocock's shipped mattpocock-skills
# names is already checked plugin-wide, for every skills/*/SKILL.md
# (including this one), by
# tests.test_plugin_smoke.SkillSkeletonTests.test_no_skill_under_skills_dir_uses_a_reserved_matt_name
# -- no need for a second, independently-maintained copy of that name list
# here.


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(path: Path) -> dict:
    text = read(path)
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{path} has no YAML frontmatter block"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def case_dirs(skill_eval_dir: Path) -> list[Path]:
    return sorted(p.parent for p in skill_eval_dir.glob("*/prompt.md") if p.is_file())


def parse_flow_list(value: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9][A-Za-z0-9_.\-]*", value))


def case_tags(case_dir: Path) -> set[str]:
    fields = frontmatter(case_dir / "prompt.md")
    return parse_flow_list(fields.get("tags", ""))


class WorkContractSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_md = SKILLS_DIR / "work-contract" / "SKILL.md"
        self.text = read(self.skill_md)
        self.lowered = self.text.lower()
        self.fields = frontmatter(self.skill_md)

    def test_has_unique_frontmatter_name(self) -> None:
        self.assertEqual(self.fields["name"], "work-contract")
        # Disjointness from Matt Pocock's reserved skill names is checked
        # plugin-wide by tests.test_plugin_smoke -- see the module-level
        # note above.

    def test_defines_every_required_section(self) -> None:
        for heading in REQUIRED_SECTION_HEADINGS:
            self.assertIn(
                heading, self.lowered, f"SKILL.md never mentions the {heading!r} section"
            )

    def test_never_invents_identity_or_blocking_edges(self) -> None:
        self.assertIn("canonical", self.lowered)
        self.assertIn("invents a new identifier", self.lowered)
        self.assertIn("blocking edge", self.lowered)

    def test_defers_decomposition_to_to_tickets(self) -> None:
        self.assertIn("to-tickets", self.text)
        self.assertIn("defer", self.lowered)
        self.assertIn("decompos", self.lowered)

    def test_teaches_vertical_slicing(self) -> None:
        self.assertIn("vertical slice", self.lowered)

    def test_rejects_vague_or_placeholder_verification_prose(self) -> None:
        for banned in ("run the tests", "verify manually", "check it works", "todo"):
            self.assertIn(banned, self.lowered, f"SKILL.md never names {banned!r} as rejected")
        self.assertIn("ellipsis", self.lowered)
        self.assertIn("...", self.text)

    def test_rejects_unsafe_commands_even_when_they_actually_exist(self) -> None:
        # STORY-007's acceptance criterion is "identify missing/unsafe/
        # placeholder commands" -- existing-but-dangerous is a third,
        # distinct failure mode from missing and from vague/placeholder
        # prose, and must be named explicitly, not left implied by the
        # "must already exist" rule alone.
        self.assertIn("unsafe", self.lowered)
        self.assertIn("existing is necessary but not sufficient", self.lowered)

    def test_requires_checking_actual_repository_configuration(self) -> None:
        for marker in ("package.json", "makefile", "pytest"):
            self.assertIn(marker, self.lowered)

    def test_forbids_fabricating_standard_sounding_commands(self) -> None:
        self.assertIn("standard", self.lowered)
        self.assertIn("fabricate", self.lowered)

    def test_requires_each_command_mapped_to_a_criterion(self) -> None:
        self.assertIn("must map to at least one acceptance criterion", self.lowered)

    def test_allows_explicit_no_automated_verification_acknowledgment(self) -> None:
        self.assertIn("no automated verification", self.lowered)
        self.assertIn("silently empty", self.lowered)

    def test_completion_evidence_is_filled_after_not_before_execution(self) -> None:
        self.assertIn("after execution", self.lowered)
        self.assertIn("pending", self.lowered)
        self.assertIn("pre-filled", self.lowered)

    def test_excludes_lifecycle_status_persona_model_routing_and_active_work(self) -> None:
        self.assertIn("lifecycle status", self.lowered)
        self.assertIn("persona", self.lowered)
        self.assertIn("specific model", self.lowered)
        self.assertIn("active-work", self.lowered)

    def test_references_migration_safety_without_duplicating_its_phase_ceremony(self) -> None:
        self.assertIn("migration-safety", self.text)
        self.assertIn("without re-deriving", self.lowered)

    def test_references_reconcile_docs_as_a_distinct_sibling(self) -> None:
        self.assertIn("reconcile-docs", self.text)

    def test_does_not_own_scope_enforcement_at_tool_call_time(self) -> None:
        self.assertIn("does not enforce", self.lowered)

    def test_skill_markdown_never_assumes_scripts_were_copied_into_project(self) -> None:
        # Mirrors tests/test_plugin_smoke.py's plugin-wide check. This
        # SKILL.md carries no runnable commands, so it should reference no
        # scripts/ path at all -- verified here rather than assumed.
        for match in re.finditer(r"[^\s`]*\bscripts/[\w.\-/]+", self.text):
            reference = match.group(0)
            self.assertTrue(
                reference.startswith("${CLAUDE_PLUGIN_ROOT}/scripts/"),
                f"{self.skill_md} references {reference!r} without ${{CLAUDE_PLUGIN_ROOT}}",
            )


class LocalWorkItemTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template_path = TEMPLATES_DIR / "local-work-item.md"
        self.text = read(self.template_path)
        self.lowered = self.text.lower()

    def test_template_exists(self) -> None:
        self.assertTrue(self.template_path.is_file())

    def test_front_matter_has_state_blockers_and_updated_at(self) -> None:
        match = re.match(r"^---\n(.*?)\n---\n", self.text, re.DOTALL)
        self.assertIsNotNone(match, "template has no YAML front matter block")
        block = match.group(1)
        for field in ("state:", "blockers:", "updated_at:"):
            self.assertIn(field, block)

    def test_defines_every_required_section(self) -> None:
        for heading in REQUIRED_SECTION_HEADINGS:
            self.assertIn(f"## {heading}", self.lowered)

    def test_never_invents_a_separate_identifier_scheme(self) -> None:
        self.assertIn("never invent a different identifier scheme", self.lowered)

    def test_verification_commands_guidance_covers_unsafe_commands(self) -> None:
        self.assertIn("be safe to run as a verification step", self.lowered)

    def test_completion_evidence_defaults_to_pending(self) -> None:
        self.assertIn("pending", self.lowered)
        self.assertIn("never pre-fill", self.lowered)

    def test_points_to_the_work_contract_skill(self) -> None:
        self.assertIn("skills/work-contract/skill.md", self.lowered)

    def test_is_parseable_by_the_story_006_local_adapter_end_to_end(self) -> None:
        """The template must be a real, working local-tracker Markdown file
        -- not just superficially similar prose. Fill in its placeholders
        and resolve it through the actual STORY-006 `resolve_work_item`
        public entry point, exactly as a real project's `local` tracker
        would."""
        filled = self.text
        filled = filled.replace("state: draft", "state: ready")
        filled = filled.replace("blockers:\n", "blockers: STORY-010\n", 1)
        filled = filled.replace("updated_at:\n", "updated_at: 2026-01-01T00:00:00Z\n", 1)
        filled = filled.replace("{{WORK_ITEM_ID}}", "STORY-900")
        filled = filled.replace("{{TITLE}}", "Fixture ticket filled from the template")
        filled = filled.replace("{{WHAT_TO_BUILD}}", "A user-observable change.")
        filled = filled.replace("{{BLOCKED_BY}}", "local:STORY-010")
        filled = filled.replace("{{ACCEPTANCE_CRITERIA}}", "- Observable outcome one.")
        filled = filled.replace("{{MAY_TOUCH}}", "- src/example.py")
        filled = filled.replace("{{MUST_NOT_TOUCH}}", "- src/unrelated.py")
        filled = filled.replace("{{VERIFICATION_COMMANDS}}", "```bash\npython3 -m unittest\n```")
        filled = filled.replace("{{OUT_OF_SCOPE}}", "- Not handling case Y.")
        self.assertNotIn("{{", filled, "template placeholder left unfilled by this test's fixture")

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "STORY-900.md").write_text(filled, encoding="utf-8")

            cfg = dict(config.DEFAULT_CONFIG)
            cfg["tracker"] = {"type": "local", "local_root": "."}
            cfg["context"] = {"max_bytes": 20000}

            result = work_items.resolve_work_item(
                "STORY-900", cfg, project_root=project_root
            )

        self.assertTrue(result.ok, f"template-derived ticket failed to resolve: {result.error}")
        item = result.item
        self.assertEqual(item.canonical_id, "local:STORY-900")
        self.assertEqual(item.state, "ready")
        self.assertEqual(item.blockers, ("STORY-010",))
        self.assertIn("Fixture ticket filled from the template", item.title)
        self.assertIn("## What to build", item.body)
        self.assertIn("## Verification commands", item.body)
        self.assertIn("## Completion evidence", item.body)


class WorkContractEvalCaseStructureTests(unittest.TestCase):
    """Every case directory must look like `claude plugin eval` expects: a
    `prompt.md` with YAML frontmatter and at least one grader under
    `graders/*.md`, itself carrying a `type:` field."""

    def setUp(self) -> None:
        self.cases = case_dirs(EVALS_DIR / "work-contract")

    def test_has_eval_cases(self) -> None:
        self.assertTrue(self.cases, "no work-contract eval cases found")

    def test_every_case_is_well_formed(self) -> None:
        for case_dir in self.cases:
            prompt_md = case_dir / "prompt.md"
            self.assertTrue(prompt_md.is_file(), f"{case_dir} has no prompt.md")
            fields = frontmatter(prompt_md)
            self.assertIn("name", fields)

            graders_dir = case_dir / "graders"
            self.assertTrue(graders_dir.is_dir(), f"{case_dir} has no graders/")
            grader_files = sorted(graders_dir.glob("*.md"))
            self.assertTrue(grader_files, f"{case_dir} has no grader files")
            for grader_md in grader_files:
                grader_fields = frontmatter(grader_md)
                self.assertIn("type", grader_fields, f"{grader_md} has no type:")


class WorkContractEvalCoverageTests(unittest.TestCase):
    """STORY-007 acceptance criterion: eval fixtures include feature, bug,
    documentation-only, migration, and external-manual-step work, each
    exercising a distinct acceptance-criteria shape."""

    def setUp(self) -> None:
        self.cases = case_dirs(EVALS_DIR / "work-contract")
        self.by_tag = {}
        for case_dir in self.cases:
            for tag in case_tags(case_dir):
                self.by_tag.setdefault(tag, []).append(case_dir)

    def test_has_a_feature_case(self) -> None:
        self.assertIn("feature", self.by_tag)

    def test_has_a_bug_case(self) -> None:
        self.assertIn("bug", self.by_tag)

    def test_has_a_documentation_only_case(self) -> None:
        self.assertIn("documentation-only", self.by_tag)

    def test_has_a_migration_case(self) -> None:
        self.assertIn("migration", self.by_tag)

    def test_has_an_external_manual_step_case(self) -> None:
        self.assertIn("external-manual", self.by_tag)

    def test_migration_case_references_migration_safety_without_duplication(self) -> None:
        migration_cases = self.by_tag["migration"]
        found_reference = False
        found_no_duplication_grader = False
        for case_dir in migration_cases:
            prompt_text = read(case_dir / "prompt.md").lower()
            if "migration-safety" in prompt_text:
                found_reference = True
            for grader_md in (case_dir / "graders").glob("*.md"):
                text = read(grader_md).lower()
                if "duplicat" in text or "restate" in text:
                    found_no_duplication_grader = True
        self.assertTrue(found_reference, "migration case never references migration-safety")
        self.assertTrue(
            found_no_duplication_grader,
            "migration case has no grader checking against duplicating migration-safety's content",
        )

    def test_documentation_only_case_demonstrates_no_automated_verification_path(self) -> None:
        cases = self.by_tag["documentation-only"]
        found = False
        for case_dir in cases:
            for grader_md in (case_dir / "graders").glob("*.md"):
                if "no automated verification" in read(grader_md).lower():
                    found = True
        self.assertTrue(
            found, "documentation-only case has no grader checking the acknowledgment path"
        )

    def test_external_manual_case_demonstrates_no_automated_verification_path(self) -> None:
        cases = self.by_tag["external-manual"]
        found = False
        for case_dir in cases:
            for grader_md in (case_dir / "graders").glob("*.md"):
                if "no automated verification" in read(grader_md).lower():
                    found = True
        self.assertTrue(
            found, "external-manual case has no grader checking the acknowledgment path"
        )

    def test_feature_and_bug_cases_check_identity_and_blocker_preservation(self) -> None:
        for tag in ("feature", "bug"):
            cases = self.by_tag[tag]
            self.assertTrue(cases)
        # The feature case is the one STORY-007 designates for the
        # "enrich without changing identity/blocking edges" criterion.
        feature_case = self.by_tag["feature"][0]
        grader_text = " ".join(
            read(g).lower() for g in (feature_case / "graders").glob("*.md")
        )
        self.assertIn("identity", grader_text)
        self.assertIn("blocker", grader_text)

    def test_each_case_carries_a_no_vague_or_no_fabrication_grader(self) -> None:
        # Check the grader's actual matching field (pattern/criteria), not
        # just any prose in the file -- a mention of "invent" in a grader's
        # explanatory paragraph is not the same as that grader actually
        # checking for it.
        for case_dir in self.cases:
            matching_field_text = " ".join(
                frontmatter(g).get("pattern", frontmatter(g).get("criteria", "")).lower()
                for g in (case_dir / "graders").glob("*.md")
            )
            self.assertTrue(
                "run the tests" in matching_field_text
                or "fabricat" in matching_field_text
                or "invent" in matching_field_text,
                f"{case_dir} has no grader whose pattern/criteria guards against "
                "vague or fabricated verification",
            )

    def test_bug_case_rejects_the_unsafe_real_command_it_was_offered(self) -> None:
        # STORY-007's "identify ... unsafe ... commands" acceptance
        # criterion needs a case where a real, existing-in-the-repo command
        # is nonetheless unsafe to use for verification -- distinct from
        # both the missing-command and placeholder-prose failure modes the
        # other cases exercise.
        bug_case = self.by_tag["bug"][0]
        prompt_text = read(bug_case / "prompt.md").lower()
        self.assertIn("reset-db", prompt_text)
        self.assertIn("not a safe", prompt_text)
        grader_text = " ".join(
            read(g).lower() for g in (bug_case / "graders").glob("*.md")
        )
        self.assertIn("unsafe", grader_text)
        self.assertIn("reset-db", grader_text)


if __name__ == "__main__":
    unittest.main()
