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
  │   └── [one folder per domain]/SKILL.md
  ├── hooks/
  │   ├── pre_tool_use.py        ← safety + per-agent scope enforcement
  │   ├── post_tool_use.py       ← auto-lint on Write/Edit
  │   ├── session_start.py       ← inject golden rule + active story
  │   ├── user_prompt_submit.py  ← inject story scope when STORY-XXX mentioned
  │   ├── subagent_stop.py       ← handoff-chain audit log
  │   ├── pre_compact.py         ← preserve story state across compaction
  │   ├── session_end.py         ← session record on SessionEnd
  │   └── scopes.json            ← agent → allowed-folders map (from Repo Ownership)
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
      ├── pre_tool_use.py
      ├── post_tool_use.py
      ├── session_start.py
      ├── user_prompt_submit.py
      ├── subagent_stop.py
      ├── pre_compact.py
      ├── session_end.py
      └── scopes.json

  .agents/
  ├── skills/
  │   └── [one folder per domain]/SKILL.md
  └── stories/
      └── [all STORY-XXX.md files]

  project_context.md    ← human-readable summary of intake
  roadmap.md            ← the phase plan

Then display:
  "Type GO to generate all files, or CANCEL to exit without writing anything."

Wait for a fresh `GO` or `CANCEL` after displaying the Step 6 checkpoint. A `GO`
typed during any earlier step is invalid and must not be reused.

On CANCEL: exit cleanly, display "No files written."

On GO for `CLAUDE` (hooks are copied BEFORE settings.json so no hook registration
ever points at a missing script):
  1. Create all directories
  2. Generate CLAUDE.md from template (templates/claude/CLAUDE_md.md)
  3. Copy shared hook scripts (templates/shared/hooks/*.py) to .claude/hooks/
  4. Generate .claude/hooks/scopes.json from templates/shared/hooks/scopes.json —
     one entry per persona, allow lists from the Repo Ownership scopes
     (read-only agents get an empty allow list)
  5. Generate settings.json from template (templates/claude/settings.json)
  6. Generate one agent file per persona (templates/claude/agent.md);
     add `permissionMode: plan` to final-judge and `memory: project` to architects
  7. Generate skill folders per domain: .claude/skills/<domain>/SKILL.md (templates/claude/skill.md)
  8. Move all stories from .bootstrap/stories/ to .claude/stories/
  9. Write project_context.md and roadmap.md to project root
  10. Add .bootstrap/ and .claude/session-log.txt to .gitignore
  11. Display the Done summary

On GO for `CODEX` (hooks are copied BEFORE hooks.json):
  1. Create all directories
  2. Generate AGENTS.md from template (templates/codex/AGENTS_md.md)
  3. Copy shared hook scripts (templates/shared/hooks/*.py) to .codex/hooks/
  4. Generate .codex/hooks/scopes.json from templates/shared/hooks/scopes.json
  5. Generate .codex/hooks.json from template (templates/codex/hooks.json)
  6. Generate one custom agent file per persona (templates/codex/agent.toml)
  7. Generate skill files per domain: .agents/skills/<domain>/SKILL.md (templates/codex/skill.md)
  8. Move all stories from .bootstrap/stories/ to .agents/stories/
  9. Write project_context.md and roadmap.md to project root
  10. Add .bootstrap/ and .codex/session-log.txt to .gitignore
  11. Display the Done summary, including the Codex hook-trust reminder:
      run `/hooks` in Codex and trust the generated hooks, and mark the project
      trusted so the .codex/ layer loads.
