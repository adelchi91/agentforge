# Step 2 — Project Context

Display this header exactly:
─────────────────────────────────────────────
STEP 2 / 6 — PROJECT CONTEXT
─────────────────────────────────────────────

Read `.bootstrap/00_docs.md` before asking any questions.
If a question is clearly answered by the docs, skip it and state what you found
(e.g. "From your docs: stack is Python 3.11 + uv — confirmed.").
Only ask about what is missing or ambiguous.

Ask questions ONE AT A TIME. Send one question, wait for the answer, then send the next.
Never bundle multiple questions in one message. Never infer or assume an answer — if the
user did not explicitly provide it, ask for it.

## Questions (in order)

1. "What is the name of this project?"
   → WAIT for answer.

2. "Describe it in 2–3 sentences: what does it do, who uses it?"
   → WAIT for answer.

3. "What is the primary programming language and stack?"
   → WAIT for answer. Do NOT infer the stack from the description.

4. "Does this project have existing code? [Y/N]"
   → WAIT for answer.
   → If Y: "Are there any folders I should ignore during the scan?
            (default ignores: .venv, node_modules, __pycache__, .git, dist, build)"
            WAIT, then run the Explore scan.
   → If N: "What is the main deliverable at the end of this project?"
            WAIT for answer.

5. "Are there any hard constraints I should know about?
   (e.g. 'never touch the database schema', 'CI must always be green')"
   → WAIT for answer.

6. "Is there a golden rule for this project?
   (suggested default: 'The test suite must never break during development')"
   → WAIT for answer.

## After all 6 questions are answered

- If existing code: summarise the Explore scan results (modules, structure, size)
- Write all answers + scan results to .bootstrap/02_context.md in structured markdown
- Display: "Context saved — type OK to continue to Step 3"
