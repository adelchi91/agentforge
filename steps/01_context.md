# Step 1 — Project Context

Display this header exactly:
─────────────────────────────────────────────
STEP 1 / 5 — PROJECT CONTEXT
─────────────────────────────────────────────

Ask the questions below in three separate exchanges. Do NOT bundle groups together.
Do NOT ask Group B until you have received answers to Group A.
Do NOT ask Group C until you have received answers to Group B.

---

## GROUP A — Identity

Ask these three questions together, then STOP and wait for the user's response:

  1. What is the name of this project?
  2. Describe it in 2–3 sentences: what does it do, who uses it?
  3. What is the primary programming language / stack?

WAIT. Do not proceed until the user has answered all three.

---

## GROUP B — Codebase

After receiving Group A answers, ask:

  4. Does this project have existing code? [Y/N]

WAIT for the answer.

  - If Y: say "I'll scan the repo structure now." Then ask:
          "Are there any folders I should ignore?
           (default ignores: .venv, node_modules, __pycache__, .git, dist, build)"
          Run the Explore scan after receiving the ignore list.
  - If N: ask: "What is the main deliverable at the end of this project?"

WAIT for the answer before continuing to Group C.

---

## GROUP C — Constraints

After receiving Group B answers, ask both questions together, then STOP and wait:

  5. Are there any hard constraints I should know about?
     (e.g. "never touch the database schema", "CI must always be green",
            "no breaking changes to the public API")
  6. Is there a golden rule for this project?
     (default suggestion: "The test suite must never break during development")

WAIT. Do not proceed until the user has answered.

---

## After all three groups are complete

- If existing code: summarise the Explore scan results (modules, structure, size)
- Write all answers + scan results to .bootstrap/01_context.md in structured markdown
- Display: "Context saved to .bootstrap/01_context.md — type OK to continue to Step 2"
