# Step 2 — Project Context

Display this header exactly:
─────────────────────────────────────────────
STEP 2 / 6 — PROJECT CONTEXT
─────────────────────────────────────────────

Read `.bootstrap/00_docs.md` before asking any questions.

First, extract a draft context from Step 1:
- project name
- 2-3 sentence project description
- primary language and stack
- whether existing code is present
- folders to ignore during scanning, if mentioned
- main deliverable, if greenfield
- hard constraints
- golden rule

Display the fields that are clearly answered by the docs under `From your docs:`.
Treat those fields as answered. Do not ask the user to repeat them.

Only ask about fields that are missing or ambiguous. If the user replies with
`go on`, `continue`, or `use the docs` for a field that has a clear draft value,
use the draft value and move on. If there is no clear draft value, ask a concise
follow-up instead of inventing an answer.

Ask missing or ambiguous questions ONE AT A TIME. Send one question, wait for the
answer, then send the next. Never bundle multiple questions in one message. Never
infer an answer from unrelated context; Step 1 docs count as provided context when
they clearly answer the field.

## Questions (in order)

1. "What is the name of this project?"
   → WAIT for answer.

2. "Describe it in 2–3 sentences: what does it do, who uses it?"
   → WAIT for answer.

3. "What is the primary programming language and stack?"
   → WAIT for answer only if the docs do not clearly answer it. Do NOT infer the
     stack from the project description alone.

4. "Does this project have existing code? [Y/N]"
   → WAIT for answer only if the docs and repository context do not clearly answer it.
   → If Y, or if existing code is clear from docs/repository context: run the
     Explore scan using default ignores unless the user already provided custom
     ignore folders.
   → Ask "Are there any additional folders I should ignore during the scan?
            (default ignores: .venv, node_modules, __pycache__, .git, dist, build)"
            only when the default ignores are likely insufficient or the docs mention
            generated/vendor directories.
   → If N: "What is the main deliverable at the end of this project?"
            WAIT for answer only if the docs do not clearly answer it.

5. "Are there any hard constraints I should know about?
   (e.g. 'never touch the database schema', 'CI must always be green')"
   → WAIT for answer.

6. "Is there a golden rule for this project?
   (suggested default: 'The test suite must never break during development')"
   → WAIT for answer.

## After all 6 questions are answered

- If existing code: summarise the Explore scan results (modules, structure, size)
- Display the proposed context summary and ask:
  "Does this context look correct?
   - Type OK to save and continue
   - Or describe corrections in natural language"
- Accept corrections and re-display the summary until the user types OK.
- Write all answers + scan results to `.bootstrap/02_context.md` in structured markdown
- Display: "Context saved — type OK to continue to Step 3"
- Then stop. Do not propose a roadmap until the user sends `OK` for Step 3.
