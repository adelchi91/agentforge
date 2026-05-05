# Step 2 — Roadmap Planning

Display this header exactly:
─────────────────────────────────────────────
STEP 2 / 5 — ROADMAP
─────────────────────────────────────────────

Read .bootstrap/01_context.md fully before proposing anything.

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

After OK:
- Write the finalised roadmap to .bootstrap/02_roadmap.md
- Display: "Roadmap saved — type OK to continue to Step 3"
