# Step 1 — Project Context

Display this header exactly:
─────────────────────────────────────────────
STEP 1 / 5 — PROJECT CONTEXT
─────────────────────────────────────────────

Ask the following questions one group at a time. Wait for answers before proceeding.

GROUP A — Identity:
  1. What is the name of this project?
  2. Describe it in 2–3 sentences: what does it do, who uses it?
  3. What is the primary programming language / stack?

GROUP B — Codebase:
  4. Does this project have existing code? [Y/N]
     - If Y: I will scan the repo structure automatically.
             Ask: "Are there any folders I should ignore?
                   (default ignores: .venv, node_modules, __pycache__, .git, dist, build)"
     - If N: Ask: "What is the main deliverable at the end of this project?"

GROUP C — Constraints:
  5. Are there any hard constraints I should know about?
     (e.g. "never touch the database schema", "CI must always be green",
            "no breaking changes to the public API")
  6. Is there a golden rule for this project?
     (default suggestion: "The test suite must never break during development")

After collecting answers:
- If existing code: run repo scan (find, ls) and summarise what you found
- Write all answers + scan results to .bootstrap/01_context.md in structured markdown
- Display: "Context saved to .bootstrap/01_context.md — type OK to continue to Step 2"
