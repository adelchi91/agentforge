# Step 1 — Reference Documents

Display this header exactly:
─────────────────────────────────────────────
STEP 1 / 6 — REFERENCE DOCUMENTS
─────────────────────────────────────────────

Ask:
  "Do you have any reference documents to share?
   (PRD, technical spec, architecture doc, existing roadmap, design notes)

   You can:
   - Paste content directly
   - Provide file paths (one per line)
   - Type NONE to skip this step"

  → WAIT for answer.

## If NONE or empty

Write `.bootstrap/00_docs.md`:
```
# Reference Documents
(none provided)
```
Display: "No documents provided — type OK to continue to Step 2"

## If documents provided

For each **file path** provided:
- Read the file with the Read tool
- If unreadable: notify the user and skip it

For each document (pasted or read from file), extract:
- Goals and purpose
- Constraints and non-negotiables
- Stack or technology mentions
- Proposed phases, milestones, or delivery plan
- Deliverables and success criteria
- Any other signals relevant to planning

Write a structured summary to `.bootstrap/00_docs.md`:

```markdown
# Reference Documents

## Source: [filename or "pasted text"]
### Extracted signals
- **Goals:** ...
- **Constraints:** ...
- **Stack:** ...
- **Proposed phases / milestones:** ...
- **Deliverables:** ...
- **Other:** ...
```

Repeat the block for each document.

After writing, display:
```
✓ [N] document(s) ingested and summarised.

These signals will be used to:
  - Pre-fill answers in Step 2 (skipping questions the docs already answer)
  - Cross-check the roadmap in Step 3

Type OK to continue to Step 2, or BACK to add more documents.
```
