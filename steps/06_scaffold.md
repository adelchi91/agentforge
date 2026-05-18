# Step 6 — Scaffold Generation

Display this header exactly:
─────────────────────────────────────────────
STEP 6 / 6 — SCAFFOLDING
─────────────────────────────────────────────

Read ALL .bootstrap/ files and .bootstrap/stories/ before doing anything.

Display the complete file tree of what will be created:

  .claude/
  ├── CLAUDE.md
  ├── settings.json
  ├── agents/
  │   └── [one file per persona]
  ├── skills/
  │   └── [one folder per domain identified from roadmap]
  ├── hooks/
  │   ├── pre-tool-use.sh
  │   ├── post-tool-use.sh
  │   └── stop.sh
  └── stories/
      └── [all STORY-XXX.md files]

  project_context.md    ← human-readable summary of intake
  roadmap.md            ← the phase plan

Then display:
  "Type GO to generate all files, or CANCEL to exit without writing anything."

On CANCEL: exit cleanly, display "No files written."

On GO:
  1. Create all directories
  2. Generate CLAUDE.md from template (templates/CLAUDE_md.md)
  3. Generate settings.json from template (templates/settings.json)
  4. Generate one agent file per persona (templates/agent.md)
  5. Generate skill files per domain (templates/skill.md)
  6. Copy hook templates (templates/hooks/) to .claude/hooks/
  7. Move all stories from .bootstrap/stories/ to .claude/stories/
  8. Write project_context.md and roadmap.md to project root
  9. Add .bootstrap/ to .gitignore
  10. Run: chmod +x .claude/hooks/*.sh
  11. Display the Done summary (Section 6.5 of the bootstrap spec)
