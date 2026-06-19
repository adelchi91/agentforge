# Step 6 — Scaffold Generation

Display this header exactly:
─────────────────────────────────────────────
STEP 6 / 6 — SCAFFOLDING
─────────────────────────────────────────────

Read ALL .bootstrap/ files, including `.bootstrap/target_platform.md`, and
`.bootstrap/stories/` before doing anything.

If target platform is `CLAUDE`, display the complete file tree of what will be created:

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

If target platform is `CODEX`, display the complete file tree of what will be created:

  AGENTS.md
  .codex/
  ├── hooks.json
  ├── agents/
  │   └── [one .toml file per persona]
  └── hooks/
      ├── pre_tool_use_policy.py
      ├── post_tool_use_lint.py
      └── stop_session_log.py

  .agents/
  ├── skills/
  │   └── [one folder per domain identified from roadmap]
  └── stories/
      └── [all STORY-XXX.md files]

  project_context.md    ← human-readable summary of intake
  roadmap.md            ← the phase plan

Then display:
  "Type GO to generate all files, or CANCEL to exit without writing anything."

On CANCEL: exit cleanly, display "No files written."

On GO for `CLAUDE`:
  1. Create all directories
  2. Generate CLAUDE.md from template (templates/claude/CLAUDE_md.md)
  3. Generate settings.json from template (templates/claude/settings.json)
  4. Generate one agent file per persona (templates/claude/agent.md)
  5. Generate skill files per domain (templates/claude/skill.md)
  6. Copy hook templates (templates/claude/hooks/) to .claude/hooks/
  7. Move all stories from .bootstrap/stories/ to .claude/stories/
  8. Write project_context.md and roadmap.md to project root
  9. Add .bootstrap/ to .gitignore
  10. Run: chmod +x .claude/hooks/*.sh
  11. Display the Done summary (Section 6.5 of the bootstrap spec)

On GO for `CODEX`:
  1. Create all directories
  2. Generate AGENTS.md from template (templates/codex/AGENTS_md.md)
  3. Generate .codex/hooks.json from template (templates/codex/hooks.json)
  4. Generate one custom agent file per persona (templates/codex/agent.toml)
  5. Generate skill files per domain (templates/codex/skill.md)
  6. Copy hook scripts (templates/codex/hooks/) to .codex/hooks/
  7. Move all stories from .bootstrap/stories/ to .agents/stories/
  8. Write project_context.md and roadmap.md to project root
  9. Add .bootstrap/ to .gitignore
  10. Display the Done summary
