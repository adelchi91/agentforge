# Step 4 — Persona Definition

Display this header exactly:
─────────────────────────────────────────────
STEP 4 / 6 — PERSONAS
─────────────────────────────────────────────

Read `.bootstrap/target_platform.md`, `.bootstrap/02_context.md`, and `.bootstrap/03_roadmap.md`
before proposing anything.

If target platform is `CLAUDE`, use Claude model routing:
- Judgment tasks, architects, story authors, final-judge → `claude-sonnet-4-6`
- Deterministic implementation, tester, migration/copy agents → `claude-haiku-4-5-20251001`

If target platform is `CODEX`, use Codex model routing:
- Judgment tasks, architects, story authors, final-judge → `gpt-5.5`, reasoning: `high`
- Deterministic implementation, tester, migration/copy agents → `gpt-5.4-mini`, reasoning: `low` or `medium`
- Read-only reviewers/testers/final-judge → `sandbox_mode = "read-only"`
- Implementation agents → `sandbox_mode = "workspace-write"`

Apply these rules when proposing agents:

ALWAYS include:
  - final-judge   → judgment model | scope: full repo | role: approval authority (that's the user)
  - tester        → deterministic model | scope: read + bash only | role: run verification, write reports
                    Claude: allowed-tools must include Agent so it can spawn an Explore subagent
                    Codex: developer instructions should be read-heavy and verification-focused

INCLUDE if roadmap has design phases:
  - architect     → judgment model | scope: read + write docs only | role: ADRs, stories

INCLUDE if roadmap has implementation phases:
  - dev           → deterministic model | scope: restricted to specific folders | role: implementation

ADD specialised agents if:
  - The project has distinct technical domains (e.g. frontend/backend/infra)
  - A phase requires a clearly different skill set from existing agents
  - The user explicitly requests one

For each proposed agent display:
  Name | Model | Reasoning | Scope | Role (one sentence)

Then ask:
  "Do you need any additional specialised agents?
   (e.g. 'a migration agent', 'a separate docs writer')
   Or type OK to continue."

Accept additions and show updated list until OK.

After OK:
- Write finalised personas to `.bootstrap/04_personas.md` in this exact format:

```markdown
## Agents

### [name]
- model: [model string]
- reasoning: [Codex high / medium / low, or n/a for Claude]
- color: [Claude color, or n/a for Codex]
- sandbox_mode: [Codex read-only / workspace-write, or n/a for Claude]
- scope: [folders or "full repo"]
- allowed-tools: [Claude allowed tools, or Codex tool policy notes]
- description: [one sentence]
```

- Display: "Personas saved — type OK to continue to Step 5"
- Then stop. Do not generate stories until the user sends `OK` for Step 5.
