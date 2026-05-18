# Step 5 — Story Generation

Display this header exactly:
─────────────────────────────────────────────
STEP 5 / 6 — STORIES
─────────────────────────────────────────────

Read all `.bootstrap/` files (00_docs, 02_context, 03_roadmap, 04_personas) before generating anything.

First ask:
  "Review each story individually as I generate it? [Y/N]
   Y → I'll show each story and wait for your OK before continuing
   N → I'll generate all stories now, you can edit the files afterwards"

For each phase in the roadmap, generate stories following these rules:

STORY RULES:
  1. One story per unit of work. A unit = something one agent can complete in one session.
  2. Stories are numbered sequentially across all phases: STORY-001, STORY-002, ...
  3. The first story of Phase N always depends on the last story of Phase N-1
  4. Verification commands must be real runnable shell commands — never "run the tests"
  5. Each story is assigned to exactly one agent from .bootstrap/04_personas.md
  6. Scope constraint: explicitly state which folders/files the agent may touch
  7. "Out of scope" section is mandatory — state what must NOT be changed

If review mode Y:
  - Show each story formatted as it will appear in the file
  - Wait for OK or edits before writing to .bootstrap/stories/STORY-XXX.md
  - Accept natural language edits ("make the scope narrower", "add a verification for the imports")

If review mode N:
  - Generate all stories
  - Write all to .bootstrap/stories/
  - Show the complete list with one-line summary per story

After all stories written:
  - Display: "X stories generated across Y phases — type OK to continue to Step 6"
