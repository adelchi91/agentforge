---
name: review
description: >
  Review and update the roadmap or agent personas in an existing bootstrapped project.
  Triggers on: "update roadmap", "review personas", "revise agents", "update phases",
  "change my roadmap", "/project-bootstrap:review"
agent: interviewer
---

## Purpose

Review and update `roadmap.md` or agents in `.claude/agents/` without re-running the
full bootstrap. Use this when project scope changes, new phases are added, or agent
assignments need revision.

## Procedure

1. Read `roadmap.md` and all files in `.claude/agents/`
2. Display the current state:
   ```
   Current roadmap: [N] phases
   Current agents: [list of name + model + scope]
   ```
3. Ask: "What would you like to update? [roadmap / personas / both]"

### If roadmap:

4. Display the current `roadmap.md` content in full
5. Accept natural language edits:
   - "Add a Phase 3 for documentation"
   - "Rename Phase 1 to Setup"
   - "Split Phase 2 into two phases"
6. Regenerate the roadmap with edits applied
7. Display the new roadmap and ask:

```
Apply these changes to roadmap.md? [GO / CANCEL]
```

### If personas:

4. Display the current agent list (name, model, scope, description)
5. Ask: "What would you like to change? (add / remove / modify)"
6. Apply model routing rules automatically for any new or changed agent
7. Show the updated agent list and ask:

```
Apply these changes? [GO / CANCEL]
```

### If both:

Handle roadmap first, then personas. Separate GO/CANCEL gate for each.

## On GO

Update the affected files. Display each changed file:
```
✓ roadmap.md updated
✓ .claude/agents/NAME.md updated
```

## On CANCEL

Display: "No changes applied." and exit cleanly.

## Safety Rules

- Never remove a phase that has active or completed stories without a warning:
  ```
  Warning: Phase N has X stories. Removing it will orphan STORY-NNN through STORY-MMM.
  Continue? [Y/N]
  ```
- Model routing rules from `refs/model_routing.md` apply to any agent modifications
- Updated agent files must follow the agent template structure exactly
- No template variable may remain unfilled in any updated file
