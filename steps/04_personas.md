# Step 4 — Persona Definition

Display this header exactly:
─────────────────────────────────────────────
STEP 4 / 6 — PERSONAS
─────────────────────────────────────────────

Read `.bootstrap/02_context.md` and `.bootstrap/03_roadmap.md` before proposing anything.

Apply these rules when proposing agents:

ALWAYS include:
  - final-judge   → model: Sonnet  | scope: full repo | role: approval authority (that's the user)
  - tester        → model: Haiku   | scope: read + bash only | role: run verification, write reports
                    allowed-tools must include Agent so it can spawn an Explore subagent to locate
                    test files before running them

INCLUDE if roadmap has design phases:
  - architect     → model: Sonnet  | scope: read + write docs only | role: ADRs, stories

INCLUDE if roadmap has implementation phases:
  - dev           → model: Haiku   | scope: restricted to specific folders | role: implementation

ADD specialised agents if:
  - The project has distinct technical domains (e.g. frontend/backend/infra)
  - A phase requires a clearly different skill set from existing agents
  - The user explicitly requests one

For each proposed agent display:
  Name | Model | Scope | Role (one sentence)

Then ask:
  "Do you need any additional specialised agents?
   (e.g. 'a migration agent', 'a separate docs writer')
   Or type OK to continue."

Accept additions and show updated list until OK.

After OK:
- Write finalised personas to .bootstrap/04_personas.md in this exact format:

## Agents

### [name]
- model: [model string]
- color: [color]
- scope: [folders or "full repo"]
- allowed-tools: [comma-separated list]
- description: [one sentence]

- Display: "Personas saved — type OK to continue to Step 5"
