# Step 3 — Roadmap Planning

Display this header exactly:
─────────────────────────────────────────────
STEP 3 / 6 — ROADMAP
─────────────────────────────────────────────

Read `.bootstrap/02_context.md` and `.bootstrap/00_docs.md` fully before proposing anything.

First, ask:
  "Do you already have an idea of how you'd like to structure this project —
   phases, milestones, or a rough plan? Or should I propose one based on what
   you've told me?"
  → WAIT for answer.
  → If the user provides a structure: use it as the starting point and refine it
    into a formal phase breakdown (apply the rules below).
  → If the user says no / defer to you: generate a phase breakdown from context.

Propose a phase breakdown following these rules:
- Minimum 2 phases, maximum 8 phases
- Each phase has: number, name, description (one sentence), estimated story count
- Phases are ordered by dependency (later phases depend on earlier ones)
- If existing code: first phase is always extraction/isolation, last phase handles deletion
- If greenfield: first phase is always foundation/scaffolding

Display the proposed roadmap as a numbered list, then ask:
  "Does this structure make sense?
   - Type OK to continue
   - Or describe changes in natural language"

Accept edits and regenerate until the user types OK.

## Cross-check against reference documents

After the roadmap is accepted, check `.bootstrap/00_docs.md` for any phases, milestones,
or constraints mentioned in the docs that are NOT covered by the roadmap. For each gap:
  - Surface it explicitly: "Your docs mention [X] but the roadmap has no phase for it — intentional?"
  - Wait for the user to confirm or adjust the roadmap before saving.
Skip this check if `.bootstrap/00_docs.md` contains "(none provided)".

After OK (and any cross-check adjustments):
- Write the finalised roadmap to .bootstrap/03_roadmap.md
- Display: "Roadmap saved — type OK to continue to Step 4"
