---
name: project-review
description: >
  Review and update the roadmap or agent personas in an existing bootstrapped project.
  Triggers on: "update roadmap", "review personas", "revise agents", "update phases",
  "change my roadmap", "/project-review"
agent: interviewer
---

## Purpose

Review and update `roadmap.md` or agents without re-running the
full bootstrap. Use this when project scope changes, new phases are added, or agent
assignments need revision.

## Procedure

1. Detect the scaffold target:
   - Claude if `.claude/CLAUDE.md` exists
   - Codex if `AGENTS.md` and `.codex/agents/` exist
2. Read `roadmap.md` and all files in the selected platform's agent directory
3. Display the current state:
   ```
   Current roadmap: [N] phases
   Current agents: [list of name + model + scope]
   ```
4. Ask: "What would you like to update? [roadmap / personas / both]"

### If roadmap:

5. Display the current `roadmap.md` content in full
6. Accept natural language edits:
   - "Add a Phase 3 for documentation"
   - "Rename Phase 1 to Setup"
   - "Split Phase 2 into two phases"
7. Regenerate the roadmap with edits applied
8. Display the new roadmap and ask:

```
Apply these changes to roadmap.md? [GO / CANCEL]
```

### If personas:

5. Display the current agent list (name, model, scope, description)
6. Ask: "What would you like to change? (add / remove / modify)"
7. Apply model routing rules automatically for any new or changed agent
8. Show the updated agent list and ask:

```
Apply these changes? [GO / CANCEL]
```

### If both:

Handle roadmap first, then personas. Separate GO/CANCEL gate for each.

## On GO

Update the affected files. Display each changed file:
```
✓ roadmap.md updated
✓ [agent directory]/NAME updated
```

## On CANCEL

Display: "No changes applied." and exit cleanly.

## Safety Rules

- Never remove a phase that has active or completed stories without a warning:
  ```
  Warning: Phase N has X stories. Removing it will orphan STORY-NNN through STORY-MMM.
  Continue? [Y/N]
  ```
- Model routing rules from the installed refs/model_routing.md apply to any agent modifications
- Updated agent files must follow the selected platform template structure exactly
- No template variable may remain unfilled in any updated file
