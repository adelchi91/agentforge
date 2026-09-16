"""Structural tests for the STORY-016 disciplines: `reconcile-docs` and
`migration-safety`, plus their eval suites under `evals/`.

`claude plugin eval` (the real behavioral check named in STORY-016's
verification commands) is gated behind early access in this environment
("`plugin eval` is currently in early access") and could not be run. These
tests are the offline substitute: they mechanically verify the two SKILL.md
files carry the guidance STORY-016 requires, and that each eval case
directory is well-formed and actually exercises the distinction the
acceptance criteria call for (omission vs. intentional exclusion; migration
vs. ordinary feature work; no-delete-before-validation). They do not invoke
a model and cannot confirm behavioral compliance the way a real eval run
would -- see the STORY-016 final report for that caveat.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
EVALS_DIR = REPO_ROOT / "evals"


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
    return sorted(
        p.parent for p in skill_eval_dir.glob("*/prompt.md") if p.is_file()
    )


def parse_flow_list(value: str) -> set[str]:
    """Parse a YAML flow-sequence frontmatter value (e.g. ``[a, "b-c"]``)
    into its member tokens, tolerating quoted or bare entries. Not a full
    YAML parser -- sufficient for the plain tag/plugin lists this suite's
    eval `prompt.md` frontmatter actually uses."""
    return set(re.findall(r"[A-Za-z0-9][A-Za-z0-9_.\-]*", value))


def case_tags(case_dir: Path) -> set[str]:
    fields = frontmatter(case_dir / "prompt.md")
    return parse_flow_list(fields.get("tags", ""))


class ReconcileDocsSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_md = SKILLS_DIR / "reconcile-docs" / "SKILL.md"
        self.text = read(self.skill_md)
        self.fields = frontmatter(self.skill_md)

    def test_has_unique_frontmatter_name(self) -> None:
        self.assertEqual(self.fields["name"], "reconcile-docs")

    def test_describes_the_four_report_categories(self) -> None:
        for term in ("omission", "contradiction", "stale assumption", "intentional exclusion"):
            self.assertIn(
                term, self.text.lower(), f"SKILL.md never mentions {term!r}"
            )

    def test_explicitly_forbids_conflating_omission_and_exclusion(self) -> None:
        self.assertIn("never conflate", self.text.lower())

    def test_disclaims_interviewing_and_ticket_creation(self) -> None:
        lowered = self.text.lower()
        self.assertIn("grilling", lowered)
        self.assertIn("to-spec", lowered)
        self.assertIn("to-tickets", lowered)

    def test_requires_pointers_over_copying_source_text(self) -> None:
        self.assertIn("pointer", self.text.lower())
        self.assertIn("does not copy", self.text.lower())

    # Neither SKILL.md references scripts/ at all (they carry no runnable
    # commands), and tests.test_plugin_smoke.SkillSkeletonTests already
    # checks the ${CLAUDE_PLUGIN_ROOT} convention plugin-wide across every
    # skills/*/SKILL.md -- no need to duplicate that check per skill here.


class MigrationSafetySkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_md = SKILLS_DIR / "migration-safety" / "SKILL.md"
        self.text = read(self.skill_md)
        self.fields = frontmatter(self.skill_md)

    def test_has_unique_frontmatter_name(self) -> None:
        self.assertEqual(self.fields["name"], "migration-safety")

    def test_names_every_phase_in_order(self) -> None:
        phases = ["extract", "expand", "migrate", "validate", "contract", "delete"]
        lowered = self.text.lower()
        positions = [lowered.index(f"**{phase}**") for phase in phases]
        self.assertEqual(
            positions, sorted(positions), "phases are not presented in order"
        )

    def test_states_no_delete_before_validation_as_non_negotiable(self) -> None:
        lowered = self.text.lower()
        self.assertIn("no-delete-before-validation", lowered)
        self.assertIn("not negotiable", lowered)

    def test_documents_migration_classification_signals(self) -> None:
        lowered = self.text.lower()
        self.assertIn("signals this is a migration", lowered)
        self.assertIn("signals this is ordinary feature work", lowered)

    def test_instructs_stopping_for_non_migration_work(self) -> None:
        self.assertIn(
            "stop here", self.text.lower(),
            "skill never instructs the model to bail out of phase ceremony "
            "for non-migration work",
        )

    # See the equivalent note in ReconcileDocsSkillTests: the
    # ${CLAUDE_PLUGIN_ROOT} convention is already checked plugin-wide by
    # tests.test_plugin_smoke, and this SKILL.md references no scripts/
    # path anyway.


class EvalCaseStructureTests(unittest.TestCase):
    """Every case directory must look like `claude plugin eval` expects:
    a `prompt.md` with YAML frontmatter and at least one grader under
    `graders/*.md`, itself carrying a `type:` field."""

    def _assert_well_formed_case(self, case_dir: Path) -> None:
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

    def test_reconcile_docs_cases_are_well_formed(self) -> None:
        cases = case_dirs(EVALS_DIR / "reconcile-docs")
        self.assertTrue(cases, "no reconcile-docs eval cases found")
        for case_dir in cases:
            self._assert_well_formed_case(case_dir)

    def test_migration_safety_cases_are_well_formed(self) -> None:
        cases = case_dirs(EVALS_DIR / "migration-safety")
        self.assertTrue(cases, "no migration-safety eval cases found")
        for case_dir in cases:
            self._assert_well_formed_case(case_dir)


class ReconcileDocsEvalCoverageTests(unittest.TestCase):
    """STORY-016 acceptance criterion: reconciliation identifies both an
    omitted requirement and an intentional exclusion without conflating
    them -- so the eval suite must carry one case of each kind."""

    def setUp(self) -> None:
        self.cases = case_dirs(EVALS_DIR / "reconcile-docs")

    def test_has_an_omission_case(self) -> None:
        self.assertTrue(
            any("omission" in case_tags(c) for c in self.cases),
            "no eval case tagged 'omission'",
        )

    def test_has_an_intentional_exclusion_case(self) -> None:
        self.assertTrue(
            any("exclusion" in case_tags(c) for c in self.cases),
            "no eval case tagged 'exclusion'",
        )

    def test_omission_and_exclusion_cases_share_the_same_missing_requirement(
        self,
    ) -> None:
        # Same PRD item (the admin audit log) must appear as the subject of
        # the omission and exclusion cases specifically, so the only
        # variable between them is whether an exclusion statement exists --
        # the intended minimal pair. Other reconcile-docs cases (e.g. the
        # contradiction/stale-assumption case) are not part of this pair
        # and are exempt.
        pair_cases = [
            c for c in self.cases if case_tags(c) & {"omission", "exclusion"}
        ]
        self.assertTrue(pair_cases, "no omission/exclusion cases found")
        for case_dir in pair_cases:
            prompt_text = read(case_dir / "prompt.md")
            self.assertRegex(prompt_text.lower(), r"audit\s+log")

    def test_only_the_exclusion_case_declares_an_out_of_scope_statement(
        self,
    ) -> None:
        by_tag = {}
        for case_dir in self.cases:
            tags = case_tags(case_dir)
            prompt_text = read(case_dir / "prompt.md").lower()
            if "omission" in tags:
                by_tag["omission"] = prompt_text
            if "exclusion" in tags:
                by_tag["exclusion"] = prompt_text
        self.assertIn("omission", by_tag)
        self.assertIn("exclusion", by_tag)
        self.assertNotIn("out of scope", by_tag["omission"])
        self.assertIn("out of scope", by_tag["exclusion"])


class ReconcileDocsAdditionalCategoryCoverageTests(unittest.TestCase):
    """The skill also defines 'contradiction' and 'stale assumption' as
    first-class report categories (STORY-016's implementation
    requirements), distinct from the omission/exclusion pair above -- the
    eval suite must exercise those too, not just the omission/exclusion
    minimal pair."""

    def setUp(self) -> None:
        self.cases = case_dirs(EVALS_DIR / "reconcile-docs")

    def test_has_a_contradiction_and_stale_assumption_case(self) -> None:
        self.assertTrue(
            any(
                {"contradiction", "stale-assumption"} <= case_tags(c)
                for c in self.cases
            ),
            "no eval case tagged with both 'contradiction' and "
            "'stale-assumption'",
        )


class MigrationSafetyEvalCoverageTests(unittest.TestCase):
    """STORY-016 acceptance criteria: eval cases distinguish migration from
    ordinary feature work, and migration deletion cannot be recommended
    before validation evidence exists."""

    def setUp(self) -> None:
        self.cases = case_dirs(EVALS_DIR / "migration-safety")

    def test_has_a_genuine_migration_case(self) -> None:
        self.assertTrue(
            any("is-migration" in case_tags(c) for c in self.cases),
            "no eval case tagged 'is-migration'",
        )

    def test_has_an_ordinary_feature_work_case(self) -> None:
        self.assertTrue(
            any("not-a-migration" in case_tags(c) for c in self.cases),
            "no eval case tagged 'not-a-migration'",
        )

    def test_migration_case_has_a_delete_gated_on_validation_grader(self) -> None:
        migration_cases = [c for c in self.cases if "is-migration" in case_tags(c)]
        self.assertTrue(migration_cases)
        found = False
        for case_dir in migration_cases:
            for grader_md in (case_dir / "graders").glob("*.md"):
                text = read(grader_md).lower()
                if "valid" in text and ("delet" in text or "drop" in text):
                    found = True
        self.assertTrue(
            found,
            "no grader in the migration case checks that deletion is "
            "gated on validation evidence",
        )

    def test_ordinary_feature_work_case_has_a_no_ceremony_grader(self) -> None:
        ordinary_cases = [
            c for c in self.cases if "not-a-migration" in case_tags(c)
        ]
        self.assertTrue(ordinary_cases)
        found = False
        for case_dir in ordinary_cases:
            for grader_md in (case_dir / "graders").glob("*.md"):
                text = read(grader_md).lower()
                if "phase" in text or "ceremony" in text:
                    found = True
        self.assertTrue(
            found,
            "no grader in the ordinary-feature-work case checks for the "
            "absence of migration phase ceremony",
        )

    def test_ordinary_feature_work_case_is_brownfield_not_greenfield(self) -> None:
        # ADR-0007 and STORY-016 both frame the discriminating case as
        # "ordinary brownfield feature work" -- touching an existing,
        # already-shipped system without replacing anything in it -- which
        # is a harder (and more realistic) discriminator than a purely
        # greenfield/net-new scenario.
        ordinary_cases = [
            c for c in self.cases if "not-a-migration" in case_tags(c)
        ]
        self.assertTrue(ordinary_cases)
        for case_dir in ordinary_cases:
            prompt_text = read(case_dir / "prompt.md").lower()
            self.assertIn(
                "already",
                prompt_text,
                f"{case_dir} does not read as brownfield work on an "
                "already-existing system",
            )


if __name__ == "__main__":
    unittest.main()
